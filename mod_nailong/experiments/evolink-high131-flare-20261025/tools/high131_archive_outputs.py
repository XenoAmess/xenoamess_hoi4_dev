import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.high131_io import write_json
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"
OUTPUTS = EXPERIMENT / "outputs"
MASTER_DIR = ROOT / "mod_nailong/assets/generated_fullsize"
MINIMUM_FREE_BYTES = 60 * 1024 ** 3


def image_info(path):
    with Image.open(path) as image:
        result = {"size": list(image.size), "mode": image.mode}
        image.verify()
    return result


def archive_png(path, expected_sha):
    if file_sha256(path) != expected_sha:
        raise RuntimeError(f"Output SHA differs before archive: {path}")
    target = MASTER_DIR / f"{expected_sha}.png"
    if target.is_symlink():
        raise RuntimeError(f"Refusing symlink master: {target}")
    if not target.exists():
        free = shutil.disk_usage("C:/").free
        if free < path.stat().st_size + MINIMUM_FREE_BYTES:
            raise RuntimeError(f"Insufficient free space for {path}: {free}")
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(path, target)
    if not target.is_file() or file_sha256(target) != expected_sha:
        raise RuntimeError(f"Archived master differs from original: {target}")
    return {
        "generated_fullsize_image": target.relative_to(ROOT).as_posix(),
        "generated_fullsize_sha256": expected_sha,
        "bytes": target.stat().st_size,
        **image_info(target),
    }


