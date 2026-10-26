import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.high131_prepare_card_repairs import revise_undispatched_prompt
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"
MODE = "raw-hd-edit-v1"
NOTE_INDICES = (40, 52, 53, 54, 57, 61, 62, 63, 64, 65, 67)


def main():
    parser = argparse.ArgumentParser(description="Prepare raw-HD localized HIGH note repairs without any image-generation call.")
    parser.add_argument("--remote-commit", required=True)
    parser.add_argument("--readback", required=True)
    parser.add_argument("--index", action="append", type=int)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.remote_commit):
        raise RuntimeError("Expected a full lowercase remote commit")
    indices = set(args.index or NOTE_INDICES)
    if not indices <= set(NOTE_INDICES):
        raise RuntimeError("Only reviewed HIGH note sources are eligible; 60 and 117 remain unresolved")
    readback_path = (ROOT / args.readback).resolve()
    readback_path.relative_to((ROOT / "runtime").resolve())
    proof = read_json(readback_path)
    if proof.get("status") != "verified" or proof.get("commit") != args.remote_commit or proof.get("machine_id") != machine_id():
        raise RuntimeError("The fixed remote original-byte proof is not verified for this machine and commit")
    committed_index = json.loads(subprocess.check_output(
        ["git", "show", f"{args.remote_commit}:mod_nailong/data/fullsize-files.json"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ))
    if proof.get("distinct_outputs") != committed_index["count"] or proof.get("original_png_bytes") != committed_index["original_png_bytes"]:
        raise RuntimeError("Remote original proof does not match the pinned fullsize index")

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
        masters = [row for row in archive if row["source_sha256"] == key and row["attempt"] == decision["attempt"] and row["output_sha256"] == digest]
        if len(masters) != 1:
            raise RuntimeError(f"Expected one retained raw-HD target for index {index}")
        master = masters[0]
        if master["output"] != decision["output"] or master["generated_fullsize_sha256"] != digest:
            raise RuntimeError(f"Raw-HD target differs from the rejected output for index {index}")
        master_path = ROOT / master["generated_fullsize_image"]
        if file_sha256(master_path) != digest:
            raise RuntimeError(f"Raw-HD target byte mismatch for index {index}")
        relative_master = master_path.relative_to(ROOT).as_posix()
        indexed = committed_index["outputs"].get(digest)
        if indexed is None or indexed["path"] != relative_master or indexed["bytes"] != master_path.stat().st_size:
            raise RuntimeError(f"Raw-HD target is not covered by the verified remote index for index {index}")
        target_url = f"https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{args.remote_commit}/{relative_master}"
        route = prepared[key]
        original_source = ROOT / source["source_png"]
        if file_sha256(original_source) != source["converted_png_sha256"]:
            raise RuntimeError(f"Original source changed for index {index}")
        observation_path = ROOT / route["observation"]
        if file_sha256(observation_path) != route["observation_sha256"]:
            raise RuntimeError(f"Source observation changed for index {index}")
        observations = [row for row in read_json(observation_path)["entries"] if row["source_sha256"] == key]
        if len(observations) != 1:
            raise RuntimeError(f"Expected one source observation for index {index}")
        observation = observations[0]
        reasons = " ".join(decision["remaining_reasons"])
        prompt = (
            "Use case: precise-object-edit. Image1 is the actual raw-HD mascot edit target with output SHA256 "
            + digest
            + ". Image2 is the exact original game portrait/card and sole authority for the original visible features and note shapes. Image3 is the user mascot identity reference.\n\n"
            + "ACTUAL OBSERVED CORRECTION: " + reasons + "\n\n"
            + "The exact original note has TWO separated irregular gray-mark groups in its upper note row and TWO separated irregular gray-mark groups in its lower row. Restore exactly TWO source-scale irregular groups in EACH row, with the original relative lengths, spacing and compact footprint. They are not generic repeated dots, uniform short dashes, long horizontal bars, extra groups or newly readable writing. Keep the lower paper blank outside the original marks and retain the original small dark right-edge tab.\n\n"
            + "Preserve every already-correct part of Image1: the yellow compact mascot identity, green-ringed black eyes, exactly one source-appropriate mouth, source-visible hair, brows and facial hair, headgear, clothing, decorations, expression, head pose, crop and lighting. Do not replace the person with a human or a generic mascot. Preserve the short broad fitted neck and correct collar without pinching, floating cloth or a cream bib.\n\n"
            + "SOURCE-VISIBLE CONTRACT FROM IMAGE2:\n"
            + observation["source_features_prompt"].strip() + "\n"
            + observation["composition_prompt"].strip() + "\n"
            + observation["background_prompt"].strip() + "\n"
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
            "repair_input_mode": MODE,
            "edit_target_image": relative_master,
            "edit_target_sha256": digest,
            "remote_commit": args.remote_commit,
            "remote_readback": readback_path.relative_to(ROOT).as_posix(),
            "remote_target_url": target_url,
            "image_urls": [target_url, route["image_urls"][0], route["image_urls"][1]],
            "ordered_input_sha256": [digest, source["converted_png_sha256"], scope["mascot_reference"]["sha256"]],
        }
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
        "scope": "SHA-bound HIGH art repairs. Legacy source/mascot and raw-HD edit-target modes are explicit per entry. Raw-HD targets require verified fixed remote original bytes and a three-input prompt. No image call is established by preparation; existing attempts, prompts and rejected reviews remain retained.",
    })
    print(json.dumps({"prepared": len(entries), "indices": sorted(indices), "remote_commit": args.remote_commit, "readback": readback_path.relative_to(ROOT).as_posix(), "network_image_calls": 0}, ensure_ascii=True))


if __name__ == "__main__":
    main()
