"""Audit the actual HIGH131 build profile and native display bindings without image generation."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT, file_sha256, game_root, machine_id, read_json, utc_now, write_json
from mod_nailong.tools import build_release
from mod_nailong.tools.catalog import read_source, sources
from mod_nailong.tools.hd_masking import sprite_records, unique_aliases

EXPERIMENT = 'mod_nailong/experiments/evolink-high131-flare-20261025'


def profile_scope(root, packages=None):
    root = Path(root).resolve()
    scope = read_json(root/EXPERIMENT/'scope.json')
    approved = read_json(root/EXPERIMENT/'approved-masters.json')
    catalog = read_json(root/'mod_nailong/data/catalog.json')
    keys = {row['source_sha256'] for row in scope['entries']}
    people = {row['source_sha256'] for row in approved['entries']}
    if len(scope['entries'])!=len(keys)!=131 or len(people)!=127:
        raise ValueError('HIGH scope must contain exactly 131 sources and 127 approved people')
    selected = build_release.profile_assets(catalog,packages)
    active = {row['source_sha256'] for row in selected.values()}
    paths = {row['path'].lower() for row in selected.values() if row['source_sha256'] in keys}
    return {
        'source_count':131, 'active_source_count':len(keys&active),
        'active_person_count':len(keys&active&people), 'active_nonperson_count':len(keys&active-people),
        'selected_keys':sorted(keys&active), 'selected_paths':sorted(paths),
        'inactive':[{'index':row['index'],'source_sha256':row['source_sha256'],'source_assets':row['source_assets']} for row in scope['entries'] if row['source_sha256'] not in active],
        'approved_people':people,
    }


def native_binding_audit(root=ROOT, packages=None):
    root = Path(root).resolve()
    profile = profile_scope(root,packages)
    catalog = read_json(root/'mod_nailong/data/catalog.json')
    install = game_root()
    if catalog['machine_id']!=machine_id() or file_sha256(install/'hoi4.exe')!=catalog['exe_sha256']:
        raise ValueError('Native binding audit does not match this machine and executable')
    selected_paths = set(profile['selected_paths'])
    records = []
    proofs = []
    text_references = []
    for row in sources(install):
        suffix = Path(row[1]).suffix.lower()
        if suffix not in {'.gfx','.txt'}:
            continue
        raw = read_source(row)
        source_id = len(proofs)
        proof = {'id':source_id,'package':row[0],'path':row[1],'sha256':__import__('hashlib').sha256(raw).hexdigest(),'archive_member':row[3]}
        proofs.append(proof)
        text = raw.decode('utf-8-sig',errors='replace')
        if suffix=='.gfx':
            records.extend(dict(record,source_id=source_id) for record in sprite_records(text))
        else:
            normalized = text.lower().replace('\\','/')
            for path in selected_paths:
                if path in normalized:
                    text_references.append({**proof,'texture':path,'matching_lines':[{'line':number,'text':line.strip()} for number,line in enumerate(text.splitlines(),1) if path in line.lower().replace('\\','/')]})
    by_path = {}
    for asset in build_release.profile_assets(catalog,packages).values():
        if asset['path'].lower() in selected_paths:
            by_path[asset['path'].lower()] = asset
    aliases = []
    unresolved = []
    for path in sorted(selected_paths):
        asset = by_path[path]
        if asset['source_sha256'] not in profile['approved_people']:
            continue
        try:
            found = unique_aliases(records,{path})
        except ValueError as error:
            reason = str(error)
            definitions = [record for record in records if reason.endswith(record['name'].lower())]
            unresolved.append({'path':path,'source_sha256':asset['source_sha256'],'package':asset['package'],'references':asset.get('references',[]),'reason':reason,'conflicting_definitions':definitions})
        else:
            aliases.extend(found)
    gui_references = []
    if unresolved:
        targets = {row['path'] for row in unresolved}
        text_references = [row for row in text_references if row['texture'] in targets]
        for file in sorted((install/'interface').rglob('*.gui')):
            raw = file.read_bytes()
            text = raw.decode('utf-8-sig',errors='replace')
            for line_number,line in enumerate(text.splitlines(),1):
                if any(path in line.lower().replace('\\','/') for path in targets):
                    gui_references.append({'path':file.relative_to(install).as_posix(),'sha256':file_sha256(file),'line':line_number,'text':line.strip()})
    audit = {
        'schema':'naiwa-high131-native-binding-audit-v1', 'machine_id':machine_id(), 'observed_at_utc':utc_now(),
        'root':str(root), 'packages':sorted(packages) if packages is not None else None,
        'exe_sha256':catalog['exe_sha256'], 'catalog_sha256':file_sha256(root/'mod_nailong/data/catalog.json'),
        'source_profile':{key:value for key,value in profile.items() if key not in {'selected_keys','selected_paths','approved_people'}},
        'selected_paths':profile['selected_paths'], 'selected_asset_packages':{path:asset['package'] for path,asset in by_path.items()},
        'aliases':aliases, 'unresolved':unresolved,
        'gui_references':gui_references, 'native_text_references':text_references, 'native_source_proofs':proofs,
        'production_import_verified':False, 'build_authorized':False,
        'scope':'Static actual-source binding analysis only. No production import, display pass, global HD qualification or LOW completion is implied.',
    }
    return classify_bindings(audit)


def classify_bindings(audit):
    proofs = {row['id']:row for row in audit['native_source_proofs']}
    selected = set(audit['selected_paths'])
    packages = audit['selected_asset_packages']
    resolved = []
    unbound = []
    remaining = []
    for row in audit['unresolved']:
        definitions = row.get('conflicting_definitions',[])
        if definitions:
            candidates = [record for record in definitions if record['kind']=='spritetype' and record['frames']=='1' and not record['existing_mask'] and record['texture'] in selected and proofs[record['source_id']]['package']==packages[record['texture']]]
            dlc = [record for record in candidates if proofs[record['source_id']]['package']!='base']
            choices = dlc or [record for record in candidates if proofs[record['source_id']]['package']=='base']
            targets = {record['texture'] for record in choices}
            if len(targets)==1:
                target = next(iter(targets))
                alias = next(record['name'] for record in choices if record['texture']==target)
                resolved.append({'name':alias,'texture':target,'source_ids':sorted({record['source_id'] for record in choices if record['texture']==target}),'selection_method':'actual-installed-package-definition-v1'})
                continue
        has_reference = bool(row.get('references')) or any(ref.get('texture')==row['path'] for ref in audit['native_text_references']) or any(row['path'] in ref['text'].lower().replace('\\','/') for ref in audit['gui_references'])
        if not definitions and not has_reference:
            unbound.append({**row,'classification':'no_current_native_consumer_in_bounded_inventory','runtime_display_not_applicable_unless_a_consumer_is_found':True})
        else:
            remaining.append(row)
    unique = {(row['name'].lower(),row['texture']):row for row in resolved}
    audit['initial_unresolved'] = audit['unresolved']
    audit['resolved_profile_aliases'] = sorted(unique.values(),key=lambda row:row['name'].lower())
    audit['inventory_without_current_consumer'] = unbound
    audit['unresolved'] = remaining
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worktree',type=Path,default=ROOT)
    parser.add_argument('--base-only',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = native_binding_audit(args.worktree,[] if args.base_only else None)
    output = args.output.resolve()
    output.relative_to((ROOT/'runtime').resolve())
    write_json(output,result)
    print({'active_sources':result['source_profile']['active_source_count'],'aliases':len(result['aliases']),'unresolved':len(result['unresolved']),'gui_references':len(result['gui_references']),'output':str(output)})


if __name__=='__main__':
    main()
