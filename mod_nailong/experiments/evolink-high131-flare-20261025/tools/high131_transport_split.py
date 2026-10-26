import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
PLAN_PATH = RUNTIME / "high131-transport-split-20261025.json"
CHECKPOINT_PATH = RUNTIME / "checkpoint-high131-transport-20261025.json"
READBACK_PATH = RUNTIME / "master-readback-high131-transport-20261025.json"
PUBLISH_LOCK_PATH = RUNTIME / "production-publish.lock"
PUBLISHER_PATH = ROOT / "tools/production_checkpoint_publish.py"
ORIGINAL_COMMIT = "4665a751a7f59522f2c950ad4a842b58c1fff49c"
BASE_COMMIT = "d2bd73ef48ecad7cf491326c6e366aa09c2a89b9"
BATCH = "high131-transport-20261025"
SCHEMA = "naiwa-high131-transport-split-v1"
EXPECTED_PATH_COUNT = 498
GROUP_BYTE_LIMIT = 24 * 1024 ** 2
LAST_PATH = "mod_nailong/data/fullsize-files.json"
ALLOWED_ORIGINS = {
    "https://github.com/xenoamess/xenoamess_hoi4_dev.git",
    "git@github.com:xenoamess/xenoamess_hoi4_dev.git",
}
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
BATCH_PATTERN = re.compile(r"[A-Za-z0-9-]+")


