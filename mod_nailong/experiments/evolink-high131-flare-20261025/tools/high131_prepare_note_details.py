import argparse
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.high131_io import write_json
from tools.common import ROOT, file_sha256, machine_id, utc_now

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"
CROP_RECT = (32, 22, 65, 67)
SCALE = 16
METHOD = "source-crop-resize-nearest-v1"


def main():
    parser = argparse.ArgumentParser(description="Prepare source-only enlarged note references; no generated master or game payload is edited.")
    parser.add_argument("--index", action="append", type=int, required=True)
    args = parser.parse_args()
    indices = sorted(set(args.index))
    if not indices or (indices not in ([40], [52], [53]) and not set(indices) <= {65, 67}):
        raise RuntimeError("Only reviewed source-40, source-52 or source-53 note regions or pilot note regions for 65 and 67 are eligible")
    manifest_path = EXPERIMENT / (f"note-detail-sources-{indices[0]}.json" if indices in ([40], [52], [53]) else "note-detail-sources.json")
    if manifest_path.exists():
        raise RuntimeError(f"Refusing to overwrite the source-detail manifest: {manifest_path}")
    scope = {row["index"]: row for row in json.loads((EXPERIMENT / "scope.json").read_text(encoding="utf-8"))["entries"]}
    entries = []
    for index in indices:
        source = scope[index]
        key = source["source_sha256"]
        source_path = ROOT / source["source_png"]
        if file_sha256(source_path) != source["converted_png_sha256"]:
            raise RuntimeError(f"Source bytes changed for index {index}")
        with Image.open(source_path) as opened:
            source_image = opened.convert("RGBA")
            if source_image.size != (65, 67):
                raise RuntimeError(f"Pilot source dimensions differ for index {index}: {source_image.size}")
            left, top, right, bottom = CROP_RECT
            detail = source_image.crop(CROP_RECT).resize(((right - left) * SCALE, (bottom - top) * SCALE), Image.Resampling.NEAREST)
        output = EXPERIMENT / "review-source-details" / f"{key}-note-nearest16.png"
        if output.exists():
            raise RuntimeError(f"Refusing to overwrite an existing source-detail reference: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        detail.save(output)
        with Image.open(output) as saved:
            if saved.convert("RGBA").tobytes() != detail.tobytes():
                raise RuntimeError(f"Source-detail pixels differ after PNG encoding: {output}")
            size = list(saved.size)
            mode = saved.mode
        entries.append({
            "index": index,
            "source_sha256": key,
            "source_png": source_path.relative_to(ROOT).as_posix(),
            "source_png_sha256": source["converted_png_sha256"],
            "crop_rect": list(CROP_RECT),
            "scale": SCALE,
            "method": METHOD,
            "path": output.relative_to(ROOT).as_posix(),
            "sha256": file_sha256(output),
            "size": size,
            "mode": mode,
            "role": "source-note-detail-reference",
            "source_region": "The complete original note and small right-edge tab with a narrow source-context margin; no reconstructed glyphs or strokes.",
            "source_detail_page": f"mod_nailong/experiments/evolink-high131-flare-20261025/review-source-details/{index}-source-nearest8.png",
            "not_generated_or_game_payload": True,
            "derivative_reviewed": False,
            "reviewed_at_utc": None,
            "reviewer": None,
        })
    write_json(manifest_path, {
        "schema": "naiwa-high131-note-detail-sources-v1",
        "machine_id": machine_id(),
        "created_at_utc": utc_now(),
        "status": "pending_actual_derivative_review",
        "entries": entries,
        "scope": "Only exact source-derived crop/NEAREST enlargements for additional visual reference. No source or generated master RGB is replaced, no new art is invented, and these derivatives are not game payload or proof of art approval.",
        "new_image_generation_calls": 0,
    })
    print(json.dumps({
        "status": "pending_actual_derivative_review",
        "manifest": manifest_path.relative_to(ROOT).as_posix(),
        "entries": [{"index": row["index"], "path": row["path"], "sha256": row["sha256"], "size": row["size"]} for row in entries],
        "new_image_generation_calls": 0,
    }, ensure_ascii=True))


if __name__ == "__main__":
    main()
