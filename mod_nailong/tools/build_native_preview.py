"""Build all currently approved native-size portraits with scoped storage admission."""
import argparse,json,os,shutil,sys,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT,read_json,write_json,machine_id,utc_now,file_sha256
from mod_nailong.tools import build_release as builder


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--inventory',type=Path,required=True)
    parser.add_argument('--reuse-verified-build',type=Path,help='Reuse byte-identical, already pixel-verified textures; update only descriptor and cover')
    args=parser.parse_args();output=args.output.resolve();output.relative_to((ROOT/'dist').resolve())
    if output.exists():raise SystemExit('Choose a fresh native preview output')
    inventory=read_json(args.inventory)
    if inventory.get('machine_id')!=machine_id() or (datetime.now(timezone.utc)-datetime.fromisoformat(inventory['observed_at_utc'])).total_seconds()>1800:
        raise SystemExit('Fresh local storage inventory required')
    catalog=read_json(ROOT/'mod_nailong/data/catalog.json');generated=read_json(ROOT/'mod_nailong/data/generated.json')['portraits']
    selected=builder.profile_assets(catalog);exceptions,_=builder.nonperson_scope()
    estimate=sum(4*a['size'][0]*a['size'][1]+128 for a in selected.values() if builder.ready(generated.get(a['source_sha256'],{})))
    estimate+=sum(len(builder.original_nonperson_bytes(a)) for a in selected.values() if a['source_sha256'] in exceptions)
    peak=2*estimate+64*1024**2
    lock=ROOT/'runtime/production-publish.lock';token=uuid.uuid4().hex
    batch='native-preview-20261030-'+token[:8]
    receipt=ROOT/'runtime/release-20261030'/(batch+'-admission.json')
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        with os.fdopen(fd,'w',encoding='ascii') as stream:
            json.dump({'machine_id':machine_id(),'process_id':os.getpid(),'batch':batch,'token':token,'acquired_at_utc':utc_now()},stream)
        coordination=read_json(ROOT/'runtime/storage-coordination-observation.json')
        if (datetime.now(timezone.utc)-datetime.fromisoformat(coordination['observed_at_utc'])).total_seconds()>1800:
            raise SystemExit('Fresh project capacity coordination observation required')
        outstanding=[r for task in coordination['tasks'] for r in (task.get('resources') or []) if any(word in str(r).lower() for word in ('capacity','storage','reservation','disk'))]
        if outstanding:raise SystemExit('Other registered storage resources need explicit accounting')
        disk=shutil.disk_usage(ROOT);system=read_json(ROOT/'runtime/local-profile.json')['system_growth_reserve_bytes']
        other=16*1024**3
        safety=max(2*1024**3,min(20*1024**3,int(disk.total*.05)))
        # The bounded scan may hit 100k files. A whole-volume used-byte bound
        # safely includes the unscanned project; it is not a claimed project total.
        usage=max(inventory['project_usage_upper_bound'],disk.used)
        quota=usage+peak+other
        now=datetime.now(timezone.utc);review=now+timedelta(hours=24)
        body={'schema':'naiwa-native-size-heavy-write-admission-v1','scope':'native-source-size-v1','machine_id':machine_id(),'status':'admitted','policy_version':'1.0.0',
            'batch':batch,'output_root':str(output),'decoded_payload_bytes':estimate,'this_write_peak_estimate_bytes':peak,
            'volume_total_bytes':disk.total,'available_bytes':disk.free,'other_unspent_reservations_bytes':other,
            'other_reservation_basis':'Fresh task resource observation contains no other registered project storage reservation. An additional 16 GiB remains allocated as conservative allowance for separately owned task work; this is local coordination, not a system-wide allocator.',
            'system_growth_reserve_bytes':system,'safety_margin_bytes':safety,'project_usage_upper_bound_bytes':usage,
            'project_inventory':str(args.inventory.resolve()),'project_inventory_sha256':file_sha256(args.inventory),
            'usage_bound_method':'Conservative entire local volume used bytes; includes unrelated usage and does not treat incomplete scan as zero',
            'effective_project_quota_bytes':quota,'quota_override':{'owner':'Codex native-size portrait repair task','reason':'One bounded 349 MiB native payload rebuild required by the user. Whole-volume usage is used as a conservative upper bound instead of claiming an incomplete metadata scan is complete. The exception grants only this peak plus separately counted task allowance.','max_project_bytes':quota,'review_at_utc':review.isoformat(),'automatic_renewal':False},
            'admitted_at_utc':now.isoformat(),'retention_review_by_utc':review.isoformat(),'coordination_lock':str(lock.relative_to(ROOT)),
            'coordination_lock_sha256':file_sha256(lock),'coordination_lock_token':token,'git_operations':0,'publication_performed':False}
        write_json(receipt,body);builder.validate_heavy_write_admission(receipt,estimate,output)
        manifest=(builder.repackage_verified(args.reuse_verified_build,output,receipt) if args.reuse_verified_build else builder.build(output,preview=True,heavy_write_admission=receipt))
        body.update(status='build_completed',completed_at_utc=utc_now(),manifest_sha256=file_sha256(output/'manifest.json'))
        write_json(receipt,body)
        write_json(output/'build-receipt.json',{'machine_id':machine_id(),'observed_at_utc':utc_now(),'source':('Byte-identical verified native textures repackaged with current branding; existing pixel proof and current approval bindings checked; no new PNG-to-pixel comparison' if args.reuse_verified_build else 'Native-size default builder, exact source/master/derived-pixel binding and staging/ZIP verification'),
            'preview':True,'formal_release_eligible':False,'live_acceptance':'not-run','exe_sha256':catalog['exe_sha256'],'bindings':len(manifest['bindings']),
            'manifest_sha256':file_sha256(output/'manifest.json'),'zip_sha256':file_sha256(output/'gangnailongxin.zip'),'heavy_write_admission':str(receipt.relative_to(ROOT))})
        print({'status':'built','bindings':len(manifest['bindings']),'bytes':sum(r['bytes'] for r in manifest['files']),'preview':True})
    except BaseException as error:
        if receipt.exists():
            body=read_json(receipt);body.update(status='build_failed',error=str(error),failed_at_utc=utc_now());write_json(receipt,body)
        raise
    finally:
        current=read_json(lock)
        if current.get('token')!=token:raise RuntimeError('Coordination lock owner changed')
        lock.unlink()


if __name__=='__main__':main()
