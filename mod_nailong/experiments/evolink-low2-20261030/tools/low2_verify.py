import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from mod_nailong.tools.art_contract import portrait_ready
from tools.common import file_sha256, machine_id, read_json, utc_now, write_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-low2-20261030"
RUNTIME = Path("runtime/low2-evolink-20261030")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_originals():
    import importlib
    prepare = importlib.import_module("mod_nailong.experiments.evolink-low2-20261030.tools.low2_prepare")
    index = read_json(ROOT / "runtime/source-index.json")
    verified = []
    for key, asset_id in prepare.ASSETS.items():
        location = index[asset_id]
        if location["member"] is None:
            data = Path(location["path"]).read_bytes()
        else:
            with zipfile.ZipFile(location["path"]) as archive:
                data = archive.read(location["member"])
        require(hashlib.sha256(data).hexdigest() == key, f"Installed original SHA differs: {key}")
        verified.append({"asset_id": asset_id, "source_sha256": key, "package": "dlc/dlc036_by_blood_alone"})
    return verified


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--passed-tests", type=int, default=0)
    args = parser.parse_args()
    approved = read_json(EXPERIMENT / "approved-masters.json")
    require(approved["schema"] == "low2-kimi-approved-masters-v1" and approved["count"] == len(approved["entries"]) == 2, "Approved count is not two")
    formal_count = approved["formal_canonical_import_count"]
    require(formal_count in {0, 2} and approved["canonical_import_pending"] is (formal_count < 2), "Canonical state differs")
    scope = read_json(EXPERIMENT / "scope.json")
    require(file_sha256(ROOT / scope["handoff"]) == scope["handoff_sha256"], "Handoff changed")
    require(file_sha256(ROOT / scope["authorization"]) == scope["authorization_sha256"], "Authorization changed")
    indexed = read_json(EXPERIMENT / "outputs-index.json")["entries"]
    require(len(indexed) == 2, "Expected exactly two actual returned outputs")
    queue = read_json(ROOT / "mod_nailong/data/image-retry-queue.json")
    generated = read_json(ROOT / "mod_nailong/data/generated.json")
    records = []
    for entry in approved["entries"]:
        key = entry["source_sha256"]
        master = ROOT / entry["generated_fullsize_image"]
        require(master.read_bytes() == (ROOT / next(row["output"] for row in indexed if row["source_sha256"] == key)).read_bytes(), f"Master differs from approved output: {key}")
        require(file_sha256(master) == entry["generated_fullsize_sha256"] and master.stat().st_size == entry["bytes"], f"Master bytes differ: {key}")
        with Image.open(master) as image:
            image.load()
            require(list(image.size) == entry["size"] == [1776, 2368] and image.mode == entry["mode"] == "RGB", f"Master canvas differs: {key}")
        for field in ("request", "result", "execution", "review", "evidence"):
            require(file_sha256(ROOT / entry[field]) == entry[field + "_sha256"], f"Evidence binding differs for {key}: {field}")
        require(file_sha256(ROOT / entry["prompt_file"]) == entry["prompt_sha256"], f"Prompt binding differs: {key}")
        request, result = read_json(ROOT / entry["request"]), read_json(ROOT / entry["result"])
        execution, review = read_json(ROOT / entry["execution"]), read_json(ROOT / entry["review"])
        require(request["endpoint"] == "https://api.evolink.ai/v1/images/generations" and request["model"] == "gpt-image-2.5-flare", f"Generation route differs: {key}")
        require(request["background"] == "opaque" and request["n"] == 1 and request["resolution"] == "2K" and request["quality"] == "high", f"Generation parameters differ: {key}")
        require(request["prompt"] == entry["prompt"] and request["image_urls"] == [row["url"] for row in entry["inputs"]], f"Prompt/inputs differ: {key}")
        require(result["task_id"] == entry["task_id"] and result["sha256"] == entry["generated_fullsize_sha256"] and result["bytes"] == entry["bytes"], f"Task/result differs: {key}")
        require(result["png_signature_verified"] is True and execution["status"] == "completed" and execution["exit_code"] == 0, f"Execution incomplete: {key}")
        require(execution["task_id"] == entry["task_id"] and execution["attempt"] == "external-01" and execution["ordered_input_sha256"] == [row["sha256"] for row in entry["inputs"]], f"Execution differs: {key}")
        decisions = [row for row in review["entries"] if row["source_sha256"] == key]
        require(len(decisions) == 1, f"Review missing: {key}")
        decision = decisions[0]
        require(decision["decision"] == "approved_for_production" and decision["output_sha256"] == entry["generated_fullsize_sha256"], f"Wrong approval: {key}")
        require(decision["hair_features"] == {"policy": "hair-features-v1", "status": "approved"} and decision["collar_fit"] == {"policy": "collar-fit-v1", "status": "approved"}, f"Art approval missing: {key}")
        require(decision["remaining_reasons"] == [] and decision["production_import_pending"] is True and decision["source_alpha_repair_performed"] is False, f"Unresolved art issue: {key}")
        require(queue["sources"][key]["retries_used"] == 0, f"Builtin retry counter changed: {key}")
        current = generated["portraits"].get(key)
        if formal_count == 0:
            require(current is None or current.get("generated_fullsize_sha256") != entry["generated_fullsize_sha256"], f"Unexpected canonical import: {key}")
        else:
            require(current is not None and portrait_ready(current) and current["generated_fullsize_sha256"] == entry["generated_fullsize_sha256"], f"Canonical import missing: {key}")
            require(current["production_import"]["schema"] == entry["import_schema"] and current["production_import"]["review_sha256"] == entry["review_sha256"], f"Canonical evidence differs: {key}")
        records.append({"source_sha256": key, "master_sha256": entry["generated_fullsize_sha256"], "attempt": entry["attempt"], "task_id": entry["task_id"], "review_sha256": entry["review_sha256"], "resource_instances": len(entry["source_assets"])})
    originals = verify_originals()
    require(len(originals) == 2, "Expected two resource-instance original bindings")
    receipt = {
        "schema": "low2-kimi-final-verification-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
        "status": "two_sources_generated_reviewed_integrated_pending_publication" if formal_count == 2 else "two_sources_generated_reviewed_and_archived_pending_canonical_import_and_git_publication",
        "approved_person_sources": 2, "source_scope_percent": 100, "resource_instances": 2,
        "new_generation_tasks_created": 2, "same_task_recoveries_without_new_post": 0,
        "reviewed_actual_outputs": 2, "archived_original_pngs": 2,
        "approved_original_png_bytes": sum(row["bytes"] for row in approved["entries"]),
        "original_dds_resource_bindings_verified": originals, "canonical_manifest_imported": formal_count,
        "git_operations_by_this_verifier": 0, "remote_original_png_verification": "not_run",
        "permission_documents_modified": False, "codex_evolink_permission_changed": False,
        "unresolved_generation_tasks": 0, "hoi4_runtime_acceptance_claimed": False,
        "scoped_tests": {"file": "tests/test_low2_evolink.py", "passed": args.passed_tests},
        "free_bytes_at_verification": shutil.disk_usage(ROOT).free, "entries": records,
    }
    destination = ROOT / RUNTIME / "final-verification.json"
    write_json(destination, receipt)
    print(json.dumps({field: value for field, value in receipt.items() if field not in {"entries", "original_dds_resource_bindings_verified"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
