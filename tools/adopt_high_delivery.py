"""Adopt an already published HIGH delivery into a live workspace, without Git.

This reconciles metadata and copies byte-identical previews. It creates no image
requests, changes no LOW row, and retains an exact backup before any overwrite.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now
from mod_nailong.tools.art_contract import portrait_ready

EXPERIMENT = 'mod_nailong/experiments/evolink-high131-flare-20261025'
GENERATED = 'mod_nailong/data/generated.json'
QUEUE = 'mod_nailong/data/image-retry-queue.json'
INDEX = 'mod_nailong/data/fullsize-files.json'
COMMIT = '9db7c7e069ea73e7d72dccc1975f4f08e994b239'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encode(body):
    return (json.dumps(body, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(root, relative):
    path = (root / relative).resolve()
    require(not Path(relative).is_absolute() and path.is_relative_to(root.resolve()),
            'Unsafe project path: ' + str(relative))
    return path


def assert_history_retained(old, new):
    if old is None or old == new:
        return
    history = new.get('revision_history', [])
    prior = old.get('revision_history', [])
    require(len(history) >= len(prior), 'Incoming HIGH drops prior revisions')
    for before, after in zip(prior, history):
        normalized = dict(before)
        if 'previous_fullsize_image' not in normalized and after.get('previous_fullsize_image'):
            expected = 'mod_nailong/assets/generated_fullsize/' + str(before.get('previous_fullsize_sha256')) + '.png'
            require(after['previous_fullsize_image'] == expected, 'Invalid historical fullsize path')
            normalized['previous_fullsize_image'] = expected
        require(normalized == after, 'Incoming HIGH changes prior revisions')
    require(any(r.get('previous_fullsize_sha256') == old.get('generated_fullsize_sha256')
                and r.get('previous_image_sha256') == old.get('image_sha256')
                and r.get('previous_prompt') == old.get('prompt') for r in history[len(prior):]),
            'Incoming HIGH does not preserve the current output and actual prompt')


def adopt_portraits(live, published, keys):
    result = copy.deepcopy(live)
    for key in keys:
        row = published['portraits'][key]
        require(row.get('source_sha256') == key and portrait_ready(row), 'Unapproved HIGH: ' + key)
        assert_history_retained(live['portraits'].get(key), row)
        result['portraits'][key] = copy.deepcopy(row)
    return result


def adopt_queue(live, published, keys):
    result = copy.deepcopy(live)
    for key in keys:
        old = live['sources'].get(key, {})
        new = published['sources'][key]
        require(new.get('state', '').startswith('approved_external_'), 'Incoming HIGH is not approved')
        require(old.get('retries_used', 0) == new.get('retries_used', 0), 'Retry consumption differs')
        # Preserve the entire live retry history and policy fields; accept only
        # the explicit completed-delivery state/output fields.
        fields = {'state', 'output_sha256', 'generated_at_utc', 'approved_at_utc',
                  'approved_image_sha256', 'external_task_id', 'external_execution',
                  'external_review', 'external_art_repair'}
        merged = copy.deepcopy(old)
        for field, value in new.items():
            if field in fields or field not in merged:
                merged[field] = copy.deepcopy(value)
        result['sources'][key] = merged
    return result


def assert_journal_retained(live, published):
    old = live.get('attempts', [])
    new = published['attempts']
    require(new[:len(old)] == old, 'Incoming journal changes or drops live attempts')
    require(new and new[-1].get('status') == 'approved', 'Incoming journal is not approved')


def assert_unchanged(root, fingerprints):
    for relative, expected in fingerprints.items():
        path = safe_path(root, relative)
        actual = file_sha256(path) if path.exists() else None
        require(actual == expected, 'Concurrent modification: ' + relative)


def check_bound_files(root, body, planned_files=None):
    """Validate path/SHA pairs in the existing import marker and final attempt."""
    checked = set()
    aliases = {'prompt': 'prompt_file', 'output': 'output', 'fullsize': 'fullsize_image'}
    for name, expected in body.items():
        if not name.endswith('_sha256') or not expected:
            continue
        stem = name[:-7]
        relative = body.get(aliases.get(stem, stem))
        if isinstance(relative, str) and ('/' in relative or '\\' in relative):
            planned = (planned_files or {}).get(relative)
            actual = digest(planned) if planned is not None else file_sha256(safe_path(root, relative))
            require(actual == expected,
                    'Bound evidence changed: ' + relative)
            checked.add(relative)
    return checked


def published_preview_files(root, source, rows, cache):
    def obtain(row):
        relative, expected = row['image'], row['image_sha256']
        cached = cache / (row['source_sha256'] + '.png')
        for candidate in (safe_path(source, relative), safe_path(root, relative), cached):
            if candidate.is_file():
                data = candidate.read_bytes()
                if digest(data) == expected:
                    return relative, data
        url = 'https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/' + COMMIT + '/' + relative
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read(2 * 1024**2)
            require(not response.read(1), 'Preview response exceeds bounded size')
        require(digest(data) == expected, 'Published preview SHA mismatch: ' + relative)
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(data)
        return relative, data
    with ThreadPoolExecutor(max_workers=8) as executor:
        return dict(executor.map(obtain, rows))


def counts(priority, generated, exceptions):
    approved = {k for k, r in generated['portraits'].items() if portrait_ready(r)}
    sources = priority['sources']
    high = {k for k, r in sources.items() if r['high_priority']}
    low = set(sources) - high
    return {'high_approved_persons': len(high & approved), 'high_total': len(high),
            'high_preserved_nonperson_exceptions': len(high & exceptions),
            'high_covered': len(high & (approved | exceptions)),
            'low_approved': len(low & approved), 'low_total': len(low),
            'covered_total': len(set(sources) & (approved | exceptions)),
            'total': len(sources), 'remaining_low_keys': sorted(low - approved)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-verification', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = ROOT.resolve()
    output = args.output.resolve()
    require(output.is_relative_to(root) and not output.exists(), 'Use a new receipt path inside the project')
    proof = read_json(args.source_verification)
    require(proof['status'] == 'verified_fixed_public_source' and proof['commit'] == COMMIT,
            'A complete fixed-commit source proof is required')
    require(proof['machine_id'] == machine_id(), 'Wrong source verification machine')
    source = Path(proof['source_root']).resolve()
    verified = {row['path']: row for row in proof['files']}
    for relative, row in verified.items():
        path = safe_path(source, relative)
        require(path.stat().st_size == row['bytes'] and file_sha256(path) == row['sha256'],
                'Published source changed: ' + relative)
    for path in (root / 'runtime/production-queue/dispatch').glob('*.json'):
        require(read_json(path).get('status') != 'calling', 'Image call still in progress')
    approved = read_json(source / EXPERIMENT / 'approved-masters.json')['entries']
    keys = {row['source_sha256'] for row in approved}
    require(len(approved) == len(keys) == 127, 'Expected 127 unique approved HIGH sources')
    nonperson_relative = EXPERIMENT + '/nonperson-scope-decision.json'
    nonperson = read_json(source / nonperson_relative)
    require(nonperson['decision'] == 'preserved_original_nonperson_exception'
            and nonperson['canonical_generated_row_must_not_be_fabricated'] is True
            and {r['index'] for r in nonperson['entries']} == {78, 125, 129, 131},
            'Nonperson scope is not the explicit four original-preservation exceptions')
    exceptions = {r['source_sha256'] for r in nonperson['entries']}
    initial_bytes = (root / GENERATED).read_bytes()
    old = json.loads(initial_bytes)
    initial_fingerprints = {GENERATED: digest(initial_bytes)}
    published = read_json(source / GENERATED)
    require(not exceptions.intersection(old['portraits']), 'Fabricated nonperson row')
    require(not exceptions.intersection(published['portraits']), 'Published nonperson row')
    new = adopt_portraits(old, published, keys)
    initial_bytes = (root / QUEUE).read_bytes()
    old_queue = json.loads(initial_bytes)
    initial_fingerprints[QUEUE] = digest(initial_bytes)
    new_queue = adopt_queue(old_queue, read_json(source / QUEUE), keys)
    previews = published_preview_files(root, source, [new['portraits'][r['source_sha256']] for r in approved],
                                       output.parent / 'published-previews')
    files = {GENERATED: encode(new), QUEUE: encode(new_queue)}
    fingerprints = {}
    checked = set()
    master_bytes = 0
    for item in approved:
        key = item['source_sha256']
        row = new['portraits'][key]
        require(row['generated_fullsize_sha256'] == item['generated_fullsize_sha256'], 'Master mismatch')
        raw = safe_path(root, row['generated_fullsize_image'])
        require(file_sha256(raw) == row['generated_fullsize_sha256']
                and raw.stat().st_size == item['bytes'], 'Master bytes changed: ' + key)
        with Image.open(raw) as image:
            require(list(image.size) == item['size'] and image.mode == item['mode'], 'Master format differs')
            image.verify()
        master_bytes += raw.stat().st_size
        preview = previews[row['image']]
        require(digest(preview) == row['image_sha256'], 'Preview changed: ' + key)
        files[row['image']] = preview
        journal_relative = row['request_journal']
        incoming_journal_bytes = safe_path(source, journal_relative).read_bytes()
        incoming_journal = json.loads(incoming_journal_bytes)
        existing = read_json(root / journal_relative) if (root / journal_relative).exists() else {'attempts': []}
        assert_journal_retained(existing, incoming_journal)
        final = incoming_journal['attempts'][-1]
        marker = row['production_import']
        require(final['external_task_id'] == marker['task_id'] == item['task_id']
                and final['fullsize_sha256'] == row['generated_fullsize_sha256']
                and final['output_sha256'] == row['image_sha256']
                and final['method'] == row['method']
                and final['external_review_sha256'] == marker['review_sha256'] == item['review_sha256'],
                'Approved output/task/review binding differs: ' + key)
        checked.update(check_bound_files(root, marker))
        checked.update(check_bound_files(root, final, files))
        require(digest(row['prompt'].encode('utf-8')) == final['prompt_sha256'], 'Actual prompt differs')
        files[journal_relative] = incoming_journal_bytes
    for relative in (EXPERIMENT + '/approved-masters.json', EXPERIMENT + '/progress.json', nonperson_relative):
        files[relative] = safe_path(source, relative).read_bytes()
    # The fullsize index is regenerated separately with the established archive
    # tool. Never overwrite it with an older published index that misses LOWs.
    for relative in files:
        path = safe_path(root, relative)
        fingerprints[relative] = initial_fingerprints.get(relative, file_sha256(path) if path.exists() else None)
    assert_unchanged(root, fingerprints)
    unchanged_files = ['mod_nailong/data/generation-failures.json', INDEX,
                       'mod_nailong/data/retry-cooldown-waivers/20261029-remaining-low-immediate.json']
    protected = {relative: file_sha256(root / relative) for relative in unchanged_files}
    priority = read_json(root / 'mod_nailong/data/production-priority.json')
    require(keys <= {k for k, row in priority['sources'].items() if row['high_priority']}, 'Scope includes LOW')
    changed = {p: b for p, b in files.items() if fingerprints[p] != digest(b)}
    backup_bytes = sum((root / p).stat().st_size for p in changed if (root / p).exists())
    free = shutil.disk_usage(root).free
    require(free > 10 * 1024**3 + backup_bytes + sum(map(len, changed.values())), 'Insufficient bounded-write space')
    report = {'schema': 'naiwa-high-published-delivery-adoption-v1', 'machine_id': machine_id(),
              'observed_at_utc': utc_now(), 'source_commit': COMMIT,
              'source_verification': str(args.source_verification),
              'source_verification_sha256': file_sha256(args.source_verification),
              'status': 'validated_plan', 'approved_delivery_sources': 127,
              'master_bytes_freshly_verified': master_bytes, 'bound_evidence_files_verified': len(checked),
              'before': counts(priority, old, exceptions), 'after': counts(priority, new, exceptions),
              'changed_files': len(changed), 'backup_bytes': backup_bytes,
              'free_bytes_before': free, 'git_commands': 0, 'new_image_calls': 0,
              'game_runtime_acceptance_claimed': False, 'git_user_hold_still_active': True}
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.apply:
        backup = root / 'runtime/high-delivery-adoption-backups' / output.stem / 'before'
        require(not backup.exists(), 'Backup already exists; reconcile the earlier application')
        assert_unchanged(root, fingerprints | protected)
        for relative in changed:
            path = root / relative
            if path.exists():
                destination = backup / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
                require(file_sha256(destination) == fingerprints[relative], 'Backup mismatch')
        assert_unchanged(root, fingerprints | protected)
        report.update(status='applying', backup=str(backup), files=[])
        output.write_bytes(encode(report))
        try:
            for relative, data in changed.items():
                assert_unchanged(root, {relative: fingerprints[relative]})
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                temp = path.with_name(path.name + '.high-adoption-tmp')
                require(not temp.exists(), 'Unreconciled temporary file')
                temp.write_bytes(data)
                os.replace(temp, path)
                report['files'].append({'path': relative, 'before_sha256': fingerprints[relative],
                                        'after_sha256': digest(data), 'bytes': len(data)})
            final = read_json(root / GENERATED)
            final_queue = read_json(root / QUEUE)
            require(final == new and final_queue == new_queue, 'Post-write metadata changed')
            require({k: r for k, r in old['portraits'].items() if k not in keys}
                    == {k: r for k, r in final['portraits'].items() if k not in keys}, 'Unrelated portrait changed')
            require({k: r for k, r in old_queue['sources'].items() if k not in keys}
                    == {k: r for k, r in final_queue['sources'].items() if k not in keys}, 'Unrelated retry row changed')
            assert_unchanged(root, protected)
            for item in report['files']:
                require(file_sha256(root / item['path']) == item['after_sha256'], 'Post-write SHA differs')
            report.update(status='local_adoption_verified', completed_at_utc=utc_now(),
                          non_target_portraits_unchanged=True, non_target_retry_rows_unchanged=True,
                          all_retry_consumption_preserved=True, original_failures_unchanged=True,
                          exact_published_portrait_rows_retained=True)
        except Exception as error:
            report.update(status='partial_application_requires_reconciliation', error=str(error))
            output.write_bytes(encode(report))
            raise
    output.write_bytes(encode(report))
    print(json.dumps({k: v for k, v in report.items() if k != 'files'}, ensure_ascii=True))


if __name__ == '__main__':
    main()
