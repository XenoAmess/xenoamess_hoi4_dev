import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.common import file_sha256, machine_id, read_json, utc_now, write_json

prepare = importlib.import_module("mod_nailong.experiments.evolink-low7-20261030.tools.low7_prepare")
EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-low2-20261030"
HANDOFF = ROOT / "docs/handoffs/2026-10-30-low-two-pending.md"
HANDOFF_SHA256 = file_sha256(HANDOFF)
ROUND = ROOT / "mod_nailong/data/extra-retry-rounds/20261030-remaining-low-nine-one-immediate-round-completed.json"
AUTHORIZATION = EXPERIMENT / "authorization.json"
RELEASE = EXPERIMENT / "input-release.json"
SCOPE = EXPERIMENT / "scope.json"
PREPARED = EXPERIMENT / "prepared.json"
TAG = "evolink-low2-source-20261030"
REPOSITORY = "XenoAmess/xenoamess_hoi4_dev"
KEYS = ["13714c9266d4867e2c831f01322fe8647b46db795f3c5673aeb93cd2be8d36d7", "9e6fa74c90e6a74a306bf02b7c08780ec9318e67ef685c9d46cc0fecc670e805"]
ASSETS = {"13714c9266d4867e2c831f01322fe8647b46db795f3c5673aeb93cd2be8d36d7": "63ca34a2c8a3b90bfa75", "9e6fa74c90e6a74a306bf02b7c08780ec9318e67ef685c9d46cc0fecc670e805": "4bd53739fda50ed225be"}
MASCOT = {
    "path": "mod_nailong/assets/reference/naiwa.png",
    "sha256": "766ae05fcdab3bd41f9f0967e64f387de3adafef0f29626570d5670d9b460976",
    "url": f"https://raw.githubusercontent.com/{REPOSITORY}/a539d87d41f2865bf41ba22432dd67cace308ae5/mod_nailong/assets/reference/naiwa.png",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_url(key):
    return f"https://github.com/{REPOSITORY}/releases/download/{TAG}/{key}.png"


def validated_entries():
    require(file_sha256(HANDOFF) == HANDOFF_SHA256, "Pinned LOW2 handoff changed")
    auth = read_json(AUTHORIZATION)
    require(auth.get("authorized_agent") == "Kimi" and auth.get("source_sha256") == KEYS, "LOW2 authorization differs")
    require(auth.get("permission_documents_modified") is False and auth.get("codex_tool_permission_changed") is False, "Permission boundary changed")
    results = {row["source_sha256"]: row for row in read_json(ROUND)["results"]}
    index = read_json(ROOT / "runtime/source-index.json")
    catalog = read_json(ROOT / "mod_nailong/data/catalog.json")
    generated = read_json(ROOT / "mod_nailong/data/generated.json")
    queue = read_json(ROOT / "mod_nailong/data/image-retry-queue.json")
    entries = []
    for position, key in enumerate(KEYS, 1):
        result = results[key]
        journal = read_json(ROOT / f"mod_nailong/data/generation-requests/{key}.json")
        snapshot = journal["attempts"][0]
        require(result["attempt_number"] == snapshot["number"] == 1 and result["status"] == "service_refused" and result["output_created"] is False, f"Only the original failed builtin attempt is in scope: {key}")
        require(result["complete_actual_prompt"] == snapshot["prompt"], f"Prompt differs: {key}")
        prompt_path = ROOT / snapshot["prompt_file"]
        require(prompt_path.read_bytes() == result["complete_actual_prompt"].encode("utf-8") and file_sha256(prompt_path) == result["prompt_sha256"], f"Frozen prompt bytes differ: {key}")
        ordered = result["ordered_inputs"]
        require(len(ordered) == 2 and result["ordered_input_sha256"] == snapshot["actual_request_verification"]["input_sha256"], f"Input order differs: {key}")
        source = next(row for row in ordered if row["role"] == "original source portrait")
        mascot = next(row for row in ordered if row["role"] == "user mascot reference")
        require(source["raw_sha256"] == key and source["converted_png_sha256"] == ordered[0]["converted_png_sha256"], f"Source identity differs: {key}")
        require(mascot["sha256"] == MASCOT["sha256"], f"Mascot differs: {key}")
        source_path = ROOT / f"runtime/references/{key}.png"
        require(file_sha256(source_path) == source["converted_png_sha256"] == ordered[0]["converted_png_sha256"], f"Local source PNG differs: {key}")
        require(file_sha256(ROOT / MASCOT["path"]) == MASCOT["sha256"], "Mascot bytes changed")
        with Image.open(source_path) as image:
            require(list(image.size) == [156, 210] and list(image.convert("RGBA").getchannel("A").getextrema()) == [255, 255], f"Source canvas differs: {key}")
        asset_id = ASSETS[key]
        original = index[asset_id]
        raw = Path(original["path"]).read_bytes() if original["member"] is None else zipfile.ZipFile(original["path"]).read(original["member"])
        require(hashlib.sha256(raw).hexdigest() == key, f"Installed original DDS differs: {key}")
        catalog_assets = [row for row in catalog["assets"] if row["id"] == asset_id and row["source_sha256"] == key]
        require(len(catalog_assets) == 1 and catalog_assets[0]["path"] == result["source_path"], f"Catalog binding differs: {key}")
        require(generated["portraits"].get(key) is None, f"Unexpected existing generated row: {key}")
        require(queue["sources"][key]["retries_used"] == 0, f"Builtin retry count changed: {key}")
        journal = read_json(ROOT / f"mod_nailong/data/generation-requests/{key}.json")
        require(len(journal["attempts"]) == 1 and journal["attempts"][0]["status"] == "failed" and not journal["attempts"][0].get("fullsize_sha256"), f"Existing returned image needs reconciliation: {key}")
        inputs = [
            {"role": "original source portrait", "path": f"runtime/references/{key}.png", "sha256": source["converted_png_sha256"], "url": source_url(key), "cache_name": f"{key}-{source['converted_png_sha256']}.png"},
            {"role": "user mascot reference", "path": MASCOT["path"], "sha256": MASCOT["sha256"], "url": MASCOT["url"], "cache_name": f"naiwa-{MASCOT['sha256']}.png"},
        ]
        entries.append({
            "index": position, "source_sha256": key, "source_assets": [result["source_path"]],
            "source_packages": [catalog_assets[0]["package"]], "source_png": inputs[0]["path"], "converted_png_sha256": inputs[0]["sha256"],
            "prompt": result["complete_actual_prompt"], "prompt_file": snapshot["prompt_file"], "prompt_sha256": result["prompt_sha256"],
            "reference_set": inputs, "builtin_attempt": 1, "builtin_retries_used": 0, "asset_id": asset_id,
        })
    return entries


def verify_public():
    entries = validated_entries()
    assets = []
    reference_sets = []
    for entry in entries:
        references = [prepare.download_public(row) for row in entry["reference_set"]]
        reference_sets.append({"source_sha256": entry["source_sha256"], "ordered_inputs": references})
        original = references[0]
        assets.append({"source_sha256": entry["source_sha256"], "converted_png_sha256": original["sha256"], "bytes": original["bytes"], "url": original["url"], "public_unauthenticated_sha256_verified": True})
    write_json(RELEASE, {
        "schema": "low2-public-input-release-v1", "machine_id": machine_id(), "public_readback_recorded_at_utc": utc_now(),
        "release": {"tag": TAG, "url": f"https://github.com/{REPOSITORY}/releases/tag/{TAG}", "prerelease": True, "purpose": "Only two converted single source portraits for the explicitly authorized Kimi EvoLink task; not a mod release or complete game assets."},
        "assets": assets, "reference_sets": reference_sets, "new_generation_tasks_created": 0,
    })
    print(json.dumps({"status": "public_inputs_verified", "sources": 2, "new_generation_tasks_created": 0}))


def prepare_requests():
    entries = validated_entries()
    release = read_json(RELEASE)
    require(release["schema"] == "low2-public-input-release-v1", "Wrong public input manifest")
    scope_entries = []
    prepared_entries = []
    for entry in entries:
        key = entry["source_sha256"]
        reference_set = next(row["ordered_inputs"] for row in release["reference_sets"] if row["source_sha256"] == key)
        require([row["sha256"] for row in reference_set] == [row["sha256"] for row in entry["reference_set"]], f"Public input order differs: {key}")
        require(all(row["public_unauthenticated_sha256_verified"] is True for row in reference_set), f"Public proof missing: {key}")
        for row in reference_set:
            require(file_sha256(ROOT / row["path"]) == row["sha256"], f"Local input changed: {row['path']}")
        stem = f"{key}-01"
        prompt_path = EXPERIMENT / "prompts" / f"{stem}.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt = entry["prompt"].encode("utf-8")
        if prompt_path.exists():
            require(prompt_path.read_bytes() == prompt, f"Existing frozen prompt differs: {key}")
        else:
            with prompt_path.open("xb") as stream:
                stream.write(prompt)
        for suffix in (".png", ".request.json", ".task.json", ".result.json"):
            require(not (EXPERIMENT / "outputs" / f"{stem}{suffix}").exists(), f"Existing dispatch needs reconciliation: {key}{suffix}")
        require(not (EXPERIMENT / "executions" / f"{stem}.json").exists(), f"Existing execution needs reconciliation: {key}")
        base = {field: entry[field] for field in ("index", "source_sha256", "source_assets", "source_packages", "source_png", "converted_png_sha256")}
        scope_entries.append({**base, "source_size": [156, 210], "source_alpha_extrema": [255, 255], "builtin_attempt": 1, "builtin_retries_used": 0})
        prepared_entries.append({
            **base, "status": "prepared_not_dispatched", "attempt": "external-01", "model": "gpt-image-2.5-flare", "size": "3:4", "resolution": "2K", "quality": "high", "background": "opaque", "n": 1,
            "prompt_file": prompt_path.relative_to(ROOT).as_posix(), "prompt_sha256": file_sha256(prompt_path),
            "output": f"mod_nailong/experiments/evolink-low2-20261030/outputs/{stem}.png",
            "image_urls": [row["url"] for row in reference_set], "ordered_input_sha256": [row["sha256"] for row in reference_set],
            "inputs": [{field: row[field] for field in ("role", "path", "sha256", "url")} for row in reference_set],
            "builtin_attempt": 1, "builtin_retries_used": 0,
        })
    write_json(SCOPE, {
        "schema": "low2-kimi-evolink-scope-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(), "source_count": 2,
        "handoff": "docs/handoffs/2026-10-30-low-two-pending.md", "handoff_sha256": HANDOFF_SHA256,
        "handoff_pinned_commit": "398db2a4959364c4303f9d912397b58df5fe907a",
        "authorization": "mod_nailong/experiments/evolink-low2-20261030/authorization.json", "authorization_sha256": file_sha256(AUTHORIZATION),
        "source_release_tag": TAG, "model": "gpt-image-2.5-flare", "mascot_reference": MASCOT,
        "builtin_retry_counters_preserved": True, "permission_documents_modified": False, "codex_tool_permission_changed": False,
        "entries": scope_entries,
    })
    scope_sha = file_sha256(SCOPE)
    release["scope_sha256"] = scope_sha
    write_json(RELEASE, release)
    write_json(PREPARED, {
        "schema": "low2-kimi-evolink-prepared-v1", "machine_id": machine_id(), "prepared_at_utc": utc_now(),
        "scope_sha256": scope_sha, "input_release_sha256": file_sha256(RELEASE), "source_count": 2,
        "counts": {"prepared_not_dispatched": 2}, "entries": prepared_entries,
    })
    print(json.dumps({"status": "prepared_not_dispatched", "sources": 2, "new_generation_tasks_created": 0}))


def main():
    parser = argparse.ArgumentParser(description="Verify two public inputs or freeze exact LOW2 external requests; never creates an image task.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify-public", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    verify_public() if args.verify_public else prepare_requests()


if __name__ == "__main__":
    main()
