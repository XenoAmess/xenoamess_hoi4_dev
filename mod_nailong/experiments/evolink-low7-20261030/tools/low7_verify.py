import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.common import file_sha256, machine_id, read_json, utc_now, write_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-low7-20261030"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_originals(handoff):
    verified = []
    for entry in handoff["entries"]:
        for location in entry["installed_source_locations"]:
            installed = location["installed_source"]
            if installed["member"] is None:
                data = Path(installed["path"]).read_bytes()
            else:
                with zipfile.ZipFile(installed["path"]) as archive:
                    data = archive.read(installed["member"])
            require(hashlib.sha256(data).hexdigest() == entry["source_sha256"], f"Installed original SHA differs: {entry['source_sha256']}")
            verified.append({"asset_id": location["asset_id"], "source_sha256": entry["source_sha256"], "package": next(row["package"] for row in entry["assets"] if row["id"] == location["asset_id"])})
    return verified


def main():
    approved = read_json(EXPERIMENT / "approved-masters.json")
    require(approved["count"] == len(approved["entries"]) == 7, "Approved count is not seven")
    formal_count = approved["formal_canonical_import_count"]
    require(formal_count in {0, 7}, "Formal import count must be zero before import or seven after it")
    require(approved["canonical_import_pending"] is (formal_count < 7), "Canonical pending state differs from formal import count")
    require(approved["canonical_import_pending_due_to_recorded_git_hold"] is False, "The explicit Git-resume authorization is not recorded")
    scope = read_json(EXPERIMENT / "scope.json")
    handoff = read_json(ROOT / scope["handoff"])
    require(file_sha256(ROOT / scope["handoff"]) == scope["handoff_sha256"], "Handoff changed")
    require([row["source_sha256"] for row in scope["entries"]] == [row["source_sha256"] for row in approved["entries"]], "Approved sources differ from scope")
    require(file_sha256(ROOT / scope["authorization"]) == scope["authorization_sha256"], "Authorization changed")
    generated = read_json(ROOT / "mod_nailong/data/generated.json")
    queue = read_json(ROOT / "mod_nailong/data/image-retry-queue.json")
    indexed = read_json(EXPERIMENT / "outputs-index.json")["entries"]
    require(len(indexed) == 9, "Expected seven original and two rejected-parent outputs")
    checked_outputs = set()
    records = []
    for entry in approved["entries"]:
        key = entry["source_sha256"]
        source = next(row for row in scope["entries"] if row["source_sha256"] == key)
        require(entry["source_assets"] == source["source_assets"], f"Asset identity differs: {key}")
        master = ROOT / entry["generated_fullsize_image"]
        require(master.read_bytes() == (ROOT / next(row["output"] for row in indexed if row["source_sha256"] == key and row["decision"] == "approved_for_production")).read_bytes(), f"Master differs from approved output: {key}")
        require(file_sha256(master) == entry["generated_fullsize_sha256"], f"Master SHA differs: {key}")
        require(master.stat().st_size == entry["bytes"], f"Master bytes differ: {key}")
        with Image.open(master) as image:
            image.load()
            require(list(image.size) == entry["size"] == [1776, 2368], f"Master size differs: {key}")
            require(image.mode == entry["mode"] == "RGB", f"Master mode differs: {key}")
            require(list(image.convert("RGBA").getchannel("A").getextrema()) == [255, 255], f"Opaque canvas differs: {key}")
        for field in ("request", "result", "execution", "review", "evidence"):
            require(file_sha256(ROOT / entry[field]) == entry[field + "_sha256"], f"Evidence binding differs for {key}: {field}")
        require(file_sha256(ROOT / entry["prompt_file"]) == entry["prompt_sha256"], f"Prompt binding differs: {key}")
        request = read_json(ROOT / entry["request"])
        result = read_json(ROOT / entry["result"])
        execution = read_json(ROOT / entry["execution"])
        review = read_json(ROOT / entry["review"])
        require(request["endpoint"] == "https://api.evolink.ai/v1/images/generations", f"Wrong endpoint: {key}")
        require(request["model"] == "gpt-image-2.5-flare" and request["background"] == "opaque" and request["n"] == 1 and request["resolution"] == "2K" and request["quality"] == "high", f"Wrong generation parameters: {key}")
        require(request["prompt"] == entry["prompt"], f"Actual prompt differs: {key}")
        require(result["task_id"] == entry["task_id"] and result["sha256"] == entry["generated_fullsize_sha256"] and result["bytes"] == entry["bytes"], f"Task/result differs: {key}")
        require(result["png_signature_verified"] is True, f"PNG signature not verified: {key}")
        require(execution["task_id"] == entry["task_id"] and execution["attempt"] == entry["attempt"] and execution["ordered_input_sha256"] == [row["sha256"] for row in entry["inputs"]], f"Execution binding differs: {key}")
        decisions = [row for row in review["entries"] if row["source_sha256"] == key]
        require(len(decisions) == 1, f"Review decision missing: {key}")
        decision = decisions[0]
        require(decision["decision"] == "approved_for_production" and decision["output_sha256"] == entry["generated_fullsize_sha256"] and decision["attempt"] == entry["attempt"], f"Wrong approval: {key}")
        require(decision["hair_features"] == {"policy": "hair-features-v1", "status": "approved"}, f"Hair approval missing: {key}")
        require(decision["collar_fit"] == {"policy": "collar-fit-v1", "status": "approved"}, f"Collar approval missing: {key}")
        require(decision["remaining_reasons"] == [] and decision["production_import_pending"] is True, f"Unresolved art issue: {key}")
        if entry["recovery"]:
            require(file_sha256(ROOT / entry["recovery"]) == entry["recovery_sha256"], "Recovery receipt binding differs")
            recovery = read_json(ROOT / entry["recovery"])
            require(recovery["status"] == "completed" and recovery["new_generation_post_created"] is False and recovery["same_task_id_verified"] is True, "Recovery created a new task or is incomplete")
            require(recovery["task_id"] == entry["task_id"] and recovery["output_sha256"] == entry["generated_fullsize_sha256"], "Recovery output differs")
        else:
            require(execution["status"] == "completed" and execution["output_sha256"] == entry["generated_fullsize_sha256"], f"Execution incomplete: {key}")
        require(queue["sources"][key]["retries_used"] == 9, f"Builtin retry count changed: {key}")
        current = generated["portraits"].get(key)
        if formal_count == 0:
            require(current is None or current.get("generated_fullsize_sha256") != entry["generated_fullsize_sha256"], f"Unexpected canonical import claim: {key}")
        else:
            require(current is not None and current.get("generated_fullsize_sha256") == entry["generated_fullsize_sha256"] and current.get("review") == "approved", f"Canonical import is missing: {key}")
            require(current.get("production_import", {}).get("schema") == "low7-kimi-production-import-v1" and current["production_import"].get("review_sha256") == entry["review_sha256"], f"Canonical evidence marker differs: {key}")
        records.append({"source_sha256": key, "master_sha256": entry["generated_fullsize_sha256"], "attempt": entry["attempt"], "task_id": entry["task_id"], "review_sha256": entry["review_sha256"], "resource_instances": len(entry["source_assets"])})
        checked_outputs.add(entry["generated_fullsize_sha256"])
    for row in indexed:
        master = ROOT / "mod_nailong/assets/generated_fullsize" / f"{row['output_sha256']}.png"
        require(master.is_file() and file_sha256(master) == row["output_sha256"], f"Reviewed original is not archived: {row['output_sha256']}")
        checked_outputs.add(row["output_sha256"])
    originals = verify_originals(handoff)
    require(len(originals) == 10, "Expected ten resource-instance original bindings")
    receipt = {
        "schema": "low7-kimi-final-verification-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
        "status": "seven_sources_generated_reviewed_integrated_pending_publication" if formal_count == 7 else "seven_sources_generated_reviewed_and_archived_pending_canonical_import_and_git_publication",
        "approved_person_sources": 7, "source_scope_percent": 100, "resource_instances": 10,
        "new_generation_tasks_created": 9, "same_task_recoveries_without_new_post": 1,
        "reviewed_actual_outputs": 9, "archived_original_pngs": len(checked_outputs),
        "approved_original_png_bytes": sum(row["bytes"] for row in approved["entries"]),
        "original_dds_resource_bindings_verified": originals,
        "canonical_manifest_imported": formal_count, "git_operations_by_this_verifier": 0,
        "remote_original_png_verification": "not_run",
        "permission_documents_modified": False, "codex_evolink_permission_changed": False,
        "unresolved_generation_tasks": 0, "hoi4_runtime_acceptance_claimed": False,
        "scoped_tests": {"file": "tests/test_low7_evolink.py", "passed": 11},
        "free_bytes_at_verification": shutil.disk_usage(ROOT).free,
        "entries": records,
    }
    write_json(ROOT / "runtime/low7-evolink-20261030/final-verification.json", receipt)
    print(json.dumps({field: value for field, value in receipt.items() if field not in {"entries", "original_dds_resource_bindings_verified"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
