"""Development HD adapters: preserve pixels, reject ambiguous native bindings."""
from __future__ import annotations
from collections import defaultdict
import io
from pathlib import Path
import zipfile
from PIL import Image
from tools.common import ROOT, file_sha256, read_json, sha256, write_json
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


def partition_bindings(bindings, exception_keys):
    people={};preserved={}
    for binding in bindings:
        path=binding['path'].lower()
        if binding['source_sha256'] in exception_keys:
            if not binding.get('preserved_original_nonperson_exception') or binding.get('fullsize_master_sha256') is not None:
                raise ValueError('Non-person exception must preserve original bytes, not a generated master')
            preserved[path]=binding
        else:
            if binding.get('preserved_original_nonperson_exception') or not binding.get('fullsize_master_sha256'):
                raise ValueError('Person binding is missing its fullsize master')
            people[path]=binding
    return people,preserved


def take_inventory_only(bindings, records):
    result={}
    for record in records or []:
        path=record['path'].lower()
        if path not in bindings or record.get('classification')!='no_current_native_consumer_in_bounded_inventory' or record.get('runtime_display_not_applicable_unless_a_consumer_is_found') is not True:
            raise ValueError('Unproven inventory-only binding')
        if bindings[path]['source_sha256']!=record['source_sha256']:
            raise ValueError('Inventory-only source identity changed')
        result[path]=bindings[path]
    return result


def verify_layout_bindings(output, manifest=None):
    """Deployment gate independent of a historical ZIP's byte integrity."""
    output = Path(output)
    manifest = manifest or read_json(output/'manifest.json')
    gfx = output/'staging/interface/zz_naiwa_hd_masking_samples.gfx'
    fixture = manifest.get('development_fixture')
    if not gfx.exists():
        if fixture and fixture.get('aliases'):
            raise ValueError('HD fixture alias definitions are absent')
        return {'scope':'no generated multi-portrait masking fixture'}
    if not fixture or 'aliases' not in fixture:
        raise ValueError('HD masking definitions have no binding manifest')
    records = sprite_records(gfx.read_text(encoding='utf-8'))
    actual = {record['name'].lower(): virtual_texture_path(record.get('existing_mask') or '').lower() for record in records}
    expected = {alias['name'].lower(): alias['texture'].lower() for alias in fixture['aliases']}
    if len(actual) != len(records) or actual != expected:
        raise ValueError('HD sprite names/masks differ from their exact manifest aliases')
    exception_keys = {row['source_sha256'] for row in fixture.get('preserved_original_nonperson_paths', [])}
    people, _ = partition_bindings(manifest['bindings'], exception_keys)
    for record in records:
        if actual[record['name'].lower()] not in people:raise ValueError('HD alias has no matching person binding')
        binding = people[actual[record['name'].lower()]]
        carrier = output/'staging'/record['texture']
        with Image.open(carrier) as image:
            if list(image.size) != binding['original_game_size'] or image.convert('RGBA').getextrema() != ((255,255),)*4:
                raise ValueError('HD layout carrier changed its size or contains portrait pixels: '+record['texture'])
    return {'scope':'exact native masking alias graph and layout carrier dimensions',
            'aliases':len(records), 'primary_layout_textures':len({r['texture'] for r in records}), 'runtime_acceptance_implied':False}


