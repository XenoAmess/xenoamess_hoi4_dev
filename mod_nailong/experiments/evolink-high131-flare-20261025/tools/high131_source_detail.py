import argparse
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"


def main():
    parser = argparse.ArgumentParser(description="Enlarge exact source pixels for HIGH131 visual review only.")
    parser.add_argument("--index", required=True, type=int)
    parser.add_argument("--scale", type=int, default=8)
    args = parser.parse_args()
    if args.scale < 2 or args.scale > 12:
        raise RuntimeError("scale must be in 2..12")
    scope = read_json(EXPERIMENT / "scope.json")
    matches = [row for row in scope["entries"] if row["index"] == args.index]
    if len(matches) != 1:
        raise RuntimeError("Expected one source at index")
    source = matches[0]
    source_path = ROOT / source["source_png"]
    if file_sha256(source_path) != source["converted_png_sha256"]:
        raise RuntimeError("Source SHA differs from scope")
    directory = EXPERIMENT / "review-source-details"
    output = directory / f"{args.index}-source-nearest{args.scale}.png"
    receipt_path = directory / f"{args.index}-source-nearest{args.scale}.json"
    if output.exists() or receipt_path.exists():
        receipt = read_json(receipt_path)
        if receipt["source_png_sha256"] != file_sha256(source_path) or receipt["output_sha256"] != file_sha256(output):
            raise RuntimeError("Existing source detail does not match the retained source")
    else:
        directory.mkdir(parents=True, exist_ok=True)
        with Image.open(source_path) as opened:
            source_image = opened.convert("RGBA")
            enlarged = source_image.resize((source_image.width * args.scale, source_image.height * args.scale), Image.Resampling.NEAREST)
            white = Image.new("RGBA", enlarged.size, (255, 255, 255, 255))
            white.alpha_composite(enlarged)
            combined = Image.new("RGB", (enlarged.width * 2, enlarged.height), (0, 0, 0))
            combined.paste(enlarged.convert("RGB"), (0, 0))
            combined.paste(white.convert("RGB"), (enlarged.width, 0))
            combined.save(output)
        receipt = {
            "schema": "naiwa-evolink-high131-source-detail-v1",
            "machine_id": machine_id(),
            "created_at_utc": utc_now(),
            "index": args.index,
            "source_sha256": source["source_sha256"],
            "source_png": source["source_png"],
            "source_png_sha256": file_sha256(source_path),
            "source_size": list(source_image.size),
            "scale": args.scale,
            "resampling": "NEAREST",
            "panels": ["exact RGBA RGB channels", "source over white"],
            "output": output.relative_to(ROOT).as_posix(),
            "output_sha256": file_sha256(output),
            "review_display_only": True,
        }
        write_json(receipt_path, receipt)
    print(json.dumps(receipt, ensure_ascii=True))


if __name__ == "__main__":
    main()
