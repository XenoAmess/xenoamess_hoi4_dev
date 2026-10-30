import base64
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from runtime import high131_exact_api_publish as exact
from tools.common import machine_id, read_json, utc_now, write_json

publish_tools = importlib.import_module("mod_nailong.experiments.evolink-low2-20261030.tools.low2_exact_publish")
BASE = publish_tools.BASE
EXPECTED_IMPORT = publish_tools.EXPECTED_IMPORT
EXPECTED_TARGET = publish_tools.EXPECTED_TARGET
MANIFEST = "mod_nailong/data/generated.json"
original_identity = exact.identity


def normalized_identity(line):
    identity = original_identity(line)
    identity["email"] = identity["email"].strip("<>")
    return identity


exact.identity = normalized_identity


def require(condition, message):
    if not condition:
        raise ValueError(message)


def local_commit(worktree, tree, parent, author, committer, message):
    environment = os.environ.copy()
    for role, record in (("AUTHOR", author), ("COMMITTER", committer)):
        require(all(isinstance(record.get(field), str) for field in ("name", "email", "date")), "Commit identity is incomplete")
        environment[f"GIT_{role}_NAME"] = record["name"]
        environment[f"GIT_{role}_EMAIL"] = record["email"]
        environment[f"GIT_{role}_DATE"] = record["date"]
    result = subprocess.run(["git", "-c", "core.longpaths=true", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "commit-tree", tree, "-p", parent], cwd=worktree, input=message.encode("utf-8"), capture_output=True, timeout=60)
    require(result.returncode == 0, result.stderr.decode("utf-8", errors="replace"))
    return result.stdout.decode("ascii").strip()


def upload_large_manifest(api):
    detail = exact.commit_details(EXPECTED_IMPORT)
    change = next(row for row in detail["changes"] if row["path"] == MANIFEST)
    payload = exact.git_bytes("cat-file", "blob", f"{EXPECTED_IMPORT}:{MANIFEST}")
    digest = exact.hashlib.sha1(b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload).hexdigest()
    require(digest == change["sha"], "Large manifest blob identity differs")
    message = "Integrate two reviewed LOW portraits (manifest staging)"
    body = {
        "message": message,
        "content": base64.b64encode(payload).decode("ascii"),
        "sha": exact.git_text("rev-parse", f"{BASE}:{MANIFEST}"),
        "branch": "master",
    }
    try:
        result = api.request(f"repos/XenoAmess/xenoamess_hoi4_dev/contents/{MANIFEST}", "PUT", body, 300)
    except (exact.ApiError, subprocess.TimeoutExpired):
        remote = api.get_json("git/ref/heads/master")["object"]["sha"]
        require(remote != BASE, "Manifest upload failed without a confirmed branch update")
        candidate = api.get_json(f"repos/XenoAmess/xenoamess_hoi4_dev/git/commits/{remote}")
        require(candidate["message"] == message and [row["sha"] for row in candidate["parents"]] == [BASE], "An unrelated remote commit appeared after the uncertain upload")
        content = api.get_json(f"repos/XenoAmess/xenoamess_hoi4_dev/contents/{MANIFEST}?ref={remote}")
        require(content["sha"] == digest, "Remote manifest content differs after uncertain upload")
        result = {"commit": candidate, "content": content}
    require(isinstance(result.get("content"), dict) and result["content"].get("sha") == digest, "Contents API returned a different manifest blob")
    commit = result["commit"]
    require([row["sha"] for row in commit["parents"]] == [BASE], "Manifest staging is not a child of the expected public base")
    require(commit["message"] == message, "Unexpected manifest staging commit message")
    return commit


def build_chain(worktree, manifest_commit):
    parent = local_commit(worktree, manifest_commit["tree"]["sha"], BASE, manifest_commit["author"], manifest_commit["committer"], manifest_commit["message"])
    require(parent == manifest_commit["sha"], "Local manifest staging identity differs from the public commit")
    mapping = {}
    for original in exact.git_text("rev-list", "--reverse", f"{BASE}..{EXPECTED_TARGET}").splitlines():
        detail = exact.commit_details(original)
        parent = local_commit(worktree, detail["tree"], parent, detail["author"], detail["committer"], detail["message"])
        mapping[original] = parent
    final = parent
    expected_tree = exact.git_text("rev-parse", f"{EXPECTED_TARGET}^{{tree}}")
    require(exact.git_text("rev-parse", f"{final}^{{tree}}") == expected_tree, "Final tree differs from the fully validated tree")
    require(final != EXPECTED_TARGET, "Unexpected original/alternate commit identity; document the actual publication chain")
    return final, mapping, expected_tree


