"""Locate recorded imagegen originals and preserve them as ordinary Git files.

Legacy ZIP support remains for historical archive verification.
Release uploads are disabled by the user's direct-Git instruction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import time
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json

REPO = "XenoAmess/xenoamess_hoi4_dev"
MOD = ROOT / "mod_nailong"
INVENTORY = ROOT / "runtime/fullsize-master-inventory.json"
INDEX = MOD / "data/fullsize-archives.json"
BLOCK = 1024 * 1024


def recorded_outputs(mod=MOD):
    """Return current, superseded, request and experimental output digests."""
    expected = set()
    current = {}
    provenance = {}

    def remember(digest, ref):
        expected.add(digest)
        provenance.setdefault(digest, []).append(ref)

    for key, row in read_json(mod / "data/generated.json")["portraits"].items():
        digest = row["generated_fullsize_sha256"]
        current[key] = digest
        remember(digest, {"source_sha256": key, "record": "data/generated.json", "revision": "current"})
        for revision in row.get("revision_history", []):
            if revision.get("previous_fullsize_sha256"):
                remember(revision["previous_fullsize_sha256"], {"source_sha256": key, "record": "data/generated.json", "revision": "superseded"})
    for path in (mod / "data/generation-requests").glob("*.json"):
        for attempt in read_json(path)["attempts"]:
            if attempt.get("fullsize_sha256"):
                remember(attempt["fullsize_sha256"], {"source_sha256": path.stem, "journal": path.relative_to(mod).as_posix(), "attempt": attempt.get("number"), "prompt_sha256": attempt.get("prompt_sha256")})

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

    for path in (mod / "experiments").rglob("*.json"):
        experiment_hashes(read_json(path), path.relative_to(mod).as_posix())
    return expected, current, provenance


def inventory():
    """Adopt only PNGs matching an already recorded project fullsize SHA."""
    deadline = time.monotonic() + 120
    expected, current, provenance = recorded_outputs()
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
    paths.update((MOD / 'assets/generated_fullsize').glob('*.png'))
    # Older source-key receipts were overwritten on revision. Search only folders
    # already proved by project receipts, and accept exact recorded digests only.
    for folder in {path.parent for path in paths}:
        paths.update(folder.glob("*.png"))
    if len(paths) > 100000:
        raise SystemExit("Inventory metadata budget exceeded")
    from PIL import Image
    found = {}
    canonical = MOD / 'assets/generated_fullsize'
    # Hash retained project originals first. Once every recorded digest is
    # found, receipt-proven cache copies cannot add another required output.
    for path in sorted(paths, key=lambda p: (p.parent != canonical, str(p))):
        if expected <= found.keys():
            break
        if time.monotonic() > deadline:
            raise SystemExit('Inventory time budget exceeded; no missing-file conclusion published')
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
    raise SystemExit('Release uploads disabled: use sync-git, then ordinary Git commit/push and remote PNG byte verification')


def link_current():
    from mod_nailong.tools.portraits import record_fullsize_origin
    snap = inventory()
    if snap['current_masters_missing']:
        raise SystemExit('Current master missing; no lower-resolution substitution allowed')
    found = {item['sha256']: item for item in snap['masters']}
    count = 0
    for key, row in read_json(MOD/'data/generated.json')['portraits'].items():
        record_fullsize_origin(key, Path(found[row['generated_fullsize_sha256']]['path']))
        count += 1
    write_json(ROOT/'runtime/fullsize-workspace-links.json', {'machine_id': machine_id(), 'observed_at_utc': utc_now(), 'linked_current_masters': count, 'physical_png_copies_created': 0, 'method': 'Same-volume content-addressed hardlinks; byte SHA checked; no in-place edits', 'review_at_utc': (datetime.now(timezone.utc)+timedelta(days=7)).isoformat()})
    print(f'{count} current fullsize masters now present in project assets/generated_fullsize; no extra physical PNG copy')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inventory")
    commands.add_parser("link-current")
    commands.add_parser("sync-git")
    commands.add_parser("audit-git")
    verify = commands.add_parser("verify-tree")
    verify.add_argument("--commit", default="HEAD")
    upload = commands.add_parser("archive")
    upload.add_argument("--tag", required=True)
    args = parser.parse_args()
    if args.command == 'inventory': inventory()
    elif args.command == 'link-current': link_current()
    elif args.command == 'sync-git':
        from mod_nailong.tools.master_files import sync_git
        sync_git()
    elif args.command == 'audit-git':
        from mod_nailong.tools.master_files import audit_files
        print({'verified_workspace_masters': audit_files()['count']})
    elif args.command == 'verify-tree':
        from mod_nailong.tools.master_files import verify_tree
        verify_tree(args.commit)
    else: archive(args.tag)


if __name__ == "__main__":
    main()
