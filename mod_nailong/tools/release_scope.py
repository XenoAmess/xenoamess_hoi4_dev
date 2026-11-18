"""Release eligibility is separate from generation/art approval and raw PNG archiving."""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT, file_sha256, machine_id, read_json, sha256, utc_now, write_json

POLICY_PATH = Path(__file__).resolve().parents[1] / 'data/release-exclusion-policy.json'
SNAPSHOT_PATH = POLICY_PATH.with_name('release-scope.json')


def normalized_path(value):
    return re.sub('/+', '/', value.replace('\\', '/')).lower()


def inventory_fingerprint(catalog):
    assets = [{k: a.get(k) for k in ('id', 'package', 'path', 'source_sha256', 'references')}
              for a in catalog['assets']]
    body = {'assets': sorted(assets, key=lambda a: (a['package'], a['path'], a['source_sha256'])),
            'unresolved_references': catalog.get('unresolved_references', [])}
    return sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8'))


def load_policy(path=None):
    path = Path(path or POLICY_PATH)
    policy = read_json(path)
    if (policy.get('schema') != 'nailong-release-exclusion-policy-v1'
            or policy.get('scope') != 'chinese_ccp_and_related_only'
            or policy.get('generation_and_git_archive_allowed') is not True
            or policy.get('excluded_art_is_release_blocker') is not False
            or policy.get('foreign_communist_forces_excluded_as_a_class') is not False):
        raise ValueError('Invalid Chinese CCP release exclusion policy')
    return policy, file_sha256(path)


def excluded_character(character, policy):
    char = character.casefold()
    if char in {x.casefold() for x in policy['retained_character_ids']}:
        return False
    return (char in {x.casefold() for x in policy['excluded_character_ids']}
            or any(char.startswith(x.casefold()) for x in policy['excluded_character_prefixes']))


def named_source_excluded(path, policy):
    stem = PurePosixPath(normalized_path(path)).stem
    stem = re.sub(r'^(portrait_|idea_)', '', stem)
    # An explicit retained non-communist alternative identity overrides only
    # its own name; another excluded role using these bytes still wins below.
    if any(stem == x.casefold() or stem.startswith(x.casefold() + '_')
           for x in policy['retained_character_ids']):
        return False
    return (any(stem.startswith(x.casefold()) for x in policy['excluded_character_prefixes'])
            or any(stem == x.casefold() or stem.startswith(x.casefold() + '_')
                   for x in policy['excluded_character_ids']))


def excluded_reference(ref, policy):
    if excluded_character(ref.get('character', ''), policy):
        return True
    value = re.sub(r'^gfx_', '', ref.get('value', ''), flags=re.I)
    return named_source_excluded(value, policy)


def classify(catalog, policy, policy_sha256):
    reasons = {}
    unknown = []
    retained_names = {x.casefold() for x in policy['reviewed_retained_prc_folder_basenames']}
    for asset in catalog['assets']:
        key = asset['source_sha256']
        found = []
        if named_source_excluded(asset['path'], policy):
            found.append('dedicated_PRC_source_identity')
        chars = sorted({ref.get('character', '') for ref in asset.get('references', [])
                        if excluded_reference(ref, policy)})
        if chars:
            found.append('excluded_character_reference:' + ','.join(chars))
        if found:
            reasons.setdefault(key, []).extend(found)
        elif '/prc/' in normalized_path(asset['path']):
            stem = PurePosixPath(normalized_path(asset['path'])).stem
            retained_identity = any(stem in {x.casefold(), 'portrait_' + x.casefold()}
                                    for x in policy['retained_character_ids'])
            if PurePosixPath(asset['path']).name.casefold() not in retained_names and not retained_identity:
                unknown.append({'source_sha256': key, 'path': asset['path'], 'package': asset['package']})
    keys = set(reasons)
    # Exact byte aliases and older versions of a blocked virtual path must
    # not leak back through a different DLC profile or case variant.
    blocked_paths = set()
    while True:
        previous = (len(keys), len(blocked_paths))
        blocked_paths.update(normalized_path(a['path']) for a in catalog['assets'] if a['source_sha256'] in keys)
        keys.update(a['source_sha256'] for a in catalog['assets'] if normalized_path(a['path']) in blocked_paths)
        if previous == (len(keys), len(blocked_paths)):
            break
    excluded_assets = [a for a in catalog['assets'] if a['source_sha256'] in keys]
    unknown = [a for a in unknown if a['source_sha256'] not in keys and normalized_path(a['path']) not in blocked_paths]
    for asset in excluded_assets:
        reasons.setdefault(asset['source_sha256'], ['blocked_virtual_path_variant'])
    unresolved = [x for x in catalog.get('unresolved_references', []) if excluded_reference(x, policy)]
    return {'policy_id': policy['policy_id'], 'policy_sha256': policy_sha256,
            'classifier_sha256': file_sha256(Path(__file__)),
            'catalog_fingerprint': inventory_fingerprint(catalog),
            'inventory_review_current': policy.get('reviewed_inventory_fingerprint') == inventory_fingerprint(catalog),
            'excluded_source_sha256': sorted(keys), 'excluded_virtual_paths': sorted(blocked_paths),
            'excluded_asset_count': len(excluded_assets), 'excluded_unresolved_reference_count': len(unresolved),
            'unknown_prc_folder_sources': unknown,
            'source_reasons': {k: sorted(set(v)) for k, v in sorted(reasons.items())}}


