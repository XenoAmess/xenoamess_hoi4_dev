"""Build a deterministic, image-only HOI4 mod from reviewed art and registered original non-person exceptions."""
from __future__ import annotations

import argparse
import io
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT, file_sha256, machine_id, read_json, sha256, utc_now, write_json
from PIL import Image

MOD=ROOT/"mod_nailong"

def ready(row):
    from mod_nailong.tools.art_contract import portrait_ready
    return portrait_ready(row)

def thumbnail_bytes():
    """HOI4 Workshop expects a real, square PNG named thumbnail.png."""
    cover=MOD/'assets/branding/workshop-cover.jpg'
    if not cover.exists():return None
    with Image.open(cover) as image:
        if image.width!=image.height:raise SystemExit('Workshop cover must be square')
        stream=io.BytesIO();image.convert('RGB').save(stream,format='PNG',optimize=True)
    raw=stream.getvalue()
    if len(raw)>=1024*1024:raise SystemExit('Workshop thumbnail PNG must be smaller than 1 MiB')
    return raw

def profile_assets(catalog, packages=None):
    def rank(asset):
        if asset['package']=='base':return -1
        match=re.search(r'dlc(\d+)',asset['package'])
        return int(match[1]) if match else 0
    eligible=[a for a in catalog['assets'] if packages is None or a['package']=='base' or a['package'] in packages]
    selected={}
    for asset in sorted(eligible,key=lambda a:(rank(a),a['package'],a['path'])):
        selected[asset['path'].lower()]=asset
    return selected

def validation_sample_keys(catalog, generated, count, packages=None):
    # Sample the actual profile after DLC overrides. A reviewed superseded
    # source must not become an unknown sample key or replace unreviewed DLC art.
    return sorted({a['source_sha256'] for a in profile_assets(catalog,packages).values()
                   if ready(generated.get(a['source_sha256'],{}))})[:count]

def nonperson_scope():
    from mod_nailong.tools.nonperson_exceptions import load_nonperson_exceptions
    scope=read_json(MOD/'experiments/evolink-high131-flare-20261025/scope.json')
    return load_nonperson_exceptions(scope,root=ROOT)


def original_nonperson_bytes(asset):
    source=read_json(ROOT/'runtime/source-index.json').get(asset['id'])
    if source is None:raise SystemExit(f'Original non-person asset is absent from source-index: {asset["id"]}')
    if source.get('member'):
        with zipfile.ZipFile(source['path']) as archive:raw=archive.read(source['member'])
    else:raw=Path(source['path']).read_bytes()
    if sha256(raw)!=asset['source_sha256']:raise SystemExit(f'Original non-person asset SHA256 mismatch: {asset["id"]}')
    with Image.open(io.BytesIO(raw)) as image:
        if list(image.size)!=asset['size']:raise SystemExit(f'Original non-person asset size mismatch: {asset["id"]}')
    return raw


