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


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description="Materialize only local ignored test dependencies in an isolated LOW7 worktree.")
    parser.add_argument("--worktree", type=Path, required=True)
    args = parser.parse_args()
    worktree = args.worktree.resolve()
    worktree.relative_to((ROOT / "runtime").resolve())
    require((worktree / ".git").is_file(), "Expected an isolated worktree")
    runtime = worktree / "runtime"
    runtime.mkdir(exist_ok=True)
    linked = []
    for source in (ROOT / "runtime").glob("*.py"):
        target = runtime / source.name
        if target.exists():
            require(file_sha256(target) == file_sha256(source), f"Test support differs: {target}")
        else:
            os.link(source, target)
        linked.append(target.relative_to(worktree).as_posix())
    references = runtime / "references"
    if not references.exists():
        subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(references), str(ROOT / "runtime/references")], check=True, capture_output=True, text=True)
    require(references.is_dir(), "Source references are unavailable")
    (runtime / "production-sync").mkdir(exist_ok=True)
    shader_source = ROOT / "mod_nailong/assets/runtime/hd_portrait_masking_sampler.shader"
    if shader_source.is_file():
        shader_target = worktree / "mod_nailong/assets/runtime/hd_portrait_masking_sampler.shader"
        shader_target.parent.mkdir(parents=True, exist_ok=True)
        if shader_target.exists():
            require(shader_target.read_bytes() == shader_source.read_bytes(), "Shader support differs")
        else:
            shutil.copyfile(shader_source, shader_target)
    restored = []
    for source in (ROOT / HIGH_EXPERIMENT).rglob("*.json"):
        relative = source.relative_to(ROOT).as_posix()
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
        "source_references": "directory junction to existing local runtime/references; read-only source use",
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
