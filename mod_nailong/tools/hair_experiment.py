"""Freeze the 26-resource A baseline and record built-in imagegen B variants.

No image generation API: deterministic file preparation, normalization and display.
"""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT, file_sha256, machine_id, read_json, sha256, utc_now, write_json
from PIL import Image, ImageDraw

MOD = ROOT / "mod_nailong"
EXP = MOD / "experiments/hair-features-v1"
MANIFEST = EXP / "manifest.json"
BASELINE = "ec9b0af"

def git_bytes(path):
    return subprocess.check_output(["git", "show", f"{BASELINE}:{path}"], cwd=ROOT)

def freeze():
    if MANIFEST.exists():
        raise SystemExit("Experiment already frozen; use existing manifest")
    baseline = json.loads(git_bytes("mod_nailong/data/generated.json"))["portraits"]
    catalog = json.loads(git_bytes("mod_nailong/data/catalog.json"))
    assets = [a for a in catalog["assets"] if a["source_sha256"] in baseline]
    assert len(baseline) == 23 and len(assets) == 26
    source_index = read_json(ROOT / "runtime/source-index.json")
    EXP.mkdir(parents=True, exist_ok=True)
    for folder in ["a", "b", "prompts", "attempts"]:
        (EXP / folder).mkdir(exist_ok=True)
    # Stable order begins with a conspicuous moustache for the desktop comparison.
    keys = list(baseline)
    keys.sort(key=lambda k: (0 if k.startswith("cdcacddc") else 1, list(baseline).index(k)))
    jobs = []
    for key in keys:
        row = baseline[key]
        old_bytes = git_bytes(row["image"])
        assert sha256(old_bytes) == row["image_sha256"]
        old = EXP / "a" / (key + ".png")
        old.write_bytes(old_bytes)
        (EXP / "prompts" / (key + "-a.txt")).write_text(row["prompt"], encoding="utf-8")
        asset = next(a for a in assets if a["source_sha256"] == key)
        source = source_index[asset["id"]]
        if source["member"]:
            with zipfile.ZipFile(source["path"]) as archive:
                raw = archive.read(source["member"])
        else:
            raw = Path(source["path"]).read_bytes()
        assert sha256(raw) == key
        original = ROOT / "runtime/references" / (key + ".png")
        original.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(io.BytesIO(raw)) as image:
            image.convert("RGBA").save(original)
        transparent = Image.open(old).getchannel("A").getextrema()[0] < 255
        jobs.append({"key": key, "source": asset["path"], "a": old.relative_to(ROOT).as_posix(),
                     "a_sha256": file_sha256(old), "original": str(original),
                     "original_png_sha256": file_sha256(original), "size": row["size"],
                     "transparent": transparent, "a_record": row, "status": "awaiting_prompt"})
    write_json(MANIFEST, {"schema": "naiwa-hair-ab-v1", "baseline_commit": BASELINE,
        "machine_id": machine_id(), "frozen_at_utc": utc_now(),
        "request": "26 previously covered resource instances; preserve original hair, moustache, beard and eyebrows in B",
        "unique_sources": 23, "resource_instances": 26, "assets": assets, "jobs": jobs,
        "limitation": "Stochastic image edits can alter details beyond hair. Compare visually; this is not a deterministic causal pixel test."})
    write_json(ROOT / "runtime/hair-jobs.json", jobs)
    usage = shutil.disk_usage(ROOT)
    write_json(ROOT / "runtime/hair-storage-start.json", {"machine_id": machine_id(), "observed_at_utc": utc_now(),
        "source": "Python shutil.disk_usage and project-only file inventory", "volume_total": usage.total,
        "available": usage.free, "estimated_peak_bytes": 512*1024*1024,
        "project_bytes": sum(p.stat().st_size for p in ROOT.rglob("*") if p.is_file()),
        "retention": "Active experiment sources protected for seven days; no deletion in this task"})
    print(f"Frozen {len(assets)} resources / {len(jobs)} unique sources")
    sheet("original")

