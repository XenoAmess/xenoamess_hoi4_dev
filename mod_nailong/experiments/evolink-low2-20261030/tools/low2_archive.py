import json
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from mod_nailong.tools.art_contract import portrait_ready
from mod_nailong.tools.portraits import record_fullsize_origin
from tools.common import file_sha256, machine_id, read_json, utc_now, write_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-low2-20261030"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    review_path = EXPERIMENT / "review-01-agent.json"
    review = read_json(review_path)
    require(review["schema"] == "low2-kimi-evolink-manual-review-v1", "Wrong review schema")
    require(review["machine_id"] == machine_id() and review["model"] == "gpt-image-2.5-flare", "Review identity differs")
    require(file_sha256(ROOT / review["review_evidence"]) == review["review_evidence_sha256"], "Review evidence SHA differs")
    require(file_sha256(ROOT / review["review_sheet"]) == review["review_sheet_sha256"], "Review sheet SHA differs")
    scope = read_json(EXPERIMENT / "scope.json")
    prepared = read_json(EXPERIMENT / "prepared.json")["entries"]
    approved, indexed = [], []
    for decision in review["entries"]:
        key = decision["source_sha256"]
        require(decision["attempt"] == "external-01", "Only the frozen first external attempt is in scope")
        output = ROOT / decision["output"]
        require(file_sha256(output) == decision["output_sha256"], f"Review output bytes changed: {key}")
        record_fullsize_origin(key, output)
        indexed.append({"source_sha256": key, "attempt": decision["attempt"], "output": decision["output"], "output_sha256": decision["output_sha256"], "decision": decision["decision"], "review": review_path.relative_to(ROOT).as_posix(), "review_sha256": file_sha256(review_path)})
        if decision["decision"] != "approved_for_production":
            continue
        require(decision["remaining_reasons"] == [] and decision["production_import_pending"] is True, f"Unresolved approval: {key}")
        require(decision["hair_features"] == {"policy": "hair-features-v1", "status": "approved"}, f"Hair approval missing: {key}")
        require(decision["collar_fit"] == {"policy": "collar-fit-v1", "status": "approved"}, f"Collar approval missing: {key}")
        require(decision["rgb_art_approved"] is True and decision["source_alpha_repair_performed"] is False, f"Wrong RGB/alpha decision: {key}")
        entry = next(row for row in prepared if row["source_sha256"] == key and row["attempt"] == decision["attempt"])
        source = next(row for row in scope["entries"] if row["source_sha256"] == key)
        require(entry["ordered_input_sha256"] == [row["sha256"] for row in entry["inputs"]], f"Ordered input SHA differs: {key}")
        for item in entry["inputs"]:
            require(file_sha256(ROOT / item["path"]) == item["sha256"], f"Local input changed: {item['path']}")
        with Image.open(output) as image:
            image.load()
            size, mode = list(image.size), image.mode
            alpha = list(image.convert("RGBA").getchannel("A").getextrema())
        require(size == decision["size"] and mode == decision["mode"] == "RGB", f"Review image metadata differs: {key}")
        require(decision["source_alpha_extrema"] == source["source_alpha_extrema"] == [255, 255], f"Source opacity differs: {key}")
        require(decision["returned_alpha_extrema"] is None and alpha == [255, 255], f"Opaque canvas proof changed: {key}")
        stem = output.stem
        paths = {name: output.with_name(f"{stem}.{suffix}") for name, suffix in (("request", "request.json"), ("task", "task.json"), ("result", "result.json"), ("prompt", "prompt.txt"))}
        request = read_json(paths["request"])
        result = read_json(paths["result"])
        task = read_json(paths["task"])
        execution = EXPERIMENT / "executions" / f"{stem}.json"
        execution_body = read_json(execution)
        require(result["task_id"] == decision["task_id"] == task["task_id"], f"Task identity mismatch: {key}")
        require(result["sha256"] == decision["output_sha256"] and result["bytes"] == output.stat().st_size, f"Result/output mismatch: {key}")
        require(request["prompt"] == paths["prompt"].read_text(encoding="utf-8"), f"Actual prompt differs: {key}")
        require(file_sha256(paths["prompt"]) == decision["prompt_sha256"] == entry["prompt_sha256"], f"Approved prompt differs: {key}")
        require(request["image_urls"] == entry["image_urls"], f"Ordered input URLs differ: {key}")
        require(request["model"] == entry["model"] == "gpt-image-2.5-flare", f"Model differs: {key}")
        require(request["background"] == "opaque" and request["n"] == 1 and request["resolution"] == "2K" and request["quality"] == "high", f"Generation parameters differ: {key}")
        for field, expected in (("source_sha256", key), ("attempt", "external-01"), ("task_id", decision["task_id"]), ("prompt_sha256", decision["prompt_sha256"]), ("ordered_input_sha256", entry["ordered_input_sha256"]), ("status", "completed"), ("output_sha256", decision["output_sha256"])):
            require(execution_body[field] == expected, f"Execution binding differs for {key}: {field}")
        master_relative = record_fullsize_origin(key, output)
        master = ROOT / master_relative
        require(master.read_bytes() == output.read_bytes(), f"Master differs from raw output: {key}")
        approved.append({
            "index": source["index"], "source_sha256": key, "source_assets": source["source_assets"], "source_packages": source["source_packages"],
            "attempt": "external-01", "task_id": decision["task_id"], "method": "EvoLink gpt-image-2.5-flare",
            "import_schema": "low2-kimi-production-import-v1",
            "generated_fullsize_image": master_relative, "generated_fullsize_sha256": decision["output_sha256"],
            "bytes": master.stat().st_size, "size": size, "mode": mode, "alpha_extrema": alpha,
            "prompt_file": entry["prompt_file"], "prompt_sha256": decision["prompt_sha256"], "prompt": request["prompt"],
            "inputs": entry["inputs"], "request": paths["request"].relative_to(ROOT).as_posix(), "request_sha256": file_sha256(paths["request"]),
            "result": paths["result"].relative_to(ROOT).as_posix(), "result_sha256": file_sha256(paths["result"]),
            "execution": execution.relative_to(ROOT).as_posix(), "execution_sha256": file_sha256(execution),
            "recovery": None, "recovery_sha256": None,
            "generated_at_utc": result["downloaded_at_utc"], "review": review_path.relative_to(ROOT).as_posix(), "review_sha256": file_sha256(review_path),
            "reviewed_at_utc": review["reviewed_at_utc"], "reviewer": review["reviewer"],
            "evidence": review["review_evidence"], "evidence_sha256": review["review_evidence_sha256"],
            "edit_existing": False, "production_import": "pending_canonical_manifest",
        })
    approved.sort(key=lambda row: row["index"])
    require(len(approved) == scope["source_count"] == 2, "Scope must have exactly two approved sources")
    canonical = read_json(ROOT / "mod_nailong/data/generated.json")["portraits"]
    formal_count = 0
    for entry in approved:
        current = canonical.get(entry["source_sha256"], {})
        marker = current.get("production_import", {})
        imported = (current.get("generated_fullsize_sha256") == entry["generated_fullsize_sha256"] and portrait_ready(current)
                    and marker.get("schema") == entry["import_schema"] and marker.get("review_sha256") == entry["review_sha256"] and marker.get("task_id") == entry["task_id"])
        if imported:
            entry["production_import"] = "formal_canonical_import_complete_pending_publication"
            formal_count += 1
    write_json(EXPERIMENT / "approved-masters.json", {
        "schema": "low2-kimi-approved-masters-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
        "count": len(approved), "formal_canonical_import_count": formal_count, "canonical_import_pending": formal_count < len(approved),
        "original_pngs_are_ordinary_git_files_not_lfs_or_release_only": True, "remote_verification_claimed": False, "runtime_acceptance_claimed": False, "entries": approved,
    })
    write_json(EXPERIMENT / "outputs-index.json", {
        "schema": "low2-actual-output-review-index-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
        "entries": indexed, "rejected_and_superseded_outputs_retained": True,
    })
    print(json.dumps({"approved_sources": len(approved), "reviewed_outputs": len(indexed), "canonical_imported_sources": formal_count, "archive_tool_git_operations": 0}))


if __name__ == "__main__":
    main()
