"""Create local-only original/generated contact sheets for visual art review."""
import argparse
from pathlib import Path
import sys
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT,read_json,write_json,machine_id,utc_now,file_sha256

def generated_master(row,root=ROOT):
    relative=row.get('generated_fullsize_image');expected=row.get('generated_fullsize_sha256')
    if not relative or not expected or not (root/relative).is_file():
        raise ValueError('Declared fullsize master is unavailable; recover it before review')
    path=root/relative
    if file_sha256(path)!=expected:raise ValueError('Fullsize master changed; no native-preview fallback')
    return path

def review_thumbnail(image,source=False):
    image=image.convert('RGBA');ratio=min(156/image.width,210/image.height)
    return image.resize((max(1,round(image.width*ratio)),max(1,round(image.height*ratio))),Image.Resampling.NEAREST if source else Image.Resampling.LANCZOS)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jobs-file',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True,help='Directory inside runtime; original game imagery never enters Git')
    args=p.parse_args();output=args.output.resolve()
    if not output.is_relative_to((ROOT/'runtime').resolve()):raise SystemExit('Review sheets must remain under ignored runtime')
    output.mkdir(parents=True,exist_ok=True)
    if (output/'manifest.json').exists():raise SystemExit('Use a fresh review directory; existing evidence is immutable')
    rows=read_json(ROOT/'mod_nailong/data/generated.json')['portraits']
    jobs=[j for j in read_json(args.jobs_file) if j['key'] in rows and ('prompt' not in j or rows[j['key']]['prompt']==j['prompt'])]
    pages=[]
    for start in range(0,len(jobs),9):
        page=Image.new('RGB',(3*340,3*250),'#dedbd3');draw=ImageDraw.Draw(page)
        entries=[]
        for n,job in enumerate(jobs[start:start+9]):
            x=(n%3)*340;y=(n//3)*250;row=rows[job['key']]
            master=generated_master(row)
            request=read_json(ROOT/row.get('request_journal',f'mod_nailong/data/generation-requests/{job["key"]}.json'))['attempts'][-1]
            if request.get('output_sha256')!=row['image_sha256'] or request.get('fullsize_sha256')!=row['generated_fullsize_sha256']:
                raise ValueError('Import/request binding is not complete; create a new review snapshot after import')
            displayed_size=None
            for dx,path in [(0,Path(job.get('original',job.get('path')))),(170,master)]:
                with Image.open(path) as im:
                    im=review_thumbnail(im,source=dx==0)
                    page.paste(im,(x+dx,y+20),im.getchannel('A'))
                    if dx:displayed_size=list(im.size)
            draw.text((x+2,y+2),str(start+n+1)+' SOURCE | FULLSIZE (review fit)',fill='black')
            draw.text((x+2,y+233),Path(job['source']).stem[-43:],fill='black')
            entries.append({'index':start+n+1,'source_sha256':job['key'],'image_sha256':row['image_sha256'],'generated_fullsize_sha256':row['generated_fullsize_sha256'],'generated_fullsize_image':row['generated_fullsize_image'],'attempt_number':request['number'],'generated_display_size':displayed_size,'display_source':'unchanged raw imagegen master, fitted with aspect preserved; not native-size derivative or game payload'})
        path=output/f'page-{start//9+1:02}.png'
        if path.exists():raise SystemExit('Review page already exists; choose a fresh evidence directory')
        page.save(path)
        pages.append({'path':str(path),'sha256':file_sha256(path),'entries':entries});print(path)
    write_json(output/'manifest.json',{'schema':'naiwa-visual-review-v2','machine_id':machine_id(),'observed_at_utc':utc_now(),'purpose':'Local manual review from unchanged fullsize masters with aspect preserved. Display thumbnails only; game texture policy and live acceptance are separate.','pages':pages})

if __name__=='__main__':main()
