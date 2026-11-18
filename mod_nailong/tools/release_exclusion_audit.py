"""Independently audit actual mod staging/ZIP against the current release exclusion policy."""
from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT, file_sha256, machine_id, read_json, sha256, utc_now, write_json
from mod_nailong.tools.art_contract import portrait_ready
from mod_nailong.tools.release_scope import load_scope, manifest_scope, normalized_path


def audit(output, *, catalog=None, generated=None, root=None, require_review=True):
    root = Path(root or ROOT)
    output = Path(output)
    catalog = catalog if catalog is not None else read_json(root/'mod_nailong/data/catalog.json')
    generated = generated if generated is not None else read_json(root/'mod_nailong/data/generated.json')['portraits']
    scope = load_scope(catalog, require_review=require_review)
    manifest = read_json(output/'manifest.json')
    if manifest.get('release_exclusions') != manifest_scope(scope):
        raise ValueError('Release exclusion policy or source inventory missing/stale; rebuild the package')
    excluded = set(scope['excluded_source_sha256'])
    blocked_paths = set(scope['excluded_virtual_paths'])
    excluded_masters = set()
    for key in excluded:
        row = generated.get(key, {})
        excluded_masters.add(row.get('generated_fullsize_sha256'))
        excluded_masters.update(x.get('previous_fullsize_sha256') for x in row.get('revision_history', []))
    excluded_masters.discard(None)
    bindings = manifest['bindings']
    by_path = {normalized_path(x['path']): x for x in bindings}
    if len(by_path) != len(bindings):
        raise ValueError('Duplicate case-insensitive portrait bindings')
    from mod_nailong.tools.build_release import profile_assets, original_nonperson_bytes, nonperson_scope
    packages = manifest.get('selected_profile')
    selected = profile_assets(catalog, packages if isinstance(packages, list) else None)
    expected = {}
    for row in manifest['files']:
        name = row['path']
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe payload path')
        if normalized_path(name) in {normalized_path(x) for x in expected}:
            raise ValueError('Duplicate case-insensitive payload paths')
        if normalized_path(name) in blocked_paths:
            raise ValueError('Excluded portrait path in manifest: ' + name)
        if name not in {'descriptor.mod', 'thumbnail.png'} and normalized_path(name) not in by_path:
            raise ValueError('Unbound or unrelated payload file: ' + name)
        expected[name] = row
    actual = {p.relative_to(output/'staging').as_posix() for p in (output/'staging').rglob('*') if p.is_file()}
    if actual != set(expected):
        raise ValueError('Actual staging file set differs from manifest')
    if {normalized_path(x) for x in actual if normalized_path(x).startswith('gfx/')} != set(by_path):
        raise ValueError('Unbound actual portrait files')
    archive = output/manifest.get('archive_filename', 'gangnailongxin.zip')
    from mod_nailong.tools.texture_resolution import POLICY_ID
    proof = read_json(output/'native-texture-verification.json')
    expected_proof = [{'path': b['path'], 'source_sha256': b['source_sha256'],
                       'master_sha256': b.get('fullsize_master_sha256'), 'texture_sha256': b['sha256']} for b in bindings]
    if (proof.get('schema') != 'naiwa-native-pixel-proof-v1' or proof.get('policy') != POLICY_ID
            or proof.get('manifest_sha256') != file_sha256(output/'manifest.json')
            or proof.get('bindings') != expected_proof
            or proof.get('verification', {}).get('source_identity_and_rgba_verified') is not True):
        raise ValueError('Missing/stale own-source native pixel proof')
    with zipfile.ZipFile(archive) as handle:
        names = handle.namelist()
        if len(names) != len(set(normalized_path(x) for x in names)) or set(names) != set(expected):
            raise ValueError('Actual ZIP contains duplicate, extra or missing files')
        for name, row in expected.items():
            staged = output/'staging'/name
            if staged.is_symlink() or not staged.resolve().is_relative_to((output/'staging').resolve()):
                raise ValueError('Payload path escapes actual staging')
            raw = staged.read_bytes()
            if len(raw) != row['bytes'] or sha256(raw) != row['sha256'] or handle.read(name) != raw:
                raise ValueError('Actual staging/ZIP bytes differ: ' + name)
            if sha256(raw) in excluded_masters or sha256(raw) in excluded:
                raise ValueError('Excluded original/master bytes in payload: ' + name)
    checked = 0
    for path, binding in by_path.items():
        key = binding['source_sha256']
        if key in excluded or path in blocked_paths or binding.get('fullsize_master_sha256') in excluded_masters:
            raise ValueError('Excluded source/master in payload: ' + binding['path'])
        asset = selected.get(path)
        if asset is None or asset['source_sha256'] != key or asset['package'] != binding['package']:
            raise ValueError('Actual profile/source binding changed: ' + path)
        raw = (output/'staging'/binding['path']).read_bytes()
        if sha256(raw) != binding['sha256']:
            raise ValueError('Actual portrait bytes differ from source pixel proof')
        if binding.get('preserved_original_nonperson_exception'):
            exceptions, _ = nonperson_scope()
            if key not in exceptions or raw != original_nonperson_bytes(asset):
                raise ValueError('Unregistered nonperson original')
        else:
            row = generated.get(key, {})
            if not portrait_ready(row) or row.get('generated_fullsize_sha256') != binding.get('fullsize_master_sha256'):
                raise ValueError('Payload not bound to its own currently approved master')
        checked += 1
    return {'status': 'passed', 'policy_id': scope['policy_id'], 'policy_sha256': scope['policy_sha256'],
            'classifier_sha256': scope['classifier_sha256'], 'auditor_sha256': file_sha256(Path(__file__)),
            'catalog_fingerprint': scope['catalog_fingerprint'], 'inventory_review_current': scope['inventory_review_current'],
            'excluded_source_count': len(excluded), 'excluded_catalog_asset_count': scope['excluded_asset_count'],
            'checked_actual_portrait_bindings': checked, 'checked_actual_payload_files': len(actual),
            'actual_staging_and_zip_bytes_checked': True, 'own_source_native_pixel_proof_verified': True,
            'raw_master_pixels_recomputed_in_exclusion_audit': False,
            'excluded_payload_matches': 0, 'manifest_sha256': file_sha256(output/'manifest.json'),
            'zip_sha256': file_sha256(archive), 'art_complete_or_gameplay_acceptance_implied': False}


def write_audit(output, *, receipt=None, **kwargs):
    output = Path(output)
    receipt = Path(receipt) if receipt else output/('release-exclusion-audit-' + utc_now().replace(':', '').replace('+', '_') + '.json')
    if receipt.exists():
        raise ValueError('Choose a fresh exclusion audit receipt; keep historical results')
    record = {'schema': 'nailong-release-exclusion-audit-v1', 'machine_id': machine_id(), 'observed_at_utc': utc_now()}
    try:
        record.update(audit(output, **kwargs))
    except (ValueError, KeyError, OSError, SystemExit, zipfile.BadZipFile) as error:
        record.update(status='failed', reason=str(error), publication_must_stop=True)
        write_json(receipt, record)
        raise
    write_json(receipt, record)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    result = write_audit(args.build, receipt=args.receipt, require_review=True)
    print('PASS: actual staging/ZIP release exclusion audit; excluded portrait matches = 0')
