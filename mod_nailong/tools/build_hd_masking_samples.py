"""Build a small development-only original-HD masking sample, using real aliases."""
from pathlib import Path
import argparse,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT,read_json,game_root,file_sha256,sha256,machine_id,utc_now,write_json
from mod_nailong.tools.catalog import sources,read_source
from mod_nailong.tools.hd_masking import sprite_records,unique_aliases,augment
from mod_nailong.tools.build_release import build

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-key',action='append',required=True)
    args=parser.parse_args();keys=set(args.source_key)
    if not 1<=len(keys)<=12:parser.error('Choose 1 to 12 explicit development sources')
    catalog=read_json(ROOT/'mod_nailong/data/catalog.json');install=game_root()
    assert catalog['machine_id']==machine_id() and file_sha256(install/'hoi4.exe')==catalog['exe_sha256']
    paths={a['path'].lower() for a in catalog['assets'] if a['source_sha256'] in keys}
    if not paths:parser.error('No source keys found in current catalog')
    records=[];proofs=[];started=time.monotonic();count=0
    for row in sources(install):
        count+=1
        assert count<100000 and time.monotonic()-started<120,'Bounded native binding inventory incomplete'
        if not row[1].lower().endswith('.gfx'):continue
        raw=read_source(row);source_id=len(proofs)
        proofs.append({'id':source_id,'package':row[0],'path':row[1],'sha256':sha256(raw),'archive_member':row[3]})
        records.extend(dict(r,source_id=source_id) for r in sprite_records(raw.decode('utf-8-sig',errors='replace')))
    aliases=unique_aliases(records,paths)
    manifest=build(args.output,preview=True,validation_keys=keys)
    includes=[{'path':rel,'sha256':file_sha256(install/rel)} for rel in ['gfx/FX/buttonstate.fxh','gfx/FX/buttonstate.shader']]
    manifest=augment(args.output,manifest,aliases,proofs,includes)
    write_json(args.output/'build-receipt.json',{'machine_id':machine_id(),'observed_at_utc':utc_now(),
        'source':'Actual local native alias binding hashes, master/DDS full RGBA equality and exact manifest/ZIP verification',
        'source_keys':sorted(keys),'aliases':len(aliases),'hd_raster_resized':False,'preview':True,'live_acceptance':'not-run',
        'exe_sha256':catalog['exe_sha256'],'manifest_sha256':file_sha256(args.output/'manifest.json')})
    print('Built '+str(len(keys))+' unchanged-HD development sources and '+str(len(aliases))+' exact native alias adapters; actual display remains unqualified.')

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
