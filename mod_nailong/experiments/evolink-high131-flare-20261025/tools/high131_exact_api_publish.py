import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.common import ROOT, machine_id, read_json, utc_now, write_json

REPOSITORY = "XenoAmess/xenoamess_hoi4_dev"
EXPERIMENT = "mod_nailong/experiments/evolink-high131-flare-20261025"
DELIVERY_PATHS = {
    "docs/handoffs/high131-kimi-2026-10-29.md",
    "tools/isolated_production_sync.py",
    "tools/production_checkpoint_publish.py",
    "mod_nailong/tools/build_release.py",
    "mod_nailong/tools/hd_masking.py",
    "mod_nailong/tools/high131_validation.py",
    "mod_nailong/tools/build_high131_validation.py",
    "mod_nailong/tools/high131_build_with_admission.py",
    "tests/test_atomic_json.py",
    "tests/test_fullsize_game_textures.py",
    "tests/test_hd_masking.py",
    "tests/test_high131_import.py",
    "tests/test_high131_build.py",
    "tests/test_high131_exact_api_publish.py",
    "tests/test_isolated_production_sync.py",
    "tests/test_json_read_sharing.py",
    "tests/test_nonperson_build.py",
    *(f"{EXPERIMENT}/tools/{name}.py" for name in (
        "high131_checkpoint", "high131_import", "high131_recover_parent", "high131_rebase_recovery",
        "high131_complete_pending_import", "high131_verify_final_import", "high131_exact_api_publish",
    )),
}


class ExactPublishError(RuntimeError):
    pass


class ApiError(ExactPublishError):
    def __init__(self, message, transient=False, status=None):
        super().__init__(message)
        self.transient = transient
        self.status = status


def require(condition, message):
    if not condition:
        raise ExactPublishError(message)


def safe_error(value):
    text = str(value)
    text = re.sub(r"(?i)(bearer\s+|token\s+)[^\s]+", r"\1[REDACTED]", text)
    return re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b", "[REDACTED]", text)[:4000]


