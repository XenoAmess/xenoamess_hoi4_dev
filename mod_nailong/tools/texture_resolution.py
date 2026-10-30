"""Native game-size derivatives from immutable, individually approved PNG masters."""
from pathlib import Path
import struct
from PIL import Image
from tools.common import ROOT, file_sha256, read_json, write_json, machine_id, utc_now
from mod_nailong.tools.art_contract import portrait_ready

POLICY_ID='native-source-size-v1'


def native_size(size):
    if not isinstance(size,(list,tuple)) or len(size)!=2 or any(type(n) is not int or n<1 for n in size):
        raise ValueError('Invalid original game texture dimensions')
    return tuple(size)


def game_image(master, size):
    image=master.convert('RGBA');size=native_size(size)
    return image if image.size==size else image.resize(size,Image.Resampling.LANCZOS)


def read_generated_texture(path):
    """Read the builder's exact BGRA DDS without Pillow's slow Python mask loop."""
    path=Path(path)
    if path.suffix.lower()!='.dds':
        with Image.open(path) as image:return image.convert('RGBA')
    raw=path.read_bytes()
    if len(raw)<128 or raw[:4]!=b'DDS ':raise ValueError('Invalid generated DDS header')
    words=struct.unpack('<31I',raw[4:128]);h,w=words[2:4]
    if words[0]!=124 or words[18:26]!=(32,65,0,32,0x00ff0000,0x0000ff00,0x000000ff,0xff000000) or words[4]!=4*w or words[6] not in (0,1) or words[26]!=4096 or any(words[27:31]) or len(raw)!=128+4*w*h:
        raise ValueError('Unsupported or corrupt generated DDS layout')
    native_size((w,h))
    return Image.frombytes('RGBA',(w,h),raw[128:],'raw','BGRA')


def write_pixel_proof(output, manifest, verification):
    if verification.get('source_identity_and_rgba_verified') is not True or verification.get('checked_portrait_bindings')!=len(manifest['bindings']):
        raise ValueError('A completed per-portrait pixel verification is required')
    output=Path(output)
    write_json(output/'native-texture-verification.json',{'schema':'naiwa-native-pixel-proof-v1','policy':POLICY_ID,
        'machine_id':machine_id(),'observed_at_utc':utc_now(),'manifest_sha256':file_sha256(output/'manifest.json'),
        'source':'Completed source/master/native-size RGBA verification; reusable only while all bound bytes and current approvals remain identical',
        'bindings':[{'path':r['path'],'source_sha256':r['source_sha256'],'master_sha256':r.get('fullsize_master_sha256'),'texture_sha256':r['sha256']} for r in manifest['bindings']],
        'verification':verification})


def verify_game_textures(output, manifest, catalog=None, generated=None, root=None, reuse_pixel_proof=False):
    """Fail before deployment if source, person, dimensions, pixels or policy drift."""
    from mod_nailong.tools.build_release import profile_assets, nonperson_scope, original_nonperson_bytes
    if manifest.get('texture_resolution_policy_id')!=POLICY_ID:
        raise ValueError('Obsolete game texture resolution policy; rebuild at original source dimensions')
    if manifest.get('development_fixture') or manifest.get('validation_max_edge_probe') is not None:
        raise ValueError('Retired HD masking/size experiment cannot be deployed as the native-size mod')
    root=Path(root or ROOT)
    catalog=catalog or read_json(root/'mod_nailong/data/catalog.json')
    generated=generated if generated is not None else read_json(root/'mod_nailong/data/generated.json')['portraits']
    packages=manifest.get('selected_profile')
    selected=profile_assets(catalog,packages if isinstance(packages,list) else None)
    output=Path(output);staging=output/'staging';checked=0;resized=0
    bindings=manifest['bindings']
    if reuse_pixel_proof:
        proof=read_json(output/'native-texture-verification.json')
        expected=[{'path':r['path'],'source_sha256':r['source_sha256'],'master_sha256':r.get('fullsize_master_sha256'),'texture_sha256':r['sha256']} for r in bindings]
        if proof.get('schema')!='naiwa-native-pixel-proof-v1' or proof.get('policy')!=POLICY_ID or proof.get('manifest_sha256')!=file_sha256(output/'manifest.json') or proof.get('bindings')!=expected or proof.get('verification',{}).get('source_identity_and_rgba_verified') is not True:
            raise ValueError('Stale or mismatched native pixel verification proof')
    by_path={r['path'].lower():r for r in bindings}
    if len(by_path)!=len(bindings):raise ValueError('Duplicate case-insensitive portrait output path')
    textures={r['path'].lower() for r in manifest['files'] if Path(r['path']).suffix.lower() in ('.dds','.tga','.png')}
    if textures!=set(by_path):raise ValueError('Unbound texture or retired HD layout carrier in staging')
    for binding in bindings:
        rel=binding['path'];asset=selected.get(rel.lower())
        if binding.get('sha256')!=file_sha256(staging/rel):raise ValueError('Game texture bytes changed after pixel verification: '+rel)
        if asset is None or asset['source_sha256']!=binding['source_sha256'] or asset['package']!=binding['package']:
            raise ValueError('Portrait source/package binding changed: '+rel)
        size=native_size(asset['size'])
        if binding['original_game_size']!=list(size) or binding['size']!=list(size):raise ValueError('Declared game dimensions do not match original source: '+rel)
        with Image.open(staging/rel) as image:
            if image.size!=size:raise ValueError('Actual game texture dimensions do not match original source: '+rel)
        digest=binding.get('fullsize_master_sha256')
        if digest is None:
            exceptions,_=nonperson_scope()
            if binding['source_sha256'] not in exceptions or not binding.get('preserved_original_nonperson_exception') or (staging/rel).read_bytes()!=original_nonperson_bytes(asset):
                raise ValueError('Unregistered original non-person texture')
            checked+=1;continue
        row=generated.get(binding['source_sha256'],{})
        if not portrait_ready(row) or row.get('generated_fullsize_sha256')!=digest:
            raise ValueError('Portrait no longer points to its own currently approved master: '+rel)
        master=root/row['generated_fullsize_image']
        if file_sha256(master)!=digest:raise ValueError('Original fullsize master checksum changed: '+rel)
        with Image.open(master) as source:
            original=list(source.size)
            if binding.get('fullsize_master_size')!=original or row.get('generated_fullsize_size')!=original:
                raise ValueError('Actual master dimensions differ from manifest: '+rel)
            if binding.get('resolution_policy')!=POLICY_ID or bool(binding.get('resized'))!=(original!=list(size)):
                raise ValueError('Undeclared or mismatched native-size derivation: '+rel)
            if not reuse_pixel_proof:
                with read_generated_texture(staging/rel) as encoded:
                    if game_image(source,size).tobytes()!=encoded.tobytes():raise ValueError('Game texture pixels do not match their own approved master: '+rel)
            resized+=original!=list(size)
        checked+=1
    return {'policy':POLICY_ID,'checked_portrait_bindings':checked,'native_size_derivatives':resized,
            'source_identity_and_rgba_verified':True,'pixel_proof_reused':reuse_pixel_proof,'runtime_acceptance_implied':False}
