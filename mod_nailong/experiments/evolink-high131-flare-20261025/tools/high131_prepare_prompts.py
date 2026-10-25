import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"
OBSERVATIONS = ROOT / "runtime/evolink-high131-flare-20261025/observations"
SCOPE = read_json(EXPERIMENT / "scope.json")
RELEASE = read_json(EXPERIMENT / "input-release.json")


def prompt_for(observation, transparent=False):
    repair = observation["repair_focus"].strip()
    repair_block = f"\n\nKNOWN VISIBLE DEFECT TO CORRECT:\n{repair}" if repair else ""
    background = observation["background_prompt"].strip()
    if transparent:
        background = ". ".join(
            sentence for sentence in background.split(". ")
            if "working matte" not in sentence.lower()
            and "restore the exact source alpha" not in sentence.lower()
            and "restore the original source alpha" not in sentence.lower()
        )
        if not background.endswith((".", "!", "?")):
            background += "."
        background += " Return genuine transparency only outside the complete original bust or complete card/frame/note silhouette. No working matte, halo, smoke or invented backdrop may remain. Keep every subject, garment, photographic backing, frame and note interior fully opaque."
        stage = (
            "\n\nNATIVE TRANSPARENT EXTERIOR PASS AND EVIDENCE LIMITS:\n"
            "Return a native RGBA with actual transparency outside the complete silhouette, never a white, gray or colored working-matte halo. Do not paint a checkerboard or green screen. Any deterministic source-alpha mapping is a separate later decision requiring actual silhouette and visual review, not an automatic step. "
        )
    else:
        stage = (
            "\n\nOPAQUE RGB WORKING PASS AND EVIDENCE LIMITS:\n"
            "This is the authorized best-RGB pass for a real complete backplate. Source alpha will be restored separately only after actual visual RGB review, using the recorded source-alpha BILINEAR method without changing RGB. Do not request or paint a checkerboard or green screen. Keep all original opaque backing, cloth and paper solid; no interior holes, haze or see-through fabric. "
        )
    return (
        "EDIT ONLY THE PERSON in image 1. Image 1 is the exact original game portrait/card and the sole authority for visible features, composition, clothing and exterior. "
        "Image 2 is only the user mascot identity reference: a fictional yellow 奶龙 with a compact round head, short broad neck, solid black oval eyes with green rings and no white sclera, one small mouth at the actual original mouth position, and no human nose, ears or skin. "
        "If a moustache is present, the one mouth remains below it; never add a second gray slit or default mascot lip above the moustache.\n\n"
        "SOURCE-VISIBLE FEATURES TO PRESERVE:\n"
        + observation["source_features_prompt"].strip()
        + "\nRetain the actual source hair, eyebrows, facial-hair extent, headgear, eyewear, clothing and decorations only where visibly present. Source-visible eyebrows must remain distinct painted hair, never a bare yellow forehead. Do not copy a bare scalp or missing eyebrows from the mascot reference over real source hair. Do not invent features from names or biographies.\n\n"
        "COMPOSITION, EXPRESSION AND LIGHT:\n"
        + observation["composition_prompt"].strip()
        + "\nFit the existing collar naturally around a rounded chin and very short broad neck transition while preserving its original open/closed state. The rounded chin must sit close to the neckline; never extend a long yellow funnel through an open collar. No long neck column, pinched collar, floating cloth, clipping or cream bib. Preserve exactly one source-appropriate mouth and expression.\n\n"
        "BACKGROUND, FRAME AND EXTERIOR:\n"
        + background
        + repair_block
        + stage
        + (observation["visible_limitations"].strip() or "No additional microscopic feature claim is made.")
        + " Do not invent readable writing, extra note rows, symbols, people or comparison panels. Keep full returned detail and the source composition; no watermark."
    )


def output_size(source_size):
    ratio = source_size[0] / source_size[1]
    if ratio >= 0.85:
        return "1:1"
    if ratio >= 0.65:
        return "3:4"
    return "2:3"


