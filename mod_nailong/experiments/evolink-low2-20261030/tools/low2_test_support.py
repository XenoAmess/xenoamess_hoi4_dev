import argparse
import importlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.common import file_sha256, machine_id, read_json, utc_now, write_json

support = importlib.import_module("mod_nailong.experiments.evolink-low7-20261030.tools.low7_test_support")
EXPERIMENT = Path("mod_nailong/experiments/evolink-low2-20261030")
KEYS = ["13714c9266d4867e2c831f01322fe8647b46db795f3c5673aeb93cd2be8d36d7", "9e6fa74c90e6a74a306bf02b7c08780ec9318e67ef685c9d46cc0fecc670e805"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def copy_exact(source, target):
    require(source.is_file(), f"Test support is missing: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        require(target.read_bytes() == source.read_bytes(), f"Test support differs: {target}")
    else:
        shutil.copyfile(source, target)


def main():
    parser = argparse.ArgumentParser(description="Materialize local LOW2 test support without committing dependencies or invoking image generation.")
    parser.add_argument("--worktree", type=Path, required=True)
    args = parser.parse_args()
    worktree = args.worktree.resolve()
    support.main()
    source_root = support.SUPPORT_ROOT
    receipt = source_root / "mod_nailong/data/extra-retry-rounds/20261030-remaining-low-nine-one-immediate-round-completed.json"
    original = read_json(receipt)
    results = [row for key in KEYS for row in original["results"] if row["source_sha256"] == key]
    require(len(results) == 2 and all(row["status"] == "service_refused" and row["output_created"] is False for row in results), "LOW2 original failure evidence differs")
    evidence_relative = EXPERIMENT / "original-failure-evidence.json"
    evidence = {
        "schema": "low2-original-builtin-failure-evidence-v1", "machine_id": machine_id(),
        "source_receipt": receipt.relative_to(source_root).as_posix(), "source_receipt_sha256": file_sha256(receipt),
        "scope_sha256": file_sha256(source_root / EXPERIMENT / "scope.json"),
        "prepared_sha256": file_sha256(source_root / EXPERIMENT / "prepared.json"),
        "source_count": 2, "results": results,
        "scope": "Exact extraction of only the two scoped LOW sources; the complete nine-source historical receipt is not rewritten or claimed as this task's generation",
        "new_generation_calls": 0,
    }
    evidence_path = source_root / evidence_relative
    if evidence_path.exists():
        require(read_json(evidence_path) == evidence, "Existing scoped original-failure evidence differs")
    else:
        write_json(evidence_path, evidence)
    copy_exact(source_root / evidence_relative, worktree / evidence_relative)
    copy_exact(source_root / "runtime/source-index.json", worktree / "runtime/source-index.json")
    skill_relative = Path("skills/evolink-imagegen/scripts/evolink_image.py")
    copy_exact(source_root / skill_relative, worktree / skill_relative)
    prompt_files = []
    for key in KEYS:
        journal = read_json(worktree / f"mod_nailong/data/generation-requests/{key}.json")
        snapshot = journal["attempts"][0]
        prompt = Path(snapshot["prompt_file"])
        copy_exact(source_root / prompt, worktree / prompt)
        require(file_sha256(worktree / prompt) == snapshot["prompt_sha256"], f"Original prompt SHA differs: {key}")
        prompt_files.append(prompt.as_posix())
    output = {
        "schema": "low2-local-test-support-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
        "worktree": str(worktree), "original_failure_evidence": evidence_relative.as_posix(),
        "original_failure_evidence_sha256": file_sha256(worktree / evidence_relative),
        "skill_test_client_copied_without_credentials": skill_relative.as_posix(),
        "source_index_copied_for_local_dds_validation": True,
        "original_prompt_files": prompt_files, "unrelated_low_generation_records_copied": False,
        "new_image_generation_calls": 0, "permission_documents_modified": False,
    }
    write_json(ROOT / "runtime/low2-evolink-20261030/test-support.json", output)
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