class ToolError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def machine_id():
    explicit = os.environ.get("XAR_CK3_MACHINE_ID")
    if explicit:
        return re.sub(r"[^a-z0-9]+", "-", explicit.lower()).strip("-")[:64]
    if os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            token = "windows-machine-guid:" + winreg.QueryValueEx(key, "MachineGuid")[0]
    else:
        source = next((path for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")) if path.exists()), None)
        token = "machine-id:" + source.read_text().strip() if source else "node:" + platform.node()
    host = re.sub(r"[^a-z0-9]+", "-", platform.node().lower()).strip("-")[:32].rstrip("-")
    return host + "-" + sha256_bytes(token.encode())[:10]


def require_sha(value, label):
    if not isinstance(value, str) or not SHA_PATTERN.fullmatch(value):
        raise ToolError(f"Expected a full lowercase Git SHA for {label}")
    return value


def require_batch(value):
    if not isinstance(value, str) or not BATCH_PATTERN.fullmatch(value):
        raise ToolError("Batch must contain only ASCII letters, digits, and hyphens")
    return value


def require_runtime_path(value, label):
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    if path == RUNTIME or RUNTIME not in path.parents:
        raise ToolError(f"{label} must name a file inside the repository runtime directory")
    return path


def sha_argument(value):
    try:
        return require_sha(value, "argument")
    except ToolError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def batch_argument(value):
    try:
        return require_batch(value)
    except ToolError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def runtime_path_argument(value):
    try:
        return require_runtime_path(value, "Path")
    except ToolError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


@dataclass(frozen=True)
class TransportConfig:
    original_commit: str = ORIGINAL_COMMIT
    base_commit: str = BASE_COMMIT
    batch: str = BATCH
    plan_path: Path = PLAN_PATH
    checkpoint_path: Path = CHECKPOINT_PATH
    readback_path: Path = READBACK_PATH


DEFAULT_CONFIG = TransportConfig()


def sanitize(value):
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
    text = re.sub(r"(https?://)[^\s/@]+@", r"\1<redacted>@", text)
    text = re.sub(r"\b(?:ghp_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+)\b", "<redacted>", text)
    return text


def git_environment(index_path=None, identity=None, network=False):
    environment = os.environ.copy()
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_NAMESPACE"):
        environment.pop(name, None)
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    if network:
        environment["GIT_TERMINAL_PROMPT"] = "0"
    if index_path is not None:
        environment["GIT_INDEX_FILE"] = str(index_path)
    if identity is not None:
        for role in ("author", "committer"):
            item = identity[role]
            prefix = role.upper()
            environment[f"GIT_{prefix}_NAME"] = item["name"]
            environment[f"GIT_{prefix}_EMAIL"] = item["email"]
            environment[f"GIT_{prefix}_DATE"] = f"{item['timestamp']} {item['timezone']}"
    return environment


def command_result(command, timeout, environment=None):
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
        return {
            "exit_code": completed.returncode,
            "timed_out": False,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "exit_code": None,
            "timed_out": True,
            "stdout": exc.stdout or b"",
            "stderr": exc.stderr or b"",
            "error": f"Command exceeded {timeout} seconds",
        }
    except OSError as exc:
        return {
            "exit_code": None,
            "timed_out": False,
            "stdout": b"",
            "stderr": b"",
            "error": str(exc),
        }


def git_result(arguments, timeout=180, environment=None):
    return command_result(
        ["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", *arguments],
        timeout,
        git_environment() if environment is None else environment,
    )


def result_error(result):
    parts = []
    if result.get("error"):
        parts.append(sanitize(result["error"]))
    for name in ("stdout", "stderr"):
        text = sanitize(result.get(name, b"")).strip()
        if text:
            parts.append(text)
    return "\n".join(parts) or "Command failed without output"


def git_ok(arguments, timeout=180, environment=None):
    result = git_result(arguments, timeout, environment)
    if result["exit_code"] != 0:
        raise ToolError(f"git {' '.join(arguments[:2])} failed: {result_error(result)}")
    return result["stdout"]


def git_text(arguments, timeout=180, environment=None):
    return sanitize(git_ok(arguments, timeout, environment)).strip()


def parse_identity(line, label):
    match = re.fullmatch(r"(.*) <([^<>]*)> ([0-9]+) ([+-][0-9]{4})", line)
    if not match:
        raise ToolError(f"Unable to parse {label} identity from the immutable commit")
    return {
        "name": match.group(1),
        "email": match.group(2),
        "timestamp": match.group(3),
        "timezone": match.group(4),
    }


def parse_commit(raw):
    try:
        header, message = raw.split(b"\n\n", 1)
        lines = header.decode("utf-8").splitlines()
    except (ValueError, UnicodeDecodeError) as exc:
        raise ToolError(f"Unable to decode Git commit object: {exc}") from exc
    trees = [line.split(" ", 1)[1] for line in lines if line.startswith("tree ")]
    parents = [line.split(" ", 1)[1] for line in lines if line.startswith("parent ")]
    authors = [line[7:] for line in lines if line.startswith("author ")]
    committers = [line[10:] for line in lines if line.startswith("committer ")]
    if len(trees) != 1 or len(authors) != 1 or len(committers) != 1:
        raise ToolError("Invalid Git commit header")
    return {
        "tree": require_sha(trees[0], "commit tree"),
        "parents": [require_sha(parent, "commit parent") for parent in parents],
        "author": parse_identity(authors[0], "author"),
        "committer": parse_identity(committers[0], "committer"),
        "message": message.decode("utf-8"),
    }


def commit_info(commit):
    require_sha(commit, "commit")
    return parse_commit(git_ok(["cat-file", "commit", commit]))


def final_tree_entries(config=DEFAULT_CONFIG):
    entries = {}
    raw = git_ok(["ls-tree", "-r", "-l", "-z", config.original_commit])
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, sha, size = metadata.split()
            path = raw_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ToolError(f"Unable to parse final tree entry: {exc}") from exc
        entries[path] = {
            "mode": mode.decode("ascii"),
            "type": object_type.decode("ascii"),
            "sha256": sha.decode("ascii"),
            "size": None if size == b"-" else int(size),
        }
    return entries


def changed_paths(tree_entries, config=DEFAULT_CONFIG, expected_path_count=None):
    raw = git_ok([
        "diff", "--no-renames", "--no-ext-diff", "--name-status", "-z",
        config.base_commit, config.original_commit,
    ])
    tokens = raw.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    if len(tokens) % 2:
        raise ToolError("Unexpected Git name-status output")
    changes = []
    for offset in range(0, len(tokens), 2):
        try:
            status = tokens[offset].decode("ascii")
            path = tokens[offset + 1].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ToolError(f"Changed paths must be valid UTF-8: {exc}") from exc
        if status == "D":
            if path in tree_entries:
                raise ToolError(f"Deleted path remains in the final tree: {path}")
            changes.append({
                "path": path,
                "status": status,
                "mode": None,
                "blob_sha256": None,
                "size": None,
                "bytes": 0,
            })
            continue
        if status not in {"A", "M", "T"}:
            raise ToolError(f"Unsupported diff status {status!r} for {path}")
        item = tree_entries.get(path)
        if item is None:
            raise ToolError(f"Changed path is absent from the final tree: {path}")
        if item["type"] != "blob" or item["size"] is None:
            raise ToolError(f"Changed final-tree entry is not a regular blob: {path}")
        require_sha(item["sha256"], f"blob for {path}")
        if item["size"] > GROUP_BYTE_LIMIT:
            raise ToolError(
                f"Single blob exceeds the {GROUP_BYTE_LIMIT}-byte group limit: {path} has {item['size']} bytes"
            )
        changes.append({
            "path": path,
            "status": status,
            "mode": item["mode"],
            "blob_sha256": item["sha256"],
            "size": item["size"],
            "bytes": item["size"],
        })
    if expected_path_count is not None and len(changes) != expected_path_count:
        raise ToolError(f"Expected {expected_path_count} changed paths, found {len(changes)}")
    special = [item for item in changes if item["path"] == LAST_PATH]
    if len(special) != 1:
        raise ToolError(f"Expected exactly one changed {LAST_PATH}")
    changes = [item for item in changes if item["path"] != LAST_PATH] + special
    return changes


def static_layout(config=DEFAULT_CONFIG):
    original = commit_info(config.original_commit)
    if original["parents"] != [config.base_commit]:
        raise ToolError("Original commit parent does not match the required base")
    expected_path_count = None
    if (config.original_commit, config.base_commit) == (ORIGINAL_COMMIT, BASE_COMMIT):
        expected_path_count = EXPECTED_PATH_COUNT
    changes = changed_paths(
        final_tree_entries(config),
        config,
        expected_path_count=expected_path_count,
    )
    groups = []
    current_paths = []
    current_bytes = 0
    for item in changes:
        if current_paths and current_bytes + item["bytes"] > GROUP_BYTE_LIMIT:
            groups.append({
                "number": len(groups) + 1,
                "bytes": current_bytes,
                "paths": current_paths,
            })
            current_paths = []
            current_bytes = 0
        current_paths.append(item["path"])
        current_bytes += item["bytes"]
    if current_paths:
        groups.append({"number": len(groups) + 1, "bytes": current_bytes, "paths": current_paths})
    if not groups or groups[-1]["paths"][-1] != LAST_PATH:
        raise ToolError(f"{LAST_PATH} must be the final path of the final group")
    if any(group["bytes"] > GROUP_BYTE_LIMIT for group in groups):
        raise ToolError("Internal grouping error: group byte limit exceeded")
    flattened = [path for group in groups for path in group["paths"]]
    if flattened != [item["path"] for item in changes]:
        raise ToolError("Internal grouping error: path order or coverage changed")
    return {
        "original_commit": config.original_commit,
        "base": config.base_commit,
        "final_tree": original["tree"],
        "path_count": len(changes),
        "group_byte_limit": GROUP_BYTE_LIMIT,
        "bytes_basis": "sum of changed final blob sizes; deletions contribute zero",
        "path_order": f"Git diff order with {LAST_PATH} moved to the final group",
        "paths": changes,
        "groups": groups,
        "commit_identity": {
            "author": original["author"],
            "committer": original["committer"],
        },
        "commit_message_template": f"HIGH131 transport split {{group}}/{{groups}} for {config.original_commit}",
    }


def layout_fingerprint(plan):
    value = {
        key: plan[key]
        for key in (
            "original_commit", "base", "final_tree", "path_count", "group_byte_limit",
            "bytes_basis", "path_order", "paths", "commit_identity", "commit_message_template",
        )
    }
    value["groups"] = [
        {"number": group["number"], "bytes": group["bytes"], "paths": group["paths"]}
        for group in plan["groups"]
    ]
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(encoded)


def new_plan(config=DEFAULT_CONFIG):
    plan = {
        "schema": SCHEMA,
        "machine_id": machine_id(),
        "created_at_utc": utc_now(),
        **static_layout(config),
        "final_commit": None,
        "final_tree_verification": None,
        "status": "planned",
        "pushed_at_utc": None,
    }
    for group in plan["groups"]:
        group.update({
            "parent": config.base_commit if group["number"] == 1 else None,
            "tree": None,
            "commit": None,
            "push_attempts": [],
            "remote_status": "not_observed",
        })
    plan["layout_sha256"] = layout_fingerprint(plan)
    plan["updated_at_utc"] = plan["created_at_utc"]
    return plan


def read_json(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ToolError(f"Unable to read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ToolError(f"Expected a JSON object: {path}")
    return value


def validate_plan(plan, config=DEFAULT_CONFIG):
    if plan.get("schema") != SCHEMA:
        raise ToolError("Saved plan schema does not match this transport tool")
    expected = static_layout(config)
    for key, value in expected.items():
        if key == "groups":
            actual_groups = [
                {"number": group.get("number"), "bytes": group.get("bytes"), "paths": group.get("paths")}
                for group in plan.get("groups", [])
            ]
            if actual_groups != value:
                raise ToolError("Saved grouping differs from the immutable original commit; refusing to regenerate it")
        elif plan.get(key) != value:
            raise ToolError(f"Saved plan field {key!r} differs from the immutable original commit")
    if plan.get("layout_sha256") != layout_fingerprint(plan):
        raise ToolError("Saved plan layout hash is invalid; refusing to alter or reuse a changed layout")
    if not plan["groups"] or plan["groups"][-1]["paths"][-1] != LAST_PATH:
        raise ToolError(f"Saved plan does not keep {LAST_PATH} in the final group")
    final_commit = plan.get("final_commit")
    if final_commit is not None:
        require_sha(final_commit, "final split commit")
        if plan["groups"][-1].get("commit") not in (None, final_commit):
            raise ToolError("Saved final_commit conflicts with the final group commit")
    for position, group in enumerate(plan["groups"]):
        if group["number"] != position + 1 or not group["paths"]:
            raise ToolError("Saved group numbering or path coverage is invalid")
        if group.get("parent") is not None:
            require_sha(group["parent"], f"group {group['number']} parent")
        if group.get("commit") is not None:
            require_sha(group["commit"], f"group {group['number']} commit")
            require_sha(group.get("tree"), f"group {group['number']} tree")
        if not isinstance(group.get("push_attempts"), list):
            raise ToolError("Saved group push attempt history is invalid")
    return plan


def assert_plan_unchanged(plan):
    if plan.get("layout_sha256") != layout_fingerprint(plan):
        raise ToolError("Plan layout changed during execution; refusing to continue")


def atomic_write_json(path, value):
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except OSError as exc:
        raise ToolError(f"Unable to write JSON {path}: {exc}") from exc


def save_plan(plan, config=DEFAULT_CONFIG):
    assert_plan_unchanged(plan)
    plan["updated_at_utc"] = utc_now()
    atomic_write_json(config.plan_path, plan)


def create_plan_file(plan, config=DEFAULT_CONFIG):
    try:
        with config.plan_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(plan, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise ToolError(f"Unable to create saved plan {config.plan_path}: {exc}") from exc


def plan_summary(plan, existing, config=DEFAULT_CONFIG):
    group_bytes = [group["bytes"] for group in plan["groups"]]
    return {
        "status": plan["status"],
        "plan": str(config.plan_path),
        "existing_plan_validated": existing,
        "machine_id": plan["machine_id"],
        "original_commit": plan["original_commit"],
        "base": plan["base"],
        "final_tree": plan["final_tree"],
        "paths": plan["path_count"],
        "groups": len(group_bytes),
        "group_bytes": group_bytes,
        "max_group_bytes": max(group_bytes),
        "group_byte_limit": GROUP_BYTE_LIMIT,
        "last_path": plan["groups"][-1]["paths"][-1],
        "final_commit": plan.get("final_commit"),
    }


def commit_message(plan, group_number):
    return plan["commit_message_template"].format(group=group_number, groups=len(plan["groups"])) + "\n"


def build_group_commit(plan, group, parent, config=DEFAULT_CONFIG):
    index_path = RUNTIME / f"{config.batch}-{os.getpid()}-group-{group['number']:02}.index"
    if index_path.exists():
        raise ToolError(f"Temporary index already exists; refusing to remove or reuse it: {index_path}")
    environment = git_environment(index_path=index_path)
    path_entries = {item["path"]: item for item in plan["paths"]}
    try:
        git_ok(["read-tree", parent], environment=environment)
        for path in group["paths"]:
            item = path_entries[path]
            if item["status"] == "D":
                git_ok(["update-index", "--force-remove", "--", path], environment=environment)
            else:
                cache_info = f"{item['mode']},{item['blob_sha256']},{path}"
                git_ok(["update-index", "--add", "--cacheinfo", cache_info], environment=environment)
        tree = require_sha(git_text(["write-tree"], environment=environment), "written tree")
        message = commit_message(plan, group["number"])
        commit_environment = git_environment(identity=plan["commit_identity"])
        commit = require_sha(
            git_text(["commit-tree", tree, "-p", parent, "-m", message], environment=commit_environment),
            "new split commit",
        )
    finally:
        if index_path.exists():
            try:
                index_path.unlink()
            except OSError as exc:
                raise ToolError(f"Unable to remove this tool's temporary index {index_path}: {exc}") from exc
    info = commit_info(commit)
    if info["tree"] != tree or info["parents"] != [parent] or info["message"] != message:
        raise ToolError("New split commit does not match its tree, parent, or deterministic message")
    return tree, commit


def ensure_commits(plan, config=DEFAULT_CONFIG):
    plan["status"] = "building_commits"
    save_plan(plan, config)
    previous = plan["base"]
    for group in plan["groups"]:
        number = group["number"]
        if group["parent"] is None:
            group["parent"] = previous
            save_plan(plan, config)
        if group["parent"] != previous:
            raise ToolError(f"Fixed parent mismatch in group {number}; refusing to rebase or regenerate commits")
        message = commit_message(plan, number)
        if group["commit"] is not None:
            info = commit_info(group["commit"])
            if info["parents"] != [previous] or info["tree"] != group["tree"] or info["message"] != message:
                raise ToolError(f"Fixed commit validation failed for group {number}; reuse is mandatory")
        else:
            tree, commit = build_group_commit(plan, group, previous, config)
            group["tree"] = tree
            group["commit"] = commit
            save_plan(plan, config)
        previous = group["commit"]
    if plan["final_commit"] is not None and plan["final_commit"] != previous:
        raise ToolError("Fixed final split commit differs from the saved group chain")
    final_tree = commit_info(previous)["tree"]
    if final_tree != plan["final_tree"]:
        raise ToolError(
            f"Final split tree {final_tree} does not equal original tree {plan['final_tree']}; no push is allowed"
        )
    plan["final_commit"] = previous
    plan["final_tree_verification"] = {
        "expected_original_tree": plan["final_tree"],
        "actual_final_split_tree": final_tree,
        "identical": True,
        "verified_at_utc": utc_now(),
        "method": "git cat-file commit on the final split commit before any push",
    }
    plan["status"] = "commits_ready_final_tree_verified"
    save_plan(plan, config)


class PublishLock:
    def __init__(self, plan, config=DEFAULT_CONFIG):
        self.plan = plan
        self.config = config
        self.fd = None
        self.identity = None
        self.token = uuid.uuid4().hex

    def acquire(self):
        owner = {
            "machine_id": machine_id(),
            "process_id": os.getpid(),
            "acquired_at_utc": utc_now(),
            "token": self.token,
            "batch": self.config.batch,
            "original_commit": self.config.original_commit,
            "final_commit": self.plan["final_commit"],
        }
        try:
            self.fd = os.open(
                PUBLISH_LOCK_PATH,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
                0o600,
            )
        except FileExistsError:
            raise ToolError(f"Publish lock is occupied; refusing to delete another owner's lock: {PUBLISH_LOCK_PATH}") from None
        self.identity = (os.fstat(self.fd).st_dev, os.fstat(self.fd).st_ino)
        payload = json.dumps(owner, ensure_ascii=True).encode("ascii")
        view = memoryview(payload)
        while view:
            written = os.write(self.fd, view)
            view = view[written:]
        os.fsync(self.fd)

    def release(self):
        if self.fd is None:
            return
        os.close(self.fd)
        self.fd = None
        try:
            stat = PUBLISH_LOCK_PATH.stat()
            if (stat.st_dev, stat.st_ino) != self.identity:
                raise ToolError("Publish lock identity changed; leaving the other owner's lock untouched")
            owner = json.loads(PUBLISH_LOCK_PATH.read_text(encoding="utf-8"))
            if owner.get("token") != self.token:
                raise ToolError("Publish lock owner token changed; leaving the other owner's lock untouched")
            PUBLISH_LOCK_PATH.unlink()
        except FileNotFoundError:
            raise ToolError("Owned publish lock disappeared before release; not deleting any replacement") from None
        except (OSError, json.JSONDecodeError) as exc:
            raise ToolError(f"Unable to release owned publish lock safely: {exc}") from exc


def validate_origin():
    origin = git_text(["remote", "get-url", "origin"]).rstrip("/").lower()
    if origin not in ALLOWED_ORIGINS:
        raise ToolError("Origin is not the authorized HOI4 repository; refusing fetch or push")


def fetch_origin(plan, config=DEFAULT_CONFIG):
    started = utc_now()
    result = git_result(["fetch", "origin"], timeout=900, environment=git_environment(network=True))
    if result["exit_code"] != 0:
        raise ToolError(f"git fetch origin failed without retry: {result_error(result)}")
    remote_head = require_sha(git_text(["rev-parse", "--verify", "origin/master^{commit}"]), "origin/master")
    plan["last_fetch"] = {
        "started_at_utc": started,
        "finished_at_utc": utc_now(),
        "origin_master": remote_head,
    }
    save_plan(plan, config)
    return remote_head


def remote_contains(commit, remote_head):
    if commit == remote_head:
        return True
    result = git_result(["merge-base", "--is-ancestor", commit, remote_head], timeout=60)
    if result["exit_code"] == 0:
        return True
    if result["exit_code"] == 1:
        return False
    raise ToolError(f"Unable to evaluate remote ancestry: {result_error(result)}")


def fresh_remote_head():
    result = git_result(
        ["ls-remote", "origin", "refs/heads/master"],
        timeout=120,
        environment=git_environment(network=True),
    )
    if result["exit_code"] != 0:
        raise ToolError(f"Remote master readback failed: {result_error(result)}")
    lines = sanitize(result["stdout"]).splitlines()
    if len(lines) != 1:
        raise ToolError("Remote master readback did not return exactly one ref")
    fields = lines[0].split()
    if len(fields) != 2 or fields[1] != "refs/heads/master":
        raise ToolError("Remote master readback has an invalid shape")
    return require_sha(fields[0], "fresh remote master")


def mark_contained(plan, group, remote_head, config=DEFAULT_CONFIG):
    group["remote_status"] = "contained"
    group["remote_head"] = remote_head
    group["remote_observed_at_utc"] = utc_now()
    save_plan(plan, config)


def push_group(plan, group, config=DEFAULT_CONFIG):
    attempt = {
        "started_at_utc": utc_now(),
        "commit": group["commit"],
        "refspec": f"{group['commit']}:refs/heads/master",
        "status": "started",
    }
    group["push_attempts"].append(attempt)
    group["remote_status"] = "push_started"
    save_plan(plan, config)
    result = git_result(
        ["push", "origin", attempt["refspec"]],
        timeout=900,
        environment=git_environment(network=True),
    )
    attempt["finished_at_utc"] = utc_now()
    attempt["exit_code"] = result["exit_code"]
    attempt["timed_out"] = result["timed_out"]
    attempt["stdout"] = sanitize(result["stdout"])
    attempt["stderr"] = sanitize(result["stderr"])
    if result.get("error"):
        attempt["error"] = sanitize(result["error"])
    if result["exit_code"] != 0:
        attempt["status"] = "failed"
        group["remote_status"] = "push_failed"
        plan["status"] = "push_failed"
        save_plan(plan, config)
        raise ToolError(
            f"Group {group['number']} push failed without retry; later groups stopped: {result_error(result)}"
        )
    attempt["status"] = "command_succeeded_remote_readback_pending"
    save_plan(plan, config)
    try:
        observed = fresh_remote_head()
    except ToolError as exc:
        attempt["status"] = "push_succeeded_remote_readback_failed"
        attempt["remote_readback_error"] = str(exc)
        group["remote_status"] = "remote_readback_failed"
        plan["status"] = "remote_readback_failed"
        save_plan(plan, config)
        raise
    attempt["remote_master_observed"] = observed
    if observed != group["commit"]:
        attempt["status"] = "remote_head_mismatch"
        group["remote_status"] = "remote_head_mismatch"
        plan["status"] = "remote_head_mismatch"
        save_plan(plan, config)
        raise ToolError(
            f"Group {group['number']} push returned success but remote master is {observed}, not {group['commit']}"
        )
    attempt["status"] = "pushed_and_remote_head_verified"
    group["remote_status"] = "pushed_and_remote_head_verified"
    group["remote_head"] = observed
    group["remote_observed_at_utc"] = utc_now()
    save_plan(plan, config)
    return observed


def group_receipt(group):
    return {
        "number": group["number"],
        "bytes": group["bytes"],
        "parent": group["parent"],
        "tree": group["tree"],
        "commit": group["commit"],
        "remote_status": group["remote_status"],
        "remote_head": group.get("remote_head"),
        "remote_observed_at_utc": group.get("remote_observed_at_utc"),
        "push_attempts": group["push_attempts"],
    }


def write_checkpoint(plan, config=DEFAULT_CONFIG):
    if config.checkpoint_path.exists():
        existing = read_json(config.checkpoint_path)
        matching_pending_checkpoint = (
            existing.get("commit") == config.original_commit
            and existing.get("status") == "committed_push_pending"
            and existing.get("parent_commit") == config.base_commit
        )
        if not matching_pending_checkpoint and (
            existing.get("commit") not in (None, plan["final_commit"])
            or existing.get("original_commit") not in (None, config.original_commit)
        ):
            raise ToolError("Existing transport checkpoint belongs to another commit; refusing to overwrite it")
    actual_tree = commit_info(plan["final_commit"])["tree"]
    if actual_tree != plan["final_tree"]:
        raise ToolError("Final tree changed before checkpoint creation; refusing standard publication")
    pushed_at = plan.get("pushed_at_utc") or utc_now()
    plan["pushed_at_utc"] = pushed_at
    receipt = {
        "schema": "naiwa-high131-transport-checkpoint-v1",
        "commit": plan["final_commit"],
        "status": "committed_and_pushed",
        "machine_id": machine_id(),
        "original_commit": config.original_commit,
        "base": config.base_commit,
        "final_tree": plan["final_tree"],
        "groups": [group_receipt(group) for group in plan["groups"]],
        "final_tree_proof": plan["final_tree_verification"],
        "pushed_at_utc": pushed_at,
    }
    atomic_write_json(config.checkpoint_path, receipt)
    plan["status"] = "standard_publish_pending"
    save_plan(plan, config)


def transport(plan, resume, config=DEFAULT_CONFIG):
    validate_origin()
    remote_head = fetch_origin(plan, config)
    final_commit = plan["final_commit"]
    if remote_contains(final_commit, remote_head):
        for group in plan["groups"]:
            mark_contained(plan, group, remote_head, config)
    else:
        if not resume and remote_head != plan["base"]:
            plan["status"] = "remote_base_mismatch"
            save_plan(plan, config)
            raise ToolError(
                f"origin/master is {remote_head}, not required base {plan['base']}; refusing to rebase, force, or push"
            )
        for group in plan["groups"]:
            if remote_contains(group["commit"], remote_head):
                mark_contained(plan, group, remote_head, config)
                continue
            if group["parent"] != remote_head:
                plan["status"] = "remote_parent_mismatch"
                save_plan(plan, config)
                raise ToolError(
                    f"First uncontained group {group['number']} has parent {group['parent']} but remote master is {remote_head}; "
                    "fast-forward continuity is not proven"
                )
            remote_head = push_group(plan, group, config)
    if not remote_contains(final_commit, remote_head):
        raise ToolError("Final split commit is not contained by the observed remote master")
    plan["status"] = "committed_and_pushed"
    save_plan(plan, config)
    write_checkpoint(plan, config)


def standard_publish(plan, config=DEFAULT_CONFIG):
    started = utc_now()
    result = command_result(
        [sys.executable, str(PUBLISHER_PATH), plan["final_commit"], config.batch],
        timeout=7200,
        environment=git_environment(network=True),
    )
    receipt = {
        "started_at_utc": started,
        "finished_at_utc": utc_now(),
        "exit_code": result["exit_code"],
        "timed_out": result["timed_out"],
    }
    plan["standard_publish"] = receipt
    if result["exit_code"] != 0:
        receipt.update(stdout=sanitize(result["stdout"]), stderr=sanitize(result["stderr"]))
        if result.get("error"):
            receipt["error"] = sanitize(result["error"])
        plan["status"] = "standard_publish_failed"
        save_plan(plan, config)
        raise ToolError(f"Standard checkpoint publication failed; its checkpoint status is preserved: {result_error(result)}")
    checkpoint = read_json(config.checkpoint_path)
    proof = read_json(config.readback_path)
    if checkpoint.get("status") != "committed_pushed_and_originals_verified" or checkpoint.get("commit") != plan["final_commit"]:
        plan["status"] = "standard_publish_receipt_mismatch"
        save_plan(plan, config)
        raise ToolError("Standard publisher exited successfully but its checkpoint is not fully originals-verified")
    if proof.get("status") != "verified" or proof.get("commit") != plan["final_commit"]:
        plan["status"] = "remote_original_proof_mismatch"
        save_plan(plan, config)
        raise ToolError("Standard publisher exited successfully but fixed-commit original readback proof is invalid")
    receipt.update(
        checkpoint=str(config.checkpoint_path),
        remote_original_readback=str(config.readback_path),
        status="committed_pushed_and_originals_verified",
    )
    plan["status"] = "committed_pushed_and_originals_verified"
    save_plan(plan, config)
    return {
        "status": plan["status"],
        "commit": plan["final_commit"],
        "original_commit": config.original_commit,
        "final_tree": plan["final_tree"],
        "groups": len(plan["groups"]),
        "max_group_bytes": max(group["bytes"] for group in plan["groups"]),
        "checkpoint": str(config.checkpoint_path),
        "remote_original_readback": str(config.readback_path),
    }


def validate_standard_receipt_paths(config):
    expected_checkpoint = RUNTIME / f"checkpoint-{config.batch}.json"
    expected_readback = RUNTIME / f"master-readback-{config.batch}.json"
    if config.checkpoint_path != expected_checkpoint or config.readback_path != expected_readback:
        raise ToolError(
            "Standard publisher requires checkpoint/readback paths named "
            f"{expected_checkpoint} and {expected_readback} for batch {config.batch}"
        )


def execute(plan, resume, config=DEFAULT_CONFIG):
    validate_standard_receipt_paths(config)
    if plan["machine_id"] != machine_id():
        raise ToolError("Saved plan belongs to another machine; refusing to create a checkpoint with mismatched identity")
    lock = PublishLock(plan, config)
    lock.acquire()
    ready_for_publish = False
    try:
        try:
            ensure_commits(plan, config)
            transport(plan, resume, config)
            ready_for_publish = True
        except BaseException as exc:
            if plan["status"] not in {
                "push_failed", "remote_readback_failed", "remote_head_mismatch",
                "remote_base_mismatch", "remote_parent_mismatch",
            }:
                plan["status"] = "transport_failed"
            plan["last_error"] = {
                "observed_at_utc": utc_now(),
                "type": type(exc).__name__,
                "error": sanitize(exc),
            }
            save_plan(plan, config)
            raise
    finally:
        lock.release()
    if ready_for_publish:
        return standard_publish(plan, config)
    raise ToolError("Transport did not reach standard publication")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Split one immutable tree into deterministic small commits, then use the standard verified publisher.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="Read Git metadata only and create or validate the fixed local plan")
    mode.add_argument("--execute", action="store_true", help="Build the saved plan, require origin/master at base, push once per group, and verify")
    mode.add_argument("--resume", action="store_true", help="Reuse fixed commits and resume remote-fast-forward reconciliation without regenerating a layout")
    parser.add_argument("--original-commit", default=ORIGINAL_COMMIT, type=sha_argument)
    parser.add_argument("--base-commit", default=BASE_COMMIT, type=sha_argument)
    parser.add_argument("--batch", default=BATCH, type=batch_argument)
    parser.add_argument(
        "--plan-path", default=PLAN_PATH, type=runtime_path_argument,
        help="Plan JSON inside runtime; relative paths are resolved from the repository root",
    )
    parser.add_argument(
        "--checkpoint-path", default=CHECKPOINT_PATH, type=runtime_path_argument,
        help="Checkpoint JSON inside runtime; execute/resume require the standard filename for batch",
    )
    parser.add_argument(
        "--readback-path", default=READBACK_PATH, type=runtime_path_argument,
        help="Readback JSON inside runtime; execute/resume require the standard filename for batch",
    )
    return parser.parse_args(argv)


def main():
    args = parse_args()
    config = TransportConfig(
        original_commit=args.original_commit,
        base_commit=args.base_commit,
        batch=args.batch,
        plan_path=args.plan_path,
        checkpoint_path=args.checkpoint_path,
        readback_path=args.readback_path,
    )
    try:
        if args.plan:
            exists = config.plan_path.exists()
            plan = read_json(config.plan_path) if exists else new_plan(config)
            validate_plan(plan, config)
            if not exists:
                create_plan_file(plan, config)
            print(json.dumps(plan_summary(plan, exists, config), ensure_ascii=True))
            return 0
        if not config.plan_path.exists():
            raise ToolError(f"Saved plan is required before execute/resume: {config.plan_path}")
        plan = validate_plan(read_json(config.plan_path), config)
        result = execute(plan, args.resume, config)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except ToolError as exc:
        print(json.dumps({
            "status": "failed",
            "error": sanitize(exc),
            "plan": str(config.plan_path),
        }, ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
