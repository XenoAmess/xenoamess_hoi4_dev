import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import high131_hd_proof as hd_proof
from runtime.high131_io import write_json
from runtime.high131_prepare_card_repairs import revise_undispatched_prompt
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"
MODE = "raw-hd-edit-v1"
NOTE_INDICES = (40, 52, 53, 54, 57, 61, 62, 63, 64, 65, 67)


def main():
    parser = argparse.ArgumentParser(description="Prepare raw-HD localized HIGH note repairs without any image-generation call.")
    parser.add_argument("--remote-commit", required=True)
    parser.add_argument("--readback", required=True)
    parser.add_argument("--index", action="append", type=int)
    parser.add_argument("--note-details", action="store_true")
    parser.add_argument("--mask", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.remote_commit):
        raise RuntimeError("Expected a full lowercase remote commit")
    indices = set(args.index or NOTE_INDICES)
    if not indices <= set(NOTE_INDICES):
        raise RuntimeError("Only reviewed HIGH note sources are eligible; 60 and 117 remain unresolved")
    if args.note_details and not indices <= {65, 67}:
        raise RuntimeError("Only the actually reviewed pilot note references for 65 and 67 are eligible for four-input repair")
    if args.mask and (not args.note_details or indices != {65}):
        raise RuntimeError("The pilot mask requires --index 65 --note-details and its actual visual review")
    mode = hd_proof.MASK_NOTE_MODE if args.mask else hd_proof.NOTE_DETAIL_MODE if args.note_details else MODE
    detail_entries = {}
    if args.note_details:
        detail_manifest = read_json(EXPERIMENT / "note-detail-sources.json")
        if detail_manifest.get("status") != "source_derivatives_visually_verified":
            raise RuntimeError("Source-detail references still require actual derivative review")
        detail_entries = {row["index"]: row for row in detail_manifest["entries"]}
        if not indices <= set(detail_entries):
            raise RuntimeError("A requested source lacks its reviewed note-detail reference")
    readback_path = (ROOT / args.readback).resolve()
    readback_path.relative_to((ROOT / "runtime").resolve())
    proof, committed_index = hd_proof.load_remote_proof(args.remote_commit, readback_path)

    scope = read_json(EXPERIMENT / "scope.json")
    prepared = {row["source_sha256"]: row for row in read_json(EXPERIMENT / "prepared.json")["entries"]}
    progress = {row["source_sha256"]: row for row in read_json(EXPERIMENT / "progress.json")["entries"]}
    archive = read_json(EXPERIMENT / "output-masters.json")["entries"]
    scope_by_index = {row["index"]: row for row in scope["entries"]}
    target = EXPERIMENT / "card-repair-preparation.json"
    existing = read_json(target)
    entries = list(existing["entries"])
    known = {(row["source_sha256"], row["attempt"]): row for row in entries}
    for index in sorted(indices):
        source = scope_by_index[index]
        key = source["source_sha256"]
        current = progress[key]
        review_reference = current["current_review"]
        if current["status"] != "rejected_latest_attempt" or current["current_decision"] != "rejected_for_production":
            raise RuntimeError(f"Index {index} is not a current SHA-bound art rejection")
        review_path = ROOT / review_reference["review"]
        if file_sha256(review_path) != review_reference["review_sha256"]:
            raise RuntimeError(f"Review SHA mismatch for index {index}")
        decisions = [row for row in read_json(review_path)["entries"] if row["source_sha256"] == key]
        if len(decisions) != 1:
            raise RuntimeError(f"Expected one review decision for index {index}")
        decision = decisions[0]
        match = re.fullmatch(r"external-(\d{2})", decision["attempt"])
        if not match or decision["decision"] != "rejected_for_production":
            raise RuntimeError(f"Index {index} needs an ordinary rejected external attempt")
        previous_number = int(match.group(1))
        number = previous_number + 1
        attempt = f"external-{number:02}"
        digest = decision["output_sha256"]
        if review_reference.get("review_output_sha256") != digest:
            raise RuntimeError(f"Progress and review output differ for index {index}")
        prior = current["attempts_returned"][-1]
        if prior["attempt"] != decision["attempt"] or prior["output_sha256"] != digest or prior["task_id"] != decision["task_id"]:
            raise RuntimeError(f"Latest result does not match the rejection for index {index}")
        old_prompt_path = EXPERIMENT / "outputs" / f"{key}-{previous_number:02}.prompt.txt"
        if file_sha256(old_prompt_path) != decision["prompt_sha256"]:
            raise RuntimeError(f"Previous actual prompt SHA mismatch for index {index}")
        masters = [row for row in archive if row["source_sha256"] == key and row["attempt"] in {decision["attempt"], f"external-{previous_number}"} and row["output_sha256"] == digest]
        if len(masters) != 1:
            raise RuntimeError(f"Expected one retained raw-HD target for index {index}")
        master = masters[0]
        if master["output"] != decision["output"] or master["generated_fullsize_sha256"] != digest:
            raise RuntimeError(f"Raw-HD target differs from the rejected output for index {index}")
        master_path = ROOT / master["generated_fullsize_image"]
        if file_sha256(master_path) != digest:
            raise RuntimeError(f"Raw-HD target byte mismatch for index {index}")
        relative_master = master_path.relative_to(ROOT).as_posix()
        target_url = hd_proof.validate_remote_target(proof, args.remote_commit, master_path, digest, index=committed_index)
        route = prepared[key]
        original_source = ROOT / source["source_png"]
        if file_sha256(original_source) != source["converted_png_sha256"]:
            raise RuntimeError(f"Original source changed for index {index}")
        detail = None
        detail_url = None
        if args.note_details:
            detail = detail_entries[index]
            if detail["source_sha256"] != key or detail["source_png"] != source["source_png"] or detail["source_png_sha256"] != source["converted_png_sha256"]:
                raise RuntimeError(f"Source-detail reference is bound to another original for index {index}")
            detail_path = (ROOT / detail["path"]).resolve()
            detail_path.relative_to((EXPERIMENT / "review-source-details").resolve())
            detail_url = hd_proof.validate_remote_reference(proof, args.remote_commit, detail_path, detail["sha256"], original_source)
        mask = None
        mask_url = None
        if args.mask:
            manifest_path = EXPERIMENT / f"note-mask-{index}.json"
            manifest = read_json(manifest_path)
            if manifest.get("schema") != "high131-note-inpainting-mask-v1" or manifest.get("status") != "mask_visually_verified":
                raise RuntimeError(f"Mask for index {index} still requires actual visual review")
            if not manifest.get("reviewer") or not manifest.get("reviewed_at_utc") or manifest.get("machine_id") != machine_id():
                raise RuntimeError(f"Mask review for index {index} lacks reviewer, time or machine binding")
            if manifest.get("index") != index or manifest.get("source_sha256") != key or manifest.get("source_png_sha256") != source["converted_png_sha256"]:
                raise RuntimeError(f"Mask for index {index} is bound to another source")
            if manifest.get("target_sha256") != digest or manifest.get("role") != "inpainting-mask" or manifest.get("not_generated_or_game_payload") is not True:
                raise RuntimeError(f"Mask for index {index} is not bound to the current rejected target")
            mask_path = (ROOT / manifest["mask_file"]).resolve()
            mask_path.relative_to((EXPERIMENT / "review-masks").resolve())
            mask_url = hd_proof.validate_remote_mask(proof, args.remote_commit, mask_path, manifest["mask_sha256"], master_path, digest)
            mask = {
                "path": mask_path.relative_to(ROOT).as_posix(),
                "sha256": manifest["mask_sha256"],
                "url": mask_url,
                "target_sha256": digest,
                "manifest": manifest_path.relative_to(ROOT).as_posix(),
                "manifest_sha256": file_sha256(manifest_path),
            }
        observation_path = ROOT / route["observation"]
        if file_sha256(observation_path) != route["observation_sha256"]:
            raise RuntimeError(f"Source observation changed for index {index}")
        observations = [row for row in read_json(observation_path)["entries"] if row["source_sha256"] == key]
        if len(observations) != 1:
            raise RuntimeError(f"Expected one source observation for index {index}")
        observation = observations[0]
        background_prompt = observation["background_prompt"].strip()
        legacy_alpha = "use a neutral working matte only outside that silhouette for the opaque RGB pass; invent no interior backdrop, halo or smoke, and restore the source alpha afterward."
        native_alpha = "produce genuine native transparency directly; do not use a working matte or defer alpha restoration; invent no interior backdrop, halo or smoke."
        if legacy_alpha in background_prompt:
            background_prompt = background_prompt.replace(legacy_alpha, native_alpha)
        if any(term in background_prompt for term in ("working matte only outside", "opaque RGB pass", "restore the source alpha afterward")):
            raise RuntimeError(f"Legacy opaque-pass alpha wording requires explicit reconciliation for index {index}")
        reasons = " ".join(decision["remaining_reasons"])
        detail_prompt = ""
        if detail is not None:
            detail_prompt = "Image4 is only a nearest-neighbor enlarged view of Image2's actual note region, provided to make the source's small gray-mark shapes and right-edge tab easier to inspect. It is not a generated image and not an instruction to enlarge the note or imitate enlarged pixels. Image2 remains the authority for composition, card scale, backing and source alpha. Compare only the irregular group shapes, relative lengths and compact footprint; do not invent readable text or replace the person.\n\n"
        mask_prompt = ""
        if mask is not None:
            mask_prompt = "MASK CONTRACT: A separate same-size RGBA PNG mask accompanies this request; it is not Image5 and not another ordered reference image. Mask alpha<255 pixels are the only permitted regeneration regions, and alpha=255 pixels must be preserved. Its two transparent rectangles cover only the existing wrong upper and lower note-mark rows with a narrow paper margin. Do not regenerate the person, photographic frame/backplate, restored right-edge tab or blank lower paper. Within those two regions use Image2 and Image4 to restore the source-scale compact irregular gray marks, their relative lengths and spacing, without generic ovals, dots, long continuous bars, extra groups or newly readable writing. Retain the original paper colour, texture and lighting outside the actual source marks. This editing mask does not redefine the card's exterior alpha or authorize removing backing.\n\n"
        prompt = (
            "Use case: precise-object-edit. Image1 is the actual raw-HD mascot edit target with output SHA256 "
            + digest
            + ". Image2 is the exact original game portrait/card and sole authority for the original visible features and note shapes. Image3 is the user mascot identity reference.\n\n"
            + detail_prompt
            + mask_prompt
            + "ACTUAL OBSERVED CORRECTION: " + reasons + "\n\n"
            + "The exact original note has TWO separated irregular gray-mark groups in its upper note row and TWO separated irregular gray-mark groups in its lower row. Restore exactly TWO source-scale irregular groups in EACH row, with the original relative lengths, spacing and compact footprint. They are not generic repeated dots, uniform short dashes, long horizontal bars, extra groups or newly readable writing. Keep the lower paper blank outside the original marks and retain the original small dark right-edge tab.\n\n"
            + "Preserve every already-correct part of Image1: the yellow compact mascot identity, green-ringed black eyes, exactly one source-appropriate mouth, source-visible hair, brows and facial hair, headgear, clothing, decorations, expression, head pose, crop and lighting. Do not replace the person with a human or a generic mascot. Preserve the short broad fitted neck and correct collar without pinching, floating cloth or a cream bib.\n\n"
            + "SOURCE-VISIBLE CONTRACT FROM IMAGE2:\n"
            + observation["source_features_prompt"].strip() + "\n"
            + observation["composition_prompt"].strip() + "\n"
            + background_prompt + "\n"
            + "Return genuine native transparency only outside the complete original card/frame/note silhouette. Preserve the opaque photographic backing and every subject, garment, frame and note interior; no working matte, halo, smoke, interior holes or invented scene. Do not invent readable text, extra note rows, people, symbols or comparison panels. Keep the full returned detail and original composition; no watermark.\n"
            + observation["visible_limitations"].strip()
        )
        prompt_path = EXPERIMENT / "prompts" / f"{key}-{number:02}.txt"
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        row = {
            "source_sha256": key,
            "attempt": attempt,
            "review": review_path.relative_to(ROOT).as_posix(),
            "review_sha256": review_reference["review_sha256"],
            "rejected_output_sha256": digest,
            "previous_prompt": old_prompt_path.relative_to(ROOT).as_posix(),
            "previous_prompt_sha256": decision["prompt_sha256"],
            "prompt_file": prompt_path.relative_to(ROOT).as_posix(),
            "prompt_sha256": prompt_sha,
            "output": f"mod_nailong/experiments/evolink-high131-flare-20261025/outputs/{key}-{number:02}.png",
            "model": route["model"],
            "background": "transparent",
            "size": route["size"],
            "resolution": route["resolution"],
            "quality": route["quality"],
            "ordered_inputs": ["rejected raw-HD output", "original source PNG", "user mascot reference"],
            "reason": reasons,
            "repair_input_mode": mode,
            "edit_target_image": relative_master,
            "edit_target_sha256": digest,
            "remote_commit": args.remote_commit,
            "remote_readback": readback_path.relative_to(ROOT).as_posix(),
            "remote_target_url": target_url,
            "image_urls": [target_url, route["image_urls"][0], route["image_urls"][1]],
            "ordered_input_sha256": [digest, source["converted_png_sha256"], scope["mascot_reference"]["sha256"]],
        }
        if detail is not None:
            row["ordered_inputs"].append("exact source-note crop enlarged by nearest-neighbor for visual reference only")
            row["image_urls"].append(detail_url)
            row["ordered_input_sha256"].append(detail["sha256"])
            row["note_detail"] = {
                "path": detail_path.relative_to(ROOT).as_posix(),
                "sha256": detail["sha256"],
                "url": detail_url,
                "source_png_sha256": detail["source_png_sha256"],
                "crop_rect": detail["crop_rect"],
                "scale": detail["scale"],
                "method": detail["method"],
                "role": detail["role"],
                "not_generated_or_game_payload": True,
            }
        if mask is not None:
            row["mask_url"] = mask_url
            row["mask"] = mask
        prior_preparation = known.get((key, attempt))
        if prior_preparation is not None:
            if prior_preparation.get("prompt_sha256") == prompt_sha:
                if any(prior_preparation.get(name) != value for name, value in row.items()):
                    raise RuntimeError(f"Route changed without a new prompt for index {index}; preserve the draft and reconcile explicitly")
                continue
            revise_undispatched_prompt(prompt_path, prior_preparation, prompt, prompt_sha)
            prior_preparation.update(row)
            continue
        for directory in ("outputs", "executions", "logs"):
            artifacts = list((EXPERIMENT / directory).glob(f"{key}-{number:02}*"))
            if artifacts:
                raise RuntimeError(f"Refusing to prepare over existing actual artifacts: {artifacts}")
        if prompt_path.exists():
            raise RuntimeError(f"Refusing to overwrite an unrecorded prompt: {prompt_path}")
        prompt_path.write_bytes(prompt.encode("utf-8"))
        entries.append(row)
        known[(key, attempt)] = row
    write_json(target, {
        "schema": "naiwa-evolink-high131-card-repair-preparation-v1",
        "machine_id": machine_id(),
        "prepared_at_utc": existing["prepared_at_utc"],
        "updated_at_utc": utc_now(),
        "entries": entries,
        "scope": "SHA-bound HIGH art repairs. Legacy source/mascot, three-input raw-HD, explicitly verified four-input source-note-detail and source-65 pilot mask modes are distinct per entry. Raw-HD targets and additional references require fixed remote byte proof, source-derived pixel validation and full frozen prompts. Masks additionally require actual visual review, exact target-bound dimensions, RGBA 0/255 geometry and fixed remote byte proof; they are not generated masters or game payload. Preparation does not authorize or establish an image call; current tool restrictions still apply and existing attempts, prompts and rejected reviews remain retained.",
    })
    print(json.dumps({"prepared": len(entries), "indices": sorted(indices), "remote_commit": args.remote_commit, "readback": readback_path.relative_to(ROOT).as_posix(), "note_details": args.note_details, "mask": args.mask, "network_image_calls": 0}, ensure_ascii=True))


if __name__ == "__main__":
    main()
