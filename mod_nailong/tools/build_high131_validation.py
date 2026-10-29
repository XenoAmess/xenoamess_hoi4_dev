"""Build and verify a HIGH131-only original-RGBA development package after formal import."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT, file_sha256, machine_id, read_json, sha256, utc_now, write_json
from mod_nailong.tools import build_release
from mod_nailong.tools.high131_validation import profile_scope


def verify_payload_pixels(root, output, manifest):
    if manifest.get('preview') is not True or manifest.get('art_complete') is not False:
        raise ValueError('HIGH validation must remain an explicitly incomplete development package')
    people = []
    preserved = []
    output = Path(output)
    for binding in manifest['bindings']:
        payload = output/'staging'/binding['path']
        if binding.get('preserved_original_nonperson_exception'):
            if file_sha256(payload)!=binding['sha256'] or binding.get('fullsize_master_sha256') is not None:
                raise ValueError('Non-person original bytes changed')
            preserved.append({'path':binding['path'],'source_sha256':binding['source_sha256'],'sha256':binding['sha256']})
            continue
        master = Path(root)/'mod_nailong/assets/generated_fullsize'/f"{binding['fullsize_master_sha256']}.png"
        if file_sha256(master)!=binding['fullsize_master_sha256']:
            raise ValueError('Fullsize master changed during build')
        with Image.open(master) as source, Image.open(payload) as encoded:
            rgba = source.convert('RGBA')
            decoded = encoded.convert('RGBA')
            if rgba.size!=decoded.size or rgba.tobytes()!=decoded.tobytes():
                raise ValueError(f"Fullsize RGBA differs: {binding['path']}")
            people.append({'path':binding['path'],'source_sha256':binding['source_sha256'],'master_sha256':binding['fullsize_master_sha256'],'rgba_pixel_sha256':hashlib.sha256(decoded.tobytes()).hexdigest(),'size':list(decoded.size),'resized':False})
    return {'person_textures':len(people),'preserved_original_nonperson_textures':len(preserved),'people':people,'nonperson':preserved,'runtime_display_acceptance':'not-run'}


def build_profile(worktree, output, admission, packages=None, binding_audit=None):
    from runtime import high131_import

    worktree = Path(worktree).resolve()
    worktree.relative_to((ROOT/'runtime').resolve())
    if worktree==ROOT.resolve():
        raise ValueError('HIGH validation must use an isolated imported worktree')
    output = Path(output).resolve()
    output.relative_to((ROOT/'dist').resolve())
    profile = profile_scope(worktree,packages)
    plan = high131_import.build_plan(worktree,ROOT)
    for entry in plan['entries']:
        reference = {'review':entry['review'],'review_sha256':entry['review_sha256'],'attempt':entry['attempt'],'task_id':entry['task_id']}
        if not high131_import.production_import_completed(worktree,entry['source_sha256'],reference):
            raise ValueError(f"HIGH source is not formally imported: {entry['source_sha256']}")
    high131_import.refresh_normalized_receipts(worktree,plan)
    commit = high131_import.git(worktree,'rev-parse','HEAD')
    original_mod = build_release.MOD
    try:
        build_release.MOD = worktree/'mod_nailong'
        manifest = build_release.build(output,preview=True,packages=packages,validation_keys=profile['selected_keys'],heavy_write_admission=admission)
    finally:
        build_release.MOD = original_mod
    if set(manifest['validation_source_keys'])!=set(profile['selected_keys']) or len(manifest['bindings'])!=len(profile['selected_paths']):
        raise ValueError('HIGH manifest does not match its explicit build profile')
    if binding_audit is not None:
        from mod_nailong.tools.hd_masking import augment
        from tools.common import game_root

        audit = read_json(binding_audit)
        expected_packages = sorted(packages) if packages is not None else None
        if Path(audit['root']).resolve()!=worktree or audit['packages']!=expected_packages or audit['selected_paths']!=profile['selected_paths']:
            raise ValueError('Binding audit belongs to another worktree or profile')
        if audit.get('catalog_sha256')!=file_sha256(worktree/'mod_nailong/data/catalog.json'):
            raise ValueError('Binding audit is stale for this catalog')
        if audit['unresolved']:
            raise ValueError('Unresolved native bindings remain')
        aliases = audit['aliases']+audit.get('resolved_profile_aliases',[])
        install = game_root()
        includes = [{'path':relative,'sha256':file_sha256(install/relative)} for relative in ['gfx/FX/buttonstate.fxh','gfx/FX/buttonstate.shader']]
        manifest = augment(output,manifest,aliases,audit['native_source_proofs'],includes,audit.get('inventory_without_current_consumer',[]))
    proof = verify_payload_pixels(ROOT,output,manifest)
    write_json(output/'rgba-verification.json',{'schema':'naiwa-high131-rgba-verification-v1','machine_id':machine_id(),'observed_at_utc':utc_now(),'source_commit':commit,**proof})
    write_json(output/'build-receipt.json',{
        'schema':'naiwa-high131-build-receipt-v1','machine_id':machine_id(),'observed_at_utc':utc_now(),
        'source_commit':commit,'profile':profile,'preview':True,'art_complete':False,'formal_release_eligible':False,
        'decoded_payload_bytes':sum(row['bytes'] for row in manifest['bindings']),
        'manifest_sha256':file_sha256(output/'manifest.json'),'zip_sha256':file_sha256(output/'gangnailongxin.zip'),
        'heavy_write_admission':str(Path(admission).resolve()) if admission else None,
        'binding_audit':str(Path(binding_audit).resolve()) if binding_audit else None,
        'binding_audit_sha256':file_sha256(binding_audit) if binding_audit else None,
        'person_textures':proof['person_textures'],'preserved_original_nonperson_textures':proof['preserved_original_nonperson_textures'],
        'runtime_display_acceptance':'not-run','LOW_or_global_release_completion_claimed':False,
    })
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worktree',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--admission',type=Path,required=True)
    parser.add_argument('--base-only',action='store_true')
    parser.add_argument('--binding-audit',type=Path)
    args = parser.parse_args()
    manifest = build_profile(args.worktree,args.output,args.admission,[] if args.base_only else None,args.binding_audit)
    print({'built_HIGH_profile_bindings':len(manifest['bindings']),'preview':manifest['preview'],'output':str(args.output.resolve()),'runtime_acceptance':'not-run'})


if __name__=='__main__':
    main()
