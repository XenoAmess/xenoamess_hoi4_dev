import argparse
import copy
import importlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from runtime import high131_run_batch as batch
prepare = importlib.import_module("mod_nailong.experiments.evolink-low7-20261030.tools.low7_prepare")
from tools.common import file_sha256, machine_id, read_json, utc_now, write_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-low7-20261030"
REPAIR_PREPARATION = EXPERIMENT / "repair-preparation.json"
REPAIR_PREPARED = EXPERIMENT / "repair-prepared.json"
REPAIR_RELEASE = EXPERIMENT / "repair-input-release.json"
batch.PREPARED_PATH = REPAIR_PREPARED
batch.SCOPE_PATH = prepare.SCOPE
batch.RELEASE_PATH = REPAIR_RELEASE
REVIEW = EXPERIMENT / "review-02-agent.json"
TAG = "evolink-low7-repair-input-20261030"
CORRECTIONS = {
    "992fd164fd779b10388e3019ff930a9fc3f6b63794df1997709528ffec1a9cdc": (
        "a27abdb50df7e7a58a2e9a56b10160dd9a21a1208f6fba100d3e07f077ce7222",
        "The raw-HD output has a separate short horizontal mouth-like line high on the face and a second lower mouth. Remove the extra upper line. Keep exactly ONE small closed source-appropriate mouth at the actual original lower mouth position, without a second grey slit, nose-like mouth or extra lip. Do not add facial hair.",
    ),
    "31205e7b1ce58b6b6ff24c8d2241a15bc5f45c698b214f93d1bddbb4e28331f6": (
        "b4e1cded371d0bb446044b33e8f53a97c3f2ca8e21ca7fcf4d3b3e8b07cdb03f",
        "The raw-HD output invents a conspicuous brown moustache above the mouth, while the exact original has a smooth clean-shaven upper lip and chin. Remove the moustache completely and restore smooth yellow skin there. Keep exactly ONE small serious mouth at the actual original mouth position; no second grey slit, new facial-hair band, human nose or projected lips.",
    ),
}
PROMPT_TAIL = """
Keep all unrelated source-visible hairstyle and hair colour, independent eyebrows and exact fine facial-hair state, glasses, headgear when actually present, clothes/neckwear, badges/buttons/straps, expression, gaze, pose, crop and lighting. Source-visible eyebrows remain distinct independent brows; never erase them to copy the identity reference smooth forehead or merge them into head hair. Smooth golden-yellow compact round mascot head with green-ringed black eyes and exactly ONE small mouth at the actual original mouth position. No human skin/nose/ears, invented facial hair, hat replacing real hair, new symbols, people, text, comparison panels or watermark.
Preserve the successful cap, uniform, collar patches and other decorations from the actual raw-HD target and original. The compact rounded chin meets the original garment through a VERY SHORT BROAD fitted transition. Preserve the original open/closed collar fastening and coherent cloth overlap/contact shadow. No long yellow stalk, pinched collar ring, floating cloth, clipping or cream neck bib.
The original is a standalone complete rectangular painted portrait, not a framed card/note. Preserve its entire original painted background, full chest-up crop and upper-left lighting through every edge. Return a fully opaque rectangular image with alpha 255 throughout the backing, hair, glasses, dark clothing and corners. No transparent backdrop, fog, see-through fabric, haze, halo, invented frame or note. Keep the full raw-HD detail and original aspect ratio. One independent asset."""


def require(condition, message):
    if not condition:
        raise batch.BatchError("invalid_low7_repair", message)


def load_original():
    scope = read_json(prepare.SCOPE)
    prepared = read_json(prepare.PREPARED)
    release = read_json(prepare.RELEASE)
    require(file_sha256(prepare.SCOPE) == prepared["scope_sha256"] == release["scope_sha256"], "Original scope binding changed")
    require(file_sha256(prepare.RELEASE) == prepared["input_release_sha256"], "Original input release changed")
    require(scope["source_count"] == 7, "Wrong LOW7 scope")
    return scope, prepared, release


def prompt_for(key, correction):
    return (
        "Use case: precise-object-edit. Image1 is the actual raw-HD mascot edit target. "
        "Image2 is the exact original game portrait and sole authority for visible source features. "
        "Image3 is the user mascot identity reference.\n"
        f"Actual observed correction: The rejected raw-HD output is {CORRECTIONS[key][0]}. {correction}\n"
        "Keep the source-visible clean-shaven state, hair, brows, gaze, serious expression and head direction. "
        "Do not trade one visible face defect for another.\n"
        + PROMPT_TAIL
    )


