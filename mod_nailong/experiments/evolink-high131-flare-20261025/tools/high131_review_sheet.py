import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"


def image_info(path):
    with Image.open(path) as opened:
        bands = opened.getbands()
        result = {"size": list(opened.size), "mode": opened.mode}
        if "A" in bands:
            alpha = opened.getchannel("A")
            histogram = alpha.histogram()
            result.update({
                "alpha_extrema": list(alpha.getextrema()),
                "alpha_counts": {str(value): histogram[value] for value in (0, 252, 253, 254, 255)},
            })
        else:
            result.update({"alpha_extrema": None, "alpha_counts": None})
        return result


def panel(image, matte, source=False):
    image = image.convert("RGBA")
    scale = min(300 / image.width, 300 / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    resized = image.resize(size, Image.Resampling.NEAREST if source else Image.Resampling.LANCZOS)
    result = Image.new("RGBA", (300, 300), matte)
    result.alpha_composite(resized, ((300 - resized.width) // 2, (300 - resized.height) // 2))
    return result.convert("RGB")


def alpha_panel(image):
    image = image.convert("RGBA")
    alpha = image.getchannel("A")
    scale = min(300 / alpha.width, 300 / alpha.height)
    size = (max(1, round(alpha.width * scale)), max(1, round(alpha.height * scale)))
    resized = alpha.resize(size, Image.Resampling.NEAREST)
    result = Image.new("L", (300, 300), 0)
    result.paste(resized, ((300 - resized.width) // 2, (300 - resized.height) // 2))
    return result.convert("RGB")


def main():
    if len(sys.argv) < 3:
        raise SystemExit("usage: high131_review_sheet.py REVIEW_NAME OUTPUT.png [...]")
    name = sys.argv[1]
    outputs = [ROOT / value for value in sys.argv[2:]]
    sheet_path = EXPERIMENT / f"{name}.png"
    evidence_path = EXPERIMENT / f"{name}-evidence.json"
    for path in (sheet_path, evidence_path):
        if path.exists():
            raise RuntimeError(f"Refusing to overwrite review evidence: {path}")
    sheet = Image.new("RGB", (1500, 330 * len(outputs)), (48, 48, 48))
    draw = ImageDraw.Draw(sheet)
    entries = []
    for row, output in enumerate(outputs):
        key = output.name[:64]
        source = ROOT / "runtime/references" / f"{key}.png"
        result_path = output.with_name(f"{output.stem}.result.json")
        task_path = output.with_name(f"{output.stem}.task.json")
        prompt_path = output.with_name(f"{output.stem}.prompt.txt")
        request_path = output.with_name(f"{output.stem}.request.json")
        generation_output = output
        if not result_path.exists() and output.stem.endswith("-alpha-repaired-bilinear"):
            generation_output = output.with_name(output.stem.removesuffix("-alpha-repaired-bilinear") + ".png")
            result_path = generation_output.with_name(f"{generation_output.stem}.result.json")
            task_path = generation_output.with_name(f"{generation_output.stem}.task.json")
            prompt_path = generation_output.with_name(f"{generation_output.stem}.prompt.txt")
            request_path = generation_output.with_name(f"{generation_output.stem}.request.json")
        result = read_json(result_path)
        assert file_sha256(generation_output) == result["sha256"]
        with Image.open(source) as source_image, Image.open(output) as raw_image:
            source_info = image_info(source)
            raw_info = image_info(output)
            panels = [
                ("SOURCE white", panel(source_image, (255, 255, 255, 255), source=True)),
                ("RETURN white", panel(raw_image, (255, 255, 255, 255))),
                ("RETURN cyan", panel(raw_image, (0, 220, 220, 255))),
                ("SOURCE alpha", alpha_panel(source_image)),
                ("RETURN alpha" if raw_info["mode"] == "RGBA" else "RETURN RGB: no alpha", alpha_panel(raw_image)),
            ]
        for column, (label, image) in enumerate(panels):
            x, y = column * 300, row * 330
            sheet.paste(image, (x, y + 30))
            draw.text((x + 6, y + 9), f"{row + 1} {label}", fill=(255, 255, 255))
        entries.append({
            "index": row + 1,
            "source_sha256": key,
            "source_png": source.relative_to(ROOT).as_posix(),
            "source_png_sha256": file_sha256(source),
            "source_info": source_info,
            "generation_output": generation_output.relative_to(ROOT).as_posix(),
            "generation_output_sha256": file_sha256(generation_output),
            "output": output.relative_to(ROOT).as_posix(),
            "output_sha256": file_sha256(output),
            "output_info": raw_info,
            "task": task_path.relative_to(ROOT).as_posix(),
            "task_sha256": file_sha256(task_path),
            "task_id": read_json(task_path)["task_id"],
            "prompt": prompt_path.relative_to(ROOT).as_posix(),
            "prompt_sha256": file_sha256(prompt_path),
            "request": request_path.relative_to(ROOT).as_posix(),
            "request_sha256": file_sha256(request_path),
            "result": result_path.relative_to(ROOT).as_posix(),
            "result_sha256": file_sha256(result_path),
            "review_display_only": True,
        })
    sheet.save(sheet_path)
    write_json(evidence_path, {
        "schema": "naiwa-evolink-high131-review-evidence-v1",
        "machine_id": machine_id(),
        "created_at_utc": utc_now(),
        "review_sheet": sheet_path.relative_to(ROOT).as_posix(),
        "review_sheet_sha256": file_sha256(sheet_path),
        "entries": entries,
        "scope": "Technical evidence pages only. Full source and unchanged full raw must still be viewed for art decisions; never game payload or automatic approval.",
    })
    print(json.dumps({"sheet": sheet_path.relative_to(ROOT).as_posix(), "evidence": evidence_path.relative_to(ROOT).as_posix(), "entries": len(entries)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
