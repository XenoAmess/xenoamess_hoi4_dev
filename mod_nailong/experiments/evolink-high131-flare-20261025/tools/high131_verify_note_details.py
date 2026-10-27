import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.high131_io import write_json
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"
DETAIL_DIR = EXPERIMENT / "review-source-details"
METHOD = "Complete anonymous raw PNG download; SHA256 and byte count"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def main():
    parser = argparse.ArgumentParser(description="Verify exact source-only note-detail references at an immutable public commit; no image-generation call.")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--index", action="append", type=int, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise RuntimeError("Expected a full lowercase immutable commit")
    indices = sorted(set(args.index))
    if not indices or (indices not in ([40], [52]) and not set(indices) <= {65, 67}):
        raise RuntimeError("Only reviewed source-40 or source-52 note references or pilot note references for 65 and 67 are eligible")
    proof_path = ROOT / f"runtime/high131-hd-target-readback-{args.commit}.json"
    proof = read_json(proof_path)
    if proof.get("schema") != "high131-hd-target-readback-v1" or proof.get("status") != "verified":
        raise RuntimeError("Verify the current rejected raw-HD targets before adding detail references")
    if proof.get("commit") != args.commit or proof.get("machine_id") != machine_id() or proof.get("complete_archive_verified") is not False:
        raise RuntimeError("The raw-HD target proof does not match this machine, commit and scoped boundary")
    manifest_path = EXPERIMENT / (f"note-detail-sources-{indices[0]}.json" if indices in ([40], [52]) else "note-detail-sources.json")
    manifest = read_json(manifest_path)
    if manifest.get("schema") != "naiwa-high131-note-detail-sources-v1" or manifest.get("status") != "source_derivatives_visually_verified":
        raise RuntimeError("Source-detail references require actual visual review of the derivative")
    details = {row["index"]: row for row in manifest["entries"]}
    scope = {row["index"]: row for row in read_json(EXPERIMENT / "scope.json")["entries"]}
    proof["raw_target_completed_at_utc"] = proof.get("raw_target_completed_at_utc", proof.get("completed_at_utc"))
    proof["status"] = "running"
    write_json(proof_path, proof)
    downloaded = []
    reused = []
    try:
        remote_head = git("ls-remote", "origin", "refs/heads/master").split()[0]
        if not re.fullmatch(r"[0-9a-f]{40}", remote_head):
            raise RuntimeError("Remote master returned an invalid commit")
        git("fetch", "origin")
        subprocess.run(["git", "merge-base", "--is-ancestor", args.commit, remote_head], cwd=ROOT, check=True)
        proof["public_commit_ancestor_of_remote_head"] = remote_head
        for index in indices:
            row = details[index]
            source = scope[index]
            key = source["source_sha256"]
            if row["source_sha256"] != key or row["source_png"] != source["source_png"] or not row["derivative_reviewed"] or not row["reviewer"] or not row["reviewed_at_utc"]:
                raise RuntimeError(f"Source-detail identity or actual review differs for index {index}")
            source_path = ROOT / source["source_png"]
            if file_sha256(source_path) != source["converted_png_sha256"] or row["source_png_sha256"] != source["converted_png_sha256"]:
                raise RuntimeError(f"Original source changed for index {index}")
            reference = (ROOT / row["path"]).resolve()
            reference.relative_to(DETAIL_DIR.resolve())
            relative = reference.relative_to(ROOT).as_posix()
            rect = row["crop_rect"]
            scale = row["scale"]
            with Image.open(source_path) as source_image, Image.open(reference) as detail_image:
                left, top, right, bottom = rect
                expected = source_image.convert("RGBA").crop(rect).resize(((right - left) * scale, (bottom - top) * scale), Image.Resampling.NEAREST)
                if detail_image.convert("RGBA").tobytes() != expected.tobytes():
                    raise RuntimeError(f"Source-detail pixels differ from exact source crop for index {index}")
                if list(detail_image.size) != row["size"] or detail_image.mode != row["mode"]:
                    raise RuntimeError(f"Source-detail dimensions or mode changed for index {index}")
            if row["method"] != "source-crop-resize-nearest-v1" or row["role"] != "source-note-detail-reference" or row["not_generated_or_game_payload"] is not True:
                raise RuntimeError(f"Source-detail method or role changed for index {index}")
            digest = file_sha256(reference)
            if digest != row["sha256"]:
                raise RuntimeError(f"Source-detail SHA differs from manifest for index {index}")
            blob = git("hash-object", str(reference))
            tree = git("ls-tree", args.commit, "--", relative)
            if tree != f"100644 blob {blob}\t{relative}":
                raise RuntimeError(f"Pinned remote tree lacks the exact source-detail reference: {relative}")
            url = f"https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{args.commit}/{relative}"
            derivation = {
                "source_png_sha256": row["source_png_sha256"],
                "crop_rect": rect,
                "scale": scale,
                "method": row["method"],
                "derivative_reviewed": True,
                "reviewer": row["reviewer"],
                "reviewed_at_utc": row["reviewed_at_utc"],
            }
            previous = proof["targets"].get(digest, {})
            if previous and previous.get("path") != relative:
                raise RuntimeError(f"A different artifact already uses this digest: {digest}")
            if (
                previous.get("sha256") == digest
                and previous.get("path") == relative
                and previous.get("bytes") == reference.stat().st_size
                and previous.get("git_blob_sha1") == blob
                and previous.get("url") == url
                and previous.get("readback_commit") == args.commit
                and previous.get("method") == METHOD
                and previous.get("role") == row["role"]
                and previous.get("size") == row["size"]
                and previous.get("mode") == row["mode"]
                and previous.get("derivation") == derivation
                and previous.get("verified_at_utc")
            ):
                reused.append(index)
                continue
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
            if signature != b"\x89PNG\r\n\x1a\n" or size != reference.stat().st_size or sha.hexdigest() != digest:
                raise RuntimeError(f"Remote source-detail PNG differs from the reviewed local reference: {relative}")
            proof["targets"][digest] = {
                "source_index": index,
                "source_sha256": key,
                "path": relative,
                "bytes": size,
                "sha256": digest,
                "git_blob_sha1": blob,
                "url": url,
                "readback_commit": args.commit,
                "verified_at_utc": utc_now(),
                "method": METHOD,
                "remote_tree_blob_match": True,
                "local_original_matches": True,
                "png_signature_verified": True,
                "role": row["role"],
                "not_generated_or_game_payload": True,
                "size": row["size"],
                "mode": row["mode"],
                "derivation": derivation,
            }
            downloaded.append(index)
            write_json(proof_path, proof)
        proof.update(
            status="verified",
            completed_at_utc=utc_now(),
            detail_reference_completed_at_utc=utc_now(),
            detail_reference_indices=indices,
            downloaded_detail_indices=downloaded,
            reused_detail_indices=reused,
            source_detail_manifest=manifest_path.relative_to(ROOT).as_posix(),
            source_detail_manifest_sha256=file_sha256(manifest_path),
            new_image_generation_calls=0,
        )
        write_json(proof_path, proof)
        print(json.dumps({
            "status": "verified",
            "commit": args.commit,
            "detail_reference_indices": indices,
            "downloaded_detail_indices": downloaded,
            "reused_detail_indices": reused,
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
