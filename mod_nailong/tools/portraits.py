"""Import imagegen output, review contact sheets, and report actual coverage.

No image generation API or MCP dependency. Images are created with the built-in
imagegen skill; this tool performs deterministic resize/format conversion only.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json
from PIL import Image, ImageDraw

MOD = ROOT / "mod_nailong"
RECORD = MOD / "data/generated.json"
CATALOG = MOD / "data/catalog.json"

def coverage(publish=False):
    from mod_nailong.tools.art_contract import portrait_ready
    catalog=read_json(CATALOG)
    generated=read_json(RECORD)["portraits"]
    covered=[a for a in catalog["assets"] if a["source_sha256"] in generated]
    reviewed=[a for a in covered if portrait_ready(generated[a["source_sha256"]])]
    result={"machine_id":machine_id(),"observed_at_utc":utc_now(),"catalog_sha256":file_sha256(CATALOG),"textures_total":len(catalog["assets"]),"textures_generated":len(covered),"textures_reviewed":len(reviewed),"unique_total":catalog["counts"]["distinct_source_images"],"unique_generated":len(generated),"unresolved_baseline_references":len(catalog["unresolved_references"]),"status":"art-complete" if len(reviewed)==len(catalog["assets"]) else "incomplete"}
    result['unique_reviewed']=len({a['source_sha256'] for a in reviewed})
    priority_path=MOD/'data/production-priority.json'
    if priority_path.exists():
        entries=read_json(priority_path)['sources']
        high={k for k,e in entries.items() if e['high_priority']}
        high_done={k for k in high if k in generated and portrait_ready(generated[k])}
        result.update(high_priority_total=len(high),high_priority_reviewed=len(high_done),high_priority_remaining=len(high-high_done),lower_priority_locked=bool(high-high_done))
    write_json(ROOT/"runtime/coverage.json",result)
    if publish:write_json(MOD/"data/progress.json",result)
    print(__import__('json').dumps(result,ensure_ascii=False,indent=2))
    return result

def ingest(key, image_path, prompt_file, replace_reason=None):
    catalog=read_json(CATALOG)
    assets=[a for a in catalog["assets"] if a["source_sha256"]==key]
    if not assets:raise SystemExit("Unknown source SHA; inventory must precede generation")
    record=read_json(RECORD)
    previous=record["portraits"].get(key)
    if previous and not replace_reason:raise SystemExit("Already imported; use --replace-reason for an explicit art correction")
    sizes={tuple(a["size"]) for a in assets}
    if len(sizes)!=1:raise SystemExit("Identical bytes decoded to inconsistent dimensions")
    image_path=Path(image_path)
    out=MOD/"assets/portraits"/(key+".png")
    out.parent.mkdir(parents=True,exist_ok=True)
    with Image.open(image_path) as image:
        original_size=list(image.size)
        # Technical normalization only: no collage, retouching, face substitution or drawing.
        image.convert("RGBA").resize(next(iter(sizes)),Image.Resampling.LANCZOS).save(out,optimize=True)
    prompt=Path(prompt_file).read_text(encoding="utf-8")
    record["portraits"][key]={"source_sha256":key,"reference_sha256":file_sha256(MOD/"assets/reference/naiwa.png"),"method":"built-in imagegen; original portrait + user reference","prompt":prompt,"generated_fullsize_sha256":file_sha256(image_path),"generated_fullsize_size":original_size,"image":out.relative_to(ROOT).as_posix(),"image_sha256":file_sha256(out),"size":list(next(iter(sizes))),"review":"pending","machine_id":machine_id(),"imported_at_utc":utc_now()}
    if previous:
        history=list(previous.get("revision_history",[]))
        history.append({"result":"replaced after visual review","reason":replace_reason,"previous_image_sha256":previous["image_sha256"],"previous_fullsize_sha256":previous["generated_fullsize_sha256"],"previous_prompt":previous["prompt"],"replaced_at_utc":utc_now()})
        record["portraits"][key]["revision_history"]=history
    write_json(RECORD,record)
    # Machine-local full-size origin stays out of the public manifest and Git.
    fullsize=ROOT/"runtime/generated-origins"/(key+".json")
    write_json(fullsize,{"machine_id":machine_id(),"observed_at_utc":utc_now(),"source":str(image_path.resolve()),"sha256":file_sha256(image_path),"review_at_utc":__import__('datetime').datetime.fromtimestamp(__import__('time').time()+7*86400,__import__('datetime').timezone.utc).isoformat(),"reason":"Fullsize source available during art review; canonical resized deliverable is in Git"})
    record["portraits"][key]["art_direction"]="hair-features-v1"
    write_json(RECORD,record)
    print(f"Imported {key[:12]} -> {out.relative_to(ROOT)}")

def contact_sheet(include_approved=False):
    catalog=read_json(CATALOG)
    record=read_json(RECORD)["portraits"]
    pending=[(key,row) for key,row in record.items() if include_approved or row["review"]=="pending"]
    if not pending:
        print("No pending art reviews")
        return
    columns=min(8,len(pending))
    sheet=Image.new("RGB",(columns*180,((len(pending)+columns-1)//columns)*252),"#dcd9d2")
    draw=ImageDraw.Draw(sheet)
    for i,(key,row) in enumerate(pending):
        with Image.open(ROOT/row["image"]) as image:
            # Nearest display enlargement keeps the actual tiny in-game pixels apparent.
            image.thumbnail((156,210))
            if image.height<120:image=image.resize((min(156,image.width*2),min(210,image.height*2)))
            x,y=(i%columns)*180+8,(i//columns)*252+4
            sheet.paste(image,(x,y),image.getchannel("A"))
            draw.text((x,y+214),f"{i+1} {key[:10]}",fill="black")
            source=next(a["path"] for a in catalog["assets"] if a["source_sha256"]==key)
            draw.text((x,y+230),Path(source).stem[-23:],fill="black")
    path=ROOT/"runtime/output-contact-sheet.png"
    sheet.save(path)
    write_json(ROOT/"runtime/review-keys.json",[key for key,_ in pending])
    print(path)

def approve(keys):
    record=read_json(RECORD)
    if keys==["pending-sheet"]:keys=read_json(ROOT/"runtime/review-keys.json")
    failures=read_json(MOD/"data/generation-failures.json")
    held={a["source_sha256"] for a in failures.get("attempts",[]) if a.get("status")=="blocked" and not a.get("resolved_by_retry")}
    queue_path=MOD/"data/image-retry-queue.json"
    queue=read_json(queue_path) if queue_path.exists() else {"sources":{}}
    for key in keys:
        row=record["portraits"][key]
        retry=queue["sources"].get(key,{})
        if key in held and not (retry.get("state")=="generated_pending_visual_review" and retry.get("output_sha256")==row["image_sha256"]):raise SystemExit("Cannot approve a held image-generation source")
        if row.get("art_direction")!="hair-features-v1":raise SystemExit("Migrate legacy art before approval")
        if file_sha256(ROOT/row["image"])!=row["image_sha256"]:raise SystemExit("Image changed since import")
        row.update(review="approved",reviewed_at_utc=utc_now(),review_method="Visual comparison of input and output contact sheets by Codex")
        row['collar_fit']={'policy':'collar-fit-v1','status':'approved','image_sha256':row['image_sha256'],'reviewed_at_utc':utc_now(),'review_method':'Visual inspection of neck width, collar opening, front/back occlusion, fastening and absence of cream neck bib'}
        if retry.get('state')=='service_retry_succeeded_art_correction_pending':
            accepted=retry.get('accepted_retry_output_sha256')
            if not any(h.get('previous_image_sha256')==accepted for h in row.get('revision_history',[])):
                raise SystemExit('Art revision does not descend from accepted exact retry')
            retry.update(state='approved_after_single_cooldown_retry_and_art_correction',approved_at_utc=utc_now(),approved_image_sha256=row['image_sha256'])
        if row.get("request_journal"):
            path=ROOT/row["request_journal"];journal=read_json(path)
            attempt=journal["attempts"][-1]
            if attempt.get("output_sha256")!=row["image_sha256"]:raise SystemExit("Latest request does not bind reviewed image")
            attempt.update(status="approved",reviewed_at_utc=utc_now(),review="approved")
            write_json(path,journal)
            if attempt.get("retry_of_attempt"):
                retry.update(state="approved_after_single_cooldown_retry",approved_at_utc=utc_now())
                for failure in failures.get("attempts",[]):
                    if failure["source_sha256"]==key:
                        failure["resolved_by_retry"]={"output_sha256":row["image_sha256"],"approved_at_utc":utc_now(),"original_refusal_preserved":True}
    write_json(RECORD,record)
    write_json(MOD/"data/generation-failures.json",failures)
    if queue_path.exists():write_json(queue_path,queue)
    print(f"Reviewed {len(keys)} image(s)")

def reject(keys,reason):
    record=read_json(RECORD)
    for key in keys:
        record["portraits"][key].update(review="rejected",review_reason=reason,reviewed_at_utc=utc_now())
        journal_path=MOD/"data/generation-requests"/(key+".json")
        if journal_path.exists():
            journal=read_json(journal_path)
            attempt=journal["attempts"][-1]
            if attempt.get("output_sha256")==record["portraits"][key]["image_sha256"]:
                attempt.update(status="generated_rejected_visual_review",review="rejected",rejection_reason=reason,reviewed_at_utc=utc_now())
                write_json(journal_path,journal)
    write_json(RECORD,record)
    print(f"Rejected {len(keys)} image(s)")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    progress=sub.add_parser("coverage")
    progress.add_argument("--public",action="store_true",help="Also write the compact tracked progress snapshot")
    sheet=sub.add_parser("sheet")
    sheet.add_argument("--all",action="store_true",help="Include approved images for the project preview")
    add=sub.add_parser("import")
    add.add_argument("--key",required=True)
    add.add_argument("--image",required=True)
    add.add_argument("--prompt-file",default=str(MOD/"assets/portrait-prompt.txt"))
    add.add_argument("--replace-reason",help="Explicit correction of an already imported image; preserves previous provenance")
    review=sub.add_parser("approve")
    review.add_argument("keys",nargs="+")
    rejection=sub.add_parser("reject")
    rejection.add_argument("keys",nargs="+")
    rejection.add_argument("--reason",required=True)
    args=parser.parse_args()
    if args.command=="import":ingest(args.key,args.image,args.prompt_file,args.replace_reason)
    elif args.command=="coverage":coverage(args.public)
    elif args.command=="sheet":contact_sheet(args.all)
    elif args.command=="approve":approve(args.keys)
    else:reject(args.keys,args.reason)

if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
