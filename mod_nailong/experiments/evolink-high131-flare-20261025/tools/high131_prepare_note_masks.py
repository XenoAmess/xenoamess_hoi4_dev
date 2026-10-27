import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import high131_hd_proof as hd_proof
from runtime.high131_io import write_json
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"
MASTER_DIR = ROOT / "mod_nailong/assets/generated_fullsize"
MASK_RECTANGLES = {
    (65, 1): [[1180, 950, 1600, 1055], [1170, 1065, 1610, 1160]],
    (67, 1): [[1160, 940, 1770, 1050], [1150, 1055, 1770, 1160], [1740, 1140, 1940, 1390]],
    (67, 2): [[1370, 990, 1510, 1090], [1810, 1120, 1950, 1430]],
    (67, 3): [[1370, 980, 1730, 1110], [1790, 1100, 1960, 1490]],
    (40, 1): [[1080, 1025, 1410, 1095], [1080, 1105, 1410, 1170]],
    (40, 2): [[1080, 1100, 1410, 1190]],
    (52, 1): [[1140, 1070, 1470, 1145], [1140, 1150, 1470, 1225]],
    (52, 2): [[1140, 1070, 1470, 1145]],
    (52, 3): [[1140, 1070, 1560, 1145]],
    (53, 1): [[1200, 1050, 1620, 1180]],
    (54, 1): [[1100, 1040, 1600, 1125], [1100, 1135, 1600, 1210]],
}