def prepare_repairs():
    scope, original_prepared, original_release = load_original()
    review_path = REVIEW
    review = read_json(review_path)
    review_sha = file_sha256(review_path)
    reference_sets = []
    preparation_entries = []
    prepared_entries = []
    for key, (expected_sha, correction) in CORRECTIONS.items():
        decisions = [row for row in review["entries"] if row["source_sha256"] == key]
        require(len(decisions) == 1, f"Missing bound rejection: {key}")
        decision = decisions[0]
        require(decision["decision"] == "rejected_visible_feature_correction_required", f"Not an actual rejection: {key}")
        require(decision["output_sha256"] == expected_sha and decision["attempt"] == "external-01", f"Rejected output changed: {key}")
        require(review["review_evidence_sha256"] == file_sha256(ROOT / review["review_evidence"]), f"Review evidence binding changed: {key}")
        evidence = read_json(ROOT / review["review_evidence"])
        evidence_entry = next(row for row in evidence["entries"] if row["source_sha256"] == key)
        require(evidence_entry["output_sha256"] == expected_sha, f"Review evidence output differs: {key}")
        original = next(row for row in original_prepared["entries"] if row["source_sha256"] == key)
        scope_entry = next(row for row in scope["entries"] if row["source_sha256"] == key)
        output = prepare.project_path(original["output"])
        result_path = output.with_name(f"{output.stem}.result.json")
        task_path = output.with_name(f"{output.stem}.task.json")
        result = read_json(result_path)
        require(file_sha256(output) == expected_sha == result["sha256"], f"Actual returned target differs: {key}")
        require(result["task_id"] == decision["task_id"] == read_json(task_path)["task_id"], f"Rejected task differs: {key}")
        target_reference = {
            "role": "previous generated fullsize edit target",
            "path": original["output"], "sha256": expected_sha,
            "url": f"https://github.com/XenoAmess/xenoamess_hoi4_dev/releases/download/{TAG}/{key}-01.png",
            "cache_name": f"{key}-01-{expected_sha}.png",
        }
        verified_target = prepare.download_public(target_reference)
        original_reference_set = next(row["ordered_inputs"] for row in original_release["reference_sets"] if row["source_sha256"] == key)
        references = [verified_target, *original_reference_set]
        require(len(references) == 3 and references[1]["role"] == "original source portrait" and references[2]["role"] == "user mascot reference", f"Repair input order changed: {key}")
        reference_sets.append({"source_sha256": key, "ordered_inputs": references})
        stem = f"{key}-02"
        prompt_path = EXPERIMENT / "repair-prompts" / f"{stem}.txt"
        prompt = prompt_for(key, correction)
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        if prompt_path.exists():
            require(prompt_path.read_bytes() == prompt.encode("utf-8"), f"Existing repair prompt differs: {key}")
        else:
            with prompt_path.open("xb") as stream:
                stream.write(prompt.encode("utf-8"))
        for suffix in (".png", ".request.json", ".task.json", ".result.json"):
            require(not (EXPERIMENT / "repair-outputs" / f"{stem}{suffix}").exists(), f"Existing repair dispatch needs reconciliation: {key}{suffix}")
        preparation = {
            "source_sha256": key, "attempt": "external-02", "previous_attempt": "external-01",
            "previous_task_id": result["task_id"], "rejected_output_sha256": expected_sha,
            "edit_target_image": original["output"], "edit_target_sha256": expected_sha,
            "review": review_path.relative_to(ROOT).as_posix(), "review_sha256": review_sha,
            "review_evidence": review["review_evidence"], "review_evidence_sha256": review["review_evidence_sha256"],
            "repair_input_mode": "low7-raw-hd-edit-v1",
            "correction": correction,
            "prompt_file": prompt_path.relative_to(ROOT).as_posix(), "prompt_sha256": file_sha256(prompt_path),
            "input_urls": [row["url"] for row in references],
            "ordered_input_sha256": [row["sha256"] for row in references],
        }
        preparation_entries.append(preparation)
        prepared_entries.append({
            **{field: original[field] for field in ("index", "source_sha256", "source_assets", "source_packages", "source_png", "converted_png_sha256")},
            "status": "prepared_not_dispatched", "attempt": "external-02",
            "model": "gpt-image-2.5-flare", "size": "3:4", "resolution": "2K", "quality": "high", "background": "opaque", "n": 1,
            "prompt_file": preparation["prompt_file"], "prompt_sha256": preparation["prompt_sha256"],
            "output": f"mod_nailong/experiments/evolink-low7-20261030/repair-outputs/{stem}.png",
            "image_urls": preparation["input_urls"], "ordered_input_sha256": preparation["ordered_input_sha256"],
            "inputs": [{field: row[field] for field in ("role", "path", "sha256", "url")} for row in references],
            "repair_preparation": "mod_nailong/experiments/evolink-low7-20261030/repair-preparation.json",
            "repair_preparation_sha256": None,
            "review": preparation["review"], "review_sha256": review_sha,
            "rejected_output_sha256": expected_sha, "edit_target_image": original["output"], "edit_target_sha256": expected_sha,
            "repair_input_mode": "low7-raw-hd-edit-v1", "builtin_retries_used": 9,
        })
    repair_release = copy.deepcopy(original_release)
    repair_release.update({
        "schema": "low7-repair-input-release-v1", "public_readback_recorded_at_utc": utc_now(),
        "reference_sets": reference_sets, "new_generation_tasks_created": 0,
    })
    repair_release["release"] = {
        "tag": TAG, "url": f"https://github.com/XenoAmess/xenoamess_hoi4_dev/releases/tag/{TAG}", "prerelease": True,
        "purpose": "Only two actual rejected raw-HD edit-reference inputs, not master archives or a mod release. Ordinary-Git original retention remains required when the separate Git hold permits.",
    }
    write_json(REPAIR_RELEASE, repair_release)
    write_json(REPAIR_PREPARATION, {
        "schema": "low7-visible-art-repair-preparation-v1", "machine_id": machine_id(), "created_at_utc": utc_now(),
        "scope_sha256": file_sha256(prepare.SCOPE), "input_release_sha256": file_sha256(REPAIR_RELEASE),
        "authorization_basis": "The user's scoped LOW7 EvoLink instruction and existing visible-art correction policy; no builtin service retry, count reset or refusal rerouting",
        "permission_documents_modified": False, "codex_tool_permission_changed": False,
        "builtin_retry_counters_modified": False, "entries": preparation_entries,
    })
    for entry in prepared_entries:
        entry["repair_preparation_sha256"] = file_sha256(REPAIR_PREPARATION)
    write_json(REPAIR_PREPARED, {
        "schema": "low7-visible-art-repair-prepared-v1", "machine_id": machine_id(), "prepared_at_utc": utc_now(),
        "scope_sha256": file_sha256(prepare.SCOPE), "input_release_sha256": file_sha256(REPAIR_RELEASE),
        "repair_preparation_sha256": file_sha256(REPAIR_PREPARATION), "source_count": 2, "entries": prepared_entries,
    })
    print(json.dumps({"status": "repair_prepared_not_dispatched", "sources": 2, "new_generation_tasks_created": 0}))


