"""Click only after fresh pixels exactly match an already inspected UI patch."""
import sys,argparse,hashlib,time
from pathlib import Path
from types import SimpleNamespace
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import read_json,write_json,file_sha256,machine_id,utc_now
from tools.desktop import focus,observe,click

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--reference',type=Path,required=True);parser.add_argument('--hwnd',type=int,required=True)
 parser.add_argument('--patch',nargs=4,type=int,required=True,metavar=('LEFT','TOP','WIDTH','HEIGHT'))
 parser.add_argument('--x',type=int,required=True);parser.add_argument('--y',type=int,required=True)
 parser.add_argument('--output',type=Path,required=True);parser.add_argument('--receipt',type=Path,required=True)
 parser.add_argument('--freshness-hover',nargs=2,type=int,help='An explicitly inspected point outside the click patch; require changed pixels after a guarded real mouse move')
 args=parser.parse_args();reference=read_json(args.reference.with_suffix('.json'))
 assert file_sha256(args.reference)==reference['sha256'],'Reference screenshot changed'
 assert not args.output.exists(),'Fresh evidence must not replace previous screenshot'
 focus(args.hwnd);fresh=observe(args.output,ocr=False)
 assert fresh['foreground_hwnd']==args.hwnd and fresh['foreground_title']==reference['foreground_title']
 assert fresh['window_rect']==reference['window_rect'] and fresh['image_size']==reference['image_size']==fresh['desktop_size']
 left,top,width,height=args.patch;assert width>0 and height>0
 assert left<=args.x<left+width and top<=args.y<top+height
 assert 0<=left<left+width<=fresh['image_size'][0] and 0<=top<top+height<=fresh['image_size'][1]
 box=(left,top,left+width,top+height)
 with Image.open(args.reference) as old,Image.open(args.output) as current:
  before=old.convert('RGBA').crop(box).tobytes();after=current.convert('RGBA').crop(box).tobytes()
  assert before==after,'UI pixels differ from inspected reference; inspect fresh screenshot; no click sent'
 source=args.output
 if args.freshness_hover:
  hx,hy=args.freshness_hover;assert not (left<=hx<left+width and top<=hy<top+height)
  click(SimpleNamespace(hwnd=args.hwnd,screenshot=str(source),max_age=120,content_rect=[0,0,*fresh['image_size']],x=hx,y=hy,receipt=str(args.output.with_suffix('.hover-input.json')),move_only=True))
  time.sleep(.3);hover=args.output.with_name(args.output.stem+'-hover.png');assert not hover.exists()
  changed=observe(hover,ocr=False)
  assert changed['sha256']!=fresh['sha256'],'No actual changed desktop pixels after cursor move; stop input'
  assert changed['foreground_hwnd']==args.hwnd and changed['image_size']==fresh['image_size'] and changed['window_rect']==fresh['window_rect']
  with Image.open(hover) as current:assert current.convert('RGBA').crop(box).tobytes()==before,'Target UI changed while proving freshness; stop input'
  source=hover;fresh=changed
 else:assert fresh['sha256']!=reference['sha256'],'Whole desktop pixels unchanged; obtain independent fresh-frame evidence before input'
 proof={'machine_id':machine_id(),'observed_at_utc':utc_now(),'mechanism':'Exact visual template comparison of raw screenshots, then guarded real mouse input; no UIA or game API','reference_screenshot':str(args.reference.resolve()),'reference_sha256':reference['sha256'],'initial_screenshot':str(args.output.resolve()),'initial_screenshot_sha256':file_sha256(args.output),'new_screenshot':str(source.resolve()),'new_screenshot_sha256':fresh['sha256'],'freshness_hover':args.freshness_hover,'pixel_patch':args.patch,'patch_sha256':hashlib.sha256(after).hexdigest(),'patch_pixels_identical':True,'target_hwnd':args.hwnd,'boundary':'Requires an actually inspected reference. A mismatch refuses input; screenshot freshness and the resulting business state remain separate requirements.'}
 write_json(args.output.with_suffix('.template-proof.json'),proof)
 click(SimpleNamespace(hwnd=args.hwnd,screenshot=str(source),max_age=120,content_rect=[0,0,*fresh['image_size']],x=args.x,y=args.y,receipt=str(args.receipt)))
if __name__=='__main__':
 sys.stdout.reconfigure(encoding='utf-8');main()