def main():
    if len(sys.argv) not in {2, 3}:
        raise SystemExit("usage: low2_contents_publish.py WORKTREE [--check]")
    worktree = Path(sys.argv[1]).resolve()
    require(worktree.parent == (ROOT / "runtime").resolve() and (worktree / ".git").exists(), "Expected an isolated runtime worktree")
    exact.ROOT = worktree
    if "--check" in sys.argv:
        changes = publish_tools.scoped_paths(worktree, BASE, EXPECTED_TARGET)
        commits = exact.git_text("rev-list", "--reverse", f"{BASE}..{EXPECTED_TARGET}").splitlines()
        require(len(commits) == 6, "Expected the six validated LOW2 commits")
        print(json.dumps({"status": "ready_for_contents_staging_and_exact_tree_chain", "changed_files": len(changes), "commits": len(commits), "network_or_ref_changes": 0}))
        return 0
    receipt_path = worktree / "runtime/low2-evolink-20261030/contents-publish.json"
    receipt = read_json(receipt_path) if receipt_path.is_file() else None
    if receipt is not None:
        require(receipt["schema"] == "low2-kimi-contents-publish-v1" and receipt["base_commit"] == BASE and receipt["original_validation_commit"] == EXPECTED_TARGET, "Contents publication checkpoint differs")
        final = receipt["final_commit"]
        manifest_sha = receipt["manifest_staging_commit"]
        require(exact.git_text("cat-file", "-t", final) == "commit" and exact.git_text("rev-parse", f"{final}^{{tree}}") == receipt["final_tree"], "Checkpoint final identity differs")
        require(receipt["final_tree"] == exact.git_text("rev-parse", f"{EXPECTED_TARGET}^{{tree}}"), "Checkpoint no longer matches the validated tree")
    else:
        api = publish_tools.DirectApi()
        require(api.get_json("git/ref/heads/master")["object"]["sha"] == BASE, "Remote master changed before manifest staging")
        manifest_commit = upload_large_manifest(api)
        final, mapping, expected_tree = build_chain(worktree, manifest_commit)
        manifest_sha = manifest_commit["sha"]
        receipt = {
            "schema": "low2-kimi-contents-publish-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
            "status": "staged_pending_remaining_publication", "base_commit": BASE,
            "manifest_staging_commit": manifest_sha, "original_import_commit": EXPECTED_IMPORT,
            "original_validation_commit": EXPECTED_TARGET, "final_commit": final,
            "rebased_commits": mapping, "final_tree": expected_tree,
            "final_tree_matches_validation_commit": True,
            "history_note": "The Contents API creates a normal single-parent manifest staging commit. Remaining original trees and identities are retained on that parent; original local commit IDs are not claimed as the remote chain.",
            "force": False, "merge_commit": False, "public_history_rewrite": False,
            "new_image_generation_calls": 0, "original_png_readback_claimed": False, "runtime_acceptance_claimed": False,
        }
        write_json(receipt_path, receipt)
    if receipt["status"] not in {"published_pending_original_readback", "already_public_pending_original_readback"}:
        exact.DELIVERY_PATHS = publish_tools.scoped_paths(worktree, BASE, EXPECTED_TARGET)
        project_lock = exact.PublishLock
        class SharedProjectPublishLock(project_lock):
            def __init__(self, batch, target):
                super().__init__(batch, target)
                self.path = ROOT / "runtime/production-publish.lock"
        exact.PublishLock = SharedProjectPublishLock
        publisher = exact.ExactApiPublisher(manifest_sha, final, "delivery", "low2-contents-20261030", api=publish_tools.DirectApi(), receipt_path=worktree / "runtime/low2-evolink-20261030/remaining-publish.json")
        require(len(publisher.commits) == 5, "Expected five exact-tree commits after manifest staging")
        result = publisher.publish()
        require(result["remote_master_observed"] == final and result["status"] in {"published_pending_original_readback", "already_public_pending_original_readback"}, "Remaining publication is not confirmed")
        previous = exact.git_text("rev-parse", "HEAD")
        exact.git_text("update-ref", "HEAD", final, previous)
        receipt.update(status=result["status"], ref_updated=result["ref_updated"], remote_master=result["remote_master_observed"], observed_at_utc=utc_now())
        receipt["method"] = "Official Contents API for the original large manifest, followed by exact-tree single-parent Git Data commits; force=false"
        receipt["ordinary_fast_forward"] = True
        write_json(receipt_path, receipt)
    receipt["original_png_readback_claimed"] = False
    write_json(ROOT / "runtime/low2-evolink-20261030/publish-receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
