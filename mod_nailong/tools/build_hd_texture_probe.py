"""Build one explicit development-only HD sprite sizing experiment."""
import sys,argparse,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT,read_json,write_json,file_sha256,sha256,machine_id,utc_now,game_root
from mod_nailong.tools.build_release import build,verify
KEY='0198603566189470fb173b47c179055d93461815d71e3ec1421c14df457ddd0f'
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--mode',choices=['sprite-size','cornered-tile','cornered-buttons','cornered-icon-size','cornered-unknown-initializer','masked-hd-sampler','masked-hd-sampler-g','uv-window-shader','uv-clipped-containers','progress-hd-native','animation-hd-sampler','masking-hd-sampler'],default='sprite-size');args=parser.parse_args()
 manifest=build(args.output,preview=True,validation_keys={KEY})
 text='spriteTypes = {\n spriteType = {\n  name = GFX_portrait_USA_franklin_delano_roosevelt\n  texturefile = "gfx/leaders/USA/Portrait_USA_Franklin_Roosevelt.dds"\n  size = { x = 156 y = 210 }\n }\n}\n'
 if args.mode.startswith('cornered-'):text='spriteTypes = {\n corneredTileSpriteType = {\n  name = GFX_portrait_USA_franklin_delano_roosevelt\n  texturefile = "gfx/leaders/USA/Portrait_USA_Franklin_Roosevelt.dds"\n  size = { x = 156 y = 210 }\n  borderSize = { x = 0 y = 0 }\n  tilingCenter = no\n }\n}\n'
 if args.mode=='progress-hd-native':text='spriteTypes = {\n progressbartype = {\n name = "GFX_portrait_USA_franklin_delano_roosevelt"\n color = { 1.0 1.0 1.0 }\n colortwo = { 1.0 1.0 1.0 }\n textureFile1 = "gfx/leaders/USA/Portrait_USA_Franklin_Roosevelt.dds"\n textureFile2 = "gfx/leaders/USA/Portrait_USA_Franklin_Roosevelt.dds"\n size = { x = 156 y = 210 }\n effectFile = "gfx/FX/progress.lua"\n horizontal = yes\n steps = 1000000\n }\n}\n'
 relative='interface/zz_naiwa_hd_sprite_size_probe.gfx';path=args.output/'staging'/relative;path.parent.mkdir(parents=True);path.write_text(text,encoding='utf-8',newline='\n')
 manifest['files'].append({'path':relative,'bytes':path.stat().st_size,'sha256':file_sha256(path)});manifest['files'].sort(key=lambda r:r['path'])
 if args.mode.startswith('masked-hd-sampler'):
  from PIL import Image
  carrier_relative='gfx/interface/naiwa_hd_size_carrier_156_210.dds';carrier=args.output/'staging'/carrier_relative;carrier.parent.mkdir(parents=True,exist_ok=True)
  Image.new('RGBA',(156,210),(0,0,0,0)).save(carrier,format='DDS')
  shader_name='hd_portrait_sampler_g' if args.mode.endswith('-g') else 'hd_portrait_sampler'
  effect_relative='gfx/FX/naiwa_'+shader_name+'.shader';effect=args.output/'staging'/effect_relative;effect.parent.mkdir(parents=True,exist_ok=True)
  shader=(ROOT/f'mod_nailong/assets/runtime/{shader_name}.shader').read_bytes();effect.write_bytes(shader)
  effect_reference=effect_relative.removesuffix('.shader')+'.lua' if args.mode.endswith('-g') else effect_relative
  text='spriteTypes = {\n maskedShieldType = {\n  name = GFX_portrait_USA_franklin_delano_roosevelt\n  textureFile1 = "'+carrier_relative+'"\n  textureFile2 = "gfx/leaders/USA/Portrait_USA_Franklin_Roosevelt.dds"\n  effectFile = "'+effect_reference+'"\n }\n}\n'
  path.write_text(text,encoding='utf-8',newline='\n')
  for item in manifest['files']:
   if item['path']==relative:item.update(bytes=path.stat().st_size,sha256=file_sha256(path))
  for rel,p in [(carrier_relative,carrier),(effect_relative,effect)]:manifest['files'].append({'path':rel,'bytes':p.stat().st_size,'sha256':file_sha256(p)})
 source_binding=None
 if args.mode=='masking-hd-sampler':
  from PIL import Image
  binding=manifest['bindings'][0];width,height=binding['original_game_size'];portrait_relative=binding['path']
  assert portrait_relative=='gfx/leaders/USA/Portrait_USA_Franklin_Roosevelt.dds'
  carrier_relative=f'gfx/interface/naiwa_white_layout_{width}_{height}.dds';carrier=args.output/'staging'/carrier_relative;carrier.parent.mkdir(parents=True,exist_ok=True)
  Image.new('RGBA',(width,height),(255,255,255,255)).save(carrier,format='DDS')
  effect_relative='gfx/FX/naiwa_hd_masking_sampler.shader';effect=args.output/'staging'/effect_relative;effect.parent.mkdir(parents=True,exist_ok=True)
  effect.write_bytes((ROOT/'mod_nailong/assets/runtime/hd_portrait_masking_sampler.shader').read_bytes())
  master=ROOT/'mod_nailong/assets/generated_fullsize'/f'{binding["fullsize_master_sha256"]}.png';assert file_sha256(master)==binding['fullsize_master_sha256']
  with Image.open(master) as original,Image.open(args.output/'staging'/portrait_relative) as payload:
   assert original.size==payload.size==tuple(binding['size'])
   assert original.convert('RGBA').tobytes()==payload.convert('RGBA').tobytes(),'HD payload pixels changed'
   decoded_pixel_sha256=sha256(payload.convert('RGBA').tobytes())
  text=('spriteTypes = {\n spriteType = {\n name = GFX_portrait_USA_franklin_delano_roosevelt\n texturefile = "'+carrier_relative+'"\n masking_texture = "'+portrait_relative+'"\n effectFile = "gfx/FX/naiwa_hd_masking_sampler.lua"\n noOfFrames = 1\n legacy_lazy_load = no\n }\n}\n')
  path.write_text(text,encoding='utf-8',newline='\n')
  for item in manifest['files']:
   if item['path']==relative:item.update(bytes=path.stat().st_size,sha256=file_sha256(path))
  for rel,p in [(carrier_relative,carrier),(effect_relative,effect)]:manifest['files'].append({'path':rel,'bytes':p.stat().st_size,'sha256':file_sha256(p)})
  source_binding={'changes':'Normal native-size opaque-white empty carrier with masking_texture binding untouched HD portrait. Custom shader samples actual stock masking slot 5 as full RGBA. No portrait downsample, GUI change or animation. All runtime behavior remains unqualified.',
   'payload_rgba_pixels_equal_master':True,'payload_rgba_pixel_sha256':decoded_pixel_sha256,'carrier_contains_no_portrait_pixels':True,
   'native_source_evidence':[{'path':str(game_root()/rel),'sha256':file_sha256(game_root()/rel)} for rel in ['gfx/FX/buttonstate.fxh','gfx/FX/buttonstate.shader','interface/mapicons.gfx']]}
 if args.mode=='animation-hd-sampler':
  from PIL import Image
  binding=manifest['bindings'][0];width,height=binding['original_game_size']
  carrier_relative=f'gfx/interface/naiwa_empty_layout_{width}_{height}.dds';carrier=args.output/'staging'/carrier_relative;carrier.parent.mkdir(parents=True,exist_ok=True)
  Image.new('RGBA',(width,height),(0,0,0,0)).save(carrier,format='DDS')
  effect_relative='gfx/FX/naiwa_hd_animation_sampler.shader';effect=args.output/'staging'/effect_relative;effect.parent.mkdir(parents=True,exist_ok=True)
  effect.write_bytes((ROOT/'mod_nailong/assets/runtime/hd_portrait_animation_sampler.shader').read_bytes())
  portrait_relative=binding['path'] if 'path' in binding else 'gfx/leaders/USA/Portrait_USA_Franklin_Roosevelt.dds'
  assert portrait_relative=='gfx/leaders/USA/Portrait_USA_Franklin_Roosevelt.dds'
  master=ROOT/'mod_nailong/assets/generated_fullsize'/f'{binding["fullsize_master_sha256"]}.png'
  assert file_sha256(master)==binding['fullsize_master_sha256']
  with Image.open(master) as original,Image.open(args.output/'staging'/portrait_relative) as payload:
   assert original.size==payload.size==tuple(binding['size'])
   assert original.convert('RGBA').tobytes()==payload.convert('RGBA').tobytes(),'HD payload pixels changed'
   decoded_pixel_sha256=sha256(payload.convert('RGBA').tobytes())
  with Image.open(carrier) as empty:assert empty.size==(width,height) and empty.getchannel('A').getextrema()==(0,0)
  text=('spriteTypes = {\n spriteType = {\n name = GFX_portrait_USA_franklin_delano_roosevelt\n texturefile = "'+carrier_relative+'"\n effectFile = "gfx/FX/naiwa_hd_animation_sampler.lua"\n noOfFrames = 1\n animation = {\n animationmaskfile = "'+carrier_relative+'"\n animationtexturefile = "'+portrait_relative+'"\n animationrotation = 0\n animationlooping = yes\n animationtime = 26\n animationdelay = 0\n animationblendmode = "normal"\n animationtype = "scrolling"\n animationrotationoffset = { x = 0 y = 0 }\n animationtexturescale = { x = 1 y = 1 }\n }\n legacy_lazy_load = no\n }\n}\n')
  path.write_text(text,encoding='utf-8',newline='\n')
  for item in manifest['files']:
   if item['path']==relative:item.update(bytes=path.stat().st_size,sha256=file_sha256(path))
  for rel,p in [(carrier_relative,carrier),(effect_relative,effect)]:manifest['files'].append({'path':rel,'bytes':p.stat().st_size,'sha256':file_sha256(p)})
  source_binding={'changes':'Normal sprite keeps native-size empty layout carrier. Stock animation texture slot 2 binds untouched HD portrait; custom shader uses static unmodified 0..1 UV rather than animation time/offset. No GUI/gameplay or portrait raster change. Dynamic binding, scaling, alpha hit testing, tooltip and selection are unqualified.',
   'payload_rgba_pixels_equal_master':True,'payload_rgba_pixel_sha256':decoded_pixel_sha256,'empty_carrier_is_not_a_downsampled_portrait':True,
   'native_source_evidence':[{'path':str(game_root()/rel),'sha256':file_sha256(game_root()/rel)} for rel in ['gfx/FX/buttonstate.fxh','gfx/FX/buttonstate.shader','interface/frontendmainview.gfx','interface/goals_shine.gfx']]}
 if args.mode=='cornered-unknown-initializer':
  import re
  from PIL import Image
  original=game_root()/'interface/countrypoliticsview.gfx'
  original_text=original.read_text(encoding='utf-8-sig')
  match=re.search(r'name\s*=\s*"GFX_leader_unknown"\s+textureFile\s*=\s*"([^"]+)"',original_text)
  assert match,'Native unknown portrait sprite binding changed'
  unknown_relative=match.group(1)
  with Image.open(game_root()/unknown_relative) as unknown:assert unknown.size==(156,210)
  text=text.rstrip().removesuffix('}')+'\n corneredTileSpriteType = {\n name = "GFX_leader_unknown"\n texturefile = "'+unknown_relative+'"\n size = { x = 156 y = 210 }\n borderSize = { x = 0 y = 0 }\n tilingCenter = no\n }\n}\n'
  path.write_text(text,encoding='utf-8',newline='\n')
  for item in manifest['files']:
   if item['path']==relative:item.update(bytes=path.stat().st_size,sha256=file_sha256(path))
  source_binding={'path':str(original),'sha256':file_sha256(original),'changes':'Only sprite definitions for Roosevelt and the stock unknown initializer use the same cornered-tile class and native logical size. Stock GUI and all raster bytes unchanged. Hypothesis: initialization with the same sprite class may preserve icon scale on dynamic replacement; unqualified until actual frontend inspection.','unknown_texture':{'path':unknown_relative,'sha256':file_sha256(game_root()/unknown_relative),'size':[156,210]}}
 if args.mode in ('uv-window-shader','uv-clipped-containers'):
  binding=manifest['bindings'][0];nw,nh=binding['original_game_size'];hw,hh=binding['size']
  shader=(ROOT/'mod_nailong/assets/runtime/hd_portrait_uv_window.shader').read_text(encoding='utf-8').replace('__WINDOW_X__',format(nw/hw,'.12g')).replace('__WINDOW_Y__',format(nh/hh,'.12g'))
  relative_effect=f'gfx/FX/naiwa_hd_window_{nw}_{nh}_{hw}_{hh}.shader';effect=args.output/'staging'/relative_effect;effect.parent.mkdir(parents=True,exist_ok=True);effect.write_text(shader,encoding='utf-8',newline='\n')
  manifest['files'].append({'path':relative_effect,'bytes':effect.stat().st_size,'sha256':file_sha256(effect)})
  text='spriteTypes = {\n spriteType = {\n  name = GFX_portrait_USA_franklin_delano_roosevelt\n  texturefile = "gfx/leaders/USA/Portrait_USA_Franklin_Roosevelt.dds"\n  effectFile = "'+relative_effect.removesuffix('.shader')+'.lua"\n }\n}\n'
  path.write_text(text,encoding='utf-8',newline='\n')
  for item in manifest['files']:
   if item['path']==relative:item.update(bytes=path.stat().st_size,sha256=file_sha256(path))
 if args.mode in ('cornered-buttons','cornered-icon-size'):
  import re
  original=game_root()/'interface/frontendgamesetupview.gui'
  gui=original.read_text(encoding='utf-8-sig')
  for name,scale in [('minor_country_leader','0.696'),('country_leader','0.4')]:
   pattern=rf'iconType(\s*=\s*\{{\s*name\s*=\s*"{name}"\s*quadTextureSprite\s*=\s*"GFX_leader_unknown"\s*position\s*=\s*\{{[^}}]*\}}\s*scale\s*=\s*{re.escape(scale)}\b)'
   if args.mode=='cornered-buttons':replacement=r'buttonType\1'
   else:
    width,height=(108,146) if name=='minor_country_leader' else (62,84)
    replacement=rf'iconType\1\n            size = {{ width = {width} height = {height} }}'
   gui,n=re.subn(pattern,replacement,gui);assert n==1,(name,n)
  gui_relative='interface/frontendgamesetupview.gui'
  gui_path=args.output/'staging'/gui_relative;gui_path.write_text(gui,encoding='utf-8',newline='\n')
  manifest['files'].append({'path':gui_relative,'bytes':gui_path.stat().st_size,'sha256':file_sha256(gui_path)})
  source_binding={'path':str(original),'sha256':file_sha256(original),'changes':('Only minor_country_leader scale 0.696 and lobby country_leader scale 0.4 controls changed from iconType to buttonType' if args.mode=='cornered-buttons' else 'Only explicit iconType size constraints 108x146 and 62x84 added to minor_country_leader and lobby country_leader')+'; stock scales and positions preserved. Development output only, stock GUI not committed.'}
 if args.mode=='uv-clipped-containers':
  import re
  from PIL import Image
  original=game_root()/'interface/frontendgamesetupview.gui';gui=original.read_text(encoding='utf-8-sig')
  for kind,name,scale,w,h in [('iconType','minor_country_leader','0.696',109,147),('iconType','country_leader','0.4',63,84),('buttonType','country_leader','0.75',117,158)]:
   pattern=rf'{kind}\s*=\s*\{{\s*name\s*=\s*"{name}"\s*quadTextureSprite\s*=\s*"GFX_leader_unknown"\s*position\s*=\s*(\{{[^}}]*\}})\s*scale\s*=\s*{re.escape(scale)}\b(?P<tail>[^{{}}]*)\}}'
   def wrap(match):
    tail=re.sub(r'rotation\s*=\s*-?[0-9.]+','',match.group('tail'))
    return ('containerWindowType = {\n name = "naiwa_hd_clip_'+name+'_'+scale.replace('.','_')+'"\n position = '+match.group(1)+f'\n size = {{ width = {w} height = {h} }}\n clipping = yes\n background = {{ name = "naiwa_clear_clip_bg" quadTextureSprite = "GFX_naiwa_hd_clip_clear" }}\n'+kind+' = {\n name = "'+name+'"\n quadTextureSprite = "GFX_leader_unknown"\n position = { x = 0 y = 0 }\n scale = '+scale+'\n'+tail+'\n}\n}')
   gui,n=re.subn(pattern,wrap,gui);assert n==1,(kind,name,scale,n)
  gui_relative='interface/frontendgamesetupview.gui';gui_path=args.output/'staging'/gui_relative;gui_path.write_text(gui,encoding='utf-8',newline='\n')
  manifest['files'].append({'path':gui_relative,'bytes':gui_path.stat().st_size,'sha256':file_sha256(gui_path)})
  carrier_relative='gfx/interface/naiwa_hd_clip_clear.dds';carrier=args.output/'staging'/carrier_relative;carrier.parent.mkdir(parents=True,exist_ok=True);Image.new('RGBA',(1,1),(0,0,0,0)).save(carrier,format='DDS')
  manifest['files'].append({'path':carrier_relative,'bytes':carrier.stat().st_size,'sha256':file_sha256(carrier)})
  text=text.rstrip().removesuffix('}')+'\n corneredTileSpriteType = {\n name = "GFX_naiwa_hd_clip_clear"\n texturefile = "'+carrier_relative+'"\n size = { x = 1 y = 1 }\n borderSize = { x = 0 y = 0 }\n tilingCenter = no\n }\n}\n';path.write_text(text,encoding='utf-8',newline='\n')
  for item in manifest['files']:
   if item['path']==relative:item.update(bytes=path.stat().st_size,sha256=file_sha256(path))
  source_binding={'path':str(original),'sha256':file_sha256(original),'changes':'Three frontend portrait consumers wrapped in bounded clipping containers; original child type/name/scale retained, local origin reset, minor rotation removed because oversized quad changes its pivot. Dynamic binding, tooltip and hit testing remain unqualified. Native GUI remains only in ignored staging.'}
 manifest['files'].sort(key=lambda r:r['path'])
 manifest['development_fixture']={'kind':'Unqualified '+args.mode+' logical size property experiment','source_sha256':KEY,'property':'native-size transparent layout carrier and original-HD shader sampler' if args.mode.startswith('masked-') else 'size = { x = 156 y = 210 }','hd_raster_unchanged':True,'formal_release_eligible':False,'expected_outcome':'Observe in real game; this build does not claim the property/type works for portraits','native_gui_source':source_binding}
 if args.mode in ('uv-window-shader','uv-clipped-containers'):manifest['development_fixture'].update(property='Full original texture sampled into a native-size UV window; engine quad dimensions unchanged',uv_window=[nw/hw,nh/hh],hit_testing_and_layout='unqualified; actual clicks and all portrait consumer classes must be checked')
 if args.mode=='progress-hd-native':manifest['development_fixture'].update(property='Native progressbartype explicit logical size and unchanged HD texture in both samplers; stock GUI and shader unchanged',native_source_evidence=[{'path':str(game_root()/rel),'sha256':file_sha256(game_root()/rel)} for rel in ['interface/load_screen.gfx','gfx/FX/progress.shader']],consumer_binding_and_scale='unqualified until actual game inspection; native loading bar support does not prove portrait compatibility')
 if args.mode=='animation-hd-sampler':manifest['development_fixture'].update(property='Native-size empty normal sprite with unchanged fullsize portrait in animation sampler 2; static original UV, no animation or GUI size override')
 if args.mode=='masking-hd-sampler':manifest['development_fixture'].update(property='Native-size empty normal sprite with unchanged fullsize portrait through masking_texture slot 5; no GUI size override')
 write_json(args.output/'manifest.json',manifest)
 with zipfile.ZipFile(args.output/'naiwa-world.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
  for row in manifest['files']:
   info=zipfile.ZipInfo(row['path'],date_time=(2020,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;info.create_system=3
   archive.writestr(info,(args.output/'staging'/row['path']).read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
 verify(args.output)
 write_json(args.output/'build-receipt.json',{'machine_id':machine_id(),'observed_at_utc':utc_now(),'source':'build_hd_texture_probe.py + verified manifest','live_acceptance':'not-run','preview':True,'gameplay_changes':False,'hd_raster_resized':False})
 print('Built one unqualified HD sprite size probe; no image generation or raster resampling')
if __name__=='__main__':main()