def git_bytes(*args, input_bytes=None):
    result = subprocess.run(["git", "-c", "core.longpaths=true", "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args], cwd=ROOT, input=input_bytes, capture_output=True)
    if result.returncode:
        raise ExactPublishError(safe_error(result.stderr.decode("utf-8", errors="replace")))
    return result.stdout


def git_text(*args):
    return git_bytes(*args).decode("utf-8").strip()


def identity(line):
    name, rest = line.rsplit(" <", 1)
    email, timestamp, offset = rest.rstrip(">").rsplit(" ", 2)
    require(re.fullmatch(r"[+-]\d{4}", offset) is not None, "Unsupported commit timezone")
    zone = timezone(timedelta(minutes=int(offset[:3]) * 60 + (1 if offset[0] == "+" else -1) * int(offset[3:])))
    return {"name": name, "email": email, "date": datetime.fromtimestamp(int(timestamp), zone).isoformat()}


def commit_details(commit):
    raw = git_bytes("cat-file", "-p", commit).decode("utf-8")
    header, message = raw.split("\n\n", 1)
    lines = header.splitlines()
    require(not any(line.startswith(("gpgsig", "mergetag", "encoding")) for line in lines), "Signed or specially encoded commits require explicit review")
    parents = [line.split()[1] for line in lines if line.startswith("parent ")]
    require(len(parents) == 1, "Only ordinary single-parent commits are allowed")
    parent = parents[0]
    tree = next(line.split()[1] for line in lines if line.startswith("tree "))
    author = next(line[len("author "):] for line in lines if line.startswith("author "))
    committer = next(line[len("committer "):] for line in lines if line.startswith("committer "))
    changes = []
    raw_diff = git_bytes("diff-tree", "--raw", "-z", "--no-commit-id", "-r", parent, commit)
    fields = raw_diff.split(b"\0")
    for index in range(0, len(fields) - 1, 2):
        header_parts = fields[index].decode("ascii").split()
        path = fields[index + 1].decode("utf-8")
        require(len(header_parts) == 5 and header_parts[4] in {"A", "M"}, f"Unreviewed file deletion or rename: {path}")
        require(header_parts[1] in {"100644", "100755", "120000"}, f"Unsupported Git object mode: {path}")
        changes.append({"path": path, "mode": header_parts[1], "type": "blob", "sha": header_parts[3]})
    return {"commit": commit, "parent": parent, "tree": tree, "base_tree": git_text("rev-parse", f"{parent}^{{tree}}"),
            "author": identity(author), "committer": identity(committer), "message": message, "changes": changes}


def import_paths(target):
    body = json.loads(git_text("show", f"{target}:{EXPERIMENT}/approved-masters.json"))
    require(body.get("count") == len(body.get("entries", [])) == 127, "HIGH import must contain 127 approved people")
    keys = {row["source_sha256"] for row in body["entries"]}
    return {"mod_nailong/data/generated.json", "mod_nailong/data/image-retry-queue.json", f"{EXPERIMENT}/progress.json", f"{EXPERIMENT}/approved-masters.json",
            *(f"mod_nailong/assets/portraits/{key}.png" for key in keys),
            *(f"mod_nailong/data/generation-requests/{key}.json" for key in keys)}


def api_endpoint(endpoint):
    if endpoint.startswith("repos/"):
        return endpoint
    if endpoint.startswith(("git/", "compare/")):
        return f"repos/{REPOSITORY}/{endpoint}"
    return endpoint


class Api:
    def __init__(self, runner=None, curl_runner=None, token=None):
        self.runner = runner or self._run_gh
        self.curl_runner = curl_runner or self._run_curl
        self.allow_curl_fallback = runner is None
        self._token = token

    def request(self, endpoint, method, payload, timeout):
        try:
            return self.runner(api_endpoint(endpoint), method, payload, timeout)
        except (ApiError, subprocess.TimeoutExpired) as error:
            if not self.allow_curl_fallback or isinstance(error, ApiError) and not error.transient:
                raise
            self.runner = self.curl_runner
            return self.runner(api_endpoint(endpoint), method, payload, timeout)

    @staticmethod
    def _run_gh(endpoint, method, payload, timeout):
        arguments = ["gh", "api", endpoint, "--method", method]
        input_bytes = None
        if payload is not None:
            arguments.extend(["--input", "-"])
            input_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        result = subprocess.run(arguments, input=input_bytes, capture_output=True, timeout=timeout)
        if result.returncode:
            detail = safe_error(result.stderr.decode("utf-8", errors="replace"))
            status_match = re.search(r"HTTP\s+(\d{3})", detail)
            status = int(status_match.group(1)) if status_match else None
            transient = any(term in detail.lower() for term in ("tls handshake timeout", "unexpected eof", "connection reset", "connection was reset", "recv failure", "forcibly closed", "connection aborted", "broken pipe", "schannel", "connection timed out", "i/o timeout", "http 408", "http 500", "http 502", "http 503", "http 504"))
            raise ApiError(detail, transient=transient, status=status)
        try:
            return json.loads(result.stdout)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ApiError(f"Invalid GitHub API JSON: {error}", transient=False) from error

    def github_token(self):
        if self._token is None:
            try:
                token = subprocess.check_output(["gh", "auth", "token"], text=True, encoding="utf-8", stderr=subprocess.PIPE).strip()
            except subprocess.CalledProcessError as error:
                raise ApiError("GitHub CLI authentication is unavailable", transient=False) from error
            require(re.fullmatch(r"[A-Za-z0-9_]+", token) is not None, "Invalid GitHub token shape")
            self._token = token
        return self._token

    def _run_curl(self, endpoint, method, payload, timeout):
        token = self.github_token()
        config = (f'header = "Authorization: Bearer {token}"\n'
                  'header = "Accept: application/vnd.github+json"\n'
                  'header = "X-GitHub-Api-Version: 2022-11-28"\n'
                  'header = "User-Agent: high131-exact-object-publisher"\n').encode("ascii")
        payload_path = None
        try:
            arguments = ["curl.exe", "--proto", "=https", "--request", method,
                         "--url", f"https://api.github.com/{endpoint}", "--silent", "--show-error", "--fail-with-body",
                         "--http1.1", "--connect-timeout", "20", "--max-time", str(timeout), "--config", "-"]
            if payload is not None:
                descriptor, name = tempfile.mkstemp(dir=ROOT / "runtime", prefix=".high131-api-", suffix=".json")
                payload_path = Path(name)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                    stream.flush()
                    os.fsync(stream.fileno())
                arguments.extend(["--json", "@" + name])
            result = subprocess.run(arguments, input=config, capture_output=True, timeout=timeout,
                                    env={**os.environ, "HTTPS_PROXY": "http://127.0.0.1:10808", "HTTP_PROXY": "http://127.0.0.1:10808"})
        finally:
            if payload_path is not None:
                payload_path.unlink(missing_ok=True)
        if result.returncode:
            detail = safe_error(result.stderr.decode("utf-8", errors="replace") + "\n" + result.stdout[:2000].decode("utf-8", errors="replace"))
            match = re.search(r"\b(401|403|404|408|409|422|429|500|502|503|504)\b", detail)
            status = int(match.group(1)) if match else None
            transient = any(term in detail.lower() for term in ("tls", "timeout", "timed out", "connection reset", "connection was reset", "recv failure", "forcibly closed", "connection aborted", "broken pipe", "schannel", "unexpected eof", "http 408", "http 500", "http 502", "http 503", "http 504"))
            raise ApiError(detail, transient=transient, status=status)
        try:
            return json.loads(result.stdout)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ApiError(f"Invalid GitHub API JSON: {error}", transient=False) from error

    def get_json(self, endpoint, expected_sha=None):
        last_error = None
        for attempt in range(3):
            try:
                body = self.request(endpoint, "GET", None, 120)
                if expected_sha is not None:
                    require(body.get("sha") == expected_sha, f"Remote object SHA mismatch: {endpoint}")
                return body
            except subprocess.TimeoutExpired as error:
                last_error = ApiError(safe_error(error), transient=True)
            except ApiError as error:
                if not error.transient or attempt == 2:
                    raise
                last_error = error
            time.sleep((2, 5)[attempt])
        raise last_error

    def get_optional(self, endpoint, expected_sha=None):
        try:
            return self.get_json(endpoint, expected_sha)
        except ApiError as error:
            if error.status == 404:
                return None
            raise

    def post_json(self, endpoint, payload, expected_sha):
        last_error = None
        for attempt in range(3):
            try:
                body = self.request(endpoint, "POST", payload, 300)
                require(body.get("sha") == expected_sha, f"Created object SHA differs from the local object: {endpoint}")
                return body
            except subprocess.TimeoutExpired as error:
                last_error = ApiError(safe_error(error), transient=True)
            except ApiError as error:
                if not error.transient:
                    raise
                last_error = error
            except ExactPublishError:
                raise
            existing = self.get_optional(f"{endpoint}/{expected_sha}", expected_sha)
            if existing is not None:
                return existing
            if attempt == 2:
                raise last_error
            time.sleep((2, 5)[attempt])
        raise last_error


class PublishLock:
    def __init__(self, batch, target):
        self.path = ROOT / "runtime/production-publish.lock"
        self.token = uuid.uuid4().hex
        self.body = {"machine_id": machine_id(), "process_id": os.getpid(), "batch": batch, "target": target, "token": self.token, "acquired_at_utc": utc_now()}

    def __enter__(self):
        deadline = time.monotonic() + 180
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise ExactPublishError("Publication lock remains occupied; inspect its owner instead of deleting it")
                time.sleep(1)
            else:
                with os.fdopen(fd, "w", encoding="ascii", newline="\n") as stream:
                    json.dump(self.body, stream)
                return self

    def __exit__(self, exc_type, exc_value, traceback):
        if read_json(self.path).get("token") != self.token:
            raise ExactPublishError("Publication lock ownership changed; refusing to remove another owner's lock")
        self.path.unlink()


class ExactApiPublisher:
    def __init__(self, base, target, scope, batch, api=None, receipt_path=None):
        require(re.fullmatch(r"[0-9a-f]{40}", base) and re.fullmatch(r"[0-9a-f]{40}", target), "Expected full base and target commit IDs")
        require(scope in {"import", "delivery"}, "Unsupported publication scope")
        require(re.fullmatch(r"[A-Za-z0-9-]+", batch) is not None, "Invalid publication batch")
        self.base, self.target, self.scope, self.batch = base, target, scope, batch
        self.api = api or Api()
        self.commits = [commit_details(commit) for commit in git_text("rev-list", "--reverse", f"{base}..{target}").splitlines()]
        require(self.commits and self.commits[-1]["commit"] == target and self.commits[0]["parent"] == base, "Target is not a linear descendant of base")
        allowed = import_paths(target) if scope == "import" else DELIVERY_PATHS
        for detail in self.commits:
            for change in detail["changes"]:
                path = PurePosixPath(change["path"])
                require(not path.is_absolute() and ".." not in path.parts and change["path"] in allowed, f"Path is outside the authorized HIGH delivery: {path}")
        self.allowed = allowed
        self.receipt_path = receipt_path or ROOT / f"runtime/high131-exact-api-publish-{batch}.json"
        self.receipt_path.resolve().relative_to((ROOT / "runtime").resolve())
        self.receipt = {"schema": "high131-exact-api-publish-v1", "machine_id": machine_id(), "batch": batch, "scope": scope,
                        "base_commit": base, "target_commit": target, "status": "pending", "force": False,
                        "ref_updated": False, "completed_commits": [], "new_image_generation_calls": 0,
                        "runtime_acceptance_claimed": False}
        self.known_blobs = set()

    def save(self, **updates):
        self.receipt.update(updates, observed_at_utc=utc_now())
        write_json(self.receipt_path, self.receipt)

    def ensure_blob(self, commit, change):
        payload = git_bytes("cat-file", "blob", f"{commit}:{change['path']}")
        digest = hashlib.sha1(b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload).hexdigest()
        require(digest == change["sha"], f"Local blob content changed: {change['path']}")
        if digest in self.known_blobs:
            return
        created = self.api.post_json("git/blobs", {"content": base64.b64encode(payload).decode("ascii"), "encoding": "base64"}, digest)
        require(created["sha"] == digest, f"Remote blob SHA mismatch: {change['path']}")
        self.known_blobs.add(digest)
        self.save(last_blob_sha=digest)

    def ensure_tree(self, detail):
        expected = detail["tree"]
        existing = self.api.get_optional(f"git/trees/{expected}", expected)
        if existing is not None:
            return existing
        for change in detail["changes"]:
            self.ensure_blob(detail["commit"], change)
        tree = self.api.post_json("git/trees", {"base_tree": detail["base_tree"], "tree": detail["changes"]}, expected)
        require(tree["sha"] == expected, "Remote tree SHA mismatch")
        self.save(last_tree_sha=expected)
        return tree

    def ensure_commit(self, detail):
        commit = detail["commit"]
        existing = self.api.get_optional(f"git/commits/{commit}", commit)
        if existing is not None:
            require(existing["tree"]["sha"] == detail["tree"] and [row["sha"] for row in existing["parents"]] == [detail["parent"]], f"Existing remote commit has a different tree or parent: {commit}")
            return existing
        self.ensure_tree(detail)
        body = {"message": detail["message"], "tree": detail["tree"], "parents": [detail["parent"]],
                "author": detail["author"], "committer": detail["committer"]}
        created = self.api.post_json("git/commits", body, commit)
        require(created["sha"] == commit, "Remote commit SHA mismatch")
        self.receipt["completed_commits"].append(commit)
        self.save(last_commit_sha=commit)
        return created

    def remote_master(self):
        return self.api.get_json("git/ref/heads/master")["object"]["sha"]

    def remote_contains(self, remote):
        if remote == self.target:
            return True
        try:
            comparison = self.api.get_json(f"compare/{self.target}...{remote}")
        except ApiError as error:
            if error.status == 404:
                return False
            raise
        return comparison.get("status") in {"ahead", "identical"}

    def require_publication_parent(self, remote):
        if remote == self.base:
            return True
        if self.remote_contains(remote):
            return False
        require(remote == self.base, f"Remote master advanced or diverged; rebase before publication: {remote}")
        return True

    def update_ref(self):
        remote = self.remote_master()
        if not self.require_publication_parent(remote):
            return False
        try:
            result = self.api.request("git/refs/heads/master", "PATCH", {"sha": self.target, "force": False}, 120)
            require(result.get("ref") == "refs/heads/master" and result.get("object", {}).get("sha") == self.target, "GitHub ref update did not confirm the exact target")
        except (ApiError, subprocess.TimeoutExpired) as error:
            observed = self.remote_master()
            if observed != self.target:
                raise ExactPublishError(f"Ref update is unconfirmed; remote master is {observed}: {safe_error(error)}") from error
        require(self.remote_master() == self.target, "Remote master does not equal the validated target")
        return True

    def publish(self):
        with PublishLock(self.batch, self.target):
            try:
                self.save(status="validating_remote_and_rate_limit")
                remote = self.remote_master()
                if not self.require_publication_parent(remote):
                    self.save(status="already_public_pending_original_readback", remote_master_observed=remote)
                    return self.receipt
                estimated = sum(len(detail["changes"]) + 3 for detail in self.commits) + 10
                rate = self.api.get_json("rate_limit")["resources"]["core"]
                require(rate["remaining"] >= estimated, f"Insufficient API allowance for estimated writes and control reads: {estimated}, have {rate['remaining']}")
                self.save(status="creating_exact_objects", estimated_write_calls_upper_bound=estimated,
                          rate_limit_accounting="One create per changed blob/tree/commit plus control reads; retries and existing-object reads are additional")
                for detail in self.commits:
                    self.save(current_commit=detail["commit"])
                    self.ensure_commit(detail)
                updated = self.update_ref()
                self.save(status="published_pending_original_readback", ref_updated=updated, remote_master_observed=self.remote_master())
                return self.receipt
            except BaseException as error:
                try:
                    observed = self.remote_master()
                except BaseException:
                    observed = None
                if observed is not None:
                    self.receipt["remote_master_observed"] = observed
                    self.receipt["ref_updated"] = observed == self.target
                self.receipt["ref_update_unconfirmed"] = observed is None
                self.save(status="published_verification_pending" if self.receipt["ref_updated"] else "failed_original_readback_not_claimed", error=safe_error(error))
                raise


def main():
    parser = argparse.ArgumentParser(description="Publish exact local Git objects through the official GitHub API, with SHA checks and force=false only.")
    parser.add_argument("--base", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--scope", choices=["import", "delivery"], required=True)
    parser.add_argument("--batch", required=True)
    args = parser.parse_args()
    result = ExactApiPublisher(args.base, args.target, args.scope, args.batch).publish()
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