def main():
    scope = read_json(EXPERIMENT / "scope.json")
    sources = {row["source_sha256"]: row for row in scope["entries"]}
    entries = []
    raw_by_path = {}
    for result_path in sorted(OUTPUTS.glob("*.result.json")):
        stem = result_path.name[:-len(".result.json")]
        match = re.fullmatch(r"([0-9a-f]{64})-(\d+)(?:-.+)?", stem)
        if not match:
            raise RuntimeError(f"Unexpected result stem: {result_path}")
        key, number = match.group(1), int(match.group(2))
        source = sources[key]
        output = result_path.with_name(stem + ".png")
        result = read_json(result_path)
        task = read_json(result_path.with_name(stem + ".task.json"))
        if result["task_id"] != task["task_id"]:
            raise RuntimeError(f"Task binding differs: {result_path}")
        prompt_path = result_path.with_name(stem + ".prompt.txt")
        request_path = result_path.with_name(stem + ".request.json")
        request = read_json(request_path)
        if request["prompt"] != prompt_path.read_text(encoding="utf-8"):
            raise RuntimeError(f"Actual request prompt differs: {request_path}")
        record = {
            "index": source["index"],
            "source_sha256": key,
            "source_assets": source["source_assets"],
            "attempt": f"external-{number}",
            "output_stem": stem,
            "output": output.relative_to(ROOT).as_posix(),
            "output_sha256": result["sha256"],
            "task_id": result["task_id"],
            "task": result_path.with_name(stem + ".task.json").relative_to(ROOT).as_posix(),
            "task_sha256": file_sha256(result_path.with_name(stem + ".task.json")),
            "prompt": prompt_path.relative_to(ROOT).as_posix(),
            "prompt_sha256": file_sha256(prompt_path),
            "request": request_path.relative_to(ROOT).as_posix(),
            "request_sha256": file_sha256(request_path),
            "result": result_path.relative_to(ROOT).as_posix(),
            "result_sha256": file_sha256(result_path),
            "downloaded_at_utc": result["downloaded_at_utc"],
            **archive_png(output, result["sha256"]),
        }
        entries.append(record)
        raw_by_path[output.resolve()] = record

    for review_path in sorted(EXPERIMENT.glob("review-*.json")):
        if review_path.name.endswith("-evidence.json"):
            continue
        review = read_json(review_path)
        for review_entry in review.get("entries", []):
            attempt = review_entry["attempt"]
            if not attempt.endswith("-alpha-repaired-bilinear"):
                continue
            method = review_entry.get("alpha_repair_method")
            if method is None:
                if "source-alpha-resize-bilinear-rgb-unchanged-v1" not in review["model"]:
                    raise RuntimeError(f"Unexpected alpha method: {review_path}")
            elif method != "source-alpha-resize-bilinear-rgb-unchanged-v1":
                raise RuntimeError(f"Unexpected alpha method: {review_path}")
            key = review_entry["source_sha256"]
            source = sources[key]
            output = (ROOT / review_entry["output"]).resolve()
            output.relative_to(OUTPUTS.resolve())
            parent = output.with_name(output.stem.removesuffix("-alpha-repaired-bilinear") + ".png")
            parent_record = raw_by_path[parent.resolve()]
            if review_entry["parent_output_sha256"] != parent_record["output_sha256"]:
                raise RuntimeError(f"Alpha parent differs: {review_path}")
            if review_entry.get("parent_task_id", parent_record["task_id"]) != parent_record["task_id"]:
                raise RuntimeError(f"Alpha parent task differs: {review_path}")
            if review_entry.get("rgb_unchanged") is not True or review_entry.get("alpha_matches_resized_source") is not True:
                raise RuntimeError(f"Alpha review lacks technical validation: {review_path}")
            source_path = ROOT / source["source_png"]
            if file_sha256(source_path) != source["converted_png_sha256"]:
                raise RuntimeError(f"Source changed: {source_path}")
            with Image.open(source_path) as source_image, Image.open(parent) as parent_image, Image.open(output) as derived_image:
                resized_alpha = source_image.convert("RGBA").getchannel("A").resize(parent_image.size, Image.Resampling.BILINEAR)
                if derived_image.convert("RGB").tobytes() != parent_image.convert("RGB").tobytes():
                    raise RuntimeError(f"Alpha derivative changed RGB: {output}")
                if derived_image.getchannel("A").tobytes() != resized_alpha.tobytes():
                    raise RuntimeError(f"Alpha derivative differs from resized source: {output}")
            alpha_sha = hashlib.sha256(resized_alpha.tobytes()).hexdigest()
            receipt_record = None
            if review.get("alpha_repair_receipt"):
                receipt_path = (ROOT / review["alpha_repair_receipt"]).resolve()
                receipt_path.relative_to(EXPERIMENT.resolve())
                if file_sha256(receipt_path) != review["alpha_repair_receipt_sha256"]:
                    raise RuntimeError(f"Alpha repair receipt changed: {receipt_path}")
                receipt = read_json(receipt_path)
                if receipt.get("status", "completed") != "completed":
                    raise RuntimeError(f"Alpha repair is not complete: {receipt_path}")
                proof = receipt.get("result", receipt)
                if not isinstance(proof, dict):
                    raise RuntimeError(f"Alpha repair proof is missing: {receipt_path}")
                if proof["base_sha256"] != parent_record["output_sha256"] or proof["output_sha256"] != review_entry["output_sha256"]:
                    raise RuntimeError(f"Alpha receipt binding differs: {receipt_path}")
                if proof["resized_alpha_sha256"] != alpha_sha or proof["rgb_unchanged"] is not True or proof["alpha_matches_resized_source"] is not True:
                    raise RuntimeError(f"Alpha receipt does not match retained pixels: {receipt_path}")
                receipt_record = {
                    "path": receipt_path.relative_to(ROOT).as_posix(),
                    "sha256": review["alpha_repair_receipt_sha256"],
                }
            entries.append({
                "index": source["index"],
                "source_sha256": key,
                "source_assets": source["source_assets"],
                "attempt": attempt,
                "output_stem": output.stem,
                "output": output.relative_to(ROOT).as_posix(),
                "output_sha256": review_entry["output_sha256"],
                "parent_task_id": parent_record["task_id"],
                "parent_output": parent_record["output"],
                "parent_output_sha256": parent_record["output_sha256"],
                "prompt": parent_record["prompt"],
                "prompt_sha256": parent_record["prompt_sha256"],
                "review": review_path.relative_to(ROOT).as_posix(),
                "review_sha256": file_sha256(review_path),
                "reviewed_at_utc": review["reviewed_at_utc"],
                "alpha_repair_receipt": receipt_record,
                "alpha_validation_at_archive": "Recomputed RGB and resized source alpha from retained source, parent and derivative; not claimed as a replacement original command receipt",
                "resized_alpha_sha256": alpha_sha,
                "rgb_unchanged": True,
                "alpha_matches_resized_source": True,
                **archive_png(output, review_entry["output_sha256"]),
            })

    entries.sort(key=lambda row: (row["index"], row["attempt"], row["output_stem"]))
    target = EXPERIMENT / "output-masters.json"
    existing = read_json(target) if target.exists() else {}
    body = {
        "schema": "naiwa-evolink-high131-output-masters-v1",
        "machine_id": machine_id(),
        "created_at_utc": existing.get("created_at_utc", utc_now()),
        "observed_at_utc": utc_now(),
        "scope_sha256": file_sha256(EXPERIMENT / "scope.json"),
        "counts": {
            "actual_returned_outputs": len(entries),
            "alpha_derivatives": sum(row["attempt"].endswith("-alpha-repaired-bilinear") for row in entries),
            "unique_output_sha256": len({row["output_sha256"] for row in entries}),
            "original_png_bytes": sum(row["bytes"] for row in entries),
        },
        "archive_scope": "Every retained actual return, including rejected, pending and intermediate PNGs, plus validated alpha derivatives. Hardlink or existing byte-identical file only; no re-encoding, source-original-as-generated substitution or canonical metadata writes. Archival is not art approval or production import.",
        "entries": entries,
    }
    write_json(target, body)
    print(json.dumps({"target": target.relative_to(ROOT).as_posix(), **body["counts"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
