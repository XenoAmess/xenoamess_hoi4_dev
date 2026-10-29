import json
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from mod_nailong.tools.portraits import record_fullsize_origin
from tools.common import file_sha256, machine_id, read_json, utc_now, write_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-low7-20261030"
REVIEW_FILES = [EXPERIMENT / f"review-{number:02}-agent.json" for number in range(1, 6)]
REVIEW_FILES.extend([EXPERIMENT / "review-repair-01-agent.json", EXPERIMENT / "review-repair-02-agent.json"])


def require(condition, message):
    if not condition:
        raise ValueError(message)


def evidence_for(key, approved):
    attempt = approved["attempt"]
    original = read_json(EXPERIMENT / "prepared.json")["entries"]
    repairs = read_json(EXPERIMENT / "repair-prepared.json")["entries"] if (EXPERIMENT / "repair-prepared.json").exists() else []
    entry = next(row for row in [*original, *repairs] if row["source_sha256"] == key and row["attempt"] == attempt)
    output = ROOT / approved["output"]
    require(file_sha256(output) == approved["output_sha256"], f"Approved output bytes changed: {key}")
    stem = output.stem
    paths = {
        "request": output.with_name(f"{stem}.request.json"),
        "task": output.with_name(f"{stem}.task.json"),
        "result": output.with_name(f"{stem}.result.json"),
        "prompt": output.with_name(f"{stem}.prompt.txt"),
    }
    for name, path in paths.items():
        require(path.is_file(), f"Missing actual {name}: {path}")
    request = read_json(paths["request"])
    result = read_json(paths["result"])
    task = read_json(paths["task"])
    require(result["task_id"] == approved["task_id"] == task["task_id"], f"Task identity mismatch: {key}")
    require(result["sha256"] == approved["output_sha256"] and result["bytes"] == output.stat().st_size, f"Result/output mismatch: {key}")
    require(request["prompt"] == paths["prompt"].read_text(encoding="utf-8"), f"Actual prompt differs: {key}")
    require(file_sha256(paths["prompt"]) == approved["prompt_sha256"], f"Approved prompt differs: {key}")
    require(request["image_urls"] == entry["image_urls"], f"Ordered input URLs differ: {key}")
    require(request["model"] == entry["model"] == "gpt-image-2.5-flare", f"Model differs: {key}")
    require(request["background"] == "opaque" and request["n"] == 1 and request["resolution"] == "2K" and request["quality"] == "high", f"Generation parameters differ: {key}")
    require([row["sha256"] for row in entry["inputs"]] == entry["ordered_input_sha256"], f"Ordered input SHA differs: {key}")
    for item in entry["inputs"]:
        require(file_sha256(ROOT / item["path"]) == item["sha256"], f"Local input changed: {item['path']}")
    execution = EXPERIMENT / ("repair-executions" if attempt == "external-02" else "executions") / f"{stem}.json"
    execution_body = read_json(execution)
    for field, expected in (("source_sha256", key), ("attempt", attempt), ("task_id", approved["task_id"]), ("prompt_sha256", approved["prompt_sha256"]), ("ordered_input_sha256", entry["ordered_input_sha256"])):
        require(execution_body[field] == expected, f"Execution binding differs for {key}: {field}")
    require(execution_body["output"] == approved["output"], f"Execution output differs: {key}")
    recovery = None
    if execution_body["status"] == "resume_existing_task_required":
        require(execution_body["result"] is None and execution_body["exit_code"] == 1, f"Unexpected recovery origin: {key}")
        recovery_log = ROOT / "runtime/low7-evolink-20261030/navy2-resume.log"
        require(recovery_log.is_file(), "Missing same-task recovery log")
        recovery = EXPERIMENT / "executions" / f"{stem}-recovery.json"
        write_json(recovery, {
            "schema": "low7-existing-task-recovery-v1", "machine_id": machine_id(),
            "source_sha256": key, "attempt": attempt, "task_id": approved["task_id"],
            "initial_execution": execution.relative_to(ROOT).as_posix(), "initial_execution_sha256": file_sha256(execution),
            "initial_error": execution_body["error"],
            "command": ["python", "skills/evolink-imagegen/scripts/evolink_image.py", "--task-id", approved["task_id"], "--output", approved["output"]],
            "log": recovery_log.relative_to(ROOT).as_posix(), "log_sha256": file_sha256(recovery_log),
            "new_generation_post_created": False, "same_task_id_verified": True,
            "result": paths["result"].relative_to(ROOT).as_posix(), "result_sha256": file_sha256(paths["result"]),
            "output": approved["output"], "output_sha256": approved["output_sha256"],
            "status": "completed", "completed_at_utc": result["downloaded_at_utc"],
        })
    else:
        require(execution_body["status"] == "completed" and execution_body["output_sha256"] == approved["output_sha256"], f"Execution is incomplete: {key}")
    return entry, paths, result, request, execution, recovery


