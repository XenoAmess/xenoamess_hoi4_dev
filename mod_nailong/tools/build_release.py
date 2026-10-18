"""Build a deterministic, image-only HOI4 mod from reviewed generated art."""
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

def payload(preview=False, packages=None, validation_keys=None, sink=None):
    catalog=read_json(MOD/"data/catalog.json")
    generated=read_json(MOD/"data/generated.json")["portraits"]
    missing=[a for a in catalog["assets"] if a["source_sha256"] not in generated or not ready(generated[a["source_sha256"]])]
    if not preview and missing:
        raise SystemExit(f"RELEASE BLOCKED: {len(missing)} of {len(catalog['assets'])} source textures not generated/reviewed; use --preview for an explicitly incomplete development package")
    if not preview and catalog["unresolved_references"]:
        raise SystemExit(f"RELEASE BLOCKED: {len(catalog['unresolved_references'])} unresolved baseline character references need analysis")
    if not generated:raise SystemExit("No generated art available")
    selected={}
    # Product build profile is explicit. Higher numbered DLC wins shared texture paths;
    # preserve every distinct variant as a generation input, never flatten the inventory.
    def rank(asset):
        if asset["package"]=="base":return -1
        match=re.search(r"dlc(\d+)",asset["package"])
        return int(match[1]) if match else 0
    eligible=[a for a in catalog["assets"] if packages is None or a["package"]=="base" or a["package"] in packages]
    for asset in sorted(eligible,key=lambda a:(rank(a),a["package"],a["path"])):
        # Choose profile variant BEFORE checking art readiness; a missing DLC image
        # must not silently turn into another package's generated portrait.
        selected[asset["path"].lower()]=asset
    if validation_keys is not None:
        if not preview:raise SystemExit('Validation subsets are development previews only; never a formal release')
        validation_keys=set(validation_keys)
        if not validation_keys or not validation_keys<={a['source_sha256'] for a in selected.values()}:raise SystemExit('Unknown or empty validation source selection')
        selected={path:a for path,a in selected.items() if a['source_sha256'] in validation_keys}
    # Fullsize encoding is not proof that all native GUI consumers display it
    # correctly. Actual probes found overflow, so a complete art catalog alone
    # must not accidentally unlock a broken formal release.
    qualification_file=MOD/'data/hd-display-qualification.json'
    qualification=read_json(qualification_file) if qualification_file.exists() else {'status':'unqualified'}
    if not preview and qualification.get('status')!='qualified_for_release':
        raise SystemExit('RELEASE BLOCKED: fullsize portrait display compatibility remains unqualified; actual GUI overflow must be resolved and evidenced before release')
    files={}
    file_records=[]
    def emit(name,data):
        file_records.append({'path':name,'bytes':len(data),'sha256':sha256(data)})
        if sink is None:files[name]=data
        else:sink(name,data)
    # Lossless fullsize DDS can be much larger than the old native-size preview.
    # Keep routine checks within the already observed bounded-write allowance.
    estimate=sum(4*generated[a['source_sha256']]['generated_fullsize_size'][0]*generated[a['source_sha256']]['generated_fullsize_size'][1]+128 for a in selected.values() if a['source_sha256'] in generated and ready(generated[a['source_sha256']]))
    if estimate>256*1024*1024:
        raise SystemExit('Fullsize staging exceeds the bounded 256 MiB check/export allowance; use an explicit preview validation subset for routine checks. A full export needs shared-policy heavy-write admission before increasing this bound.')
    bindings=[]
    profile_missing=[]
    for asset in sorted(selected.values(),key=lambda a:a['path']):
        key=asset["source_sha256"]
        if key not in generated or not ready(generated[key]):
            profile_missing.append(asset["id"])
            continue
        row=generated[key]
        if not row.get('generated_fullsize_image') or not row.get('generated_fullsize_sha256'):raise SystemExit('Missing original fullsize master; no silent low-resolution fallback')
        source=ROOT/row['generated_fullsize_image']
        if file_sha256(source)!=row['generated_fullsize_sha256']:raise SystemExit(f'Fullsize master checksum mismatch: {source}')
        path=PurePosixPath(asset["path"])
        if path.is_absolute() or ".." in path.parts or not path.as_posix().startswith("gfx/"):raise SystemExit("Invalid virtual texture path")
        stream=io.BytesIO()
        with Image.open(source) as image:
            published_size=list(image.size)
            # Uncompressed legacy DDS ARGB8888 is supported by Clausewitz and
            # preserves arbitrary original dimensions and transparent advisor borders.
            if path.suffix.lower()==".dds":image.convert("RGBA").save(stream,format="DDS")
            elif path.suffix.lower()==".tga":image.convert("RGBA").save(stream,format="TGA")
            else:image.convert("RGBA").save(stream,format="PNG")
        data=stream.getvalue()
        with Image.open(io.BytesIO(data)) as readback:
            if list(readback.size)!=published_size:raise SystemExit("Encoded texture readback failed")
        emit(path.as_posix(),data)
        bindings.append({"path":path.as_posix(),"package":asset["package"],"source_sha256":key,"sha256":sha256(data),"size":published_size,'original_game_size':asset['size'],'fullsize_master_sha256':row['generated_fullsize_sha256'],'resized':False,'resolution_policy':'original-fullsize-master; compatibility not implied by static encoding'})
    if not bindings:raise SystemExit("No reviewed portraits in selected profile")
    descriptor=(MOD/"mod/descriptor.mod").read_text(encoding="utf-8")
    if "remote_file_id" in descriptor or "replace_path" in descriptor:raise SystemExit("Invalid descriptor")
    if preview:descriptor=descriptor.replace("(Development)","(INCOMPLETE PREVIEW)")
    emit('descriptor.mod',descriptor.encode('utf-8'))
    return files,{"schema":"naiwa-release-manifest-v2","preview":preview,"art_complete":not missing,"game_version":catalog["game_version"],"catalog_sha256":file_sha256(MOD/"data/catalog.json"),"source_textures":len(catalog["assets"]),"generated_unique_images":len(generated),"selected_profile":sorted(packages) if packages is not None else "all-installed-catalog-packages; highest DLC numeric ID on shared paths","unresolved_baseline_references":len(catalog["unresolved_references"]),"profile_missing_texture_count":len(profile_missing),'texture_resolution_policy':'original fullsize master; no pre-downscale','validation_source_keys':sorted(validation_keys) if validation_keys is not None else None,'validation_scope':'selected development subset only' if validation_keys is not None else 'entire selected profile',"bindings":bindings,"files":sorted(file_records,key=lambda r:r['path'])}

