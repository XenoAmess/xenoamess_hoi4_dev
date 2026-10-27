import atexit
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json
from runtime.high131_transport_split import PublishLock
from mod_nailong.tools.master_archive import recorded_outputs
from mod_nailong.tools.master_files import sync_git

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"
MASTER_DIR = ROOT / "mod_nailong/assets/generated_fullsize"
CHECKPOINT_STAGE_PATHS = (
    "mod_nailong/README.md",
    "mod_nailong/docs/portrait-generation-and-repair-methodology.md",
    "mod_nailong/experiments/evolink-high131-flare-20261025",
    "mod_nailong/data/fullsize-files.json",
    "tests/test_high131_record_review.py",
    "tests/test_high131_run_batch.py",
    "tests/test_high131_prepare_card_repairs.py",
    "tests/test_high131_run_repairs.py",
    "tests/test_scoped_readback_checkpoint.py",
    "tests/test_high131_verify_records.py",
    "tests/test_high131_note_details.py",
    "tests/test_high131_note_masks.py",
    "tests/test_high131_checkpoint.py",
    "tests/test_evolink_skill_client.py",
    "skills/evolink-imagegen/scripts/evolink_image.py",
    "tools/production_checkpoint_publish.py",
)


def git(*args, cwd=ROOT, data=None):
    result = subprocess.run(
        ["git", "-c", "core.longpaths=true", "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args],
        cwd=cwd,
        input=data,
        capture_output=True,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )
    if result.returncode:
        raise RuntimeError(result.stdout.decode("utf-8", "replace") + "\n" + result.stderr.decode("utf-8", "replace"))
    return result.stdout


def stage_checkpoint(worktree, master_paths):
    paths = (*CHECKPOINT_STAGE_PATHS, *master_paths)
    git("add", "--pathspec-from-file=-", "--pathspec-file-nul", cwd=worktree, data=("\0".join(paths) + "\0").encode("utf-8"))


def merge_fullsize_index(ours, theirs, expected_digest, master_dir):
    ours_outputs = ours.get("outputs")
    theirs_outputs = theirs.get("outputs")
    if not isinstance(ours_outputs, dict) or not isinstance(theirs_outputs, dict):
        raise RuntimeError("Fullsize index outputs must be objects")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        raise RuntimeError("Expected a complete original SHA256 for the conflict resolution")
    missing = set(theirs_outputs) - set(ours_outputs)
    if missing != {expected_digest}:
        raise RuntimeError(f"Unexpected index additions; refusing to choose a side: {sorted(missing)[:5]}")
    row = theirs_outputs[expected_digest]
    source = Path(master_dir) / f"{expected_digest}.png"
    if row.get("sha256", expected_digest) != expected_digest or row.get("path") != f"mod_nailong/assets/generated_fullsize/{expected_digest}.png":
        raise RuntimeError("The added original has an invalid path or SHA binding")
    if file_sha256(source) != expected_digest or source.stat().st_size != row.get("bytes"):
        raise RuntimeError("The added raw PNG differs from its archived bytes")
    from PIL import Image
    with Image.open(source) as image:
        if list(image.size) != row.get("size") or image.mode != row.get("mode"):
            raise RuntimeError("The added raw PNG dimensions or mode differ from its index row")
    outputs = {**ours_outputs, expected_digest: row}
    return {**ours, "outputs": outputs, "count": len(outputs), "original_png_bytes": sum(item["bytes"] for item in outputs.values())}


def finish_index_conflict_resolution(worktree, original_commit, expected_digest, merged, resumed):
    relative = "mod_nailong/data/fullsize-files.json"
    final = git("rev-parse", "HEAD", cwd=worktree).decode().strip()
    if git("status", "--porcelain", cwd=worktree).strip():
        raise RuntimeError("Resolved worktree still has uncommitted changes")
    parent = git("rev-parse", "HEAD^", cwd=worktree).decode().strip()
    original_paths = set(git("diff", "--name-only", f"{original_commit}^", original_commit, cwd=worktree).decode().splitlines())
    for path in original_paths - {relative}:
        before = git("rev-parse", f"{original_commit}:{path}", cwd=worktree).decode().strip()
        after = git("rev-parse", f"{final}:{path}", cwd=worktree).decode().strip()
        if before != after:
            raise RuntimeError(f"Resolved commit changed an unrelated HIGH blob: {path}")
    committed = json.loads(git("show", f"{final}:{relative}", cwd=worktree).decode("utf-8"))
    if committed != merged:
        raise RuntimeError("Resolved commit differs from the verified union index")
    blob = git("hash-object", str(worktree / relative), cwd=worktree).decode().strip()
    if git("ls-tree", final, "--", relative, cwd=worktree).decode().strip() != f"100644 blob {blob}\t{relative}":
        raise RuntimeError("Resolved index bytes differ from the committed index")
    receipt = {
        "schema": "high131-index-conflict-resolution-v1",
        "machine_id": machine_id(),
        "completed_at_utc": utc_now(),
        "status": "resolved_ready_for_scoped_publication",
        "original_snapshot_commit": original_commit,
        "resolved_commit": final,
        "parent_commit": parent,
        "worktree": worktree.relative_to(ROOT).as_posix(),
        "merged_index": relative,
        "index_sha256": file_sha256(worktree / relative),
        "added_original_digests": [expected_digest],
        "merged_output_count": merged["count"],
        "merged_original_png_bytes": merged["original_png_bytes"],
        "original_snapshot_blobs_unchanged_except_merged_index": True,
        "main_worktree_and_LOW_generated_manifest_not_modified": True,
        "existing_resolved_commit_revalidated": resumed,
        "new_local_commits_created_by_this_call": 0 if resumed else 1,
        "complete_archive_verified": False,
        "new_image_generation_calls": 0,
        "next_step": "Use ordinary fast-forward publication of resolved_commit with a HIGH-scoped readback pointer; do not force push.",
    }
    receipt_path = ROOT / f"runtime/high131-index-conflict-resolution-{final}.json"
    if receipt_path.exists():
        raise RuntimeError(f"Refusing to overwrite an existing conflict-resolution receipt: {receipt_path}")
    from runtime.high131_io import write_json as write_json_with_retry
    write_json_with_retry(receipt_path, receipt)
    return {"status": receipt["status"], "commit": final, "parent_commit": parent, "receipt": receipt_path.relative_to(ROOT).as_posix()}


def resolve_index_conflict(worktree, original_commit, expected_digest):
    worktree = Path(worktree).resolve()
    sync_root = (ROOT / "runtime/production-sync").resolve()
    worktree.relative_to(sync_root)
    if worktree == sync_root or not worktree.is_dir() or worktree.is_symlink() or worktree.is_junction():
        raise RuntimeError("Expected a real isolated rebase worktree")
    if not re.fullmatch(r"[0-9a-f]{40}", original_commit):
        raise RuntimeError("Expected the full original snapshot commit")
    actual_worktree = Path(git("rev-parse", "--show-toplevel", cwd=worktree).decode().strip()).resolve()
    if actual_worktree != worktree:
        raise RuntimeError("Conflict resolution is limited to the expected worktree")
    git("merge-base", "--is-ancestor", f"{original_commit}^", "HEAD", cwd=worktree)
    relative = "mod_nailong/data/fullsize-files.json"
    rebase_states = []
    for name in ("rebase-merge", "rebase-apply"):
        state = Path(git("rev-parse", "--git-path", name, cwd=worktree).decode().strip())
        rebase_states.append(state if state.is_absolute() else worktree / state)
    resumed = not any(state.exists() for state in rebase_states)
    if resumed:
        if git("rev-parse", "--verify", "ORIG_HEAD", cwd=worktree).decode().strip() != original_commit:
            raise RuntimeError("The completed rebase belongs to another snapshot")
        remote = json.loads(git("show", f"HEAD^:{relative}", cwd=worktree).decode("utf-8"))
        snapshot = json.loads(git("show", f"{original_commit}:{relative}", cwd=worktree).decode("utf-8"))
        base = json.loads(git("show", f"{original_commit}^:{relative}", cwd=worktree).decode("utf-8"))
    else:
        if git("rev-parse", "--verify", "REBASE_HEAD", cwd=worktree).decode().strip() != original_commit:
            raise RuntimeError("The rebase belongs to another snapshot")
        conflicts = set(git("diff", "--name-only", "--diff-filter=U", cwd=worktree).decode().splitlines())
        if conflicts != {relative}:
            raise RuntimeError(f"Refusing to resolve unrelated conflicts: {sorted(conflicts)}")
        remote, snapshot, base = (
            json.loads(git("show", f":{stage}:{relative}", cwd=worktree).decode("utf-8"))
            for stage in (2, 3, 1)
        )
    merged = merge_fullsize_index(remote, snapshot, expected_digest, MASTER_DIR)
    if not set(base.get("outputs", {})) <= set(merged["outputs"]):
        raise RuntimeError("The merged index would drop a base output")
    if not resumed:
        from runtime.high131_io import write_json as write_json_with_retry
        write_json_with_retry(worktree / relative, merged)
        git("add", "--sparse", "--", relative, cwd=worktree)
        git("diff", "--cached", "--check", cwd=worktree)
        if git("diff", "--name-only", "--diff-filter=U", cwd=worktree).strip():
            raise RuntimeError("Index conflict remains unresolved")
        git("-c", "core.editor=true", "rebase", "--continue", cwd=worktree)
    return finish_index_conflict_resolution(worktree, original_commit, expected_digest, merged, resumed)


def windows_io_root(path):
    if os.name != "nt" or str(path).startswith("\\\\?\\"):
        return path
    return Path("\\\\?\\" + str(path))


def windows_io_path(path):
    if os.name != "nt" or len(str(path)) < 240:
        return path
    return windows_io_root(path)


def copy_stable(source, target):
    source_io = windows_io_path(source)
    target_io = windows_io_path(target)
    before = file_sha256(source_io)
    payload = source_io.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == before
    windows_io_path(target.parent).mkdir(parents=True, exist_ok=True)
    if target_io.is_symlink() or target_io.is_junction():
        raise RuntimeError(f"Refusing checkpoint link: {target}")
    if source.suffix.lower() == ".png":
        if not target_io.exists() or (source_io.stat().st_dev, source_io.stat().st_ino) != (target_io.stat().st_dev, target_io.stat().st_ino):
            if target_io.exists():
                target_io.unlink()
            os.link(source_io, target_io)
    else:
        temporary = windows_io_path(target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp"))
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if file_sha256(temporary) != before:
            raise RuntimeError(f"Checkpoint temporary file differs from its source: {temporary}")
        temporary.replace(target_io)
    assert file_sha256(source_io) == before
    assert file_sha256(target_io) == before


def storage_precheck_path(batch):
    return ROOT / f"runtime/{batch}-storage-precheck.json"


def checkpoint_workdir(batch):
    folder = ROOT / "runtime/high131-checkpoints" / batch
    if folder.is_symlink() or folder.exists() and any(folder.iterdir()):
        raise RuntimeError("Refusing to replace a nonempty earlier checkpoint")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def checkpoint_publish_lock(batch):
    return PublishLock(
        {"machine_id": machine_id(), "final_commit": None},
        SimpleNamespace(batch=batch, original_commit=None, final_commit=None),
    )


def validate_remote_recovery(parent, approved, previous_snapshot, published_prefix):
    for commit in (parent, previous_snapshot, published_prefix):
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise RuntimeError("Remote recovery requires full immutable commit IDs")
    git("merge-base", "--is-ancestor", published_prefix, parent)
    experiment = EXPERIMENT.relative_to(ROOT).as_posix()
    for relative in (f"{experiment}/scope.json", f"{experiment}/input-release.json"):
        previous_blob = git("rev-parse", f"{previous_snapshot}:{relative}").decode().strip()
        remote_blob = git("rev-parse", f"{parent}:{relative}").decode().strip()
        local_blob = git("hash-object", str(ROOT / relative)).decode().strip()
        if local_blob != previous_blob or remote_blob != previous_blob:
            raise RuntimeError(f"Frozen HIGH task input changed; reconcile it explicitly: {relative}")
    protected = [
        "mod_nailong/README.md",
        "mod_nailong/docs/portrait-generation-and-repair-methodology.md",
    ]
    try:
        git("diff", "--quiet", previous_snapshot, parent, "--", *protected)
    except RuntimeError as exc:
        raise RuntimeError("Remote protected documentation changed after the last HIGH snapshot; refusing an automatic overwrite") from exc
    remote_paths = set(git("ls-tree", "-r", "--name-only", parent, "--", experiment).decode("utf-8").splitlines())
    local_paths = {source.relative_to(ROOT).as_posix() for source in EXPERIMENT.rglob("*") if source.is_file()}
    unknown_paths = sorted(remote_paths - local_paths)
    if unknown_paths:
        raise RuntimeError(f"Remote HIGH experiment contains files absent locally; reconcile before snapshot: {unknown_paths[:5]}")
    remote = json.loads(git("show", f"{parent}:{experiment}/approved-masters.json"))
    local_approvals = {row["source_sha256"]: row["generated_fullsize_sha256"] for row in approved["entries"]}
    unknown_approvals = sorted(
        (row["source_sha256"], row["generated_fullsize_sha256"])
        for row in remote["entries"]
        if local_approvals.get(row["source_sha256"]) != row["generated_fullsize_sha256"]
    )
    if unknown_approvals:
        raise RuntimeError(f"Remote HIGH approvals are not retained locally; refusing to overwrite them: {unknown_approvals[:3]}")
    if remote["count"] != len(remote["entries"]) or approved["count"] != len(local_approvals):
        raise RuntimeError("Approved-master count or source uniqueness is invalid")
    return {
        "schema": "high131-remote-recovery-validation-v1",
        "machine_id": machine_id(),
        "observed_at_utc": utc_now(),
        "parent_commit": parent,
        "previous_complete_snapshot": previous_snapshot,
        "published_prefix": published_prefix,
        "published_prefix_is_ancestor": True,
        "frozen_scope_and_input_release_match_previous_snapshot": True,
        "protected_documentation_unchanged_since_previous_snapshot": protected,
        "remote_experiment_file_count": len(remote_paths),
        "local_experiment_file_count": len(local_paths),
        "remote_files_absent_locally": unknown_paths,
        "remote_approved_masters": len(remote["entries"]),
        "local_approved_masters": len(local_approvals),
        "every_remote_approval_retained_at_the_same_source_and_sha": True,
        "scope": "Reconcile the newer local HIGH experiment against the current remote without replacing unknown remote HIGH files or approvals, changing frozen task inputs, or staging unrelated LOW work. Restored required request/review records remain distinct from art approval and production import.",
    }


def main():
    if len(sys.argv) == 5 and sys.argv[1] == "resolve-index":
        print(json.dumps(resolve_index_conflict(*sys.argv[2:5]), ensure_ascii=True), flush=True)
        return
    if len(sys.argv) not in (2, 4):
        raise SystemExit("usage: high131_checkpoint.py BATCH [PREVIOUS_SNAPSHOT PUBLISHED_PREFIX] | resolve-index WORKTREE ORIGINAL_COMMIT EXPECTED_DIGEST")
    batch = sys.argv[1]
    assert re.fullmatch(r"[A-Za-z0-9-]+", batch)
    previous_snapshot = sys.argv[2] if len(sys.argv) == 4 else "b4af5f5e03bf5db62564d66685c9b8d208eed6bf"
    published_prefix = sys.argv[3] if len(sys.argv) == 4 else "0881ee0cba93b4479b532946cf43fd1207b5ebf7"
    folder = checkpoint_workdir(batch)
    publish_lock = checkpoint_publish_lock(batch)
    publish_lock.acquire()
    atexit.register(publish_lock.release)
    assert not git("diff", "--cached", "--name-only").strip(), "Another staged task must remain untouched"
    budget_path = storage_precheck_path(batch)
    print(json.dumps({"batch": batch, "storage_precheck": str(budget_path), "exists": budget_path.exists()}, ensure_ascii=True), flush=True)
    budget = read_json(budget_path)
    assert budget["machine_id"] == machine_id() and budget["batch"] == batch
    assert budget["status"] == "precheck_passed"
    disk = shutil.disk_usage(ROOT)
    safety = max(2 * 1024 ** 3, min(20 * 1024 ** 3, int(disk.total * 0.05)))
    quota = min(100 * 1024 ** 3, int(disk.total * 0.10))
    required = budget["this_write_peak_estimate_bytes"] + budget["other_unspent_reservations_bytes"] + budget["system_growth_reserve_bytes"] + safety
    assert disk.free >= required, "Insufficient current free space for the scoped checkpoint"
    assert budget["project_usage_upper_bound_bytes"] + budget["this_write_peak_estimate_bytes"] <= quota
    tools = [
        "high131_prepare_prompts.py",
        "high131_prepare_card_repairs.py",
        "high131_prepare_hd_repairs.py",
        "high131_hd_proof.py",
        "high131_io.py",
        "high131_tree_cache.py",
        "high131_verify_hd_targets.py",
        "high131_verify_note_details.py",
        "high131_verify_note_mask.py",
        "high131_prepare_note_details.py",
        "high131_prepare_note_masks.py",
        "high131_prepare_note_repairs.py",
        "high131_review_sheet.py",
        "high131_run_batch.py",
        "high131_run_repairs.py",
        "high131_status.py",
        "high131_archive_approved.py",
        "high131_archive_outputs.py",
        "high131_verify_records.py",
        "high131_retrieve_existing.py",
        "high131_record_review.py",
        "high131_alpha_recovery.py",
        "high131_source_detail.py",
        "high131_transport_split.py",
        "verify-production-commit.py",
        "high131_checkpoint.py",
    ]
    for name in tools:
        copy_stable(ROOT / "runtime" / name, EXPERIMENT / "tools" / name)
    git("fetch", "origin")
    parent = git("rev-parse", "origin/master").decode().strip()
    base_validation = validate_remote_recovery(
        parent,
        read_json(EXPERIMENT / "approved-masters.json"),
        previous_snapshot,
        published_prefix,
    )
    base_validation_path = ROOT / f"runtime/{batch}-remote-base-validation.json"
    write_json(base_validation_path, base_validation)
    print(json.dumps(base_validation, ensure_ascii=True), flush=True)
    worktree = folder / "worktree"
    git("worktree", "add", "--detach", "--no-checkout", str(worktree), parent)
    sparse = [
        "/AGENTS.md",
        "/README.md",
        "/.gitignore",
        "/mod_nailong/README.md",
        "/mod_nailong/docs/portrait-generation-and-repair-methodology.md",
        "/mod_nailong/experiments/evolink-high131-flare-20261025",
        "/mod_nailong/data/generated.json",
        "/mod_nailong/data/fullsize-files.json",
        "/tests/test_high131_record_review.py",
        "/tests/test_high131_run_batch.py",
        "/tests/test_high131_prepare_card_repairs.py",
        "/tests/test_high131_run_repairs.py",
        "/tests/test_scoped_readback_checkpoint.py",
        "/tests/test_high131_verify_records.py",
        "/tests/test_high131_note_details.py",
        "/tests/test_high131_note_masks.py",
        "/tests/test_high131_checkpoint.py",
        "/tests/test_evolink_skill_client.py",
        "/skills/evolink-imagegen/scripts/evolink_image.py",
        "/tools/production_checkpoint_publish.py",
    ]
    approved = read_json(EXPERIMENT / "approved-masters.json")
    archive_path = EXPERIMENT / "output-masters.json"
    archived = read_json(archive_path) if archive_path.exists() else approved
    archive_digests = {row["generated_fullsize_sha256"] for row in archived["entries"]}
    master_paths = [row["generated_fullsize_image"] for row in archived["entries"]]
    sparse.extend("/" + path for path in master_paths)
    git("sparse-checkout", "set", "--no-cone", "--no-sparse-index", "--stdin", cwd=worktree, data=("\n".join(sparse) + "\n").encode("utf-8"))
    git("read-tree", "-mu", "HEAD", cwd=worktree)
    assert not git("status", "--porcelain", cwd=worktree).strip()
    paths = set()
    for source in EXPERIMENT.rglob("*"):
        if source.is_file():
            relative = source.relative_to(ROOT).as_posix()
            copy_stable(source, worktree / relative)
            paths.add(relative)
    for relative in [
        "mod_nailong/README.md",
        "mod_nailong/docs/portrait-generation-and-repair-methodology.md",
        "tests/test_high131_record_review.py",
        "tests/test_high131_run_batch.py",
        "tests/test_high131_prepare_card_repairs.py",
        "tests/test_high131_run_repairs.py",
        "tests/test_scoped_readback_checkpoint.py",
        "tests/test_high131_verify_records.py",
        "tests/test_high131_note_details.py",
        "tests/test_high131_note_masks.py",
        "tests/test_high131_checkpoint.py",
        "tests/test_evolink_skill_client.py",
        "skills/evolink-imagegen/scripts/evolink_image.py",
        "tools/production_checkpoint_publish.py",
        *master_paths,
    ]:
        copy_stable(ROOT / relative, worktree / relative)
        paths.add(relative)
    index = json.loads(git("show", parent + ":mod_nailong/data/fullsize-files.json"))
    expected, _, provenance = recorded_outputs(windows_io_root(worktree) / "mod_nailong")
    approved_digests = {row["generated_fullsize_sha256"] for row in approved["entries"]}
    assert approved_digests <= archive_digests
    indexed_digests = set(index["outputs"])
    assert archive_digests <= expected
    digests = expected - indexed_digests
    assert digests == archive_digests - indexed_digests
    masters = []
    for digest in sorted(digests):
        source = worktree / f"mod_nailong/assets/generated_fullsize/{digest}.png"
        assert source.is_file()
        assert file_sha256(source) == digest
        from PIL import Image
        with Image.open(source) as image:
            size = list(image.size)
            mode = image.mode
        masters.append({
            "path": str(source),
            "sha256": digest,
            "bytes": source.stat().st_size,
            "size": size,
            "mode": mode,
            "provenance": provenance[digest],
        })
    synced = sync_git({"current_masters_missing": [], "historical_fullsize_sha_missing": [], "masters": masters}, root=worktree)
    assert set(synced["outputs"]) == digests
    for digest in archive_digests:
        assert file_sha256(worktree / f"mod_nailong/assets/generated_fullsize/{digest}.png") == digest
    synced["outputs"] = {**index["outputs"], **synced["outputs"]}
    assert archive_digests <= set(synced["outputs"])
    synced["count"] = len(synced["outputs"])
    synced["original_png_bytes"] = sum(row["bytes"] for row in synced["outputs"].values())
    write_json(worktree / "mod_nailong/data/fullsize-files.json", synced)
    paths.add("mod_nailong/data/fullsize-files.json")
    assert not set(git("diff", "--name-only", cwd=worktree).decode().splitlines()) - paths
    new_original_bytes = sum(synced["outputs"][digest]["bytes"] for digest in digests)
    assert new_original_bytes <= budget["this_write_peak_estimate_bytes"], "Checkpoint exceeds its scoped physical-write estimate"
    ordered = sorted(paths)
    stage_checkpoint(worktree, master_paths)
    git("diff", "--cached", "--check", cwd=worktree)
    staged = set(git("diff", "--cached", "--name-only", cwd=worktree).decode().splitlines())
    assert staged <= paths
    assert not any(path.startswith("mod_nailong/data/") and path != "mod_nailong/data/fullsize-files.json" for path in staged)
    git("commit", "-m", "Preserve HIGH portrait evidence", cwd=worktree)
    commit = git("rev-parse", "HEAD", cwd=worktree).decode().strip()
    receipt = {
        "machine_id": machine_id(),
        "completed_at_utc": utc_now(),
        "batch": batch,
        "parent_commit": parent,
        "remote_base_validation": base_validation_path.relative_to(ROOT).as_posix(),
        "commit": commit,
        "new_original_PNGs": len(digests),
        "new_original_bytes": new_original_bytes,
        "original_index_count": synced["count"],
        "approved_masters_in_this_snapshot": len(approved["entries"]),
        "original_outputs_in_this_snapshot": len(archived["entries"]),
        "original_output_manifest": archive_path.relative_to(ROOT).as_posix(),
        "paths": ordered,
        "snapshot": worktree.relative_to(ROOT).as_posix(),
        "status": "committed_push_pending",
        "local_original_validation": "New HIGH originals fully verified with sync-git; existing index retained from immutable origin/master parent, not claimed freshly read",
        "scope": "Isolated sparse checkpoint of HIGH131 experiment evidence and offline input validation only, including all retained actual output PNGs rather than only approvals. No new image generation or EvoLink invocation is authorized by this snapshot. Primary worktree and all unrelated LOW dirty records remain untouched. No production import, game build or Steam claim.",
    }
    receipt["storage_precheck"] = storage_precheck_path(batch).relative_to(ROOT).as_posix()
    receipt["shared_publication_lock_during_snapshot"] = str(publish_lock.config.batch)
    write_json(ROOT / f"runtime/checkpoint-{batch}.json", receipt)
    write_json(folder / "receipt.json", receipt)
    publish_lock.release()
    atexit.unregister(publish_lock.release)
    print(json.dumps({key: value for key, value in receipt.items() if key != "paths"}, ensure_ascii=True))


if __name__ == "__main__":
    main()
