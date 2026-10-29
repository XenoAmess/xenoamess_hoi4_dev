import argparse
import json
from pathlib import Path
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.common import file_sha256, machine_id, read_json, utc_now, write_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-low7-20261030"
HANDOFF = ROOT / "docs/handoffs/2026-10-30-low7-exhausted.json"
HANDOFF_SHA256 = "36d28fbf52106df2949007e6658514c026030f122a16f8d9adbe5f5bf9228eb5"
AUTHORIZATION = EXPERIMENT / "authorization.json"
RELEASE = EXPERIMENT / "input-release.json"
SCOPE = EXPERIMENT / "scope.json"
PREPARED = EXPERIMENT / "prepared.json"
TAG = "evolink-low7-source-20261030"
REPOSITORY = "XenoAmess/xenoamess_hoi4_dev"
MASCOT = {
    "path": "mod_nailong/assets/reference/naiwa.png",
    "sha256": "766ae05fcdab3bd41f9f0967e64f387de3adafef0f29626570d5670d9b460976",
    "url": f"https://raw.githubusercontent.com/{REPOSITORY}/a539d87d41f2865bf41ba22432dd67cace308ae5/mod_nailong/assets/reference/naiwa.png",
}
EDIT_TARGET = {
    "path": "mod_nailong/assets/generated_fullsize/fca9eca6c6b5bfc340b9b931f88abc0b1af0a23cb870fadd823eb6663d1b6614.png",
    "sha256": "fca9eca6c6b5bfc340b9b931f88abc0b1af0a23cb870fadd823eb6663d1b6614",
    "url": f"https://raw.githubusercontent.com/{REPOSITORY}/323e50248b85560678710b986836f82b3b1ac596/mod_nailong/assets/generated_fullsize/fca9eca6c6b5bfc340b9b931f88abc0b1af0a23cb870fadd823eb6663d1b6614.png",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_url(key):
    return f"https://github.com/{REPOSITORY}/releases/download/{TAG}/{key}.png"


def project_path(value):
    require(isinstance(value, str) and value and not Path(value).is_absolute(), f"Invalid local input path: {value}")
    path = (ROOT / value).resolve()
    path.relative_to(ROOT.resolve())
    return path


def load_handoff():
    require(file_sha256(HANDOFF) == HANDOFF_SHA256, "The supplied handoff changed")
    body = read_json(HANDOFF)
    require(body.get("source_count") == len(body.get("entries", [])) == 7, "Expected seven distinct sources")
    require(len({row["source_sha256"] for row in body["entries"]}) == 7, "Duplicate source")
    return body


def reference_for(item):
    key = item["path"]
    if key.startswith("runtime/references/") and key.endswith(".png"):
        source = Path(key).stem
        return source, {**item, "url": source_url(source)}
    for candidate in (MASCOT, EDIT_TARGET):
        if key == candidate["path"]:
            require(item["sha256"] == candidate["sha256"], f"Frozen reference differs: {key}")
            return Path(key).stem, {**item, "url": candidate["url"]}
    raise ValueError(f"Input is not in the authorized reference set: {key}")


def validated_entries():
    handoff = load_handoff()
    auth = read_json(AUTHORIZATION)
    require(auth.get("handoff_sha256") == HANDOFF_SHA256, "Authorization is not bound to this handoff")
    require(auth.get("authorized_agent") == "Kimi", "This runner is only for the user-authorized Kimi task")
    require(auth.get("source_sha256") == [row["source_sha256"] for row in handoff["entries"]], "Authorization scope differs")
    require(auth.get("permission_documents_modified") is False and auth.get("codex_tool_permission_changed") is False, "Permission boundary changed")
    entries = []
    for index, source in enumerate(handoff["entries"], 1):
        key = source["source_sha256"]
        latest = source["latest_result"]
        snapshot = source["latest_attempt_snapshot"]
        require(latest["source_sha256"] == key and snapshot["number"] == latest["attempt_number"], f"Source identity mismatch: {key}")
        require(latest["status"] == "service_refused" and latest["output_created"] is False, f"Latest builtin result is not the retained refusal: {key}")
        require(source["retry_queue_snapshot"]["retries_used"] == 9, f"Historical builtin count is not preserved: {key}")
        prompt = latest["complete_actual_prompt"]
        require(snapshot["prompt"] == prompt, f"Prompt mismatch: {key}")
        prompt_path = project_path(snapshot["prompt_file"])
        require(prompt_path.read_bytes() == prompt.encode("utf-8"), f"Frozen prompt bytes differ: {key}")
        require(file_sha256(prompt_path) == latest["prompt_sha256"], f"Prompt SHA mismatch: {key}")
        ordered_inputs = source["ordered_actual_inputs"]
        require(len(ordered_inputs) == len(snapshot["inputs"]), f"Ordered input count differs: {key}")
        for item, historical in zip(ordered_inputs, snapshot["inputs"]):
            require(item["role"] == historical["role"], f"Input role changed: {key}")
            require(item["path"] == historical.get("path", f"runtime/references/{key}.png"), f"Input path changed: {key}")
            require(item["sha256"] == historical.get("sha256", historical.get("converted_png_sha256")), f"Input SHA changed: {key}")
        require(latest["ordered_input_sha256"] == [row["sha256"] for row in ordered_inputs], f"Historical ordered input SHA mismatch: {key}")
        reference_set = []
        for position, item in enumerate(ordered_inputs, 1):
            require(item["index"] == position, f"Input order changed: {key}")
            path = project_path(item["path"])
            require(file_sha256(path) == item["sha256"], f"Local input SHA changed: {item['path']}")
            name, reference = reference_for(item)
            reference_set.append({**reference, "cache_name": f"{name}-{item['sha256']}.png"})
        expected_count = 3 if key == "1f66d040d3ea98c01ad0d0c91bc6a150d379c89d2a4840f604bad60984cab616" else 2
        require(len(reference_set) == expected_count, f"Wrong input count: {key}")
        if expected_count == 3:
            current = source["current_generated_row_snapshot"]
            require(current["review"] == "rejected" and current["generated_fullsize_sha256"] == EDIT_TARGET["sha256"], "Navy_2 is not the frozen rejected edit target")
            require(reference_set[0]["sha256"] == EDIT_TARGET["sha256"], "Navy_2 target must be first")
        original = next(row for row in reference_set if row["role"] == "original source portrait")
        assets = source["assets"]
        require(Path(original["path"]).stem == key and all(row["source_sha256"] == key for row in assets), f"Asset binding differs: {key}")
        with Image.open(project_path(original["path"])) as image:
            require(list(image.size) == [156, 210], f"Unexpected source dimensions: {key}")
            require(list(image.convert("RGBA").getchannel("A").getextrema()) == [255, 255], f"Source is not the verified opaque canvas: {key}")
        entries.append({
            "index": index,
            "source_sha256": key,
            "source_assets": [row["path"] for row in assets],
            "source_packages": sorted({row["package"] for row in assets}),
            "source_png": original["path"],
            "converted_png_sha256": original["sha256"],
            "prompt": prompt,
            "prompt_file": snapshot["prompt_file"],
            "prompt_sha256": latest["prompt_sha256"],
            "reference_set": reference_set,
            "builtin_attempt": latest["attempt_number"],
            "builtin_retries_used": 9,
        })
    return auth, entries


def download_public(reference):
    import subprocess

    url = reference["url"]
    require(url.startswith("https://") and "?" not in url and "#" not in url, f"Reference is not fixed public HTTPS: {url}")
    errors = []
    for route in (("proxy", "http://127.0.0.1:10808"), ("noproxy", "*")):
        result = subprocess.run([
            "curl.exe", f"--{route[0]}", route[1], "--fail", "--silent", "--show-error",
            "--location", "--proto", "=https", "--connect-timeout", "20", "--max-time", "60",
            "--max-filesize", str(16 * 1024 * 1024), url,
        ], capture_output=True, timeout=75)
        if result.returncode == 0:
            data = result.stdout
            break
        errors.append(result.stderr.decode("utf-8", errors="replace")[:300])
    else:
        raise RuntimeError(f"Public input readback failed: {'; '.join(errors)}")
    require(len(data) <= 16 * 1024 * 1024, f"Unexpectedly large reference: {url}")
    require(data.startswith(b"\x89PNG\r\n\x1a\n"), f"Reference is not PNG: {url}")
    from tools.common import sha256
    require(sha256(data) == reference["sha256"], f"Public reference SHA differs: {url}")
    target = ROOT / "runtime/low7-evolink-20261030/public-inputs" / reference["cache_name"]
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        require(target.read_bytes() == data, f"Existing public input cache differs: {target}")
    else:
        with target.open("xb") as stream:
            stream.write(data)
    return {**reference, "bytes": len(data), "public_unauthenticated_sha256_verified": True, "readback_at_utc": utc_now()}


def verify_public():
    auth, entries = validated_entries()
    assets = []
    reference_sets = []
    seen = set()
    for entry in entries:
        key = entry["source_sha256"]
        require(key not in seen, "Duplicate source")
        seen.add(key)
        rows = [download_public(row) for row in entry["reference_set"]]
        reference_sets.append({"source_sha256": key, "ordered_inputs": rows})
        original = next(row for row in rows if row["role"] == "original source portrait")
        assets.append({
            "source_sha256": key,
            "converted_png_sha256": original["sha256"],
            "bytes": original["bytes"],
            "url": original["url"],
            "public_unauthenticated_sha256_verified": True,
        })
    write_json(RELEASE, {
        "schema": "low7-public-input-release-v1",
        "machine_id": machine_id(),
        "public_readback_recorded_at_utc": utc_now(),
        "authorization": "mod_nailong/experiments/evolink-low7-20261030/authorization.json",
        "authorization_sha256": file_sha256(AUTHORIZATION),
        "release": {
            "tag": TAG,
            "url": f"https://github.com/{REPOSITORY}/releases/tag/{TAG}",
            "prerelease": True,
            "purpose": "Seven converted single source portraits for the explicitly authorized Kimi EvoLink task; not a mod release or complete game assets.",
        },
        "assets": assets,
        "reference_sets": reference_sets,
        "mascot_and_existing_target_pinned_to_public_git_bytes": True,
        "new_generation_tasks_created": 0,
    })
    print(json.dumps({"status": "public_inputs_verified", "sources": len(assets), "reference_sets": len(reference_sets), "new_generation_tasks_created": 0}))


def prepare():
    auth, entries = validated_entries()
    release = read_json(RELEASE)
    require(release.get("schema") == "low7-public-input-release-v1", "Wrong public input manifest")
    require(release.get("authorization_sha256") == file_sha256(AUTHORIZATION), "Public input manifest is not bound to this authorization")
    reference_sets = {row["source_sha256"]: row["ordered_inputs"] for row in release["reference_sets"]}
    scope_entries = []
    prepared_entries = []
    for entry in entries:
        key = entry["source_sha256"]
        references = reference_sets[key]
        require([row["sha256"] for row in references] == [row["sha256"] for row in entry["reference_set"]], f"Public input order differs: {key}")
        require([row["path"] for row in references] == [row["path"] for row in entry["reference_set"]], f"Public local input order differs: {key}")
        require(all(row["public_unauthenticated_sha256_verified"] is True for row in references), f"Missing public readback: {key}")
        for row in references:
            require(file_sha256(project_path(row["path"])) == row["sha256"], f"Input bytes changed: {row['path']}")
        stem = f"{key}-01"
        prompt_path = EXPERIMENT / "prompts" / f"{stem}.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        data = entry["prompt"].encode("utf-8")
        if prompt_path.exists():
            require(prompt_path.read_bytes() == data, f"Existing frozen prompt differs: {key}")
        else:
            with prompt_path.open("xb") as stream:
                stream.write(data)
        for suffix in (".png", ".request.json", ".task.json", ".result.json"):
            require(not (EXPERIMENT / "outputs" / f"{stem}{suffix}").exists(), f"Existing dispatch needs reconciliation: {key}{suffix}")
        require(not (EXPERIMENT / "executions" / f"{stem}.json").exists(), f"Existing execution needs reconciliation: {key}")
        base = {field: entry[field] for field in ("index", "source_sha256", "source_assets", "source_packages", "source_png", "converted_png_sha256")}
        scope_entries.append({**base, "source_size": [156, 210], "source_alpha_extrema": [255, 255], "builtin_attempt": entry["builtin_attempt"], "builtin_retries_used": 9})
        prepared_entries.append({
            **base,
            "status": "prepared_not_dispatched",
            "attempt": "external-01",
            "model": "gpt-image-2.5-flare",
            "size": "3:4",
            "resolution": "2K",
            "quality": "high",
            "background": "opaque",
            "n": 1,
            "prompt_file": prompt_path.relative_to(ROOT).as_posix(),
            "prompt_sha256": file_sha256(prompt_path),
            "output": f"mod_nailong/experiments/evolink-low7-20261030/outputs/{stem}.png",
            "image_urls": [row["url"] for row in references],
            "ordered_input_sha256": [row["sha256"] for row in references],
            "inputs": [{field: row[field] for field in ("role", "path", "sha256", "url")} for row in references],
            "builtin_attempt": entry["builtin_attempt"],
            "builtin_retries_used": 9,
        })
    write_json(SCOPE, {
        "schema": "low7-kimi-evolink-scope-v1",
        "machine_id": machine_id(),
        "observed_at_utc": utc_now(),
        "source_count": 7,
        "handoff": "docs/handoffs/2026-10-30-low7-exhausted.json",
        "handoff_sha256": HANDOFF_SHA256,
        "authorization": "mod_nailong/experiments/evolink-low7-20261030/authorization.json",
        "authorization_sha256": file_sha256(AUTHORIZATION),
        "source_release_tag": TAG,
        "model": "gpt-image-2.5-flare",
        "mascot_reference": MASCOT,
        "edit_target": EDIT_TARGET,
        "builtin_retry_counters_preserved": True,
        "permission_documents_modified": False,
        "codex_tool_permission_changed": False,
        "entries": scope_entries,
    })
    scope_sha = file_sha256(SCOPE)
    release["scope_sha256"] = scope_sha
    write_json(RELEASE, release)
    write_json(PREPARED, {
        "schema": "low7-kimi-evolink-prepared-v1",
        "machine_id": machine_id(),
        "prepared_at_utc": utc_now(),
        "scope_sha256": scope_sha,
        "input_release_sha256": file_sha256(RELEASE),
        "source_count": 7,
        "counts": {"prepared_not_dispatched": 7},
        "entries": prepared_entries,
    })
    print(json.dumps({"status": "prepared_not_dispatched", "sources": 7, "new_generation_tasks_created": 0}))


def main():
    parser = argparse.ArgumentParser(description="Verify seven public input references or freeze their exact external requests; never creates an image task.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify-public", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    verify_public() if args.verify_public else prepare()


if __name__ == "__main__":
    main()