def validate_heavy_write_admission(receipt, estimate, output):
    from datetime import datetime, timezone
    import os

    if receipt is None:
        raise SystemExit('Fullsize staging exceeds 256 MiB; an explicit scoped heavy-write admission is required')
    receipt = Path(receipt).resolve()
    receipt.relative_to((ROOT/'runtime').resolve())
    body = read_json(receipt)
    output = Path(output).resolve()
    output.relative_to((ROOT/'dist').resolve())
    native=body.get('schema')=='naiwa-native-size-heavy-write-admission-v1'
    required_identity = {
        'schema':'naiwa-native-size-heavy-write-admission-v1' if native else 'naiwa-high131-heavy-write-admission-v1', 'machine_id':machine_id(),
        'status':'admitted', 'policy_version':'1.0.0',
        'scope':'native-source-size-v1' if native else 'high131-original-rgba-validation-v1', 'output_root':str(output),
    }
    if any(body.get(key)!=value for key,value in required_identity.items()):
        raise SystemExit('Heavy-write admission identity, machine, scope or output mismatch')
    if body.get('decoded_payload_bytes')!=estimate:
        raise SystemExit('Heavy-write admission does not match the actual decoded payload')
    peak = body.get('this_write_peak_estimate_bytes')
    if not isinstance(peak,int) or isinstance(peak,bool) or peak<2*estimate+64*1024*1024:
        raise SystemExit('Heavy-write peak must cover staging, ZIP and metadata without assumed compression gains')
    fields = ['volume_total_bytes','available_bytes','other_unspent_reservations_bytes','system_growth_reserve_bytes','project_usage_upper_bound_bytes','effective_project_quota_bytes','safety_margin_bytes']
    if any(not isinstance(body.get(key),int) or isinstance(body.get(key),bool) or body[key]<0 for key in fields):
        raise SystemExit('Heavy-write admission is missing nonnegative capacity inputs')
    safety = max(2*1024**3,min(20*1024**3,int(body['volume_total_bytes']*0.05)))
    required = peak+body['other_unspent_reservations_bytes']+body['system_growth_reserve_bytes']+safety
    quota = min(100*1024**3,int(body['volume_total_bytes']*0.10))
    if body['safety_margin_bytes']!=safety:
        raise SystemExit('Heavy-write safety margin exceeds policy 1.0.0')
    if body['effective_project_quota_bytes']>quota:
        override = body.get('quota_override',{})
        try:
            start = datetime.fromisoformat(body['admitted_at_utc'])
            review = datetime.fromisoformat(override.get('review_at_utc'))
        except (TypeError,ValueError) as error:
            raise SystemExit('Heavy-write quota override has invalid UTC times') from error
        valid = (isinstance(override.get('owner'),str) and bool(override['owner'])
                 and isinstance(override.get('reason'),str) and bool(override['reason'])
                 and override.get('max_project_bytes')==body['effective_project_quota_bytes']
                 and start.tzinfo is not None and review.tzinfo is not None
                 and start<=datetime.now(timezone.utc)<review
                 and review-start<=__import__('datetime').timedelta(days=7))
        if not valid:
            raise SystemExit('Heavy-write quota override is missing its owner, reason, bound or seven-day review')
    if required>body['available_bytes'] or body['project_usage_upper_bound_bytes']+peak>body['effective_project_quota_bytes']:
        raise SystemExit('Heavy-write admission exceeds free-space or project-quota budget')
    try:
        start = datetime.fromisoformat(body['admitted_at_utc'])
        expiry = datetime.fromisoformat(body['retention_review_by_utc'])
        now = datetime.now(timezone.utc)
    except (KeyError,TypeError,ValueError) as error:
        raise SystemExit('Heavy-write admission has invalid UTC times') from error
    if start.tzinfo is None or expiry.tzinfo is None or not start<=now<expiry or expiry-start>__import__('datetime').timedelta(days=7):
        raise SystemExit('Heavy-write admission is stale or exceeds the seven-day review bound')
    batch = body.get('batch')
    if not isinstance(batch,str) or not re.fullmatch(r'[A-Za-z0-9-]+',batch):
        raise SystemExit('Heavy-write admission batch is invalid')
    lock = (ROOT/body.get('coordination_lock','')).resolve()
    lock.relative_to((ROOT/'runtime').resolve())
    owner = read_json(lock)
    if owner.get('machine_id')!=machine_id() or owner.get('batch')!=batch or owner.get('process_id')!=os.getpid() or body.get('coordination_lock_sha256')!=file_sha256(lock):
        raise SystemExit('Heavy-write admission is not bound to the live coordination lock')
    return body


