"""Preserve byte-identical imagegen PNGs as verified GitHub art attachments.

The ZIP is streamed from existing files, without a second local PNG/ZIP copy.
This is file archiving, never image generation or image editing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json

REPO = "XenoAmess/xenoamess_hoi4_dev"
MOD = ROOT / "mod_nailong"
INVENTORY = ROOT / "runtime/fullsize-master-inventory.json"
INDEX = MOD / "data/fullsize-archives.json"
BLOCK = 1024 * 1024


def inventory():
    """Adopt only PNGs matching an already recorded project fullsize SHA."""
    expected = set()
    current = {}
    provenance = {}

    def remember(digest, ref):
        expected.add(digest)
        provenance.setdefault(digest, []).append(ref)

    for key, row in read_json(MOD / "data/generated.json")["portraits"].items():
        digest = row["generated_fullsize_sha256"]
        current[key] = digest
        remember(digest, {"source_sha256": key, "record": "data/generated.json", "revision": "current"})
        for revision in row.get("revision_history", []):
            if revision.get("previous_fullsize_sha256"):
                remember(revision["previous_fullsize_sha256"], {"source_sha256": key, "record": "data/generated.json", "revision": "superseded"})
    for path in (MOD / "data/generation-requests").glob("*.json"):
        for attempt in read_json(path)["attempts"]:
            if attempt.get("fullsize_sha256"):
                remember(attempt["fullsize_sha256"], {"source_sha256": path.stem, "journal": path.relative_to(MOD).as_posix(), "attempt": attempt.get("number"), "prompt_sha256": attempt.get("prompt_sha256")})

    def experiment_hashes(value, ref):
        if isinstance(value, dict):
            for name, item in value.items():
                if "fullsize" in name and "sha" in name and isinstance(item, str) and re.fullmatch("[0-9a-f]{64}", item):
                    remember(item, {"experiment": ref, "field": name})
                if isinstance(item, (dict, list)):
                    experiment_hashes(item, ref)
        elif isinstance(value, list):
            for item in value:
                experiment_hashes(item, ref)

    for path in (MOD / "experiments").rglob("*.json"):
        experiment_hashes(read_json(path), path.relative_to(MOD).as_posix())
    paths = set()

    def origin_paths(value):
        if isinstance(value, dict):
            for name, item in value.items():
                if name in {"path", "source", "image"} and isinstance(item, str) and item.lower().endswith(".png"):
                    path = Path(item)
                    if path.is_absolute() and ".codex" in path.parts and "generated_images" in path.parts:
                        paths.add(path)
                if name == "output_hint" and isinstance(item, str):
                    match = re.search(r" as (C:\\[^\n]+?\.png) by default\.", item)
                    if match:
                        paths.add(Path(match.group(1)))
                if isinstance(item, (dict, list)):
                    origin_paths(item)
        elif isinstance(value, list):
            for item in value:
                origin_paths(item)

    receipts = list((ROOT / "runtime/generated-origins").rglob("*.json")) + list((ROOT / "runtime").glob("*result*.json"))
    for path in receipts:
        if path.stat().st_size <= BLOCK:
            origin_paths(read_json(path))
    # Older source-key receipts were overwritten on revision. Search only folders
    # already proved by project receipts, and accept exact recorded digests only.
    for folder in {path.parent for path in paths}:
        paths.update(folder.glob("*.png"))
    if len(paths) > 100000:
        raise SystemExit("Inventory metadata budget exceeded")
    from PIL import Image
    found = {}
    for path in sorted(paths):
        if not path.is_file():
            continue
        digest = file_sha256(path)
        if digest not in expected or digest in found:
            continue
        with Image.open(path) as image:
            size, mode = list(image.size), image.mode
        found[digest] = {"path": str(path), "sha256": digest, "bytes": path.stat().st_size, "size": size, "mode": mode, "provenance": provenance[digest]}
    result = {"schema": "naiwa-fullsize-inventory-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(), "scope": "Recorded project digests only; read-only search of receipt-proven imagegen folders", "canonical_sources": len(current), "expected_distinct_fullsize_outputs": len(expected), "recoverable_distinct_fullsize_outputs": len(found), "recoverable_bytes": sum(item["bytes"] for item in found.values()), "current_masters_found": sum(digest in found for digest in current.values()), "current_masters_missing": [{"source_sha256": key, "fullsize_sha256": digest} for key, digest in current.items() if digest not in found], "historical_fullsize_sha_missing": sorted(expected - found.keys()), "masters": list(found.values())}
    write_json(INVENTORY, result)
    print(json.dumps({k: v for k, v in result.items() if k not in {"masters", "current_masters_missing", "historical_fullsize_sha_missing"}}, ensure_ascii=False))
    return result


class StoredZip:
    """Repeatable bounded-memory ZIP stream; standard stored entries, no ZIP64.

    Snapshot identity is checked both before construction and while streaming.
    A changed source aborts the upload; a successful HTTP response alone is not
    treated as a verified remote archive.
    """
    def __init__(self, entries):
        self.entries = []
        self.length = 22
        for name, source, expected_sha in entries:
            encoded = name.encode("ascii")
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError("Unsafe archive entry")
            crc, size, digest = 0, 0, hashlib.sha256()
            for chunk in self.chunks(source):
                crc = zlib.crc32(chunk, crc)
                size += len(chunk)
                digest.update(chunk)
            if digest.hexdigest() != expected_sha:
                raise ValueError("Source SHA changed before archive construction")
            self.entries.append((encoded, source, size, crc, expected_sha))
            self.length += size + 30 + 46 + 2 * len(encoded)
        if self.length >= 0xFFFFFFFF or len(self.entries) >= 65535:
            raise ValueError("Split the archive: this writer deliberately refuses ZIP64")
        self.sha256 = None

    @staticmethod
    def chunks(source):
        if isinstance(source, bytes):
            yield source
        else:
            with Path(source).open("rb") as handle:
                while chunk := handle.read(BLOCK):
                    yield chunk

    def __len__(self):
        return self.length

    def _stream(self):
        offset = 0
        directory = []
        for name, source, size, crc, expected in self.entries:
            yield struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0, 0, 0, 33, crc, size, size, len(name), 0) + name
            digest, observed_size = hashlib.sha256(), 0
            for chunk in self.chunks(source):
                digest.update(chunk)
                observed_size += len(chunk)
                yield chunk
            if observed_size != size or digest.hexdigest() != expected:
                raise ValueError("Source changed during archive streaming")
            directory.append(struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, 0, 0, 0, 33, crc, size, size, len(name), 0, 0, 0, 0, 0, offset) + name)
            offset += 30 + len(name) + size
        start = offset
        for entry in directory:
            yield entry
            offset += len(entry)
        yield struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(directory), len(directory), offset - start, start, 0)

    def __iter__(self):
        digest, size = hashlib.sha256(), 0
        for chunk in self._stream():
            digest.update(chunk)
            size += len(chunk)
            yield chunk
        if size != self.length:
            raise ValueError("ZIP stream length mismatch")
        self.sha256 = digest.hexdigest()


def archive(tag):
    import requests
    if not re.fullmatch(r"art-masters-[0-9]{3}", tag):
        raise SystemExit("Use an art-masters-NNN tag, distinct from mod releases")
    snap = inventory()
    if snap["current_masters_missing"] or snap["historical_fullsize_sha_missing"]:
        raise SystemExit("Recorded fullsize output missing; archive stopped before publishing")
    previous = read_json(INDEX) if INDEX.exists() else {"schema": "naiwa-fullsize-archives-v1", "archives": [], "outputs": {}}
    if any(item["tag"] == tag for item in previous["archives"]):
        raise SystemExit("Archive already registered; use a new tag for new masters")
    selected = [item for item in snap["masters"] if item["sha256"] not in previous["outputs"]]
    if not selected:
        raise SystemExit("No unarchived masters")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    manifest = {"schema": "naiwa-fullsize-pack-v1", "machine_id": snap["machine_id"], "observed_at_utc": snap["observed_at_utc"], "tag": tag, "source_commit": commit, "generated_record_sha256": file_sha256(MOD / "data/generated.json"), "count": len(selected), "png_bytes": sum(item["bytes"] for item in selected), "outputs": [{k: v for k, v in item.items() if k != "path"} for item in selected]}
    body = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    entries = [("index.json", body, hashlib.sha256(body).hexdigest())]
    entries += [("png/" + item["sha256"] + ".png", Path(item["path"]), item["sha256"]) for item in sorted(selected, key=lambda item: item["sha256"])]
    stream = StoredZip(entries)
    # No ZIP/PNG copy is written locally. The stream is read twice: once for an
    # expected archive digest, then for upload. Memory is bounded by BLOCK.
    for _ in stream:
        pass
    expected = stream.sha256
    name = tag + ".zip"
    print(f"Prepared {len(selected)} original PNGs; {len(stream)} archive bytes; SHA256 {expected}", flush=True)
    token = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    session = requests.Session()
    session.headers.update(Authorization="Bearer " + token, Accept="application/vnd.github+json", **{"X-GitHub-Api-Version": "2022-11-28"})
    api = "https://api.github.com/repos/" + REPO
    response = session.get(api + "/releases/tags/" + tag, timeout=(30, 60))
    if response.status_code == 404:
        response = session.post(api + "/releases", json={"tag_name": tag, "target_commitish": commit, "name": "Generated portrait masters " + tag[-3:], "body": "Development art archive: original full-size imagegen PNG bytes, including superseded experiments and images pending visual review. This is not a playable mod release. ZIP index links each PNG SHA to project generation records.\n\nZIP SHA-256: `" + expected + "`", "draft": True, "prerelease": True}, timeout=(30, 60))
    response.raise_for_status()
    release = response.json()
    matching = [item for item in release["assets"] if item["name"] == name]
    if matching:
        asset = matching[0]
        if asset["size"] != len(stream):
            raise SystemExit("Existing asset differs in size; refusing replacement")
    else:
        url = release["upload_url"].split("{")[0] + "?name=" + quote(name)
        response = session.post(url, data=stream, headers={"Content-Type": "application/zip", "Content-Length": str(len(stream))}, timeout=(30, 180))
        response.raise_for_status()
        asset = response.json()
    print("Upload present; verifying authenticated download", flush=True)

    def verify(client, url, headers=None):
        digest, count = hashlib.sha256(), 0
        with client.get(url, headers=headers, stream=True, timeout=(30, 180)) as download:
            download.raise_for_status()
            for chunk in download.iter_content(BLOCK):
                digest.update(chunk)
                count += len(chunk)
        if count != len(stream) or digest.hexdigest() != expected:
            raise SystemExit("Remote archive bytes/SHA mismatch; not registering backup")

    verify(session, asset["url"], {"Accept": "application/octet-stream"})
    if release["draft"]:
        response = session.patch(api + "/releases/" + str(release["id"]), json={"draft": False, "prerelease": True, "make_latest": "false"}, timeout=(30, 60))
        response.raise_for_status()
        release = response.json()
    print("Published art attachment; verifying anonymous download", flush=True)
    with requests.Session() as anonymous:
        verify(anonymous, asset["browser_download_url"])
    receipt = {"tag": tag, "release_url": release["html_url"], "download_url": asset["browser_download_url"], "asset_id": asset["id"], "png_count": len(selected), "png_bytes": manifest["png_bytes"], "archive_bytes": len(stream), "archive_sha256": expected, "manifest_sha256": hashlib.sha256(body).hexdigest(), "source_commit": commit, "machine_id": machine_id(), "verified_at_utc": utc_now(), "verification": "Authenticated and anonymous complete streamed downloads, exact bytes and SHA256", "local_archive_copy_created": False}
    previous["archives"].append(receipt)
    for item in selected:
        previous["outputs"][item["sha256"]] = {"archive_tag": tag, "entry": "png/" + item["sha256"] + ".png", "bytes": item["bytes"], "size": item["size"]}
    write_json(INDEX, previous)
    write_json(ROOT / "runtime" / (tag + "-verification.json"), receipt)
    print(json.dumps(receipt, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inventory")
    upload = commands.add_parser("archive")
    upload.add_argument("--tag", required=True)
    args = parser.parse_args()
    inventory() if args.command == "inventory" else archive(args.tag)


if __name__ == "__main__":
    main()