def augment(output, manifest, aliases, source_proofs, native_include_proofs=None, inventory_only=None):
    """Add layout-only carriers; DDS/PNG equality is checked for every person sample."""
    from mod_nailong.tools.build_release import verify,nonperson_scope
    if manifest.get('texture_resolution_policy_id')=='native-source-size-v1':
        raise ValueError('HD masking adapter retired for native-size game payloads by user decision')
    output=Path(output);staging=output/'staging'
    all_bindings={r['path'].lower():r for r in manifest['bindings']}
    bindings,preserved=partition_bindings(all_bindings.values(),set(nonperson_scope()[0]))
    unbound=take_inventory_only(bindings,inventory_only)
    for path in unbound:bindings.pop(path)
    if {r['texture'] for r in aliases}!=set(bindings):raise ValueError('Alias sample does not cover exactly the built person textures')
    added={};pixel_proofs=[];carriers={}
    for path,binding in {**bindings,**unbound}.items():
        master=ROOT/'mod_nailong/assets/generated_fullsize'/f'{binding["fullsize_master_sha256"]}.png'
        if file_sha256(master)!=binding['fullsize_master_sha256']:raise ValueError('Master bytes changed')
        from mod_nailong.tools.texture_resolution import read_generated_texture
        with Image.open(master) as original,read_generated_texture(staging/binding['path']) as payload:
            original=original.convert('RGBA');payload=payload.convert('RGBA')
            resized=bool(binding.get('resized'))
            if resized:
                cap=manifest.get('validation_max_edge_probe')
                if not manifest.get('preview') or not manifest.get('validation_source_keys') or binding.get('resolution_policy')!='experimental-max-edge-probe' or cap!=binding.get('validation_max_edge_probe') or type(cap) is not int or cap<1:
                    raise ValueError('Unregistered historical HD resize')
                size=tuple(max(1,round(side*min(1,cap/max(original.size)))) for side in original.size)
                original=original.resize(size,Image.Resampling.LANCZOS)
            if original.size!=payload.size or original.tobytes()!=payload.tobytes():raise ValueError('DDS pixels differ from the declared fullsize master or explicit probe transform')
            pixel_proofs.append({'source_sha256':binding['source_sha256'],
                                 'master_sha256':binding['fullsize_master_sha256'],
                                 'rgba_pixel_sha256':sha256(payload.tobytes()),'rgba_equal':not resized,'declared_transform_equal':True,'resized':resized})
        if path not in bindings:continue
        width,height=binding['original_game_size']
        if not (1<=width<=4096 and 1<=height<=4096):raise ValueError('Unexpected layout carrier size')
        # This image carries logical dimensions only. The native alias retains
        # the distinct portrait path in its secondary texture binding.
        rel=f'gfx/interface/naiwa_white_layout_{width}_{height}.dds'
        carriers[path]=rel
        if rel not in added:
            stream=io.BytesIO();Image.new('RGBA',(width,height),(255,255,255,255)).save(stream,format='DDS');added[rel]=stream.getvalue()
    added['gfx/FX/naiwa_hd_masking_sampler.shader']=(ROOT/'mod_nailong/assets/runtime/hd_portrait_masking_sampler.shader').read_bytes()
    chunks=['spriteTypes = {']
    for alias in aliases:
        binding=bindings[alias['texture']];w,h=binding['original_game_size']
        chunks.append(f''' spriteType = {{
  name = "{alias['name']}"
  texturefile = "{carriers[alias['texture']]}"
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
        'formal_release_eligible':False,'hd_raster_resized':any(b.get('resized') for b in manifest['bindings']),
        'carrier_contains_no_portrait_pixels':True,'gui_or_gameplay_changes':False,
        'primary_layout_texture_identity':'shared-size-only-layout-v1',
        'aliases':aliases,'native_source_proofs':[p for p in source_proofs if p['id'] in used],
        'native_shader_include_proofs':native_include_proofs or [],
        'preserved_original_nonperson_paths':[{'path':path,'source_sha256':binding['source_sha256'],'sha256':binding['sha256']} for path,binding in sorted(preserved.items())],
        'inventory_without_current_consumer':[{'path':path,'source_sha256':binding['source_sha256'],'master_sha256':binding['fullsize_master_sha256'],'classification':'no_current_native_consumer_in_bounded_inventory'} for path,binding in sorted(unbound.items())],
        'fullsize_pixel_proofs':pixel_proofs,
        'live_acceptance':'Not run; every actual consumer, tooltip and hit area requires separate runtime evidence. Static parsing and unchanged bytes do not qualify display.'}
    write_json(output/'manifest.json',manifest)
    verify_layout_bindings(output,manifest)
    with zipfile.ZipFile(output/'gangnailongxin.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for row in manifest['files']:
            info=zipfile.ZipInfo(row['path'],date_time=(2020,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;info.create_system=3
            archive.writestr(info,(staging/row['path']).read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    verify(output)
    return manifest
