import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.common import file_sha256, machine_id, read_json, utc_now, write_json

HIGH_EXPERIMENT = Path("mod_nailong/experiments/evolink-high131-flare-20261025")
SUPPORT_ROOT = ROOT if ROOT.parent.name != "runtime" else ROOT.parent.parent


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description="Materialize only local ignored test dependencies in an isolated LOW7 worktree.")
    parser.add_argument("--worktree", type=Path, required=True)
    args = parser.parse_args()
    worktree = args.worktree.resolve()
    authorized_runtime = ROOT if ROOT.name == "runtime" else ROOT.parent if ROOT.parent.name == "runtime" else ROOT / "runtime"
    require(worktree.parent == authorized_runtime and worktree != authorized_runtime, f"Expected a direct child of the authorized runtime directory: worktree={worktree}, authorized={authorized_runtime}")
    require((worktree / ".git").is_file(), "Expected an isolated worktree")
    runtime = worktree / "runtime"
    runtime.mkdir(exist_ok=True)
    linked = []
    for source in (SUPPORT_ROOT / "runtime").glob("*.py"):
        target = runtime / source.name
        if target.exists():
            require(file_sha256(target) == file_sha256(source), f"Test support differs: {target}")
        else:
            os.link(source, target)
        linked.append(target.relative_to(worktree).as_posix())
    for source in (SUPPORT_ROOT / "runtime").glob("high131-hd-target-readback-*.json"):
        target = runtime / source.name
        if target.exists():
            require(file_sha256(target) == file_sha256(source), f"Remote proof support differs: {target}")
        else:
            os.link(source, target)
    references = runtime / "references"
    if references.is_symlink() or references.is_junction():
        references.unlink()
    if not references.exists():
        shutil.copytree(SUPPORT_ROOT / "runtime/references", references, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    require(references.is_dir(), "Source references are unavailable")
    (runtime / "production-sync").mkdir(exist_ok=True)
    shader_source = SUPPORT_ROOT / "mod_nailong/assets/runtime/hd_portrait_masking_sampler.shader"
    if shader_source.is_file():
        shader_target = worktree / "mod_nailong/assets/runtime/hd_portrait_masking_sampler.shader"
        shader_target.parent.mkdir(parents=True, exist_ok=True)
        if shader_target.exists():
            require(shader_target.read_bytes() == shader_source.read_bytes(), "Shader support differs")
        else:
            shutil.copyfile(shader_source, shader_target)
    descriptor_source = SUPPORT_ROOT / "mod_nailong/mod/descriptor.mod"
    descriptor_text = descriptor_source.read_text(encoding="utf-8")
    require("钢奶龙心" in descriptor_text and "remote_file_id" not in descriptor_text and "replace_path" not in descriptor_text, "Descriptor is not the clean development descriptor")
    descriptor_target = worktree / "mod_nailong/mod/descriptor.mod"
    descriptor_target.parent.mkdir(parents=True, exist_ok=True)
    if descriptor_target.exists():
        require(descriptor_target.read_bytes() == descriptor_source.read_bytes(), "Descriptor target differs")
    else:
        shutil.copyfile(descriptor_source, descriptor_target)
    recovery_source = SUPPORT_ROOT / "runtime/high131-latest-recovery.json"
    if recovery_source.is_file():
        recovery_target = runtime / recovery_source.name
        if recovery_target.exists():
            require(file_sha256(recovery_target) == file_sha256(recovery_source), "Recovery fixture differs")
        else:
            os.link(recovery_source, recovery_target)
    for digest, entry in read_json(worktree / "mod_nailong/data/fullsize-files.json")["outputs"].items():
        source = SUPPORT_ROOT / entry["path"]
        target = worktree / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.samefile(source):
                require(file_sha256(target) == digest, f"Original target differs: {entry['path']}")
        else:
            require(file_sha256(source) == digest, f"Original source differs: {entry['path']}")
            os.link(source, target)
    observations_source = SUPPORT_ROOT / "runtime/evolink-high131-flare-20261025/observations"
    observations_target = runtime / "evolink-high131-flare-20261025/observations"
    shutil.copytree(observations_source, observations_target, dirs_exist_ok=True)
    handoff = read_json(worktree / "docs/handoffs/2026-10-30-low7-exhausted.json")
    for entry in handoff["entries"]:
        relative = entry["latest_attempt_snapshot"]["prompt_file"]
        expected_sha = entry["latest_result"]["prompt_sha256"]
        original = SUPPORT_ROOT / relative
        require(file_sha256(original) == expected_sha, f"Original prompt SHA differs: {relative}")
        target = worktree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            require(file_sha256(target) == expected_sha, f"Prompt target differs: {relative}")
        else:
            shutil.copyfile(original, target)
    restored = []
    for source in (SUPPORT_ROOT / HIGH_EXPERIMENT).rglob("*.json"):
        relative = source.relative_to(SUPPORT_ROOT).as_posix()
        target = worktree / relative
        if not target.is_file() or source.read_bytes() == target.read_bytes():
            continue
        committed = subprocess.check_output(["git", "show", f"HEAD:{relative}"], cwd=worktree)
        if source.read_bytes().replace(bytes([13, 10]), bytes([10])) != committed or json.loads(source.read_bytes()) != json.loads(committed):
            continue
        target.write_bytes(source.read_bytes())
        restored.append(relative)
    receipt = {
        "schema": "low7-local-test-support-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
        "worktree": str(worktree), "linked_runtime_python_tools": linked,
        "source_references": "local copy of existing original PNG references from the primary workspace; no game upload",
        "production_sync": "isolated directory, not a junction",
        "shader_copied_if_present": shader_source.is_file(),
        "original_receipt_bytes_restored": restored,
        "receipt_changes_are_test_support_not_delivery_changes": True,
        "permission_documents_modified": False,
    }
    write_json(ROOT / "runtime/low7-evolink-20261030/test-support.json", receipt)
    print(json.dumps({"linked_runtime_python_tools": len(linked), "receipt_bytes_restored": len(restored), "production_sync_isolated": True}))


if __name__ == "__main__":
    main()
