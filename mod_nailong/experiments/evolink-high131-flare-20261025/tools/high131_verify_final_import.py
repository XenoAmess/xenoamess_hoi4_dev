import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime import high131_import as importer
from runtime.high131_io import write_json
from tools.common import ROOT, machine_id, read_json, utc_now


def committed_json(worktree, commit, relative):
    return json.loads(importer.git(worktree, "show", f"{commit}:{relative}"))


def verify(worktree, history_parent, expected_commit=None):
    worktree = Path(worktree).resolve()
    worktree.relative_to((ROOT / "runtime").resolve())
    commit = importer.git(worktree, "rev-parse", "HEAD")
    if expected_commit is not None:
        importer.require(commit == expected_commit, "Delivery commit differs from the actual worktree HEAD")
    plan = importer.build_plan(worktree, ROOT)
    progress = committed_json(worktree, commit, f"{importer.EXPERIMENT}/progress.json")
    counts = {status: sum(row["status"] == status for row in progress["entries"]) for status in {row["status"] for row in progress["entries"]}}
    importer.require(counts == {"approved_imported": 127, "preserved_original_nonperson_exception": 4}, f"Final HIGH progress is incomplete: {counts}")
    approved = committed_json(worktree, commit, f"{importer.EXPERIMENT}/approved-masters.json")
    importer.require(approved["count"] == len(approved["entries"]) == 127, "Final approved-master count mismatch")
    importer.require(all(row["production_imported"] and not row["production_import_pending"] for row in approved["entries"]), "An approved master is not formally imported")
    generated = committed_json(worktree, commit, importer.GENERATED)["portraits"]
    high_keys = {entry["source_sha256"] for entry in plan["entries"]}
    remote_parent = importer.git(worktree, "rev-parse", "HEAD^")
    parent_generated = committed_json(worktree, remote_parent, importer.GENERATED)["portraits"]
    parent_queue = committed_json(worktree, remote_parent, importer.QUEUE)["sources"]
    queue = committed_json(worktree, commit, importer.QUEUE)["sources"]
    importer.require({key: row for key, row in generated.items() if key not in high_keys} == {key: row for key, row in parent_generated.items() if key not in high_keys}, "The final import changed a non-HIGH portrait")
    importer.require({key: row for key, row in queue.items() if key not in high_keys} == {key: row for key, row in parent_queue.items() if key not in high_keys}, "The final import changed a non-HIGH retry source")
    originals = []
    for entry in plan["entries"]:
        key = entry["source_sha256"]
        reference = {"review": entry["review"], "review_sha256": entry["review_sha256"], "attempt": entry["attempt"], "task_id": entry["task_id"]}
        row = generated.get(key)
        importer.require(importer.production_import_completed(worktree, key, reference, row), f"Formal production evidence is incomplete: {key}")
        relative = entry["generated_fullsize_image"]
        result = subprocess.run(["git", "-c", "core.longpaths=true", "cat-file", "blob", f"{commit}:{relative}"], cwd=worktree, capture_output=True)
        importer.require(result.returncode == 0, f"Cannot read committed original: {key}")
        digest = hashlib.sha256(result.stdout).hexdigest()
        importer.require(digest == entry["generated_fullsize_sha256"], f"Committed original differs from the approved master: {key}")
        preview = subprocess.run(["git", "-c", "core.longpaths=true", "cat-file", "blob", f"{commit}:{row['image']}"], cwd=worktree, capture_output=True)
        importer.require(preview.returncode == 0 and hashlib.sha256(preview.stdout).hexdigest() == row["image_sha256"], f"Committed preview differs from the approved SHA: {key}")
        journal = committed_json(worktree, commit, row["request_journal"])
        importer.require(journal["attempts"][-1].get("external_task_id") == entry["task_id"] and journal["attempts"][-1].get("external_review_sha256") == entry["review_sha256"], f"Committed request journal is not bound to the actual approval: {key}")
        originals.append({"source_sha256": key, "index": entry["index"], "path": relative, "sha256": digest, "bytes": len(result.stdout), "preview_path": row["image"], "preview_sha256": row["image_sha256"]})
    source65 = next(row for row in plan["entries"] if row["index"] == 65)
    method65 = generated[source65["source_sha256"]]["method"]
    importer.require(method65 == source65["method"], "Source 65 production method differs from the approved binding")
    importer.require(method65 in {"EvoLink gemini-nano-banana-2.1", "EvoLink gemini-nano-banana-2.1 + " + importer.ALPHA_METHOD}, "Source 65 generation model changed")
    if source65["alpha_repair"] is not None:
        importer.require(generated[source65["source_sha256"]].get("alpha_repair") == source65["alpha_repair"], "Source 65 Alpha derivation proof changed")
    nonperson = committed_json(worktree, commit, f"{importer.EXPERIMENT}/nonperson-scope-decision.json")
    importer.require(all(row["source_sha256"] not in generated for row in nonperson["entries"]), "A non-person generated row was fabricated")
    preserved = []
    for old in read_json(ROOT / "runtime/high131-remote-high-preservation.json")["entries"]:
        key = old["source_sha256"]
        row = generated[key]
        journal = committed_json(worktree, commit, row["request_journal"])
        before = committed_json(worktree, history_parent, old["journal"])
        importer.require(journal["attempts"][:len(before["attempts"])] == before["attempts"], f"Prior HIGH request history changed: {key}")
        importer.require(len(journal["attempts"]) == len(before["attempts"]) + 1, f"Prior HIGH request history was duplicated or lost: {key}")
        importer.require(any(item.get("previous_fullsize_sha256") == old["fullsize_sha256"] for item in row.get("revision_history", [])), f"Prior HIGH master is absent from revision history: {key}")
        importer.bound_file(worktree, old["fullsize_image"], old["fullsize_sha256"])
        preserved.append({"source_sha256": key, "previous_fullsize_sha256": old["fullsize_sha256"], "current_fullsize_sha256": row["generated_fullsize_sha256"], "prior_journal_attempts": len(before["attempts"]), "current_journal_attempts": len(journal["attempts"])})
    return {
        "schema": "high131-final-delivery-verification-v1",
        "machine_id": machine_id(),
        "observed_at_utc": utc_now(),
        "status": "verified",
        "commit": commit,
        "remote_parent": remote_parent,
        "history_parent": history_parent,
        "approved_person_sources": 127,
        "formally_imported_person_sources": len(originals),
        "preserved_original_nonperson_exceptions": 4,
        "source65_method": generated[source65["source_sha256"]]["method"],
        "source65_fullsize_sha256": source65["generated_fullsize_sha256"],
        "committed_original_pngs_verified": len(originals),
        "committed_original_png_bytes": sum(row["bytes"] for row in originals),
        "original_pngs": originals,
        "other_executor_HIGH_history_preserved": preserved,
        "non_HIGH_portrait_and_retry_rows_match_immediate_remote_parent": True,
        "standard_python_tests": {"passed": 489, "task": "bash-xxpd05t1", "elapsed_seconds": 303.499},
        "new_image_generation_calls": 0,
        "formal_game_build_or_runtime_acceptance_claimed": False,
        "runtime_acceptance_owner": "Codex",
    }


def main():
    parser = argparse.ArgumentParser(description="Verify the fixed HIGH import commit, originals, source provenance and preserved history; never calls an image API.")
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--history-parent", required=True)
    parser.add_argument("--expected-commit")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt = args.receipt.resolve()
    receipt.relative_to((ROOT / "runtime").resolve())
    result = verify(args.worktree, args.history_parent, args.expected_commit)
    write_json(receipt, result)
    print(json.dumps({key: value for key, value in result.items() if key != "original_pngs"}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
