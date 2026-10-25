import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json
from mod_nailong.tools.master_archive import recorded_outputs
from mod_nailong.tools.master_files import sync_git

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"
MASTER_DIR = ROOT / "mod_nailong/assets/generated_fullsize"


def git(*args, cwd=ROOT, data=None):
    result = subprocess.run(
        ["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args],
        cwd=cwd,
        input=data,
        capture_output=True,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )
    if result.returncode:
        raise RuntimeError(result.stdout.decode("utf-8", "replace") + "\n" + result.stderr.decode("utf-8", "replace"))
    return result.stdout


def copy_stable(source, target):
    before = file_sha256(source)
    payload = source.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == before
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    assert file_sha256(source) == before
    assert file_sha256(target) == before


def main():
    batch = sys.argv[1]
    assert re.fullmatch(r"[A-Za-z0-9-]+", batch)
    folder = ROOT / "runtime/high131-checkpoints" / batch
    assert not folder.exists(), "Refusing to replace an earlier checkpoint"
    folder.mkdir(parents=True)
    assert not git("diff", "--cached", "--name-only").strip(), "Another staged task must remain untouched"
    tools = [
        "high131_prepare_prompts.py",
        "high131_review_sheet.py",
        "high131_run_batch.py",
        "high131_status.py",
        "high131_archive_approved.py",
        "high131_checkpoint.py",
    ]
    for name in tools:
        copy_stable(ROOT / "runtime" / name, EXPERIMENT / "tools" / name)
    git("fetch", "origin")
    parent = git("rev-parse", "origin/master").decode().strip()
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
    ]
    approved = read_json(EXPERIMENT / "approved-masters.json")
    master_paths = [row["generated_fullsize_image"] for row in approved["entries"]]
    sparse.extend("/" + path for path in master_paths)
    git("sparse-checkout", "set", "--no-cone", "--no-sparse-index", *sparse, cwd=worktree)
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
        *master_paths,
    ]:
        copy_stable(ROOT / relative, worktree / relative)
        paths.add(relative)
    index = json.loads(git("show", parent + ":mod_nailong/data/fullsize-files.json"))
    expected, _, provenance = recorded_outputs(worktree / "mod_nailong")
    digests = expected - set(index["outputs"])
    assert digests == {row["generated_fullsize_sha256"] for row in approved["entries"]}
    masters = []
    for digest in sorted(digests):
        source = worktree / f"mod_nailong/assets/generated_fullsize/{digest}.png"
        assert source.is_file()
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
    synced["outputs"] = {**index["outputs"], **synced["outputs"]}
    synced["count"] = len(synced["outputs"])
    synced["original_png_bytes"] = sum(row["bytes"] for row in synced["outputs"].values())
    write_json(worktree / "mod_nailong/data/fullsize-files.json", synced)
    paths.add("mod_nailong/data/fullsize-files.json")
    assert not set(git("diff", "--name-only", cwd=worktree).decode().splitlines()) - paths
    ordered = sorted(paths)
    git(
        "add",
        "--",
        "mod_nailong/README.md",
        "mod_nailong/docs/portrait-generation-and-repair-methodology.md",
        "mod_nailong/experiments/evolink-high131-flare-20261025",
        "mod_nailong/data/fullsize-files.json",
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
        "commit": commit,
        "new_original_PNGs": len(digests),
        "new_original_bytes": sum(synced["outputs"][digest]["bytes"] for digest in digests),
        "original_index_count": synced["count"],
        "approved_masters_in_this_snapshot": len(approved["entries"]),
        "paths": ordered,
        "snapshot": worktree.relative_to(ROOT).as_posix(),
        "status": "committed_push_pending",
        "local_original_validation": "New HIGH originals fully verified with sync-git; existing index retained from immutable origin/master parent, not claimed freshly read",
        "scope": "Isolated sparse checkpoint of the authorized EvoLink HIGH131 task only. Primary worktree and all unrelated LOW dirty records remain untouched. No production import, game build or Steam claim.",
    }
    write_json(ROOT / f"runtime/checkpoint-{batch}.json", receipt)
    write_json(folder / "receipt.json", receipt)
    print(json.dumps({key: value for key, value in receipt.items() if key != "paths"}, ensure_ascii=True))


if __name__ == "__main__":
    main()
