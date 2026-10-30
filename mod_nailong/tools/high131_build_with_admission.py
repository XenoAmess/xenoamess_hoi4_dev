"""Admit and execute one bounded HIGH131 original-RGBA build under the shared publication lock."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json
from mod_nailong.tools import build_release
from mod_nailong.tools.build_high131_validation import build_profile


def verified_profile(worktree, packages):
    from runtime import high131_import

    scope = read_json(worktree/'mod_nailong/experiments/evolink-high131-flare-20261025/scope.json')
    approved = read_json(worktree/'mod_nailong/experiments/evolink-high131-flare-20261025/approved-masters.json')
    generated = read_json(worktree/'mod_nailong/data/generated.json')['portraits']
    if len(approved['entries'])!=127:
        raise ValueError('HIGH approval count is not 127')
    for row in approved['entries']:
        reference = {'review':row['review'],'review_sha256':row['review_sha256'],'attempt':row['approved_attempt'],'task_id':row['task_id']}
        if not row.get('production_imported') or not high131_import.production_import_completed(worktree,row['source_sha256'],reference):
            raise ValueError(f"HIGH source is not formally imported: {row['source_sha256']}")
    selected = build_release.profile_assets(read_json(worktree/'mod_nailong/data/catalog.json'),packages)
    scope_keys = {row['source_sha256'] for row in scope['entries']}
    selected = {path:asset for path,asset in selected.items() if asset['source_sha256'] in scope_keys}
    exceptions,_ = build_release.nonperson_scope()
    estimate = sum(4*asset['size'][0]*asset['size'][1]+128 for asset in selected.values() if asset['source_sha256'] in generated and build_release.ready(generated[asset['source_sha256']]))
    estimate += sum(len(build_release.original_nonperson_bytes(asset)) for asset in selected.values() if asset['source_sha256'] in exceptions)
    return estimate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worktree',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--admission',type=Path,required=True)
    parser.add_argument('--binding-audit',type=Path,required=True)
    parser.add_argument('--inventory',type=Path,required=True)
    parser.add_argument('--batch',required=True)
    parser.add_argument('--base-only',action='store_true')
    args = parser.parse_args()
    worktree = args.worktree.resolve()
    worktree.relative_to((ROOT/'runtime').resolve())
    output = args.output.resolve()
    output.relative_to((ROOT/'dist').resolve())
    if output.exists():
        raise SystemExit('Choose a fresh HIGH validation output')
    if not args.batch.replace('-','').isalnum():
        raise SystemExit('Invalid build batch')
    inventory_path = args.inventory.resolve()
    inventory_path.relative_to((ROOT/'runtime').resolve())
    args.binding_audit.resolve().relative_to((ROOT/'runtime').resolve())
    inventory = read_json(inventory_path)
    if inventory.get('schema')!='high131-scoped-storage-inventory-result-v1' or inventory.get('machine_id')!=machine_id() or inventory.get('status')!='verified' or not isinstance(inventory.get('project_allocated_bytes'),int):
        raise SystemExit('A verified actual project storage inventory is required')
    packages = [] if args.base_only else None
    estimate = verified_profile(worktree,packages)
    peak = 2*estimate+64*1024*1024
    stat = shutil.disk_usage(ROOT)
    profile = read_json(ROOT/'runtime/local-profile.json')
    other = 16*1024**3
    system = profile['system_growth_reserve_bytes']
    safety = max(2*1024**3,min(20*1024**3,int(stat.total*0.05)))
    if peak+other+system+safety>stat.free:
        raise SystemExit('Insufficient free space for this HIGH build and existing reservations')
    admitted = datetime.now(timezone.utc)
    review = admitted+timedelta(days=7)
    receipt = args.admission.resolve()
    receipt.relative_to((ROOT/'runtime').resolve())
    if receipt.exists():
        raise SystemExit('Choose a fresh admission receipt; previous evidence is immutable')
    lock = ROOT/'runtime/production-publish.lock'
    token = uuid.uuid4().hex
    fd = os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        with os.fdopen(fd,'w',encoding='ascii',newline='\n') as stream:
            json.dump({'machine_id':machine_id(),'process_id':os.getpid(),'batch':args.batch,'token':token,'acquired_at_utc':utc_now()},stream)
        body = {
            'schema':'naiwa-high131-heavy-write-admission-v1','machine_id':machine_id(),'status':'admitted','policy_version':'1.0.0',
            'scope':'high131-original-rgba-validation-v1','batch':args.batch,'output_root':str(output),
            'decoded_payload_bytes':estimate,'this_write_peak_estimate_bytes':peak,
            'write_peak_basis':'Uncompressed original-RGBA staging plus ZIP with no assumed compression gain, plus 64 MiB for adapters and metadata',
            'volume_total_bytes':stat.total,'available_bytes':stat.free,
            'other_unspent_reservations_bytes':other,
            'other_reservation_basis':'Conservative 16 GiB reserved for separately owned LOW production and transport; no LOW file is modified',
            'system_growth_reserve_bytes':system,'safety_margin_bytes':safety,
            'required_free_bytes':peak+other+system+safety,
            'project_usage_upper_bound_bytes':inventory['project_allocated_bytes'],
            'project_inventory':str(args.inventory.resolve()),'project_inventory_sha256':file_sha256(args.inventory),
            'effective_project_quota_bytes':128*1024**3,
            'quota_override':{
                'owner':'Kimi HIGH131 validation task','reason':'Current measured project usage exceeds the default quota; bounded HIGH original-RGBA validation is required without deleting original masters or changing global defaults',
                'max_project_bytes':128*1024**3,'review_at_utc':review.isoformat(),'automatic_renewal':False,
            },
            'admitted_at_utc':admitted.isoformat(),'retention_review_by_utc':review.isoformat(),
            'coordination_lock':'runtime/production-publish.lock','coordination_lock_sha256':file_sha256(lock),
            'coordination_lock_token':token,'source_worktree':str(worktree),
            'formal_release_or_global_HD_qualification_granted':False,
        }
        write_json(receipt,body)
        build_release.validate_heavy_write_admission(receipt,estimate,output)
        manifest = build_profile(worktree,output,receipt,packages,args.binding_audit)
        body.update(status='build_completed',completed_at_utc=utc_now(),manifest_sha256=file_sha256(output/'manifest.json'),preview=True,formal_release_eligible=False)
        write_json(receipt,body)
        print({'status':'build_completed','bindings':len(manifest['bindings']),'preview':True,'output':str(output)})
    except BaseException as error:
        if receipt.exists():
            body = read_json(receipt)
            body.update(status='build_failed',failed_at_utc=utc_now(),error_type=type(error).__name__,error=str(error))
            write_json(receipt,body)
        raise
    finally:
        current = read_json(lock)
        if current.get('token')!=token or current.get('process_id')!=os.getpid():
            raise RuntimeError('Coordination lock identity changed; refusing to remove another owner')
        lock.unlink()


if __name__=='__main__':
    main()
