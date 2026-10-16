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
    return row.get("review")=="approved" and row.get("art_direction")=="hair-features-v1"

def payload(preview=False, packages=None):
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
    files={}
    bindings=[]
    profile_missing=[]
    for asset in selected.values():
        key=asset["source_sha256"]
        if key not in generated or not ready(generated[key]):
            profile_missing.append(asset["id"])
            continue
        row=generated[key]
        source=ROOT/row["image"]
        if file_sha256(source)!=row["image_sha256"]:raise SystemExit(f"Art checksum mismatch: {source}")
        path=PurePosixPath(asset["path"])
        if path.is_absolute() or ".." in path.parts or not path.as_posix().startswith("gfx/"):raise SystemExit("Invalid virtual texture path")
        stream=io.BytesIO()
        with Image.open(source) as image:
            if list(image.size)!=asset["size"]:raise SystemExit("Original texture dimensions changed")
            # Uncompressed legacy DDS ARGB8888 is supported by Clausewitz and
            # preserves arbitrary original dimensions and transparent advisor borders.
            if path.suffix.lower()==".dds":image.convert("RGBA").save(stream,format="DDS")
            elif path.suffix.lower()==".tga":image.convert("RGBA").save(stream,format="TGA")
            else:image.convert("RGBA").save(stream,format="PNG")
        data=stream.getvalue()
        with Image.open(io.BytesIO(data)) as readback:
            if list(readback.size)!=asset["size"]:raise SystemExit("Encoded texture readback failed")
        files[path.as_posix()]=data
        bindings.append({"path":path.as_posix(),"package":asset["package"],"source_sha256":key,"sha256":sha256(data),"size":asset["size"]})
    if not bindings:raise SystemExit("No reviewed portraits in selected profile")
    descriptor=(MOD/"mod/descriptor.mod").read_text(encoding="utf-8")
    if "remote_file_id" in descriptor or "replace_path" in descriptor:raise SystemExit("Invalid descriptor")
    if preview:descriptor=descriptor.replace("(Development)","(INCOMPLETE PREVIEW)")
    files["descriptor.mod"]=descriptor.encode("utf-8")
    return files,{"schema":"naiwa-release-manifest-v1","preview":preview,"art_complete":not missing,"game_version":catalog["game_version"],"catalog_sha256":file_sha256(MOD/"data/catalog.json"),"source_textures":len(catalog["assets"]),"generated_unique_images":len(generated),"selected_profile":sorted(packages) if packages is not None else "all-installed-catalog-packages; highest DLC numeric ID on shared paths","unresolved_baseline_references":len(catalog["unresolved_references"]),"profile_missing_texture_count":len(profile_missing),"bindings":bindings,"files":[{"path":name,"bytes":len(data),"sha256":sha256(data)} for name,data in sorted(files.items())]}

def build(output,preview=False,packages=None):
    if output.exists():raise SystemExit("Output already exists; choose a fresh --output path")
    files,manifest=payload(preview,packages)
    staging=output/"staging"
    staging.mkdir(parents=True)
    for name,data in files.items():
        target=staging/Path(name)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
    write_json(output/"manifest.json",manifest)
    archive=output/"naiwa-world.zip"
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as handle:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(2020,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            info.create_system=3
            handle.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
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
    args=parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory(prefix="naiwa-repro-") as folder:
            first,second=Path(folder)/"a",Path(folder)/"b"
            build(first,args.preview,args.packages)
            build(second,args.preview,args.packages)
            if (first/"manifest.json").read_bytes()!=(second/"manifest.json").read_bytes() or (first/"naiwa-world.zip").read_bytes()!=(second/"naiwa-world.zip").read_bytes():raise SystemExit("Reproducibility check failed")
            print("PASS: deterministic double build, exact staging/manifest/ZIP and texture decode")
        return
    if not args.output:parser.error("Choose a fresh --output or use --check")
    manifest=build(args.output,args.preview,args.packages)
    write_json(args.output/"build-receipt.json",{"machine_id":machine_id(),"observed_at_utc":utc_now(),"source":"build_release.py + manifest.json","zip_sha256":file_sha256(args.output/"naiwa-world.zip"),"preview":args.preview,"files":len(manifest["files"]),"live_acceptance":"not-run"})
    print(f"Built {len(manifest['bindings'])} portrait overrides: {args.output.resolve()}")

if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