def main():
    parser = argparse.ArgumentParser(description="Prepare an inpainting mask and visual review overlay for one rejected note; no target pixels are replaced.")
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--revision", type=int, default=1)
    args = parser.parse_args()
    revision_suffix = hd_proof.mask_revision_suffix(args.revision)
    if (args.index, args.revision) not in MASK_RECTANGLES:
        raise RuntimeError("Only the actually reviewed note-mask candidates and revisions are eligible")
    scope = {row["index"]: row for row in read_json(EXPERIMENT / "scope.json")["entries"]}
    progress = {row["source_sha256"]: row for row in read_json(EXPERIMENT / "progress.json")["entries"]}
    source = scope[args.index]
    key = source["source_sha256"]
    current = progress[key]
    if current["status"] != "rejected_latest_attempt" or current["current_decision"] != "rejected_for_production":
        raise RuntimeError("The mask target must be the current SHA-bound rejected output")
    digest = current["current_review"]["review_output_sha256"]
    target = MASTER_DIR / f"{digest}.png"
    if file_sha256(target) != digest:
        raise RuntimeError("Rejected raw-HD target differs from its archived bytes")
    with Image.open(target) as opened:
        target = opened.convert("RGBA")
        if opened.size != (2048, 2048):
            raise RuntimeError(f"Unexpected pilot target size: {opened.size}")
    rectangles = MASK_RECTANGLES[(args.index, args.revision)]
    mask = Image.new("RGBA", target.size, (0, 0, 0, 255))
    overlay = Image.new("RGBA", target.size, (0, 0, 0, 0))
    mask_draw = ImageDraw.Draw(mask)
    overlay_draw = ImageDraw.Draw(overlay)
    for rectangle in rectangles:
        mask_draw.rectangle(rectangle, fill=(0, 0, 0, 0))
        overlay_draw.rectangle(rectangle, fill=(255, 0, 0, 90))
    preview = Image.alpha_composite(target, overlay)
    mask_path = EXPERIMENT / "review-masks" / f"{key}-note-mask{revision_suffix}.png"
    preview_path = EXPERIMENT / "review-masks" / f"{key}-note-mask-preview{revision_suffix}.png"
    review_path = EXPERIMENT / f"note-mask-{args.index}{revision_suffix}.json"
    for path in (mask_path, preview_path, review_path):
        if path.exists():
            raise RuntimeError(f"Refusing to overwrite mask/review evidence: {path}")
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    mask.save(mask_path)
    preview.save(preview_path)
    alpha = mask.getchannel("A")
    histogram = alpha.histogram()
    if (args.index, args.revision) in {(52, 2), (52, 3)}:
        contract = "PNG alpha<255 marks only the incorrect upper note row to regenerate; alpha=255 preserves the acceptable lower row, capped person, clothing, collar, photographic frame/backplate, correct right-edge tab, lower blank paper and all other pixels. Restore two compact comparable upper gray-mark groups and retain genuine native exterior transparency."
    elif (args.index, args.revision) == (40, 2):
        contract = "PNG alpha<255 marks only the incorrect lower note row to regenerate; alpha=255 preserves the two upper groups, strict-profile person, photographic frame/backplate, correct right-edge tab, lower blank paper and all other pixels. Restore a short lower-left group and a longer lower-right group, with genuine native exterior transparency retained."
    elif (args.index, args.revision) == (67, 3):
        contract = "PNG alpha<255 marks only the overly long upper-right gray-mark region and the incorrect vertical tab with its required position margin; alpha=255 preserves the upper-left group, both lower-row groups, person, photographic frame/backplate and all other pixels. Restore a compact upper-right group and a horizontal tab near the note's vertical middle."
    elif (args.index, args.revision) == (67, 2):
        contract = "PNG alpha<255 marks only the extra independent upper-middle gray bar and the oversized right-edge tab to regenerate; alpha=255 preserves the person, photographic frame/backplate, other note-mark groups and all other pixels. Restore the compact near-square source tab, not a tall stepped block."
    elif args.index == 40:
        contract = "PNG alpha<255 marks only the two incorrect note-mark rows to regenerate; alpha=255 preserves the strict-profile person, photographic frame/backplate, correct right-edge tab, lower blank paper and all other pixels. Restore exactly two source-scale irregular groups in each row and genuine native exterior transparency in the new output."
    elif args.index == 52:
        contract = "PNG alpha<255 marks only the two incorrect note-mark rows to regenerate; alpha=255 preserves the capped person, clothing, collar, photographic frame/backplate, correct right-edge tab, lower blank paper and all other pixels. Restore exactly two source-scale irregular groups in each row while retaining genuine native exterior transparency."
    elif args.index == 53:
        contract = "PNG alpha<255 marks only the two incorrect note-mark rows to regenerate; alpha=255 preserves the corrected viewer-right person, cap, hair and brows, clothing, collar, photographic frame/backplate, correct right-edge tab, lower blank paper and all other pixels. Restore exactly two source-scale irregular groups in each row while retaining genuine native exterior transparency."
    elif args.index == 54:
        contract = "PNG alpha<255 marks only the two incorrect note-mark rows to regenerate; alpha=255 preserves the viewer-right person, hair, clothing, collar, photographic frame/backplate, correct right-edge tab, lower blank paper and all other pixels. Restore exactly two source-scale irregular groups in each row while retaining genuine native exterior transparency."
    elif args.index == 65:
        contract = "PNG alpha<255 marks only the two incorrect note-mark rows to regenerate; alpha=255 preserves all other pixels, including the restored tab."
    else:
        contract = "PNG alpha<255 marks only the two incorrect note-mark rows and missing right-edge tab to regenerate; alpha=255 preserves the person, photographic frame/backplate and all other pixels. Keep true exterior transparency except the source's compact tab."
    write_json(review_path, {
        "schema": "high131-note-inpainting-mask-v1",
        "machine_id": machine_id(),
        "created_at_utc": utc_now(),
        "status": "pending_actual_mask_review",
        "index": args.index,
        "revision": args.revision,
        "source_sha256": key,
        "source_png_sha256": source["converted_png_sha256"],
        "target_sha256": digest,
        "target_size": list(target.size),
        "mask_size": list(mask.size),
        "mask_file": mask_path.relative_to(ROOT).as_posix(),
        "mask_sha256": file_sha256(mask_path),
        "preview_file": preview_path.relative_to(ROOT).as_posix(),
        "preview_sha256": file_sha256(preview_path),
        "size": list(mask.size),
        "mode": mask.mode,
        "rects": rectangles,
        "coordinate_convention": "Pillow rectangle [left, top, right, bottom], with right and bottom included.",
        "alpha_extrema": list(alpha.getextrema()),
        "transparent_pixels": histogram[0],
        "opaque_pixels": histogram[255],
        "role": "inpainting-mask",
        "not_generated_or_game_payload": True,
        "no_generated_master_pixels_modified": True,
        "official_contract": contract,
        "reviewed_at_utc": None,
        "reviewer": None,
    })
    print(json.dumps({
        "status": "pending_actual_mask_review",
        "mask": mask_path.relative_to(ROOT).as_posix(),
        "mask_sha256": file_sha256(mask_path),
        "preview": preview_path.relative_to(ROOT).as_posix(),
        "review": review_path.relative_to(ROOT).as_posix(),
        "target_sha256": digest,
        "new_image_generation_calls": 0,
    }, ensure_ascii=True))


if __name__ == "__main__":
    main()