def load_context():
    scope, original_prepared, original_release = load_original()
    prepared, prepared_sha = batch.read_json_with_sha(REPAIR_PREPARED)
    release, release_sha = batch.read_json_with_sha(REPAIR_RELEASE)
    require(prepared["scope_sha256"] == release["scope_sha256"] == file_sha256(prepare.SCOPE), "Repair scope binding differs")
    require(prepared["input_release_sha256"] == release_sha, "Repair input release binding differs")
    require(prepared["repair_preparation_sha256"] == file_sha256(REPAIR_PREPARATION), "Repair preparation binding differs")
    return {
        "scope": scope, "prepared": prepared, "release": release,
        "prepared_sha256": prepared_sha, "scope_sha256": file_sha256(prepare.SCOPE), "input_release_sha256": release_sha,
        "release_assets": {row["source_sha256"]: row for row in original_release["assets"]},
    }


def repair_state(context, entry):
    key = entry["source_sha256"]
    require(re.fullmatch(r"[0-9a-f]{64}", key) is not None and key in CORRECTIONS, "Unauthorized repair source")
    scope_entry = next(row for row in context["scope"]["entries"] if row["source_sha256"] == key)
    require(scope_entry["index"] == entry["index"], "Repair source index differs")
    stem = f"{key}-02"
    prompt = batch.project_path(entry["prompt_file"], EXPERIMENT / "repair-prompts")
    output = batch.project_path(entry["output"], EXPERIMENT / "repair-outputs")
    require(prompt.stem == output.stem == stem, "Repair paths differ from external-02")
    (EXPERIMENT / "repair-logs").mkdir(parents=True, exist_ok=True)
    (EXPERIMENT / "repair-executions").mkdir(parents=True, exist_ok=True)
    return {
        "entry": entry, "scope_entry": scope_entry, "index": entry["index"], "key": key, "stem": stem,
        "prompt_path": prompt, "output": output,
        "request": output.with_name(f"{output.stem}.request.json"), "task": output.with_name(f"{output.stem}.task.json"),
        "result": output.with_name(f"{output.stem}.result.json"), "client_prompt": output.with_name(f"{output.stem}.prompt.txt"),
        "dry_run_log": EXPERIMENT / "repair-logs" / f"{stem}-dryrun.log", "actual_log": EXPERIMENT / "repair-logs" / f"{stem}.log",
        "execution": EXPERIMENT / "repair-executions" / f"{stem}.json",
        "history_logs": (), "history_executions": (),
        "input_validation": repair_inputs, "frozen_validator": validate_repair,
        "repair_preparation": "mod_nailong/experiments/evolink-low7-20261030/repair-preparation.json",
        "repair_preparation_sha256": entry["repair_preparation_sha256"],
        "review": entry["review"], "review_sha256": entry["review_sha256"],
        "rejected_output_sha256": entry["rejected_output_sha256"], "repair_input_mode": "low7-raw-hd-edit-v1",
        "edit_target_image": entry["edit_target_image"], "edit_target_sha256": entry["edit_target_sha256"],
    }