def main():
    assets = {row["source_sha256"]: row for row in RELEASE["assets"]}
    observations = {}
    evidence = {}
    for number in range(1, 9):
        result = OBSERVATIONS / f"group-{number:02}.json"
        if not result.exists():
            continue
        body = read_json(result)
        assert body["schema"] == "naiwa-high131-source-observations-v1"
        assert body["group"] == number
        for row in body["entries"]:
            key = row["source_sha256"]
            assert key not in observations
            assert row["actual_source_viewed"] is True and row["mascot_reference_viewed"] is True
            observations[key] = row
            evidence[key] = result
    mascot = SCOPE["mascot_reference"]
    assert file_sha256(ROOT / mascot["path"]) == mascot["sha256"]
    rows = []
    for source in SCOPE["entries"]:
        key = source["source_sha256"]
        base = {
            "index": source["index"],
            "source_sha256": key,
            "source_assets": source["source_assets"],
        }
        if key not in observations:
            rows.append({**base, "status": "pending_actual_source_observation"})
            continue
        observation = observations[key]
        features = observation["source_features_prompt"].lower()
        draft_path = EXPERIMENT / "prompts" / f"{key}-01.txt"
        cancelled_draft = draft_path.relative_to(ROOT).as_posix() if draft_path.exists() else None
        observation_evidence = {
            "observation": evidence[key].relative_to(ROOT).as_posix(),
            "observation_sha256": file_sha256(evidence[key]),
            "observed_features": observation["source_features_prompt"],
            "cancelled_undispatched_prompt_file": cancelled_draft,
        }
        nonperson = any(value in features for value in ("no person", "non-person", "object-only", "architecture-only", "emblem-only"))
        if nonperson:
            rows.append({
                **base,
                "status": "nonperson_scope_review_required",
                **observation_evidence,
            })
            continue
        multiperson = any(value in features for value in ("three-person", "two-person", "multiple people", "group portrait"))
        if multiperson:
            rows.append({
                **base,
                "status": "multiperson_special_prompt_required",
                **observation_evidence,
            })
            continue
        source_path = ROOT / source["source_png"]
        converted_sha = file_sha256(source_path)
        assert converted_sha == source["converted_png_sha256"]
        release = assets[key]
        assert release["converted_png_sha256"] == converted_sha
        assert release["public_unauthenticated_sha256_verified"] is True
        output = EXPERIMENT / "outputs" / f"{key}-01.png"
        task_path = output.with_name(f"{output.stem}.task.json")
        result_path = output.with_name(f"{output.stem}.result.json")
        existing_dispatch = any(path.exists() for path in (output, task_path, result_path))
        transparent = source["source_alpha_extrema"][0] == 0 and not existing_dispatch
        original_draft = EXPERIMENT / "prompts" / f"{key}-01.txt"
        prompt_path = EXPERIMENT / "prompts" / f"{key}-01{'-transparent' if transparent else ''}.txt"
        generated_prompt = prompt_for(observation, transparent=transparent).encode("utf-8")
        if prompt_path.exists():
            actual_prompt = prompt_path.read_bytes()
            actual_prompt.decode("utf-8")
        else:
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            with prompt_path.open("xb") as stream:
                stream.write(generated_prompt)
            actual_prompt = generated_prompt
        rows.append({
            **base,
            "status": "existing_dispatch_record" if existing_dispatch else "prepared_not_dispatched",
            "model": "gpt-image-2.5-flare",
            "size": output_size(source["source_size"]),
            "resolution": "2K",
            "quality": "high",
            "background": "transparent" if transparent else "opaque",
            "n": 1,
            "prompt_file": prompt_path.relative_to(ROOT).as_posix(),
            "prompt_sha256": hashlib.sha256(actual_prompt).hexdigest(),
            "output": output.relative_to(ROOT).as_posix(),
            "source_png": source["source_png"],
            "converted_png_sha256": converted_sha,
            "source_alpha_extrema": source["source_alpha_extrema"],
            "image_urls": [release["url"], mascot["url"]],
            "ordered_input_sha256": [converted_sha, mascot["sha256"]],
            "observation": evidence[key].relative_to(ROOT).as_posix(),
            "observation_sha256": file_sha256(evidence[key]),
            "attempt": "external-01",
            "cancelled_undispatched_prompt_file": original_draft.relative_to(ROOT).as_posix() if transparent and original_draft.exists() else None,
        })
    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    target = EXPERIMENT / "prepared.json"
    write_json(target, {
        "schema": "naiwa-evolink-high131-prepared-v1",
        "machine_id": machine_id(),
        "prepared_at_utc": utc_now(),
        "scope_sha256": file_sha256(EXPERIMENT / "scope.json"),
        "input_release_sha256": file_sha256(EXPERIMENT / "input-release.json"),
        "source_count": len(rows),
        "counts": counts,
        "entries": rows,
    })
    print(json.dumps({"target": target.relative_to(ROOT).as_posix(), "counts": counts}, ensure_ascii=True))


if __name__ == "__main__":
    main()