def payload(preview=False, packages=None, validation_keys=None, sink=None, heavy_write_admission=None, output=None):
    catalog=read_json(MOD/"data/catalog.json")
    generated=read_json(MOD/"data/generated.json")["portraits"]
    from mod_nailong.tools.texture_resolution import game_image, POLICY_ID
    exceptions,exception_receipt=nonperson_scope()
    for key in exceptions:
        if key in generated:raise SystemExit(f'Non-person exception must not have a generated row: {key}')
    missing=[a for a in catalog["assets"] if a["source_sha256"] not in exceptions and (a["source_sha256"] not in generated or not ready(generated[a["source_sha256"]]))]
    if not preview and missing:
        raise SystemExit(f"RELEASE BLOCKED: {len(missing)} of {len(catalog['assets'])} source textures not generated/reviewed; use --preview for an explicitly incomplete development package")
    if not preview and catalog["unresolved_references"]:
        raise SystemExit(f"RELEASE BLOCKED: {len(catalog['unresolved_references'])} unresolved baseline character references need analysis")
    if not generated and not exceptions:raise SystemExit("No generated art available")
    # Product build profile is explicit. Higher numbered DLC wins shared texture paths;
    # preserve every distinct variant as a generation input, never flatten the inventory.
    selected=profile_assets(catalog,packages)
    if validation_keys is not None:
        if not preview:raise SystemExit('Validation subsets are development previews only; never a formal release')
        validation_keys=set(validation_keys)
        if not validation_keys or not validation_keys<={a['source_sha256'] for a in selected.values()}:raise SystemExit('Unknown or empty validation source selection')
        selected={path:a for path,a in selected.items() if a['source_sha256'] in validation_keys}
    # Native dimensions remove the experimental HD adapter. Art coverage and
    # actual gameplay acceptance remain separate release requirements.
    qualification_file=MOD/'data/game-display-qualification.json'
    qualification=read_json(qualification_file) if qualification_file.exists() else {'status':'unqualified'}
    if not preview and qualification.get('status')!='qualified_for_release':
        raise SystemExit('RELEASE BLOCKED: native-size portrait gameplay acceptance remains unqualified')
    originals={a['id']:original_nonperson_bytes(a) for a in selected.values() if a['source_sha256'] in exceptions}
    files={}
    file_records=[]
    def emit(name,data):
        file_records.append({'path':name,'bytes':len(data),'sha256':sha256(data)})
        if sink is None:files[name]=data
        else:sink(name,data)
    # Budget actual native-size payloads, while reading one immutable HD
    # master at a time. Original PNG bytes never enter the game staging.
    estimate=sum(4*a['size'][0]*a['size'][1]+128 for a in selected.values() if a['source_sha256'] in generated and ready(generated[a['source_sha256']]))+sum(len(raw) for raw in originals.values())
    if estimate>256*1024*1024:
        validate_heavy_write_admission(heavy_write_admission,estimate,output)
    bindings=[]
    profile_missing=[]
    for asset in sorted(selected.values(),key=lambda a:a['path']):
        key=asset["source_sha256"]
        path=PurePosixPath(asset["path"])
        if path.is_absolute() or ".." in path.parts or not path.as_posix().startswith("gfx/"):raise SystemExit("Invalid virtual texture path")
        if key in exceptions:
            data=originals[asset['id']]
            emit(path.as_posix(),data)
            bindings.append({'path':path.as_posix(),'package':asset['package'],'source_sha256':key,'sha256':sha256(data),'size':asset['size'],'original_game_size':asset['size'],'fullsize_master_sha256':None,'resized':False,'resolution_policy':'original-game-file-bytes-preserved','preserved_original_nonperson_exception':True})
            continue
        if key not in generated or not ready(generated[key]):
            profile_missing.append(asset["id"])
            continue
        row=generated[key]
        if not row.get('generated_fullsize_image') or not row.get('generated_fullsize_sha256'):raise SystemExit('Missing original fullsize master; no silent low-resolution fallback')
        source=ROOT/row['generated_fullsize_image']
        if file_sha256(source)!=row['generated_fullsize_sha256']:raise SystemExit(f'Fullsize master checksum mismatch: {source}')
        stream=io.BytesIO()
        with Image.open(source) as image:
            original_size=list(image.size)
            if original_size!=row['generated_fullsize_size']:raise SystemExit('Fullsize master dimension metadata changed')
            image=game_image(image,asset['size'])
            published_size=list(image.size)
            # Original game dimensions; uncompressed ARGB8888 preserves the
            # derived RGBA pixels, including transparent advisor borders.
            if path.suffix.lower()==".dds":image.convert("RGBA").save(stream,format="DDS")
            elif path.suffix.lower()==".tga":image.convert("RGBA").save(stream,format="TGA")
            else:image.convert("RGBA").save(stream,format="PNG")
        data=stream.getvalue()
        with Image.open(io.BytesIO(data)) as readback:
            if list(readback.size)!=published_size:raise SystemExit("Encoded texture readback failed")
        emit(path.as_posix(),data)
        bindings.append({"path":path.as_posix(),"package":asset["package"],"source_sha256":key,"sha256":sha256(data),"size":published_size,'original_game_size':asset['size'],'fullsize_master_sha256':row['generated_fullsize_sha256'],'fullsize_master_size':original_size,'resized':published_size!=original_size,'resolution_policy':POLICY_ID})
    if not bindings:raise SystemExit("No reviewed portraits in selected profile")
    descriptor=(MOD/"mod/descriptor.mod").read_text(encoding="utf-8")
    if "remote_file_id" in descriptor or "replace_path" in descriptor:raise SystemExit("Invalid descriptor")
    # Public product naming follows the user's release instruction. The
    # manifest retains exact coverage and validation status independently.
    thumbnail=thumbnail_bytes()
    if thumbnail is not None:emit('thumbnail.png',thumbnail)
    emit('descriptor.mod',descriptor.encode('utf-8'))
    return files,{"schema":"naiwa-release-manifest-v2","archive_filename":"gangnailongxin.zip","preview":preview,"art_complete":not missing,"game_version":catalog["game_version"],"catalog_sha256":file_sha256(MOD/"data/catalog.json"),"source_textures":len(catalog["assets"]),"generated_unique_images":len(generated),"selected_profile":sorted(packages) if packages is not None else "all-installed-catalog-packages; highest DLC numeric ID on shared paths","unresolved_baseline_references":len(catalog["unresolved_references"]),"profile_missing_texture_count":len(profile_missing),'texture_resolution_policy_id':POLICY_ID,'texture_resolution_policy':'Each approved original PNG master is retained unchanged; game derivatives match each original source texture dimensions exactly using RGBA LANCZOS; registered non-person exceptions preserve original file bytes','validation_source_keys':sorted(validation_keys) if validation_keys is not None else None,'validation_scope':'selected development subset only' if validation_keys is not None else 'entire selected profile',"preserved_original_nonperson_exceptions":sorted(row['index'] for row in exceptions.values() if row['source_sha256'] in {a['source_sha256'] for a in selected.values()}),"nonperson_scope_decision":exception_receipt,"bindings":bindings,"files":sorted(file_records,key=lambda r:r['path'])}

