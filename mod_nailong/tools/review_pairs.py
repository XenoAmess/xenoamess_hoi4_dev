"""Create local-only original/generated contact sheets for visual art review."""
import argparse
from pathlib import Path
import sys
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT,read_json,write_json,machine_id,utc_now,file_sha256

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jobs-file',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True,help='Directory inside runtime; original game imagery never enters Git')
    args=p.parse_args();output=args.output.resolve()
    if not output.is_relative_to((ROOT/'runtime').resolve()):raise SystemExit('Review sheets must remain under ignored runtime')
    output.mkdir(parents=True,exist_ok=True)
    rows=read_json(ROOT/'mod_nailong/data/generated.json')['portraits']
    jobs=[j for j in read_json(args.jobs_file) if j['key'] in rows]
    pages=[]
    for start in range(0,len(jobs),9):
        page=Image.new('RGB',(3*340,3*250),'#dedbd3');draw=ImageDraw.Draw(page)
        entries=[]
        for n,job in enumerate(jobs[start:start+9]):
            x=(n%3)*340;y=(n//3)*250;row=rows[job['key']]
            for dx,path in [(0,Path(job.get('original',job.get('path')))),(170,ROOT/row['image'])]:
                with Image.open(path) as im:
                    im=im.convert('RGBA');ratio=min(156/im.width,210/im.height)
                    im=im.resize((round(im.width*ratio),round(im.height*ratio)),Image.Resampling.NEAREST if ratio>1 else Image.Resampling.LANCZOS)
                    page.paste(im,(x+dx,y+20),im.getchannel('A'))
            draw.text((x+2,y+2),str(start+n+1)+' ORIGINAL | GENERATED',fill='black')
            draw.text((x+2,y+233),Path(job['source']).stem[-43:],fill='black')
            entries.append({'index':start+n+1,'source_sha256':job['key'],'image_sha256':row['image_sha256']})
        path=output/f'page-{start//9+1:02}.png';page.save(path)
        pages.append({'path':str(path),'sha256':file_sha256(path),'entries':entries});print(path)
    write_json(output/'manifest.json',{'machine_id':machine_id(),'observed_at_utc':utc_now(),'purpose':'Local contact sheets for actual manual review, not automatic approval','pages':pages})

if __name__=='__main__':main()