def build(output,preview=False,packages=None,validation_keys=None):
    if output.exists():raise SystemExit("Output already exists; choose a fresh --output path")
    staging=output/"staging"
    staging.mkdir(parents=True)
    archive=output/"naiwa-world.zip"
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as handle:
        def emit(name,data):
            target=staging/Path(name);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            info=zipfile.ZipInfo(name,date_time=(2020,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            info.create_system=3
            handle.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
        _,manifest=payload(preview,packages,validation_keys,sink=emit)
    write_json(output/"manifest.json",manifest)
    verify(output)
    return manifest

def verify(output):
    manifest=read_json(output/"manifest.json")
    expected={r["path"]:r for r in manifest["files"]}
    actual={p.relative_to(output/"staging").as_posix() for p in (output/"staging").rglob("*") if p.is_file()}
    if actual!=set(expected):raise SystemExit("Staging file set differs from manifest")
    with zipfile.ZipFile(output/"naiwa-world.zip") as archive:
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
        validation_keys=sorted(k for k,r in rows.items() if ready(r))[:args.validation_sample]
    if args.check:
        with tempfile.TemporaryDirectory(prefix="naiwa-repro-") as folder:
            first,second=Path(folder)/"a",Path(folder)/"b"
            build(first,args.preview,args.packages,validation_keys)
            build(second,args.preview,args.packages,validation_keys)
            if (first/"manifest.json").read_bytes()!=(second/"manifest.json").read_bytes() or file_sha256(first/'naiwa-world.zip')!=file_sha256(second/'naiwa-world.zip'):raise SystemExit("Reproducibility check failed")
            print('PASS: deterministic double build, exact staging/manifest/ZIP and HD texture decode; scope='+('selected preview validation subset' if validation_keys is not None else 'entire selected profile'))
        return
    if not args.output:parser.error("Choose a fresh --output or use --check")
    manifest=build(args.output,args.preview,args.packages,validation_keys)
    write_json(args.output/"build-receipt.json",{"machine_id":machine_id(),"observed_at_utc":utc_now(),"source":"build_release.py + manifest.json","zip_sha256":file_sha256(args.output/"naiwa-world.zip"),"preview":args.preview,"files":len(manifest["files"]),"live_acceptance":"not-run"})
    print(f"Built {len(manifest['bindings'])} portrait overrides: {args.output.resolve()}")

if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