def build(output,preview=False,packages=None,validation_keys=None,heavy_write_admission=None):
    if output.exists():raise SystemExit("Output already exists; choose a fresh --output path")
    staging=output/"staging"
    staging.mkdir(parents=True)
    archive=output/"gangnailongxin.zip"
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as handle:
        def emit(name,data):
            target=staging/Path(name);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            info=zipfile.ZipInfo(name,date_time=(2020,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            info.create_system=3
            handle.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
        _,manifest=payload(preview,packages,validation_keys,sink=emit,heavy_write_admission=heavy_write_admission,output=output)
        from mod_nailong.tools.texture_resolution import POLICY_ID
        manifest['texture_resolution_policy_id']=POLICY_ID
        manifest['texture_resolution_policy']='Each approved original PNG master is retained unchanged; game derivatives match each original source texture dimensions exactly using RGBA LANCZOS; registered non-person exceptions preserve original file bytes'
    write_json(output/"manifest.json",manifest)
    verify(output)
    from mod_nailong.tools.texture_resolution import verify_game_textures,write_pixel_proof
    pixel_check=verify_game_textures(output,manifest,catalog=read_json(MOD/'data/catalog.json'),generated=read_json(MOD/'data/generated.json')['portraits'],root=ROOT)
    write_pixel_proof(output,manifest,pixel_check)
    return manifest

def repackage_verified(source, output, heavy_write_admission):
    """Repackage identical, already pixel-verified textures with current branding."""
    import copy
    source=Path(source);output=Path(output)
    if output.exists():raise SystemExit('Choose a fresh package output')
    verify(source)
    from mod_nailong.tools.texture_resolution import verify_game_textures,write_pixel_proof
    prior=read_json(source/'manifest.json')
    catalog=read_json(MOD/'data/catalog.json')
    generated=read_json(MOD/'data/generated.json')['portraits']
    if prior['catalog_sha256']!=file_sha256(MOD/'data/catalog.json'):
        raise SystemExit('Catalog changed; a full rebuild is required')
    manifest=copy.deepcopy(prior)
    records={r['path']:r for r in prior['files']}
    records.pop('thumbnail.jpg',None)
    selected=profile_assets(catalog);exceptions,_=nonperson_scope()
    # Match the admission's conservative decoded-size estimate, which uses
    # a 128-byte allowance even for the smaller TGA/PNG headers.
    estimate=sum(4*a['size'][0]*a['size'][1]+128 for a in selected.values() if ready(generated.get(a['source_sha256'],{})))
    estimate+=sum(len(original_nonperson_bytes(a)) for a in selected.values() if a['source_sha256'] in exceptions)
    if estimate>256*1024*1024:validate_heavy_write_admission(heavy_write_admission,estimate,output)
    # No pixels are regenerated here. Transfer the existing pixel proof only
    # after verify() rereads every staged/ZIP byte and all source/approval
    # bindings still match. Rehashing unused PNG inputs is not required to
    # copy already verified game textures; this is explicitly not a new
    # verification of the current master files on disk.
    proof=read_json(source/'native-texture-verification.json')
    expected=[{'path':r['path'],'source_sha256':r['source_sha256'],'master_sha256':r.get('fullsize_master_sha256'),'texture_sha256':r['sha256']} for r in prior['bindings']]
    if proof.get('manifest_sha256')!=file_sha256(source/'manifest.json') or proof.get('bindings')!=expected or proof.get('verification',{}).get('source_identity_and_rgba_verified') is not True:
        raise ValueError('Stale or mismatched native pixel verification proof')
    from mod_nailong.tools.texture_resolution import POLICY_ID
    if proof.get('policy')!=POLICY_ID or prior.get('texture_resolution_policy_id')!=POLICY_ID:
        raise ValueError('Obsolete texture policy')
    for binding in prior['bindings']:
        asset=next((a for a in selected.values() if a['path'].lower()==binding['path'].lower()),None)
        if asset is None or asset['source_sha256']!=binding['source_sha256'] or asset['package']!=binding['package'] or asset['size']!=binding['size']:
            raise ValueError('Portrait source/package binding changed: '+binding['path'])
        digest=binding.get('fullsize_master_sha256')
        if digest is None:
            if binding['source_sha256'] not in exceptions or (source/'staging'/binding['path']).read_bytes()!=original_nonperson_bytes(asset):raise ValueError('Unregistered non-person texture')
        elif not ready(generated.get(binding['source_sha256'],{})) or generated[binding['source_sha256']].get('generated_fullsize_sha256')!=digest:
            raise ValueError('Portrait no longer points to its own currently approved master: '+binding['path'])
    verification=dict(proof['verification'],pixel_proof_reused=True,current_master_bytes_rehashed=False)
    descriptor=(MOD/'mod/descriptor.mod').read_bytes()
    if b'remote_file_id' in descriptor or b'replace_path' in descriptor:raise SystemExit('Invalid descriptor')
    replacements={'descriptor.mod':descriptor,'thumbnail.png':thumbnail_bytes()}
    if replacements['thumbnail.png'] is None:raise SystemExit('Missing Workshop branding')
    staging=output/'staging';staging.mkdir(parents=True)
    with zipfile.ZipFile(output/'gangnailongxin.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name in sorted(set(records)|set(replacements)):
            raw=replacements[name] if name in replacements else (source/'staging'/name).read_bytes()
            if name not in replacements and sha256(raw)!=records[name]['sha256']:raise SystemExit('Verified payload changed')
            target=staging/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16
            archive.writestr(info,raw,compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
            records[name]={'path':name,'bytes':len(raw),'sha256':sha256(raw)}
    manifest['files']=sorted(records.values(),key=lambda r:r['path'])
    write_json(output/'manifest.json',manifest);verify(output)
    verification.update(repackaged_from_manifest_sha256=file_sha256(source/'manifest.json'),texture_bytes_unchanged=True)
    write_pixel_proof(output,manifest,verification)
    return manifest


def verify(output):
    manifest=read_json(output/"manifest.json")
    expected={r["path"]:r for r in manifest["files"]}
    actual={p.relative_to(output/"staging").as_posix() for p in (output/"staging").rglob("*") if p.is_file()}
    if actual!=set(expected):raise SystemExit("Staging file set differs from manifest")
    # Older immutable build receipts predate the product-name correction.
    # Their original ZIP remains verifiable; every new build declares its name.
    archive_name=manifest.get('archive_filename','naiwa-world.zip')
    with zipfile.ZipFile(output/archive_name) as archive:
        if set(archive.namelist())!=set(expected):raise SystemExit("ZIP file set differs from manifest")
        for name,row in expected.items():
            raw=(output/"staging"/name).read_bytes()
            if len(raw)!=row["bytes"] or sha256(raw)!=row["sha256"] or raw!=archive.read(name):raise SystemExit(f"Manifest/ZIP mismatch: {name}")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview",action="store_true")
    parser.add_argument("--check",action="store_true")
    parser.add_argument("--output",type=Path)
    parser.add_argument("--packages",nargs="*",help="Explicit enabled DLC package keys; empty list builds base-only")
    parser.add_argument('--source-key',action='append',help='Explicit preview-only validation source SHA; repeat for a small HD runtime sample')
    parser.add_argument('--validation-sample',type=int,help='Preview-only bounded routine validation; does not validate the full portrait corpus')
    args=parser.parse_args()
    validation_keys=args.source_key
    if args.validation_sample is not None:
        if not args.preview or args.source_key or not 1<=args.validation_sample<=12:parser.error('Use --preview and a validation sample between 1 and 12, without --source-key')
        rows=read_json(MOD/'data/generated.json')['portraits']
        validation_keys=validation_sample_keys(read_json(MOD/'data/catalog.json'),rows,args.validation_sample,args.packages)
        if not validation_keys:raise SystemExit('No reviewed portraits in selected profile')
    if args.check:
        with tempfile.TemporaryDirectory(prefix="naiwa-repro-") as folder:
            first,second=Path(folder)/"a",Path(folder)/"b"
            build(first,args.preview,args.packages,validation_keys)
            build(second,args.preview,args.packages,validation_keys)
            if (first/"manifest.json").read_bytes()!=(second/"manifest.json").read_bytes() or file_sha256(first/'gangnailongxin.zip')!=file_sha256(second/'gangnailongxin.zip'):raise SystemExit("Reproducibility check failed")
            print('PASS: deterministic double build, exact staging/manifest/ZIP and HD texture decode; scope='+('selected preview validation subset' if validation_keys is not None else 'entire selected profile'))
        return
    if not args.output:parser.error("Choose a fresh --output or use --check")
    manifest=build(args.output,args.preview,args.packages,validation_keys)
    write_json(args.output/"build-receipt.json",{"machine_id":machine_id(),"observed_at_utc":utc_now(),"source":"build_release.py + manifest.json","zip_sha256":file_sha256(args.output/"gangnailongxin.zip"),"preview":args.preview,"files":len(manifest["files"]),"live_acceptance":"not-run"})
    print(f"Built {len(manifest['bindings'])} portrait overrides: {args.output.resolve()}")

if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