def repair_inputs(context, state):
    rows = next(row["ordered_inputs"] for row in context["release"]["reference_sets"] if row["source_sha256"] == state["key"])
    require(len(rows) == 3 and all(row["public_unauthenticated_sha256_verified"] is True for row in rows), "Repair public input proof missing")
    require(rows[0]["sha256"] == state["entry"]["rejected_output_sha256"], "Repair target is not the rejected output")
    return [row["sha256"] for row in rows], [row["url"] for row in rows]


def validate_repair(context, state):
    entry = state["entry"]
    require(file_sha256(REPAIR_PREPARATION) == entry["repair_preparation_sha256"], "Repair preparation bytes changed")
    repair = next(row for row in read_json(REPAIR_PREPARATION)["entries"] if row["source_sha256"] == state["key"])
    require(repair["attempt"] == entry["attempt"] == "external-02", "Only external-02 visible-art repair is allowed")
    for field, expected in (("model", "gpt-image-2.5-flare"), ("size", "3:4"), ("resolution", "2K"), ("quality", "high"), ("background", "opaque"), ("n", 1)):
        require(entry[field] == expected, f"Repair route differs: {field}")
    require(repair["rejected_output_sha256"] == entry["rejected_output_sha256"] == CORRECTIONS[state["key"]][0], "Rejected target binding changed")
    require(file_sha256(batch.project_path(entry["edit_target_image"])) == entry["edit_target_sha256"], "Rejected raw-HD target bytes changed")
    require(file_sha256(batch.project_path(entry["review"])) == entry["review_sha256"], "Rejection review bytes changed")
    require(file_sha256(state["prompt_path"]) == entry["prompt_sha256"] == repair["prompt_sha256"], "Repair prompt SHA differs")
    for item in entry["inputs"]:
        require(file_sha256(batch.project_path(item["path"])) == item["sha256"], "Repair ordered local input changed")
    require(read_json(ROOT / "mod_nailong/data/image-retry-queue.json")["sources"][state["key"]]["retries_used"] == 9, "Builtin retry counter changed")


def collect(context, indices=None):
    selected = []
    for entry in context["prepared"]["entries"]:
        if indices and entry["index"] not in indices:
            continue
        state = repair_state(context, entry)
        action, reason = batch.artifact_action(state, include_dry_run=True)
        if action == "stop":
            raise batch.BatchError(reason, f"Existing repair artifacts require reconciliation: {state['key']}")
        if action == "skip":
            continue
        selected.append(state)
    return selected


def main():
    parser = argparse.ArgumentParser(description="Prepare or serially run the two exact visible-art LOW7 repairs; no automatic repost.")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--limit", type=int, choices=(1, 2), default=2)
    parser.add_argument("--index", action="append", type=int)
    args = parser.parse_args()
    if args.prepare:
        require(not args.collect_only, "--prepare cannot be combined with --collect-only")
        prepare_repairs()
        return 0
    context = load_context()
    selected = collect(context, set(args.index) if args.index else None)
    if args.collect_only:
        print(json.dumps({"collect_only": True, "candidates": [{"index": row["index"], "source_sha256": row["key"], "attempt": "external-02"} for row in selected], "new_generation_tasks_created": 0}))
        return 0
    completed = []
    for state in selected[:args.limit]:
        outcome, detail = batch.dispatch_one(context, state)
        completed.append({"source_sha256": state["key"], "status": outcome, "output_sha256": detail})
    print(json.dumps({"completed": completed, "stopped": len(completed) < min(len(selected), args.limit)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