def prompt(key, text):
    manifest = read_json(MANIFEST)
    job = next(j for j in manifest["jobs"] if j["key"] == key)
    number = len(job.get("attempts", [])) + 1
    target = EXP / "prompts" / f"{key}-b-{number:02}.txt"
    target.write_text(text, encoding="utf-8")
    attempt = {"number": number, "prompt": text, "prompt_file": target.relative_to(ROOT).as_posix(),
        "prompt_sha256": file_sha256(target), "method": "built-in imagegen edit", "status": "prepared",
        "prepared_at_utc": utc_now(), "machine_id": machine_id(),
        "inputs": [{"role": "edit target A", "sha256": job["a_sha256"], "path": job["a"]},
                   {"role": "original hair and facial-hair reference", "sha256": key,
                    "converted_png_sha256": job["original_png_sha256"]},
                   {"role": "user mascot identity reference", "sha256": file_sha256(MOD / "assets/reference/naiwa.png")}]}
    job.setdefault("attempts", []).append(attempt)
    job["status"] = "prompt_saved"
    write_json(MANIFEST, manifest)
    print(f"Saved full prompt BEFORE call: {target.relative_to(ROOT)}")

def ingest(key, image):
    manifest = read_json(MANIFEST)
    job = next(j for j in manifest["jobs"] if j["key"] == key)
    attempt = job["attempts"][-1]
    assert attempt["status"] == "prepared"
    source = Path(image)
    target = EXP / "b" / f"{key}-{attempt['number']:02}.png"
    with Image.open(source) as im:
        fullsize = list(im.size)
        im.convert("RGBA").resize(tuple(job["size"]), Image.Resampling.LANCZOS).save(target, optimize=True)
    attempt.update(status="generated", output=target.relative_to(ROOT).as_posix(), output_sha256=file_sha256(target),
        generated_at_utc=utc_now(), fullsize_sha256=file_sha256(source), fullsize_size=fullsize,
        has_alpha=Image.open(target).getchannel("A").getextrema()[0] < 255)
    job.update(status="pending_visual_review", b=attempt["output"], b_sha256=attempt["output_sha256"])
    write_json(MANIFEST, manifest)
    write_json(ROOT / "runtime/hair-origins" / f"{key}-{attempt['number']:02}.json", {
        "machine_id": machine_id(), "observed_at_utc": utc_now(), "path": str(source),
        "sha256": file_sha256(source), "review_after_days": 7})
    print(f"Imported B {key[:12]}")

def fail(key, message):
    manifest = read_json(MANIFEST)
    job = next(j for j in manifest["jobs"] if j["key"] == key)
    job["attempts"][-1].update(status="failed", error=message, observed_at_utc=utc_now())
    job["status"] = "failed"
    write_json(MANIFEST, manifest)

def reject(key, message):
    manifest = read_json(MANIFEST)
    job = next(j for j in manifest["jobs"] if j["key"] == key)
    job["attempts"][-1].update(review="rejected", rejection_reason=message, reviewed_at_utc=utc_now())
    job["status"] = "needs_art_correction"
    write_json(MANIFEST, manifest)

