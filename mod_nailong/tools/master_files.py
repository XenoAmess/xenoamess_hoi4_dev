"""Keep byte-identical imagegen originals in ordinary Git, with provenance.

No generation, image editing, LFS, ZIP creation or Release uploads occur here.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PIL import Image
from tools.common import ROOT, file_sha256, read_json, write_json

MOD = ROOT / 'mod_nailong'
INDEX = MOD / 'data/fullsize-files.json'


def master_path(digest):
    if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Invalid fullsize SHA256')
    return 'mod_nailong/assets/generated_fullsize/' + digest + '.png'


def recorded_master_candidates(root):
    """Locate complete retained candidates; sync_git still verifies every byte.

    This is not a verified inventory or a checksum cache. If any recorded path
    is absent, retain the full receipt-based recovery search.
    """
    from mod_nailong.tools.master_archive import recorded_outputs
    expected, current, provenance = recorded_outputs(root / 'mod_nailong')
    paths = {digest: root / master_path(digest) for digest in expected}
    if any(not path.is_file() for path in paths.values()):
        return None
    masters = []
    for digest, path in sorted(paths.items()):
        with Image.open(path) as image:
            size, mode = list(image.size), image.mode
        masters.append({'path': str(path), 'sha256': digest,
                        'bytes': path.stat().st_size, 'size': size, 'mode': mode,
                        'provenance': provenance[digest]})
    return {'scope': 'Unverified recorded-path candidates only; every source must pass sync_git full SHA256 and PNG verification before adoption/index publication.',
            'current_masters_missing': [], 'historical_fullsize_sha_missing': [],
            'masters': masters}


def sync_git(snapshot=None, root=ROOT):
    """Adopt only recorded, byte-verified originals; never overwrite a master."""
    if snapshot is None:
        snapshot = recorded_master_candidates(root)
        if snapshot is None:
            from mod_nailong.tools.master_archive import inventory
            snapshot = inventory()
    if snapshot['current_masters_missing'] or snapshot['historical_fullsize_sha_missing']:
        raise ValueError('Recorded masters are missing; migration must remain incomplete')
    entries = {}
    for item in sorted(snapshot['masters'], key=lambda item: item['sha256']):
        digest = item['sha256']
        source = Path(item['path'])
        if file_sha256(source) != digest:
            raise ValueError('Original changed before adoption: ' + digest)
        target = root / master_path(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            os.link(source, target)
        # The source was just fully hashed. A target naming that same file
        # (including a new hardlink) contains those exact bytes; independent
        # existing targets still need their own complete checksum.
        if target.stat().st_size != item['bytes'] or (not target.samefile(source) and file_sha256(target) != digest):
            raise ValueError('Git master bytes do not match: ' + digest)
        with Image.open(target) as image:
            image.verify()
        entries[digest] = {
            'path': target.relative_to(root).as_posix(),
            'bytes': item['bytes'], 'size': item['size'], 'mode': item['mode'],
            'provenance': item['provenance'],
        }
    index = {'schema': 'naiwa-fullsize-git-files-v1',
             'storage': 'ordinary Git blobs containing original PNG bytes',
             'count': len(entries), 'original_png_bytes': sum(v['bytes'] for v in entries.values()),
             'outputs': entries}
    write_json(root / 'mod_nailong/data/fullsize-files.json', index)
    generated_path = root / 'mod_nailong/data/generated.json'
    generated = read_json(generated_path)
    generated_changed = False
    for row in generated['portraits'].values():
        expected_path = master_path(row['generated_fullsize_sha256'])
        if row.get('generated_fullsize_image') != expected_path:
            row['generated_fullsize_image'] = expected_path
            generated_changed = True
        for revision in row.get('revision_history', []):
            if revision.get('previous_fullsize_sha256'):
                expected_path = master_path(revision['previous_fullsize_sha256'])
                if revision.get('previous_fullsize_image') != expected_path:
                    revision['previous_fullsize_image'] = expected_path
                    generated_changed = True
    if generated_changed:
        write_json(generated_path, generated)
    for path in (root / 'mod_nailong/data/generation-requests').glob('*.json'):
        journal = read_json(path)
        changed = False
        for attempt in journal['attempts']:
            if attempt.get('fullsize_sha256'):
                expected_path = master_path(attempt['fullsize_sha256'])
                if attempt.get('fullsize_image') != expected_path:
                    attempt['fullsize_image'] = expected_path
                    changed = True
        if changed:
            write_json(path, journal)
    print({'masters': index['count'], 'original_png_bytes': index['original_png_bytes'],
           'storage': index['storage'], 'remote_verification': 'not implied by local sync'})
    return index


def audit_files(root=ROOT):
    """Require every known output, including history and experiments, in Git files."""
    from mod_nailong.tools.master_archive import recorded_outputs
    expected, _, _ = recorded_outputs(root / 'mod_nailong')
    index = read_json(root / 'mod_nailong/data/fullsize-files.json')
    if set(index['outputs']) != expected:
        raise ValueError('Fullsize Git index does not match all recorded outputs')
    for digest, entry in index['outputs'].items():
        if entry['path'] != master_path(digest):
            raise ValueError('Unexpected fullsize path')
        path = root / entry['path']
        if path.stat().st_size != entry['bytes'] or file_sha256(path) != digest:
            raise ValueError('Changed or missing original PNG: ' + entry['path'])
    if index['count'] != len(expected) or index['original_png_bytes'] != sum(e['bytes'] for e in index['outputs'].values()):
        raise ValueError('Inconsistent fullsize totals')
    return index


def verify_tree(commit='HEAD', root=ROOT, index=None):
    """Stream real Git blobs, checking SHA256/size and rejecting pointer files."""
    index = audit_files(root) if index is None else index
    full_commit = subprocess.check_output(['git', 'rev-parse', commit + '^{commit}'], cwd=root, text=True).strip()
    process = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=root,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    results = {}
    try:
        for digest, entry in sorted(index['outputs'].items()):
            process.stdin.write((full_commit + ':' + entry['path'] + '\n').encode('utf-8'))
            process.stdin.flush()
            header = process.stdout.readline().decode('ascii').strip().split()
            if len(header) != 3 or header[1] != 'blob' or int(header[2]) != entry['bytes']:
                raise ValueError('Missing/incorrect Git PNG blob: ' + entry['path'])
            remaining = entry['bytes']
            sha = hashlib.sha256()
            while remaining:
                block = process.stdout.read(min(1024 * 1024, remaining))
                if not block:
                    raise ValueError('Truncated Git blob')
                sha.update(block)
                remaining -= len(block)
            if process.stdout.read(1) != b'\n' or sha.hexdigest() != digest:
                raise ValueError('Git master differs from original: ' + entry['path'])
            results[digest] = header[0]
    finally:
        process.stdin.close()
        process.stdout.close()
        process.wait()
    print({'commit': full_commit, 'verified_original_png_blobs': len(results),
           'original_png_bytes': index['original_png_bytes']})
    return full_commit, results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['sync-git', 'audit', 'verify-tree'])
    parser.add_argument('--commit', default='HEAD')
    args = parser.parse_args()
    if args.command == 'sync-git':
        sync_git()
    elif args.command == 'verify-tree':
        verify_tree(args.commit)
    else:
        index = audit_files()
        print({'verified_workspace_masters': index['count']})


if __name__ == '__main__':
    main()
