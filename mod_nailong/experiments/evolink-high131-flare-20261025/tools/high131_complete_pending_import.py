import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime import high131_import as importer
from runtime.high131_io import write_json
from tools.common import ROOT, machine_id, utc_now


def main():
    parser = argparse.ArgumentParser(description="Commit an already completely written HIGH131 import after a remote-parent advance; never generates images.")
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--readback", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]+", args.batch):
        raise importer.ImportGateError("Invalid batch")
    worktree = args.worktree.resolve()
    worktree.relative_to((ROOT / "runtime").resolve())
    import_start_commit, parent = importer.resolve_import_parent(worktree)
    plan = importer.build_plan(worktree, ROOT)
    importer.refresh_normalized_receipts(worktree, plan)
    parent_proof = importer.validate_parent_readback(worktree, parent, plan, args.readback)
    for entry in plan["entries"]:
        key = entry["source_sha256"]
        reference = {"review": entry["review"], "review_sha256": entry["review_sha256"], "attempt": entry["attempt"], "task_id": entry["task_id"]}
        importer.require(importer.production_import_completed(worktree, key, reference), f"Cannot finish a partially written import without rebasing it first: {key}")
    progress = importer.evidence_json(worktree, f"{importer.EXPERIMENT}/progress.json")
    counts = {status: sum(row["status"] == status for row in progress["entries"]) for status in {row["status"] for row in progress["entries"]}}
    importer.require(counts == {"approved_imported": 127, "preserved_original_nonperson_exception": 4}, f"Formal records are not completely written: {counts}")
    restored = importer.restore_missing_tracked_import_files(worktree, plan)
    original = importer.stage_and_commit(worktree, plan)
    commit = importer.rebase_import(worktree, original, plan)
    report = {
        "schema": "high131-production-import-receipt-v1",
        "machine_id": machine_id(),
        "batch": args.batch,
        "import_start_commit": import_start_commit,
        "parent_commit": parent,
        "original_import_commit": original,
        "commit": commit,
        "approved_person_sources": 127,
        "preserved_nonperson_exceptions": 4,
        "newly_imported_sources": [],
        "completion_of_already_written_sources": 127,
        "restored_tracked_files": restored,
        "status": "committed_push_pending",
        "evidence_root": str(worktree),
        "new_image_generation_calls": 0,
        "parent_original_readback": parent_proof,
        "parent_readback_receipt": str(args.readback),
        "recovery_reason": "All 127 formal records were already written and verified before origin advanced; commit their exact scope and use ordinary rebase without losing HIGH or LOW history",
        "formal_game_build_or_runtime_acceptance_claimed": False,
        "observed_at_utc": utc_now(),
    }
    write_json(ROOT / f"runtime/checkpoint-{args.batch}.json", report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
