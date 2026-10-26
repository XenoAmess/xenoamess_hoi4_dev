import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"
METHOD = "source-alpha-resize-bilinear-rgb-unchanged-v1"
DECISIONS = {"approved_for_production", "approved_for_alpha_repair", "rejected_for_production"}


def relative_path(path):
    return path.relative_to(ROOT).as_posix()


def project_path(value):
    if not isinstance(value, str) or not value:
        raise RuntimeError("Evidence paths must be nonempty repository-relative strings")
    path = (ROOT / value).resolve()
    path.relative_to(ROOT.resolve())
    return path


def main():
    parser = argparse.ArgumentParser(description="Record actual visual observations against verified HIGH131 evidence; never imports production.")
    parser.add_argument("--draft", required=True, type=Path)
    args = parser.parse_args()
    draft = read_json(args.draft)
    if draft.get("schema") != "naiwa-evolink-high131-review-observations-v1":
        raise RuntimeError("Unexpected observation draft schema")
    evidence_path = project_path(draft["evidence"])
    evidence_path.relative_to(EXPERIMENT.resolve())
    evidence = read_json(evidence_path)
    if evidence["schema"] != "naiwa-evolink-high131-review-evidence-v1":
        raise RuntimeError("Unexpected evidence schema")
    sheet = project_path(evidence["review_sheet"])
    if file_sha256(sheet) != evidence["review_sheet_sha256"]:
        raise RuntimeError("Evidence sheet SHA mismatch")
    scope = read_json(EXPERIMENT / "scope.json")
    scope_matches = [row for row in scope["entries"] if row["index"] == draft["index"]]
    if len(scope_matches) != 1:
        raise RuntimeError("Expected one source at draft index")
    source = scope_matches[0]
    key = source["source_sha256"]
    matches = [row for row in evidence["entries"] if row["source_sha256"] == key and row["index"] == draft["evidence_entry_index"]]
    if len(matches) != 1:
        raise RuntimeError("Expected one exact source/row in evidence")
    proof = matches[0]
    if proof["source_png"] != source["source_png"] or file_sha256(project_path(proof["source_png"])) != proof["source_png_sha256"]:
        raise RuntimeError("Source identity/binding mismatch")
    for field in ("generation_output", "output", "task", "prompt", "request", "result"):
        project_path(proof[field]).relative_to((EXPERIMENT / "outputs").resolve())
    for field, sha_field in (("generation_output", "generation_output_sha256"), ("output", "output_sha256"), ("task", "task_sha256"), ("prompt", "prompt_sha256"), ("request", "request_sha256"), ("result", "result_sha256")):
        if file_sha256(project_path(proof[field])) != proof[sha_field]:
            raise RuntimeError(f"Evidence binding mismatch: {field}")
    result = read_json(project_path(proof["result"]))
    task = read_json(project_path(proof["task"]))
    prompt = project_path(proof["prompt"]).read_text(encoding="utf-8")
    request = read_json(project_path(proof["request"]))
    if result["sha256"] != proof["generation_output_sha256"] or result["task_id"] != proof["task_id"] or task["task_id"] != proof["task_id"] or request["prompt"] != prompt:
        raise RuntimeError("Generation result/task/prompt binding mismatch")
    if file_sha256(project_path(proof["generation_output"])) != result["sha256"]:
        raise RuntimeError("Generation output differs from result")
    with Image.open(project_path(proof["output"])) as opened:
        size = list(opened.size)
        mode = opened.mode
        alpha_extrema = list(opened.getchannel("A").getextrema()) if "A" in opened.getbands() else None
    if size != proof["output_info"]["size"] or mode != proof["output_info"]["mode"] or alpha_extrema != proof["output_info"]["alpha_extrema"]:
        raise RuntimeError("Evidence image metadata mismatch")
    observations = draft["entry"]
    if observations["decision"] not in DECISIONS:
        raise RuntimeError("Unsupported visual decision")
    if observations.get("rgb_art_approved") not in (True, False):
        raise RuntimeError("rgb_art_approved must be an explicit boolean")
    for policy in ("hair_features", "collar_fit"):
        if observations[policy].get("policy") not in ("hair-features-v1", "collar-fit-v1"):
            raise RuntimeError(f"Missing policy: {policy}")
        if observations[policy].get("status") not in ("approved", "rejected", "pass", "fail"):
            raise RuntimeError(f"Missing policy status: {policy}")
    attempt = observations["attempt"]
    base_attempt = re.fullmatch(r"external-\d{2}", attempt)
    derived_attempt = re.fullmatch(r"(external-\d{2})-alpha-repaired-bilinear", attempt)
    if base_attempt:
        expected = EXPERIMENT / "outputs" / f"{key}-{attempt.removeprefix('external-')}.png"
        if project_path(proof["output"]) != expected or project_path(proof["generation_output"]) != expected:
            raise RuntimeError("Ordinary attempt/evidence path mismatch")
        if observations["decision"] == "approved_for_production" and mode != "RGBA":
            raise RuntimeError("An RGB working master cannot bypass the final alpha review")
        if observations["decision"] == "approved_for_alpha_repair" and (mode != "RGB" or not observations["rgb_art_approved"]):
            raise RuntimeError("Only an art-approved RGB working master is eligible for alpha derivation")
        if observations["decision"] == "rejected_for_production" and (observations["rgb_art_approved"] or not observations.get("remaining_reasons")):
            raise RuntimeError("A rejection requires concrete visible reasons and rgb_art_approved=false")
    elif derived_attempt:
        if observations["decision"] != "approved_for_production" or not observations["rgb_art_approved"] or mode != "RGBA":
            raise RuntimeError("This recorder requires full final approval for a derived RGBA candidate")
        if project_path(proof["output"]) != EXPERIMENT / "outputs" / f"{key}-{derived_attempt.group(1).removeprefix('external-')}-alpha-repaired-bilinear.png":
            raise RuntimeError("Derived attempt/evidence path mismatch")
    else:
        raise RuntimeError("Unsupported attempt form")
    if not isinstance(draft.get("reviewer"), str) or len(draft["reviewer"]) < 50:
        raise RuntimeError("Record the actual viewing and verification performed")
    for field in ("positive_observation", "alpha_decision", "visible_limitations"):
        if not observations.get(field):
            raise RuntimeError(f"Missing visual observation: {field}")
    target = EXPERIMENT / draft["target"]
    if target.parent != EXPERIMENT or not target.name.startswith("review-") or target.name.endswith("-evidence.json"):
        raise RuntimeError("Review target must be a new review JSON in the experiment root")
    if target.exists():
        raise RuntimeError(f"Refusing to overwrite review: {target}")
    entry = {
        "source_sha256": key,
        "attempt": attempt,
        "task_id": proof["task_id"],
        "prompt_sha256": proof["prompt_sha256"],
        "output": proof["output"],
        "output_sha256": proof["output_sha256"],
        "size": size,
        "mode": mode,
        "source_alpha_extrema": proof["source_info"]["alpha_extrema"],
        "returned_alpha_extrema": alpha_extrema,
        **observations,
        "source_alpha_repair_performed": False,
        "production_imported": False,
        "production_import_pending": observations["decision"] == "approved_for_production",
        "raw_output_retained": True,
    }
    body = {
        "schema": "naiwa-evolink-experiment-manual-review-v1",
        "machine_id": machine_id(),
        "model": "gpt-image-2.5-flare",
        "reviewed_at_utc": utc_now(),
        "reviewer": draft["reviewer"],
        "review_evidence": relative_path(evidence_path),
        "review_evidence_sha256": file_sha256(evidence_path),
        "review_sheet": relative_path(sheet),
        "review_sheet_sha256": file_sha256(sheet),
        "entries": [entry],
        "production_imported": False,
        "production_import_pending": entry["production_import_pending"],
    }
    if derived_attempt:
        receipt_path = project_path(draft["alpha_repair_receipt"])
        receipt_path.relative_to(EXPERIMENT.resolve())
        receipt = read_json(receipt_path)
        if receipt["index"] != draft["index"] or receipt["source_key_sha256"] != key or receipt["status"] != "completed" or receipt["new_image_generation_calls"] != 0:
            raise RuntimeError("Alpha receipt identity/completion mismatch")
        parent_review_path = project_path(receipt["parent_review"])
        parent_review = read_json(parent_review_path)
        parent_decisions = [row for row in parent_review["entries"] if row["source_sha256"] == key and row["attempt"] == derived_attempt.group(1)]
        if len(parent_decisions) != 1 or parent_decisions[0]["decision"] != "approved_for_alpha_repair" or not parent_decisions[0]["rgb_art_approved"]:
            raise RuntimeError("Derived candidate lacks its exact art-approved parent")
        parent_decision = parent_decisions[0]
        if file_sha256(parent_review_path) != receipt["parent_review_sha256"] or receipt["parent_output_sha256"] != parent_decision["output_sha256"] or parent_decision["output_sha256"] != proof["generation_output_sha256"]:
            raise RuntimeError("Parent review/derivation binding mismatch")
        repair = receipt["result"]
        if repair["method"] != METHOD or repair["base_sha256"] != proof["generation_output_sha256"] or repair["output_sha256"] != proof["output_sha256"]:
            raise RuntimeError("Alpha receipt proof mismatch")
        with Image.open(project_path(proof["source_png"])) as source_image, Image.open(project_path(proof["generation_output"])) as parent_image, Image.open(project_path(proof["output"])) as derived_image:
            source_alpha = source_image.convert("RGBA").getchannel("A")
            resized_alpha = source_alpha.resize(parent_image.size, Image.Resampling.BILINEAR)
            if parent_image.convert("RGB").tobytes() != derived_image.convert("RGB").tobytes() or derived_image.getchannel("A").tobytes() != resized_alpha.tobytes():
                raise RuntimeError("Derived RGB/alpha pixel validation failed")
            corners = lambda channel: [channel.getpixel(point) for point in ((0, 0), (channel.width - 1, 0), (0, channel.height - 1), (channel.width - 1, channel.height - 1))]
            expected_fields = {
                "source_sha256": proof["source_png_sha256"],
                "source_corner_alpha_tl_tr_bl_br": corners(source_alpha),
                "resized_corner_alpha_tl_tr_bl_br": corners(resized_alpha),
                "output_corner_alpha_tl_tr_bl_br": corners(derived_image.getchannel("A")),
                "resized_alpha_sha256": hashlib.sha256(resized_alpha.tobytes()).hexdigest(),
                "rgb_unchanged": True,
                "alpha_matches_resized_source": True,
            }
        for field, expected in expected_fields.items():
            if repair.get(field) != expected:
                raise RuntimeError(f"Alpha receipt validation mismatch: {field}")
        entry.update({
            "parent_task_id": proof["task_id"],
            "parent_output": proof["generation_output"],
            "parent_output_sha256": proof["generation_output_sha256"],
            "parent_review": relative_path(parent_review_path),
            "parent_review_sha256": receipt["parent_review_sha256"],
            "source_alpha_repair_performed": True,
            "alpha_repair_method": METHOD,
            **{field: value for field, value in expected_fields.items() if field != "source_sha256"},
        })
        body["model"] = f"{parent_review['model']} + {METHOD}"
        body["alpha_repair_receipt"] = relative_path(receipt_path)
        body["alpha_repair_receipt_sha256"] = file_sha256(receipt_path)
    write_json(target, body)
    print(json.dumps({"review": relative_path(target), "index": draft["index"], "source_sha256": key, "attempt": attempt, "output_sha256": proof["output_sha256"], "decision": observations["decision"], "production_imported": False}, ensure_ascii=True))


if __name__ == "__main__":
    main()
