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
    batch = sys.argv[1]
    assert re.fullmatch(r"[A-Za-z0-9-]+", batch)
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
        "high131_prepare_note_repairs.py",
        "high131_review_sheet.py",
        "high131_run_batch.py",
        "high131_run_repairs.py",
        "high131_status.py",
        "high131_archive_approved.py",
        "high131_archive_outputs.py",
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
        "b4af5f5e03bf5db62564d66685c9b8d208eed6bf",
        "0881ee0cba93b4479b532946cf43fd1207b5ebf7",
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
    git(
        "add",
        "--",
        "mod_nailong/README.md",
        "mod_nailong/docs/portrait-generation-and-repair-methodology.md",
        "mod_nailong/experiments/evolink-high131-flare-20261025",
        "mod_nailong/data/fullsize-files.json",
        "tests/test_high131_record_review.py",
        "tests/test_high131_run_batch.py",
        "tests/test_high131_prepare_card_repairs.py",
        "tests/test_high131_run_repairs.py",
        "tests/test_scoped_readback_checkpoint.py",
        *master_paths,
        cwd=worktree,
    )
    git("diff", "--cached", "--check", cwd=worktree)
    staged = set(git("diff", "--cached", "--name-only", cwd=worktree).decode().splitlines())
    assert staged <= paths
    assert not any(path.startswith("mod_nailong/data/") and path != "mod_nailong/data/fullsize-files.json" for path in staged)
    git("commit", "-m", "Continue authorized HIGH portrait generation", cwd=worktree)
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
        "scope": "Isolated sparse checkpoint of the authorized EvoLink HIGH131 task only, including all retained actual output PNGs rather than only approvals. Primary worktree and all unrelated LOW dirty records remain untouched. No production import, game build or Steam claim.",
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
