import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import high131_hd_proof as hd_proof
from runtime.high131_io import write_json
from runtime.high131_verify_hd_targets import METHOD, git
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"
MASK_DIR = EXPERIMENT / "review-masks"


def main():
    parser = argparse.ArgumentParser(description="Verify a visually reviewed HIGH note mask at an immutable public commit; no image-generation call.")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--index", type=int, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise RuntimeError("Expected a full lowercase immutable commit")
    if args.index != 65:
        raise RuntimeError("Only the actually reviewed source-65 pilot mask is eligible")
    proof_path = ROOT / f"runtime/high131-hd-target-readback-{args.commit}.json"
    proof = read_json(proof_path)
    if proof.get("schema") != hd_proof.TARGET_PROOF_SCHEMA or proof.get("status") not in {"verified", "failed"}:
        raise RuntimeError("A completed raw-HD target proof is required before adding its mask")
    if proof.get("commit") != args.commit or proof.get("machine_id") != machine_id() or proof.get("complete_archive_verified") is not False:
        raise RuntimeError("The target proof does not match this machine, commit and scoped boundary")
    if proof.get("status") == "failed":
        proof["previous_mask_verification_failure"] = {
            "error": proof.get("error"),
            "completed_at_utc": proof.get("completed_at_utc"),
        }
    proof["mask_verification_started_at_utc"] = utc_now()
    proof["status"] = "running"
    write_json(proof_path, proof)
    downloaded = False
    reused = False
    try:
        remote_head = git("ls-remote", "origin", "refs/heads/master").split()[0]
        if not re.fullmatch(r"[0-9a-f]{40}", remote_head):
            raise RuntimeError("Remote master returned an invalid commit")
        git("fetch", "origin")
        subprocess.run(["git", "merge-base", "--is-ancestor", args.commit, remote_head], cwd=ROOT, check=True)
        proof["public_commit_ancestor_of_remote_head"] = remote_head
        source = {row["index"]: row for row in read_json(EXPERIMENT / "scope.json")["entries"]}[args.index]
        key = source["source_sha256"]
        current = {row["source_sha256"]: row for row in read_json(EXPERIMENT / "progress.json")["entries"]}[key]
        if current["status"] != "rejected_latest_attempt" or current["current_decision"] != "rejected_for_production":
            raise RuntimeError("The mask target is not a current SHA-bound rejected output")
        manifest_path = EXPERIMENT / f"note-mask-{args.index}.json"
        manifest = read_json(manifest_path)
        if manifest.get("schema") != "high131-note-inpainting-mask-v1" or manifest.get("status") != "mask_visually_verified":
            raise RuntimeError("The mask requires actual visual review")
        if manifest.get("machine_id") != machine_id() or not manifest.get("reviewer") or not manifest.get("reviewed_at_utc"):
            raise RuntimeError("The mask review lacks its machine, reviewer or time")
        if manifest.get("index") != args.index or manifest.get("source_sha256") != key or manifest.get("source_png_sha256") != source["converted_png_sha256"]:
            raise RuntimeError("The mask is bound to another source")
        target_digest = current["current_review"]["review_output_sha256"]
        if manifest.get("target_sha256") != target_digest:
            raise RuntimeError("The mask target differs from the current rejected master")
        target = ROOT / f"mod_nailong/assets/generated_fullsize/{target_digest}.png"
        hd_proof.validate_remote_target(proof, args.commit, target, target_digest, root=ROOT)
        source_path = ROOT / source["source_png"]
        if file_sha256(source_path) != source["converted_png_sha256"]:
            raise RuntimeError("The exact original source bytes changed")
        details = {row["index"]: row for row in read_json(EXPERIMENT / "note-detail-sources.json")["entries"]}
        detail = details[args.index]
        if detail["source_sha256"] != key or detail["source_png_sha256"] != source["converted_png_sha256"]:
            raise RuntimeError("The existing note-detail reference is bound to another source")
        hd_proof.validate_remote_reference(proof, args.commit, ROOT / detail["path"], detail["sha256"], source_path, root=ROOT)
        mask = (ROOT / manifest["mask_file"]).resolve()
        mask.relative_to(MASK_DIR.resolve())
        relative = mask.relative_to(ROOT).as_posix()
        digest = file_sha256(mask)
        if digest != manifest.get("mask_sha256") or manifest.get("role") != "inpainting-mask" or manifest.get("not_generated_or_game_payload") is not True:
            raise RuntimeError("The mask bytes or reference role differ from the reviewed manifest")
        blob = git("hash-object", str(mask))
        tree = git("ls-tree", args.commit, "--", relative)
        if tree != f"100644 blob {blob}\t{relative}":
            raise RuntimeError(f"Pinned remote tree lacks the exact reviewed mask: {relative}")
        url = f"https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{args.commit}/{relative}"
        expected = {
            "source_index": args.index,
            "source_sha256": key,
            "path": relative,
            "bytes": mask.stat().st_size,
            "sha256": digest,
            "git_blob_sha1": blob,
            "url": url,
            "readback_commit": args.commit,
            "method": METHOD,
            "remote_tree_blob_match": True,
            "local_original_matches": True,
            "png_signature_verified": True,
            "role": "inpainting-mask",
            "not_generated_or_game_payload": True,
            "target_sha256": target_digest,
            "no_generated_master_pixels_modified": True,
            "mask_manifest": manifest_path.relative_to(ROOT).as_posix(),
            "mask_manifest_sha256": file_sha256(manifest_path),
            "size": manifest["size"],
            "mode": manifest["mode"],
            "rects": manifest["rects"],
            "alpha_extrema": manifest["alpha_extrema"],
            "transparent_pixels": manifest["transparent_pixels"],
            "opaque_pixels": manifest["opaque_pixels"],
        }
        previous = proof["targets"].get(digest, {})
        if previous.get("verified_at_utc") and all(previous.get(name) == value for name, value in expected.items()):
            hd_proof.validate_remote_mask(proof, args.commit, mask, digest, target, target_digest, root=ROOT)
            reused = True
        else:
            sha = hashlib.sha256()
            size = 0
            signature = bytearray()
            with requests.get(url, stream=True, timeout=(30, 120)) as response:
                response.raise_for_status()
                for chunk in response.iter_content(1024 * 1024):
                    if len(signature) < 8:
                        signature.extend(chunk[:8 - len(signature)])
                    sha.update(chunk)
                    size += len(chunk)
            if signature != b"\x89PNG\r\n\x1a\n" or size != mask.stat().st_size or sha.hexdigest() != digest:
                raise RuntimeError(f"Remote mask PNG differs from the reviewed local mask: {relative}")
            proof["targets"][digest] = {**expected, "verified_at_utc": utc_now()}
            hd_proof.validate_remote_mask(proof, args.commit, mask, digest, target, target_digest, root=ROOT)
            downloaded = True
        proof.update(
            status="verified",
            completed_at_utc=utc_now(),
            mask_verification_completed_at_utc=utc_now(),
            mask_verification_indices=[args.index],
            downloaded_mask_indices=[args.index] if downloaded else [],
            reused_mask_indices=[args.index] if reused else [],
            mask_manifest=manifest_path.relative_to(ROOT).as_posix(),
            mask_manifest_sha256=file_sha256(manifest_path),
            complete_archive_verified=False,
            new_image_generation_calls=0,
        )
        write_json(proof_path, proof)
        print(json.dumps({
            "status": "verified",
            "commit": args.commit,
            "index": args.index,
            "mask_sha256": digest,
            "downloaded": downloaded,
            "reused": reused,
            "complete_archive_verified": False,
            "new_image_generation_calls": 0,
            "proof": proof_path.relative_to(ROOT).as_posix(),
        }, ensure_ascii=True))
    except BaseException as exc:
        proof.update(status="failed", error=f"{type(exc).__name__}: {exc}", completed_at_utc=utc_now())
        write_json(proof_path, proof)
        raise


if __name__ == "__main__":
    main()
