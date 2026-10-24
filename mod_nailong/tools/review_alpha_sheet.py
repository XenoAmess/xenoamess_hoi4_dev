import sys
from pathlib import Path
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT,read_json,write_json,file_sha256,machine_id,utc_now
jobs=read_json(ROOT/sys.argv[1]);out=ROOT/sys.argv[2];assert not out.exists();out.mkdir(parents=True)
rows=read_json(ROOT/'mod_nailong/data/generated.json')['portraits']
accepted_states=('pending','rejected') if '--include-rejected' in sys.argv else ('pending',)
selected=[j for j in jobs if j['key'] in rows and rows[j['key']].get('review') in accepted_states and rows[j['key']].get('prompt')==j['prompt']]
pages=[]
for start in range(0,len(selected),4):
 sheet=Image.new('RGB',(1280,450*min(4,len(selected)-start)),'#ddd9d1');draw=ImageDraw.Draw(sheet);entries=[]
 for n,j in enumerate(selected[start:start+4]):
  row=rows[j['key']];master=ROOT/row['generated_fullsize_image']
  with Image.open(j['original']) as opened:original=opened.convert('RGBA')
  with Image.open(master) as opened:hd=opened.convert('RGBA')
  assert file_sha256(master)==row['generated_fullsize_sha256']
  a=next(a for a in read_json(ROOT/row['request_journal'])['attempts'] if a.get('fullsize_sha256')==row['generated_fullsize_sha256'])
  for col,label in enumerate(['SOURCE','RETURN white matte','RETURN cyan matte','RETURN alpha (white=opaque)']):
   x,y=320*col,450*n;draw.text((x+4,y+4),str(start+n+1)+' '+label,fill='black')
   im=original if col==0 else hd;scale=min(308/im.width,412/im.height);size=(max(1,round(im.width*scale)),max(1,round(im.height*scale)))
   if col==3:tile=hd.getchannel('A').resize(size,Image.Resampling.NEAREST).convert('RGB')
   else:
    resized=im.resize(size,Image.Resampling.NEAREST if col==0 else Image.Resampling.LANCZOS)
    tile=Image.new('RGB',size,('#e3dfd7' if col==0 else '#ffffff' if col==1 else '#00dcdc'));tile.paste(resized,(0,0),resized.getchannel('A'))
   sheet.paste(tile,(x+4,y+20))
  draw.text((5,450*n+435),str(start+n+1)+' '+Path(j['source']).stem[-57:],fill='black')
  entries.append({'index':start+n+1,'source_sha256':j['key'],'image_sha256':row['image_sha256'],'generated_fullsize_sha256':row['generated_fullsize_sha256'],'generated_fullsize_image':row['generated_fullsize_image'],'attempt_number':a['number'],'source':j['source'],'original_png_sha256':file_sha256(Path(j['original'])),'original_alpha_extrema':original.getchannel('A').getextrema(),'returned_alpha_extrema':hd.getchannel('A').getextrema(),'display_source':'Unchanged raw master with display-only white/cyan matte and nearest alpha; never game payload.'})
 path=out/f'page-{start//4+1:02}.png';sheet.save(path);pages.append({'path':str(path),'sha256':file_sha256(path),'size':list(sheet.size),'entries':entries});print(path)
write_json(out/'manifest.json',{'schema':'naiwa-visual-review-v2','machine_id':machine_id(),'observed_at_utc':utc_now(),'purpose':'Actually inspect opaque interior, source colors and boundaries; no production images changed.','pages':pages})
print('Selected current outputs in',accepted_states,':',len(selected))

