"""Build one explicit development-only HD sprite sizing experiment."""
import sys,argparse,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT,read_json,write_json,file_sha256,sha256,machine_id,utc_now
from mod_nailong.tools.build_release import build,verify
KEY='0198603566189470fb173b47c179055d93461815d71e3ec1421c14df457ddd0f'
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 manifest=build(args.output,preview=True,validation_keys={KEY})
 text='spriteTypes = {\n spriteType = {\n  name = GFX_portrait_USA_franklin_delano_roosevelt\n  texturefile = "gfx/leaders/USA/Portrait_USA_Franklin_Roosevelt.dds"\n  size = { x = 156 y = 210 }\n }\n}\n'
 relative='interface/zz_naiwa_hd_sprite_size_probe.gfx';path=args.output/'staging'/relative;path.parent.mkdir(parents=True);path.write_text(text,encoding='utf-8',newline='\n')
 manifest['files'].append({'path':relative,'bytes':path.stat().st_size,'sha256':file_sha256(path)});manifest['files'].sort(key=lambda r:r['path'])
 manifest['development_fixture']={'kind':'Unqualified spriteType logical size property experiment','source_sha256':KEY,'property':'size = { x = 156 y = 210 }','hd_raster_unchanged':True,'formal_release_eligible':False,'expected_outcome':'Observe in real game; this build does not claim the property is supported'}
 write_json(args.output/'manifest.json',manifest)
 with zipfile.ZipFile(args.output/'naiwa-world.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
  for row in manifest['files']:
   info=zipfile.ZipInfo(row['path'],date_time=(2020,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;info.create_system=3
   archive.writestr(info,(args.output/'staging'/row['path']).read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
 verify(args.output)
 write_json(args.output/'build-receipt.json',{'machine_id':machine_id(),'observed_at_utc':utc_now(),'source':'build_hd_texture_probe.py + verified manifest','live_acceptance':'not-run','preview':True,'gameplay_changes':False,'hd_raster_resized':False})
 print('Built one unqualified HD sprite size probe; no image generation or raster resampling')
if __name__=='__main__':main()
