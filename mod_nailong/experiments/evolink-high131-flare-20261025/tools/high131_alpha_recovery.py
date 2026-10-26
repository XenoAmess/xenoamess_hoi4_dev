import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.high131_run_batch import relative_path
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"
METHOD = "source-alpha-resize-bilinear-rgb-unchanged-v1"


def derive(index, parent_review=None):
    scope = read_json(EXPERIMENT / "scope.json")
    matches = [row for row in scope["entries"] if row["index"] == index]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one scope entry for index {index}")
    source = matches[0]
    key = source["source_sha256"]
    review_name = parent_review or f"review-recovery-{index}-agent"
    review_path = EXPERIMENT / f"{review_name}.json"
    review = read_json(review_path)
    if file_sha256(ROOT / review["review_sheet"]) != review["review_sheet_sha256"]:
        raise RuntimeError("Parent review sheet binding mismatch")
    if file_sha256(ROOT / review["review_evidence"]) != review["review_evidence_sha256"]:
        raise RuntimeError("Parent review evidence binding mismatch")
    entries = [row for row in review["entries"] if row["source_sha256"] == key]
    if len(entries) != 1:
        raise RuntimeError("Parent review must contain one decision for this source")
    decision = entries[0]
    if decision["decision"] != "approved_for_alpha_repair" or decision.get("rgb_art_approved") is not True or decision.get("source_alpha_repair_performed") is not False:
        raise RuntimeError("Parent review does not authorize a pending source-alpha repair")
    attempt = decision["attempt"]
    base = ROOT / decision["output"]
    expected_base = EXPERIMENT / "outputs" / f"{key}-{attempt.removeprefix('external-')}.png"
    if base != expected_base or base.stem.endswith("-alpha-repaired-bilinear"):
        raise RuntimeError("Alpha parent must be an ordinary experiment output")
    if file_sha256(base) != decision["output_sha256"]:
        raise RuntimeError("Parent output SHA mismatch")
    result = read_json(base.with_name(f"{base.stem}.result.json"))
    task = read_json(base.with_name(f"{base.stem}.task.json"))
    prompt_path = base.with_name(f"{base.stem}.prompt.txt")
    request = read_json(base.with_name(f"{base.stem}.request.json"))
    if result["sha256"] != decision["output_sha256"] or result["task_id"] != decision["task_id"] or task["task_id"] != decision["task_id"]:
        raise RuntimeError("Parent result/task binding mismatch")
    if file_sha256(prompt_path) != decision["prompt_sha256"] or request["prompt"] != prompt_path.read_text(encoding="utf-8"):
        raise RuntimeError("Parent prompt/request binding mismatch")
    source_path = ROOT / source["source_png"]
    if file_sha256(source_path) != source["converted_png_sha256"]:
        raise RuntimeError("Scope source SHA mismatch")
    output = base.with_name(f"{base.stem}-alpha-repaired-bilinear.png")
    derived_attempt = f"{attempt}-alpha-repaired-bilinear"
    final_name = f"{review_name.removesuffix('-agent')}-alpha-final-agent"
    final_review = EXPERIMENT / f"{final_name}.json"
    sheet = EXPERIMENT / f"{final_name}.png"
    evidence = EXPERIMENT / f"{final_name}-evidence.json"
    if final_review.exists():
        raise RuntimeError(f"Final review already exists; do not replace it: {final_review}")
    command = [
        sys.executable,
        str(ROOT / "mod_nailong/tools/repair_outer_alpha.py"),
        "--source", str(source_path),
        "--base", str(base),
        "--output", str(output),
    ]
    receipt_path = EXPERIMENT / f"{review_name.removesuffix('-agent')}-alpha-repair-receipt.json"
    if receipt_path.exists():
        receipt = read_json(receipt_path)
        for field, expected in (("index", index), ("source_key_sha256", key), ("attempt", attempt), ("parent_review", relative_path(review_path)), ("parent_review_sha256", file_sha256(review_path)), ("parent_output_sha256", decision["output_sha256"]), ("status", "completed"), ("new_image_generation_calls", 0), ("command", command), ("exit_code", 0), ("output", relative_path(output))):
            if receipt.get(field) != expected:
                raise RuntimeError(f"Existing alpha receipt binding mismatch: {field}")
    else:
        for path in (output, sheet, evidence):
            if path.exists():
                raise RuntimeError(f"Incomplete alpha derivative requires reconciliation: {path}")
        started = utc_now()
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
        proof = json.loads(completed.stdout) if completed.returncode == 0 else None
        receipt = {
            "schema": "naiwa-evolink-high131-alpha-repair-receipt-v1",
            "machine_id": machine_id(),
            "index": index,
            "source_key_sha256": key,
            "attempt": attempt,
            "parent_review": relative_path(review_path),
            "parent_review_sha256": file_sha256(review_path),
            "parent_output_sha256": decision["output_sha256"],
            "status": "completed" if completed.returncode == 0 else "failed",
            "prepared_at_utc": started,
            "new_image_generation_calls": 0,
            "command": command,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "finished_at_utc": utc_now(),
            "result": proof,
            "output": relative_path(output),
            "output_sha256": file_sha256(output) if output.is_file() else None,
        }
        write_json(receipt_path, receipt)
        if completed.returncode != 0:
            raise RuntimeError(f"Alpha repair failed; retained receipt: {receipt_path}")
    proof = receipt["result"]
    if proof["method"] != METHOD:
        raise RuntimeError("Unexpected alpha method")
    with Image.open(source_path) as source_image, Image.open(base) as base_image, Image.open(output) as derived_image:
        source_alpha = source_image.convert("RGBA").getchannel("A")
        alpha = source_alpha.resize(base_image.size, Image.Resampling.BILINEAR)
        rgb_unchanged = base_image.convert("RGB").tobytes() == derived_image.convert("RGB").tobytes()
        alpha_matches = derived_image.getchannel("A").tobytes() == alpha.tobytes()
        source_size = list(source_image.size)
        base_size = list(base_image.size)
        source_mode = source_image.mode
        base_mode = base_image.mode
        output_mode = derived_image.mode
        source_corners = [source_alpha.getpixel(point) for point in ((0, 0), (source_alpha.width - 1, 0), (0, source_alpha.height - 1), (source_alpha.width - 1, source_alpha.height - 1))]
        alpha_corners = [alpha.getpixel(point) for point in ((0, 0), (alpha.width - 1, 0), (0, alpha.height - 1), (alpha.width - 1, alpha.height - 1))]
        output_corners = [derived_image.getchannel("A").getpixel(point) for point in ((0, 0), (derived_image.width - 1, 0), (0, derived_image.height - 1), (derived_image.width - 1, derived_image.height - 1))]
    expected_proof = {
        "source_sha256": file_sha256(source_path),
        "base_sha256": decision["output_sha256"],
        "output_sha256": file_sha256(output),
        "source_size": source_size,
        "base_size": base_size,
        "source_mode": source_mode,
        "base_mode": base_mode,
        "output_mode": output_mode,
        "source_corner_alpha_tl_tr_bl_br": source_corners,
        "resized_corner_alpha_tl_tr_bl_br": alpha_corners,
        "output_corner_alpha_tl_tr_bl_br": output_corners,
        "resized_alpha_sha256": hashlib.sha256(alpha.tobytes()).hexdigest(),
        "rgb_unchanged": True,
        "alpha_matches_resized_source": True,
    }
    if not rgb_unchanged or not alpha_matches or output_mode != "RGBA":
        raise RuntimeError("Alpha derivative pixel validation failed")
    for field, expected in expected_proof.items():
        if proof.get(field) != expected:
            raise RuntimeError(f"Alpha receipt result mismatch: {field}")
    if not sheet.exists() and not evidence.exists():
        sheet_command = [sys.executable, str(ROOT / "runtime/high131_review_sheet.py"), final_name, relative_path(output)]
        log_path = EXPERIMENT / "logs" / f"{final_name}.log"
        with log_path.open("x", encoding="utf-8") as log:
            completed = subprocess.run(sheet_command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"Alpha review-sheet creation failed; see {log_path}")
    if not sheet.is_file() or not evidence.is_file():
        raise RuntimeError("Incomplete sheet/evidence pair requires reconciliation")
    evidence_body = read_json(evidence)
    if evidence_body["review_sheet_sha256"] != file_sha256(sheet):
        raise RuntimeError("Evidence sheet SHA mismatch")
    evidence_entry = evidence_body["entries"][0]
    for field, expected in (("source_sha256", key), ("generation_output_sha256", decision["output_sha256"]), ("output", relative_path(output)), ("output_sha256", proof["output_sha256"]), ("task_id", decision["task_id"]), ("prompt_sha256", decision["prompt_sha256"])):
        if evidence_entry.get(field) != expected:
            raise RuntimeError(f"Alpha evidence binding mismatch: {field}")
    return {"index": index, "source_sha256": key, "attempt": derived_attempt, "output": relative_path(output), "output_sha256": proof["output_sha256"], "receipt": relative_path(receipt_path), "sheet": relative_path(sheet), "evidence": relative_path(evidence), "review_decision": "pending_actual_final_visual_review"}


def main():
    parser = argparse.ArgumentParser(description="Prepare SHA-bound alpha derivatives and technical review sheets, without approving them.")
    parser.add_argument("--index", action="append", required=True, type=int)
    parser.add_argument("--parent-review", help="Review basename without .json; requires exactly one --index")
    args = parser.parse_args()
    if args.parent_review and len(args.index) != 1:
        raise RuntimeError("--parent-review requires exactly one --index")
    if args.parent_review and (Path(args.parent_review).name != args.parent_review or not args.parent_review.startswith("review-")):
        raise RuntimeError("--parent-review must be a review basename in the experiment root")
    print(json.dumps([derive(index, args.parent_review) for index in args.index], ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
