"""Development HD adapters: preserve pixels, reject ambiguous native bindings."""
from __future__ import annotations
from collections import defaultdict
import io
from pathlib import Path
import zipfile
from PIL import Image
from tools.common import ROOT, file_sha256, sha256, write_json
from mod_nailong.tools.catalog import tokens, virtual_texture_path


def sprite_records(text):
    ts=list(tokens(text));result=[]
    kinds={'spritetype','cornersizedspritetype','corneredtilespritetype'}
    for i in range(len(ts)-2):
        if ts[i].lower() not in kinds or ts[i+1:i+3]!=['=','{']:continue
        depth=1;j=i+3;values={}
        while j<len(ts) and depth:
            if ts[j]=='{':depth+=1
            elif ts[j]=='}':depth-=1
            elif depth==1 and j+2<len(ts) and ts[j+1]=='=' and ts[j+2]!='{':
                values[ts[j].lower()]=ts[j+2]
            j+=1
        if 'name' in values and 'texturefile' in values:
            result.append({'kind':ts[i].lower(),'name':values['name'],
                           'texture':virtual_texture_path(values['texturefile']).lower(),
                           'frames':values.get('noofframes','1'),
                           'existing_mask':values.get('masking_texture')})
    return result


def unique_aliases(records, selected_paths):
    """Do not guess a DLC load order or turn animation strips into one frame."""
    selected={p.lower() for p in selected_paths};grouped=defaultdict(list)
    for record in records:grouped[record['name'].lower()].append(record)
    aliases=[];covered=set()
    for name,entries in sorted(grouped.items()):
        targets={r['texture'] for r in entries}
        if not targets&selected:continue
        if len(targets)!=1:raise ValueError('Ambiguous native sprite alias: '+name)
        for r in entries:
            if r['kind']!='spritetype':raise ValueError('Unsupported native sprite type: '+name)
            if r['frames']!='1':raise ValueError('Multi-frame or symbolic frame count requires a separate adapter: '+name)
            if r['existing_mask']:raise ValueError('Native mask already occupies the HD slot: '+name)
        target=next(iter(targets));covered.add(target)
        aliases.append({'name':entries[0]['name'],'texture':target,
                        'source_ids':sorted({r['source_id'] for r in entries})})
    if selected-covered:raise ValueError('No verified normal native sprite alias for: '+', '.join(sorted(selected-covered)))
    return aliases


def augment(output, manifest, aliases, source_proofs, native_include_proofs=None):
    """Add layout-only carriers; DDS/PNG equality is checked for every sample."""
    from mod_nailong.tools.build_release import verify
    output=Path(output);staging=output/'staging'
    bindings={r['path'].lower():r for r in manifest['bindings']}
    if {r['texture'] for r in aliases}!=set(bindings):raise ValueError('Alias sample does not cover exactly the built textures')
    added={};pixel_proofs=[]
    for path,binding in bindings.items():
        master=ROOT/'mod_nailong/assets/generated_fullsize'/f'{binding["fullsize_master_sha256"]}.png'
        if file_sha256(master)!=binding['fullsize_master_sha256']:raise ValueError('Master bytes changed')
        with Image.open(master) as original,Image.open(staging/binding['path']) as payload:
            original=original.convert('RGBA');payload=payload.convert('RGBA')
            if original.size!=payload.size or original.tobytes()!=payload.tobytes():raise ValueError('HD pixels changed')
            pixel_proofs.append({'source_sha256':binding['source_sha256'],
                                 'master_sha256':binding['fullsize_master_sha256'],
                                 'rgba_pixel_sha256':sha256(payload.tobytes()),'rgba_equal':True})
        width,height=binding['original_game_size']
        if not (1<=width<=4096 and 1<=height<=4096):raise ValueError('Unexpected layout carrier size')
        rel=f'gfx/interface/naiwa_white_layout_{width}_{height}.dds'
        if rel not in added:
            stream=io.BytesIO();Image.new('RGBA',(width,height),(255,255,255,255)).save(stream,format='DDS');added[rel]=stream.getvalue()
    added['gfx/FX/naiwa_hd_masking_sampler.shader']=(ROOT/'mod_nailong/assets/runtime/hd_portrait_masking_sampler.shader').read_bytes()
    chunks=['spriteTypes = {']
    for alias in aliases:
        binding=bindings[alias['texture']];w,h=binding['original_game_size']
        chunks.append(f''' spriteType = {{
  name = "{alias['name']}"
  texturefile = "gfx/interface/naiwa_white_layout_{w}_{h}.dds"
  masking_texture = "{binding['path']}"
  effectFile = "gfx/FX/naiwa_hd_masking_sampler.lua"
  noOfFrames = 1
  legacy_lazy_load = no
 }}''')
    chunks.append('}')
    added['interface/zz_naiwa_hd_masking_samples.gfx']=('\n'.join(chunks)+'\n').encode('utf-8')
    existing={r['path'] for r in manifest['files']}
    if existing&set(added):raise ValueError('Adapter would overwrite an existing payload file')
    for rel,data in sorted(added.items()):
        target=staging/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        manifest['files'].append({'path':rel,'bytes':len(data),'sha256':sha256(data)})
    used={source_id for a in aliases for source_id in a['source_ids']}
    manifest['files'].sort(key=lambda r:r['path'])
    manifest['development_fixture']={'kind':'Unqualified native sprite HD masking sample set',
        'formal_release_eligible':False,'hd_raster_resized':False,
        'carrier_contains_no_portrait_pixels':True,'gui_or_gameplay_changes':False,
        'aliases':aliases,'native_source_proofs':[p for p in source_proofs if p['id'] in used],
        'native_shader_include_proofs':native_include_proofs or [],
        'fullsize_pixel_proofs':pixel_proofs,
        'live_acceptance':'Not run; every actual consumer, tooltip and hit area requires separate runtime evidence. Static parsing and unchanged bytes do not qualify display.'}
    write_json(output/'manifest.json',manifest)
    with zipfile.ZipFile(output/'naiwa-world.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for row in manifest['files']:
            info=zipfile.ZipInfo(row['path'],date_time=(2020,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;info.create_system=3
            archive.writestr(info,(staging/row['path']).read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    verify(output)
    return manifest
