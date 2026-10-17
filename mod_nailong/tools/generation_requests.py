"""Persist full prompts BEFORE built-in imagegen and import its result afterward.

No API client: Codex calls the built-in tool separately for every distinct image.
"""
from __future__ import annotations
import argparse
import io
import re
from pathlib import Path
import shutil
import sys
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT, file_sha256, machine_id, read_json, sha256, utc_now, write_json
from PIL import Image, ImageDraw
from mod_nailong.tools.portraits import ingest, record_fullsize_origin

MOD = ROOT / "mod_nailong"
REQUESTS = MOD / "data/generation-requests"

def original(asset):
    src = read_json(ROOT / "runtime/source-index.json")[asset["id"]]
    if src["member"]:
        with zipfile.ZipFile(src["path"]) as archive:raw=archive.read(src["member"])
    else:raw=Path(src["path"]).read_bytes()
    assert sha256(raw)==asset["source_sha256"]
    out=ROOT/"runtime/references"/(asset["source_sha256"]+".png")
    out.parent.mkdir(parents=True,exist_ok=True)
    with Image.open(io.BytesIO(raw)) as im:im.convert("RGBA").save(out)
    return out

def prepare(key, prompt, edit_existing=False):
    asset=next(a for a in read_json(MOD/"data/catalog.json")["assets"] if a["source_sha256"]==key)
    source=original(asset)
    transparent=Image.open(source).getchannel("A").getextrema()[0]<255
    if transparent:
        prompt += "\nOutput alpha: keep a genuine fully transparent RGBA background outside the portrait silhouette. No painted gray backdrop, halo, studio gradient or rectangular plate. Retain the source's clothing, hair, headgear and portrait crop."
    record=read_json(MOD/"data/generated.json")["portraits"].get(key)
    file=REQUESTS/(key+".json")
    journal=read_json(file) if file.exists() else {"schema":"naiwa-generation-requests-v1","source_sha256":key,"attempts":[]}
    if journal["attempts"] and journal["attempts"][-1]["status"]=="prepared":
        raise SystemExit("Unresolved prepared request; inspect before resubmitting")
    from mod_nailong.tools.image_retries import require_editable_service_state
    require_editable_service_state(key,record,journal['attempts'][-1] if journal['attempts'] else None,edit_existing)
    paths=[];inputs=[]
    if edit_existing:
        if not record:raise SystemExit("No existing image to edit")
        old=MOD/"assets/legacy-before-hair"/(key+"-"+record["image_sha256"][:16]+".png")
        old.parent.mkdir(parents=True,exist_ok=True)
        if not old.exists():shutil.copyfile(ROOT/record["image"],old)
        assert file_sha256(old)==record["image_sha256"]
        paths.append(str(old));inputs.append({"role":"previous generated edit target","path":old.relative_to(ROOT).as_posix(),"sha256":file_sha256(old)})
    paths.extend([str(source),str(MOD/"assets/reference/naiwa.png")])
    inputs.extend([{"role":"original source portrait","raw_sha256":key,"converted_png_sha256":file_sha256(source)},
        {"role":"user mascot reference","path":"mod_nailong/assets/reference/naiwa.png","sha256":file_sha256(MOD/"assets/reference/naiwa.png")}])
    n=len(journal["attempts"])+1
    promptfile=MOD/"assets/prompts"/f"{key}-{n:03}.txt"
    promptfile.parent.mkdir(parents=True,exist_ok=True);promptfile.write_text(prompt,encoding="utf-8",newline="\n")
    attempt={"number":n,"status":"prepared","method":"built-in imagegen", "art_direction":"hair-features-v1",
        "prompt":prompt,"prompt_file":promptfile.relative_to(ROOT).as_posix(),"prompt_sha256":file_sha256(promptfile),
        "inputs":inputs,"edit_existing":edit_existing,"machine_id":machine_id(),"prepared_at_utc":utc_now()}
    journal["attempts"].append(attempt);write_json(file,journal)
    return {"key":key,"source":asset["path"],"references":paths,"original":str(source),
        "size":asset["size"],"transparent":transparent,"prompt":prompt,
        "journal":file.relative_to(ROOT).as_posix()}