def sheet(mode):
    jobs = read_json(MANIFEST)["jobs"]
    cell_w, cell_h, columns = (260, 280, 5) if mode == "original" else (340, 260, 4)
    canvas = Image.new("RGB", (cell_w*columns, cell_h*((len(jobs)+columns-1)//columns)), "#d7d6d1")
    draw = ImageDraw.Draw(canvas)
    for i, job in enumerate(jobs):
        x,y = (i%columns)*cell_w, (i//columns)*cell_h
        paths = [Path(job["original"])] if mode == "original" else [ROOT/job["a"], ROOT/job["b"] if job.get("b") else None]
        for side, path in enumerate(paths):
            if path is None: continue
            with Image.open(path) as im:
                ratio = min((cell_w//len(paths)-12)/im.width, 212/im.height)
                im = im.convert("RGBA").resize((round(im.width*ratio), round(im.height*ratio)), Image.Resampling.NEAREST)
                canvas.paste(im, (x+side*(cell_w//len(paths))+6,y+22), im.getchannel("A"))
        draw.text((x+6,y+3),f"{i+1} {job['key'][:8]}" + ("  A left / B right" if mode != "original" else ""), fill="black")
        draw.text((x+6,y+238),Path(job["source"]).stem[-34:],fill="black")
    out = ROOT / "runtime" / f"hair-{mode}-sheet.png"
    canvas.save(out)
    print(out)

def adopt():
    """Run only after visual review; preserve the frozen A baseline and revision history."""
    manifest = read_json(MANIFEST)
    record = read_json(MOD / "data/generated.json")
    for job in manifest["jobs"]:
        if not job.get("b"):
            raise SystemExit("All experiment images must be generated before adoption")
        source = ROOT / job["b"]
        assert file_sha256(source) == job["b_sha256"]
        if job["transparent"] and Image.open(source).getchannel("A").getextrema()[0] == 255:
            raise SystemExit("Lost transparency")
    for job in manifest["jobs"]:
        previous = record["portraits"][job["key"]]
        if previous.get("art_direction") == "hair-features-v1":
            continue
        attempt = job["attempts"][-1]
        canonical = MOD / "assets/portraits" / (job["key"] + ".png")
        history = list(previous.get("revision_history", []))
        history.append({"result": "superseded by user-adopted hair-features-v1", "reason": "User instructed all existing and future art to retain original hair and facial hair",
            "previous_image_sha256": previous["image_sha256"], "previous_fullsize_sha256": previous["generated_fullsize_sha256"],
            "previous_prompt": previous["prompt"], "previous_art_direction": previous.get("art_direction", "legacy-bald"),
            "replaced_at_utc": utc_now(), "frozen_a": job["a"]})
        shutil.copyfile(ROOT / job["b"], canonical)
        record["portraits"][job["key"]] = {"source_sha256": job["key"],
            "reference_sha256": file_sha256(MOD / "assets/reference/naiwa.png"), "method": "built-in imagegen; previous A + original hair reference + user mascot reference",
            "prompt": attempt["prompt"], "generated_fullsize_sha256": attempt["fullsize_sha256"],
            "generated_fullsize_size": attempt["fullsize_size"], "image": canonical.relative_to(ROOT).as_posix(),
            "image_sha256": file_sha256(canonical), "size": job["size"], "review": "approved",
            "art_direction": "hair-features-v1", "machine_id": machine_id(), "imported_at_utc": utc_now(),
            "reviewed_at_utc": utc_now(), "review_method": "Visual comparison of original, A and B, including normalized contact sheet",
            "revision_history": history, "experiment_manifest": MANIFEST.relative_to(ROOT).as_posix(),
            "generation_inputs": attempt["inputs"]}
        job.update(status="adopted_after_visual_review", adopted_at_utc=utc_now())
    manifest["decision"] = "User adopted B for all previous and future portraits on 2026-10-16"
    write_json(MOD / "data/generated.json", record)
    write_json(MANIFEST, manifest)
    print(f"Adopted {len(manifest['jobs'])} B variants, A baseline retained")

def render():
    manifest = read_json(MANIFEST)
    jobs = {j["key"]: j for j in manifest["jobs"]}
    order = {key: n for n, key in enumerate(jobs)}
    rows = []
    for asset in sorted(manifest["assets"], key=lambda a: (order[a["source_sha256"]], a["package"])):
        j = jobs[asset["source_sha256"]]
        if not j.get("b"): raise SystemExit("Comparison is not complete")
        title = Path(asset["path"]).stem
        for prefix in ["Portrait_", "portrait_", "idea_"]:
            if title.startswith(prefix):title=title[len(prefix):]
        rows.append({"title":title.replace("_", " "), "package":asset["package"], "source":asset["path"], "key":j["key"],
            "a":str((ROOT/j["a"]).relative_to(EXP)).replace("\\", "/"),
            "b":str((ROOT/j["b"]).relative_to(EXP)).replace("\\", "/"), "size":j["size"],
            "shared":sum(a["source_sha256"]==j["key"] for a in manifest["assets"]),
            "promptA":j["a_record"]["prompt"], "promptB":j["attempts"][-1]["prompt"]})
    template = (MOD / "tools/hair_comparison.template.html").read_text(encoding="utf-8")
    target = EXP / "index.html"
    target.write_text(template.replace("__COMPARISON_DATA__", json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")), encoding="utf-8")
    print(target)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("command",choices=["freeze","prompt","import","fail","reject","sheet","adopt","render"])
    p.add_argument("--key");p.add_argument("--text-file");p.add_argument("--image");p.add_argument("--message")
    p.add_argument("--mode",default="pairs")
    a=p.parse_args()
    if a.command=="freeze":freeze()
    elif a.command=="prompt":prompt(a.key,Path(a.text_file).read_text(encoding="utf-8"))
    elif a.command=="import":ingest(a.key,a.image)
    elif a.command=="fail":fail(a.key,a.message)
    elif a.command=="reject":reject(a.key,a.message)
    elif a.command=="adopt":adopt()
    elif a.command=="render":render()
    else:sheet(a.mode)

if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