def load_scope(catalog, require_review=False):
    policy, digest = load_policy()
    scope = classify(catalog, policy, digest)
    if scope['unknown_prc_folder_sources']:
        raise ValueError('RELEASE BLOCKED: unreviewed PRC-folder source affiliations; classify sources explicitly')
    if require_review and not scope['inventory_review_current']:
        raise ValueError('RELEASE BLOCKED: release exclusion inventory changed; review affiliation changes first')
    return scope


def asset_excluded(asset, scope):
    return (asset['source_sha256'] in scope['excluded_source_sha256']
            or normalized_path(asset['path']) in scope['excluded_virtual_paths'])


def manifest_scope(scope):
    return {k: v for k, v in scope.items() if k not in {'source_reasons', 'unknown_prc_folder_sources'}}


def art_coverage(catalog, generated):
    """Report archive and release-eligible art separately, without changing any art decision."""
    from mod_nailong.tools.art_contract import portrait_ready
    policy, digest = load_policy()
    scope = classify(catalog, policy, digest)
    excluded = set(scope['excluded_source_sha256'])
    all_keys = {a['source_sha256'] for a in catalog['assets']}
    eligible = all_keys - excluded
    return {'policy_id': scope['policy_id'], 'inventory_review_current': scope['inventory_review_current'],
            'affiliation_review_required': bool(scope['unknown_prc_folder_sources']),
            'excluded_texture_paths': scope['excluded_asset_count'], 'excluded_unique_sources': len(excluded),
            'excluded_unique_art_unqualified': sum(not portrait_ready(generated.get(k, {})) for k in excluded),
            'eligible_unique_sources': len(eligible),
            'eligible_unique_art_reviewed': sum(portrait_ready(generated.get(k, {})) for k in eligible),
            'excluded_art_blocks_release': False,
            'counts_scope': 'Art only. Nonperson original exceptions, other gaps and live-game acceptance are evaluated by the builder separately.'}


def write_snapshot(review_current=False):
    catalog = read_json(ROOT/'mod_nailong/data/catalog.json')
    policy, _ = load_policy()
    if review_current:
        policy['reviewed_inventory_fingerprint'] = inventory_fingerprint(catalog)
        write_json(POLICY_PATH, policy)
    scope = load_scope(catalog, require_review=True)
    excluded = set(scope['excluded_source_sha256'])
    entries = [{'source_sha256': key, 'reasons': scope['source_reasons'][key],
                'aliases': [{k: a[k] for k in ('id', 'package', 'path')}
                            for a in catalog['assets'] if a['source_sha256'] == key]}
               for key in sorted(excluded)]
    write_json(SNAPSHOT_PATH, {'schema': 'nailong-release-exclusion-inventory-v1',
        'generated_notice': 'GENERATED FILE: use release_scope.py after reviewing source affiliations; do not edit rows.',
        'machine_id': machine_id(), 'observed_at_utc': utc_now(), **manifest_scope(scope), 'entries': entries,
        'generation_and_archive_status_changed': False})
    print(json.dumps({k: scope[k] for k in ('policy_id', 'excluded_asset_count', 'excluded_unresolved_reference_count')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-current-inventory', action='store_true',
                        help='Record owner-reviewed current affiliations; never run blindly after a catalog change')
    args = parser.parse_args()
    write_snapshot(args.review_current_inventory)