def legacy():
    rows=read_json(MOD/"data/generated.json")["portraits"]
    common=(MOD/"experiments/hair-features-v1/prompts/cdcacddc83bb74af8ef7e666af75d7bec955403285389f35f6b922342750a03b-b-01.txt").read_text(encoding="utf-8").split("Visible features for this source:")[0]
    jobs=[]
    for key,row in rows.items():
        if row.get("art_direction")=="hair-features-v1":continue
        prompt=common+"Visible features for this source: copy ONLY the hair, eyebrows and facial hair actually visible in Image 2. Keep the original aviation helmet, goggles or cap where present. If bareheaded retain the visible hairline and hairstyle. Keep the pilot's jacket, uniform and scarf exactly as in Image 1. If there is an upper-lip moustache, it must sit ABOVE the small horizontal mouth, not under the mouth as a beard. No photograph frame, no paper note; keep this as a transparent pilot bust."
        jobs.append(prepare(key,prompt,True))
    write_json(ROOT/"runtime/legacy-hair-jobs.json",jobs)
    sheet=Image.new("RGB",(6*210,((len(jobs)+5)//6)*250),"#d7d6d1");draw=ImageDraw.Draw(sheet)
    for i,j in enumerate(jobs):
        with Image.open(j["original"]) as im:
            ratio=min(195/im.width,210/im.height);im=im.resize((round(im.width*ratio),round(im.height*ratio)),Image.Resampling.NEAREST)
            x,y=(i%6)*210+5,(i//6)*250+5;sheet.paste(im,(x,y),im.getchannel("A"));draw.text((x,y+214),f"{i+1} {j['key'][:8]}",fill="black");draw.text((x,y+230),Path(j["source"]).stem[-25:],fill="black")
    sheet.save(ROOT/"runtime/legacy-hair-originals.png")
    print(f"Prepared and recorded {len(jobs)} legacy migration requests")

def finish(key,image):
    file=REQUESTS/(key+".json");journal=read_json(file);a=journal["attempts"][-1]
    assert a["status"]=="prepared"
    record_path=MOD/"data/generated.json"
    existing=read_json(record_path)["portraits"].get(key) if record_path.exists() else None
    fullsize_sha=file_sha256(Path(image))
    recovered=False
    if (existing and existing.get('prompt')==a.get('prompt')
            and existing.get('generated_fullsize_sha256')==fullsize_sha):
        # A prior filesystem interruption can leave the image imported while
        # the request is still prepared. Reconcile that exact result; do not
        # call imagegen again or manufacture a second art revision.
        assert existing.get('review')=='pending', 'Existing result already reviewed; inspect journal state'
        assert existing.get('source_sha256')==key
        assets=[r for r in read_json(MOD/'data/catalog.json')['assets'] if r['source_sha256']==key]
        sizes={tuple(r['size']) for r in assets}
        assert len(sizes)==1 and tuple(existing['size'])==next(iter(sizes))
        canonical=ROOT/existing['image']
        assert canonical.resolve()==(MOD/'assets/portraits'/(key+'.png')).resolve()
        assert file_sha256(canonical)==existing['image_sha256'], 'Partial import image changed'
        assert file_sha256(ROOT/a['prompt_file'])==a['prompt_sha256'], 'Prepared prompt changed'
        assert (ROOT/a['prompt_file']).read_text(encoding='utf-8')==a['prompt']
        with Image.open(image) as raw:
            normalized=io.BytesIO()
            raw.convert('RGBA').resize(existing['size'],Image.Resampling.LANCZOS).save(normalized,format='PNG',optimize=True)
        assert sha256(normalized.getvalue())==existing['image_sha256'], 'Partial import does not match actual returned output'
        record_fullsize_origin(key,image,root=ROOT)
        recovered=True
    else:
        ingest(key,image,ROOT/a["prompt_file"],a.get('revision_goal','visual_feature_correction') if a["edit_existing"] else None)
    generated=read_json(MOD/"data/generated.json")
    generated["portraits"][key]["art_direction"]=a['art_direction']
    generated["portraits"][key]["generation_inputs"]=a["inputs"]
    generated["portraits"][key]["request_journal"]=file.relative_to(ROOT).as_posix()
    if recovered:
        generated['portraits'][key]['import_recovery']={'observed_at_utc':utc_now(),'machine_id':machine_id(),'reason':'Completed interrupted import of the exact already returned image; no new generation or art revision','fullsize_sha256':fullsize_sha}
    write_json(MOD/"data/generated.json",generated)
    a.update(status="generated_pending_visual_review",generated_at_utc=utc_now(),fullsize_sha256=file_sha256(Path(image)),
        output=generated["portraits"][key]["image"],output_sha256=generated["portraits"][key]["image_sha256"])
    write_json(file,journal)
    if a.get("retry_of_attempt"):
        queuefile=MOD/"data/image-retry-queue.json";queue=read_json(queuefile)
        queue["sources"][key].update(state="generated_pending_visual_review",output_sha256=a["output_sha256"],generated_at_utc=utc_now())
        write_json(queuefile,queue)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("command",choices=["legacy","batch","prepare","finish","fail","cancel","reject"])
    p.add_argument("--key");p.add_argument("--prompt-file",type=Path);p.add_argument("--edit-existing",action="store_true");p.add_argument("--image");p.add_argument("--message")
    p.add_argument("--message-file",type=Path)
    p.add_argument("--jobs-file",type=Path);p.add_argument("--directions-file",type=Path)
    args=p.parse_args()
    if args.command=="legacy":legacy()
    elif args.command=="batch":
        jobs=read_json(args.jobs_file);directions=read_json(args.directions_file)
        if len(jobs)!=len(directions):raise SystemExit("Directions must bind every prepared source in order")
        common=(MOD/"assets/portrait-prompt.txt").read_text(encoding="utf-8")
        prepared=[prepare(j["key"],common+"\nVisible source-specific features: "+d,False) for j,d in zip(jobs,directions)]
        write_json(ROOT/"runtime/current-hair-jobs.json",prepared)
        print(f"Saved {len(prepared)} full prompts before any generation calls")
    elif args.command=="prepare":write_json(ROOT/"runtime/prepared-image-job.json",prepare(args.key,args.prompt_file.read_text(encoding="utf-8"),args.edit_existing))
    elif args.command=="finish":
        try:
            finish(args.key,args.image)
        except (Exception,SystemExit):
            error_file=ROOT/'runtime/import-errors'/(args.key+'.txt')
            error_file.parent.mkdir(parents=True,exist_ok=True)
            error_file.write_text(__import__('traceback').format_exc(),encoding='utf-8',newline='\n')
            raise
    else:
        file=REQUESTS/(args.key+".json");data=read_json(file)
        if args.command=="cancel":data["attempts"][-1].update(status="cancelled_before_generation",reason=args.message,observed_at_utc=utc_now())
        elif args.command=="reject":data["attempts"][-1].update(review="rejected",rejection_reason=args.message,reviewed_at_utc=utc_now())
        else:
            error=args.message_file.read_text(encoding="utf-8") if args.message_file else args.message
            a=data["attempts"][-1];a.update(status="failed",error=error,observed_at_utc=utc_now())
            if "moderation_blocked" in error:
                failures_path=MOD/"data/generation-failures.json";failures=read_json(failures_path)
                asset=next(a for a in read_json(MOD/"data/catalog.json")["assets"] if a["source_sha256"]==args.key)
                request_ids=re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",error)
                failures.setdefault("attempts",[]).append({"source_sha256":args.key,"source_path":asset["path"],"status":"blocked",
                    "machine_id":machine_id(),"observed_at_utc":utc_now(),"tool":"built-in imagegen","code":"moderation_blocked",
                    "request_id":request_ids[0] if request_ids else None,"actual_error":error,"prompt":a["prompt"],"inputs":a["inputs"],
                    "retry":"Continue unrelated sources. Only an allowed request/tool-permitted retry may run once after the recorded eight-hour cooldown, with exact original prompt and inputs; no alternate route."})
                held=failures.setdefault("held_source_paths",[])
                if asset["path"] not in held:held.append(asset["path"])
                write_json(failures_path,failures)
        write_json(file,data)
        if args.command=="fail":
            from mod_nailong.tools.image_retries import sync
            queue=sync()
            if data["attempts"][-1].get("retry_of_attempt"):
                queue["sources"][args.key].update(state="retry_failed_no_more_automatic_retries",failed_at_utc=utc_now())
                write_json(MOD/"data/image-retry-queue.json",queue)
            elif queue.get('sources',{}).get(args.key,{}).get('retries_used',0)>=1:
                queue['sources'][args.key].update(state='new_art_request_refused_retry_quota_exhausted',latest_refusal_at_utc=utc_now(),latest_refused_prompt_sha256=data['attempts'][-1]['prompt_sha256'])
                write_json(MOD/'data/image-retry-queue.json',queue)

if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8");main()
