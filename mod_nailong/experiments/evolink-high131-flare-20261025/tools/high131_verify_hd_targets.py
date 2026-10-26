import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.high131_io import write_json
from runtime.high131_prepare_hd_repairs import NOTE_INDICES
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"
MASTER_DIR = ROOT / "mod_nailong/assets/generated_fullsize"
METHOD = "Complete anonymous raw PNG download; SHA256 and byte count"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def main():
    parser = argparse.ArgumentParser(description="Verify exact public raw-HD edit targets without any image-generation call or full-archive completion claim.")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--index", action="append", type=int, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise RuntimeError("Expected a full lowercase immutable commit")
    indices = sorted(set(args.index))
    if not indices or not set(indices) <= set(NOTE_INDICES):
        raise RuntimeError("Only explicitly prepared HIGH note-repair targets are eligible")
    receipt_path = ROOT / f"runtime/high131-hd-target-readback-{args.commit}.json"
    existing = read_json(receipt_path) if receipt_path.exists() else {}
    if existing and (existing.get("commit") != args.commit or existing.get("machine_id") != machine_id()):
        raise RuntimeError("Existing target-readback receipt belongs to another machine or commit")
    receipt = {
        "schema": "high131-hd-target-readback-v1",
        "machine_id": machine_id(),
        "commit": args.commit,
        "started_at_utc": existing.get("started_at_utc", utc_now()),
        "status": "running",
        "source_indices": indices,
        "targets": existing.get("targets", {}),
        "complete_archive_verified": False,
        "full_archive_publication_and_readback_still_required": True,
        "art_approval_or_production_import_claimed": False,
        "new_image_generation_calls": 0,
        "scope": "Only the explicitly selected rejected raw-HD edit targets are downloaded and byte-verified at this public immutable commit. This supplements, and never replaces, the complete fixed-commit archive readback still being delivered separately.",
    }
    write_json(receipt_path, receipt)
    try:
        remote_head = git("ls-remote", "origin", "refs/heads/master").split()[0]
        if not re.fullmatch(r"[0-9a-f]{40}", remote_head):
            raise RuntimeError("Remote master returned an invalid commit")
        git("fetch", "origin")
        subprocess.run(["git", "merge-base", "--is-ancestor", args.commit, remote_head], cwd=ROOT, check=True)
        receipt["public_commit_ancestor_of_remote_head"] = remote_head
        scope = {row["index"]: row for row in read_json(EXPERIMENT / "scope.json")["entries"]}
        progress = {row["source_sha256"]: row for row in read_json(EXPERIMENT / "progress.json")["entries"]}
        downloaded = []
        reused = []
        for index in indices:
            source = scope[index]
            key = source["source_sha256"]
            current = progress[key]
            review = current["current_review"]
            if current["status"] != "rejected_latest_attempt" or current["current_decision"] != "rejected_for_production":
                raise RuntimeError(f"Index {index} is not a current rejected raw-HD target")
            latest = current["attempts_returned"][-1]
            if review["attempt"] != latest["attempt"] or review["review_output_sha256"] != latest["output_sha256"]:
                raise RuntimeError(f"Review and latest returned target differ for index {index}")
            digest = review["review_output_sha256"]
            target = MASTER_DIR / f"{digest}.png"
            if file_sha256(target) != digest:
                raise RuntimeError(f"Local raw-HD target differs from its SHA: {target}")
            relative = target.relative_to(ROOT).as_posix()
            blob = git("hash-object", str(target))
            tree = git("ls-tree", args.commit, "--", relative)
            if tree != f"100644 blob {blob}\t{relative}":
                raise RuntimeError(f"Pinned remote tree does not contain the exact raw-HD target: {relative}")
            url = f"https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{args.commit}/{relative}"
            previous = receipt["targets"].get(digest, {})
            if (
                previous.get("sha256") == digest
                and previous.get("path") == relative
                and previous.get("bytes") == target.stat().st_size
                and previous.get("git_blob_sha1") == blob
                and previous.get("url") == url
                and previous.get("readback_commit") == args.commit
                and previous.get("method") == METHOD
                and previous.get("png_signature_verified") is True
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
            if signature != b"\x89PNG\r\n\x1a\n" or size != target.stat().st_size or sha.hexdigest() != digest:
                raise RuntimeError(f"Remote raw-HD PNG bytes differ from the exact local target: {relative}")
            receipt["targets"][digest] = {
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
            }
            downloaded.append(index)
            write_json(receipt_path, receipt)
        receipt.update(status="verified", completed_at_utc=utc_now(), downloaded_indices=downloaded, reused_indices=reused)
        write_json(receipt_path, receipt)
        print(json.dumps({
            "status": receipt["status"],
            "commit": args.commit,
            "source_indices": indices,
            "downloaded_indices": downloaded,
            "reused_indices": reused,
            "complete_archive_verified": False,
            "new_image_generation_calls": 0,
            "proof": receipt_path.relative_to(ROOT).as_posix(),
        }, ensure_ascii=True))
    except BaseException as exc:
        receipt.update(status="failed", error=f"{type(exc).__name__}: {exc}", completed_at_utc=utc_now())
        write_json(receipt_path, receipt)
        raise


if __name__ == "__main__":
    main()