def main():
    approved = []
    indexed = []
    seen = set()
    for review_path in REVIEW_FILES:
        if not review_path.exists():
            continue
        review = read_json(review_path)
        require(review["machine_id"] == machine_id() and review["model"] == "gpt-image-2.5-flare", f"Review identity differs: {review_path}")
        require(file_sha256(ROOT / review["review_evidence"]) == review["review_evidence_sha256"], f"Review evidence SHA differs: {review_path}")
        for decision in review["entries"]:
            key = decision["source_sha256"]
            output = ROOT / decision["output"]
            require(file_sha256(output) == decision["output_sha256"], f"Review output bytes changed: {key}")
            record_fullsize_origin(key, output)
            indexed.append({"source_sha256": key, "attempt": decision["attempt"], "output": decision["output"], "output_sha256": decision["output_sha256"], "decision": decision["decision"], "review": review_path.relative_to(ROOT).as_posix(), "review_sha256": file_sha256(review_path)})
            if decision["decision"] != "approved_for_production":
                continue
            require(key not in seen, f"Duplicate current approval: {key}")
            seen.add(key)
            require(decision["remaining_reasons"] == [] and decision["production_import_pending"] is True, f"Unresolved approval: {key}")
            require(decision["hair_features"] == {"policy": "hair-features-v1", "status": "approved"}, f"Hair approval missing: {key}")
            require(decision["collar_fit"] == {"policy": "collar-fit-v1", "status": "approved"}, f"Collar approval missing: {key}")
            with Image.open(output) as image:
                size, mode = list(image.size), image.mode
                alpha = list(image.convert("RGBA").getchannel("A").getextrema())
            require(size == decision["size"] and mode == decision["mode"], f"Review image metadata differs: {key}")
            require(mode == "RGB" and decision["source_alpha_extrema"] == [255, 255] and alpha == [255, 255], f"Opaque canvas proof changed: {key}")
            entry, paths, result, request, execution, recovery = evidence_for(key, decision)
            master_relative = record_fullsize_origin(key, output)
            master = ROOT / master_relative
            require(master.read_bytes() == output.read_bytes(), f"Master differs from raw output: {key}")
            scope = read_json(EXPERIMENT / "scope.json")
            source = next(row for row in scope["entries"] if row["source_sha256"] == key)
            approved.append({
                "index": source["index"], "source_sha256": key, "source_assets": source["source_assets"], "source_packages": source["source_packages"],
                "attempt": decision["attempt"], "task_id": decision["task_id"], "method": "EvoLink gpt-image-2.5-flare",
                "generated_fullsize_image": master_relative, "generated_fullsize_sha256": decision["output_sha256"],
                "bytes": master.stat().st_size, "size": size, "mode": mode, "alpha_extrema": alpha,
                "prompt_file": entry["prompt_file"], "prompt_sha256": decision["prompt_sha256"], "prompt": request["prompt"],
                "inputs": entry["inputs"], "request": paths["request"].relative_to(ROOT).as_posix(), "request_sha256": file_sha256(paths["request"]),
                "result": paths["result"].relative_to(ROOT).as_posix(), "result_sha256": file_sha256(paths["result"]),
                "execution": execution.relative_to(ROOT).as_posix(), "execution_sha256": file_sha256(execution),
                "recovery": recovery.relative_to(ROOT).as_posix() if recovery else None,
                "recovery_sha256": file_sha256(recovery) if recovery else None,
                "generated_at_utc": result["downloaded_at_utc"],
                "review": review_path.relative_to(ROOT).as_posix(), "review_sha256": file_sha256(review_path),
                "reviewed_at_utc": review["reviewed_at_utc"], "reviewer": review["reviewer"],
                "evidence": review["review_evidence"], "evidence_sha256": review["review_evidence_sha256"],
                "edit_existing": decision["attempt"] == "external-02" or key == "1f66d040d3ea98c01ad0d0c91bc6a150d379c89d2a4840f604bad60984cab616",
                "production_import": "pending_canonical_manifest",
            })
    approved.sort(key=lambda row: row["index"])
    from mod_nailong.tools.art_contract import portrait_ready
    canonical = read_json(ROOT / "mod_nailong/data/generated.json")["portraits"]
    for entry in approved:
        current = canonical.get(entry["source_sha256"], {})
        marker = current.get("production_import", {})
        imported = (
            current.get("generated_fullsize_sha256") == entry["generated_fullsize_sha256"]
            and portrait_ready(current) and marker.get("schema") == "low7-kimi-production-import-v1"
            and marker.get("review_sha256") == entry["review_sha256"] and marker.get("task_id") == entry["task_id"]
        )
        if imported:
            entry["production_import"] = "formal_canonical_import_complete_pending_publication"
    formal_count = sum(row["production_import"] == "formal_canonical_import_complete_pending_publication" for row in approved)
    write_json(EXPERIMENT / "approved-masters.json", {
        "schema": "low7-kimi-approved-masters-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
        "count": len(approved), "formal_canonical_import_count": formal_count,
        "canonical_import_pending": formal_count < len(approved),
        "canonical_import_pending_due_to_recorded_git_hold": False,
        "git_resume_authorization": "mod_nailong/experiments/evolink-low7-20261030/delivery-authorization.json",
        "original_pngs_are_ordinary_git_files_not_lfs_or_release_only": True,
        "remote_verification_claimed": False, "runtime_acceptance_claimed": False,
        "entries": approved,
    })
    write_json(EXPERIMENT / "outputs-index.json", {
        "schema": "low7-actual-output-review-index-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
        "entries": indexed, "rejected_and_superseded_outputs_retained": True,
    })
    print(json.dumps({"approved_sources": len(approved), "reviewed_outputs": len(indexed), "canonical_imported_sources": formal_count, "archive_tool_git_operations": 0}))


if __name__ == "__main__":
    main()
