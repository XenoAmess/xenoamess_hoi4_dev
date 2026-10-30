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

def facial_hair_instruction(description):
    """Keep uncertain lip detail from asserting a definite moustache band."""
    features=description.strip().lower()
    if 'clean-shaven' in features:
        return 'CLEAN-SHAVEN: smooth yellow upper lip and chin; no moustache, beard, goatee or chin tuft. Skin shadows are not hair.'
    if ('retain only' in features
            and ('lip detail' in features or 'lip appearance' in features)
            and 'moustache only' not in features):
        return ('Upper-lip restraint: copy only the exact tiny lip-region appearance visible in this source, at its actual fine extent and colour. '
                'Skin shading, lip highlights and the mascot grey lip do not establish a moustache. Do not grow a broad hair band, beard or goatee. '
                'Retain any definite tiny visible source moustache only to that exact extent and colour; a clean chin stays smooth yellow.')
    if 'moustache only' in features or 'clean chin' in features or 'clean smooth chin' in features:
        return 'Retain actual source upper-lip moustache only, in the exact visible color and extent; chin stays completely smooth yellow, no goatee or beard.'
    return ('Retain the actual visible source facial hair with its correct extent and color; eyes, upper-lip moustache, '
            'source-shaped open or closed creature mouth, chin beard in that top-to-bottom order. No invented hair from shadows.')


def source_alpha_policy(image, *, opaque_canvas_reason=None):
    """A nearly opaque full canvas is not evidence of an exterior cutout.

    This affects only new requests. Original input bytes and frozen requests
    remain unchanged. A new request may explicitly record a manually verified
    full painted canvas even when its original nonzero alpha is below 249.
    This is never inferred from a filename or applied to a real alpha cutout.
    """
    minimum, maximum = image.convert('RGBA').getchannel('A').getextrema()
    if opaque_canvas_reason is not None:
        if not opaque_canvas_reason.strip():
            raise ValueError('Opaque canvas classification requires an explicit visual evidence reason')
        if minimum == 0:
            raise ValueError('A source with fully transparent pixels requires its genuine exterior alpha')
        return {
            'original_alpha_extrema': [minimum, maximum],
            'transparent_background': False,
            'alpha_prompt_policy': 'source-manually-verified-opaque-canvas-v1',
            'opaque_canvas_reason': opaque_canvas_reason,
        }
    near_opaque = 249 <= minimum < 255
    return {
        'original_alpha_extrema': [minimum, maximum],
        'transparent_background': minimum < 249,
        'alpha_prompt_policy': ('source-near-opaque-backdrop-v1' if near_opaque else
                                'source-opaque-v1' if minimum == 255 else
                                'source-content-v3-opaque-body'),
    }


def near_opaque_backdrop_instruction():
    return ("\nOutput background: this exact original has a COMPLETE near-opaque canvas, "
            "with every source alpha value at least 249/255. Its existing backdrop is required image content. "
            "Preserve the original backdrop color, texture, illumination and full rectangular extent behind the mascot. "
            "Return an opaque full-canvas portrait, not a transparent figure cutout. Do not remove or replace the original background. "
            "Keep the source clothing, hair, facial hair, accessories, pose and crop unchanged apart from the requested mascot conversion or targeted art repair.")


def verified_opaque_canvas_instruction():
    return ("\nOutput background: the exact original was visually verified to be a COMPLETE rectangular painted portrait, "
            "with no fully transparent source pixels. Its small original alpha variation does not establish an exterior figure cutout. "
            "Preserve the entire original background colour, texture, lighting and crop to all four canvas edges. "
            "Return a fully opaque rectangular image, alpha 255 throughout the originally opaque backdrop and subject, "
            "including hair, glasses, dark clothing and corners. Do not copy an incorrect target cutout mask or partial transparency. "
            "No transparent backdrop, fog, see-through fabric, haze, halo or invented frame/note. Keep every unrelated source feature unchanged.")


def alpha_instruction(asset):
    """Describe exterior alpha without deleting opaque original asset content."""
    opaque_body=(" All originally OPAQUE subject surfaces must remain FULLY OPAQUE (alpha 255): yellow head/body, hair, beard, dark or black clothing, coat lapels, collar, tie, buttons and decorations. "
                 "Dark cloth is colored material, not transparent background. Never fade garment interiors into semi-transparent patches, holes, white haze or see-through fabric. "
                 "Keep any genuine source outer-edge alpha falloff only at that actual exterior boundary; preserve actual source transparency rather than making the subject itself translucent.")
    path=asset['path'].replace('\\','/').lower()
    photo_card=path.startswith('gfx/interface/ideas/') and max(asset['size'])<100
    if photo_card:
        return ("\nOutput alpha: genuine transparent RGBA ONLY OUTSIDE the complete original framed portrait silhouette. "
                "The photographic BACKING INSIDE the frame is a required OPAQUE surface: preserve its original background color and texture behind the character all the way to the inner frame rim. "
                "Never turn the gaps between frame and character into transparent holes or a window. Keep the actual frame angle and rim. "
                "Preserve an overlapping paper note, pin or other attachment ONLY when actually visible in this exact source; otherwise do not invent one. "
                "Do not invent a new backdrop outside the whole card. Retain source clothing, hair, headgear, lighting and crop at full generated resolution."+opaque_body)
    return ("\nOutput alpha: preserve genuine transparent RGBA outside the original asset's outer silhouette. "
            "Retain all original opaque content, including any existing background or dark vignette that is part of this source; do not erase it into alpha holes. "
            "Where the original exterior is transparent, do not invent a new solid canvas, halo or studio backdrop. "
            "Retain source clothing, hair, headgear, lighting and portrait crop at full generated resolution."+opaque_body)

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

def supporting_crop_inputs(record, crops, edit_existing):
    """Validate unchanged native target crops used only to locate a small edit."""
    if not crops:return []
    if not edit_existing or not record or not record.get('generated_fullsize_image'):
        raise ValueError('Supporting crops require a current fullsize edit target')
    parent=ROOT/record['generated_fullsize_image']
    if file_sha256(parent)!=record['generated_fullsize_sha256']:
        raise ValueError('Supporting crop parent master changed')
    result=[]
    with Image.open(parent) as image:
        full=image.convert('RGBA')
        for item in crops:
            path=(ROOT/item['path']).resolve()
            if not path.is_relative_to((MOD/'assets/request_context').resolve()):
                raise ValueError('Supporting crop must be a retained request-context file')
            box=item['crop_box']
            if (len(box)!=4 or any(type(n) is not int for n in box)
                    or not 0<=box[0]<box[2]<=full.width or not 0<=box[1]<box[3]<=full.height):
                raise ValueError('Invalid native target crop bounds')
            if item['parent_fullsize_sha256']!=record['generated_fullsize_sha256'] or file_sha256(path)!=item['sha256']:
                raise ValueError('Supporting crop provenance changed')
            with Image.open(path) as cropped:
                actual=cropped.convert('RGBA');expected=full.crop(box)
                if actual.size!=expected.size or actual.tobytes()!=expected.tobytes():
                    raise ValueError('Supporting context must be unmodified native target pixels')
            result.append({'role':'unmodified native crop of current fullsize edit target; localization only',
                           'path':path.relative_to(ROOT.resolve()).as_posix(),'sha256':item['sha256'],
                           'parent_fullsize_sha256':item['parent_fullsize_sha256'],'crop_box':box})
    return result


def supporting_original_input(key, context, record, edit_existing, replacement_reason):
    """Bind a manually matched larger original as context for an independent call."""
    if context is None:return None
    if edit_existing or not record or record.get('review')!='rejected' or not replacement_reason:
        raise ValueError('Matched original context requires an independent replacement of rejected art')
    if context.get('actually_viewed_same_composition') is not True or not context.get('visual_match_reason','').strip():
        raise ValueError('Matched source context needs actual visual composition evidence')
    other=context['source_sha256']
    if other==key:
        raise ValueError('The primary original is already a required input')
    assets=read_json(MOD/'data/catalog.json')['assets']
    matches=[a for a in assets if a['source_sha256']==other]
    if not matches:raise ValueError('Supporting original is not in the actual catalog')
    path=original(matches[0])
    if file_sha256(path)!=context['converted_png_sha256']:
        raise ValueError('Observed supporting original PNG changed')
    return {'role':'composition-matched original context; primary source and independent generation remain distinct',
            'path':path.relative_to(ROOT).as_posix(),'sha256':context['converted_png_sha256'],
            'raw_sha256':other,'actually_viewed_same_composition':True,'visual_match_reason':context['visual_match_reason']}


def prepare(key, prompt, edit_existing=False, *, replacement_reason=None, opaque_canvas_reason=None, supporting_crops=None, supporting_original_context=None):
    asset=next(a for a in read_json(MOD/"data/catalog.json")["assets"] if a["source_sha256"]==key)
    source=original(asset)
    with Image.open(source) as image:alpha_policy=source_alpha_policy(image,opaque_canvas_reason=opaque_canvas_reason)
    transparent=alpha_policy['transparent_background']
    if transparent:
        prompt += alpha_instruction(asset)
    elif alpha_policy['alpha_prompt_policy']=='source-near-opaque-backdrop-v1':
        prompt += near_opaque_backdrop_instruction()
    elif alpha_policy['alpha_prompt_policy']=='source-manually-verified-opaque-canvas-v1':
        prompt += verified_opaque_canvas_instruction()
    record=read_json(MOD/"data/generated.json")["portraits"].get(key)
    file=REQUESTS/(key+".json")
    journal=read_json(file) if file.exists() else {"schema":"naiwa-generation-requests-v1","source_sha256":key,"attempts":[]}
    if journal["attempts"] and journal["attempts"][-1]["status"]=="prepared":
        raise SystemExit("Unresolved prepared request; inspect before resubmitting")
    feature_policy = None
    priority_path = MOD/'data/production-priority.json'
    if not edit_existing and not record and not journal['attempts'] and priority_path.exists():
        tier = read_json(priority_path)['sources'].get(key, {})
        if tier.get('high_priority') is False:
            feature_policy = 'fresh-low-visible-features-v1'
            prompt = ('Source-feature priority: Image 1 controls the actual visible hair, eyebrow HAIR, facial hair and clothing. '
                      'Image 2 controls mascot anatomy and identity only; its bare scalp or lack of eyebrows must not erase source-visible hair. '
                      'Retain every clearly visible source eyebrow as colored HAIR in its actual shape, extent and color, not a yellow ridge, socket shadow or cap shadow. '
                      'Keep the source hairstyle and any visible temple/side hair and beard extent. Features actually covered or absent in the source stay covered or absent. '
                      'The rounded chin meets a VERY SHORT BROAD neck transition. Refit the existing neckline and lapels around the compact head while preserving their open/closed style; do not fill an open V with a long narrow yellow funnel.\n'
                      + prompt)
    if replacement_reason is not None and not replacement_reason.strip():
        raise ValueError('Replacement reason must be explicit and nonempty')
    if record and not edit_existing and not replacement_reason:
        raise ValueError('Original-based replacement requires an explicit replacement_reason before generation')
    extra_inputs=supporting_crop_inputs(record,supporting_crops,edit_existing)
    original_context=supporting_original_input(key,supporting_original_context,record,edit_existing,replacement_reason)
    from mod_nailong.tools.image_retries import require_editable_service_state
    require_editable_service_state(key,record,journal['attempts'][-1] if journal['attempts'] else None,edit_existing,original_replacement_reason=replacement_reason)
    paths=[];inputs=[]
    if edit_existing:
        if not record:raise SystemExit("No existing image to edit")
        if record.get('generated_fullsize_image') or record.get('generated_fullsize_sha256'):
            if not record.get('generated_fullsize_image'):
                raise ValueError('Declared fullsize edit target is missing or changed; recover the exact master path before preparing')
            old=ROOT/record['generated_fullsize_image']
            expected=record.get('generated_fullsize_sha256')
            if not old.is_file() or not expected or file_sha256(old)!=expected:
                raise ValueError('Declared fullsize edit target is missing or changed; recover the exact master before preparing')
            target={'role':'previous generated fullsize edit target','path':old.relative_to(ROOT).as_posix(),
                    'sha256':expected,'derived_game_image_sha256':record['image_sha256']}
        else:
            # Pre-master legacy records can still be migrated. A declared but
            # unavailable master above must never silently degrade to this.
            old=MOD/"assets/legacy-before-hair"/(key+"-"+record["image_sha256"][:16]+".png")
            old.parent.mkdir(parents=True,exist_ok=True)
            if not old.exists():shutil.copyfile(ROOT/record["image"],old)
            assert file_sha256(old)==record["image_sha256"]
            target={'role':'legacy game-size generated edit target; no declared master',
                    'path':old.relative_to(ROOT).as_posix(),'sha256':file_sha256(old)}
        paths.append(str(old));inputs.append(target)
    paths.extend([str(source),str(MOD/"assets/reference/naiwa.png")])
    inputs.extend([{"role":"original source portrait","raw_sha256":key,"converted_png_sha256":file_sha256(source)},
        {"role":"user mascot reference","path":"mod_nailong/assets/reference/naiwa.png","sha256":file_sha256(MOD/"assets/reference/naiwa.png")}])
    for item in extra_inputs:
        paths.append(str(ROOT/item['path']));inputs.append(item)
    if original_context:
        paths.append(str(ROOT/original_context['path']));inputs.append(original_context)
    n=len(journal["attempts"])+1
    promptfile=MOD/"assets/prompts"/f"{key}-{n:03}.txt"
    promptfile.parent.mkdir(parents=True,exist_ok=True);promptfile.write_text(prompt,encoding="utf-8",newline="\n")
    attempt={"number":n,"status":"prepared","method":"built-in imagegen", "art_direction":"hair-features-v1",
        "prompt":prompt,"prompt_file":promptfile.relative_to(ROOT).as_posix(),"prompt_sha256":file_sha256(promptfile),
        "inputs":inputs,"edit_existing":edit_existing,"machine_id":machine_id(),"prepared_at_utc":utc_now(),
        **alpha_policy}
    if replacement_reason:
        attempt['replacement_reason']=replacement_reason
    if feature_policy:
        attempt['feature_preservation_prompt_policy']=feature_policy
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
        replacement_reason=a.get('replacement_reason') or (a.get('revision_goal','visual_feature_correction') if a['edit_existing'] else None)
        ingest(key,image,ROOT/a["prompt_file"],replacement_reason)
    generated=read_json(MOD/"data/generated.json")
    from mod_nailong.tools.master_files import master_path
    generated["portraits"][key]["generated_fullsize_image"]=master_path(fullsize_sha)
    generated["portraits"][key]["art_direction"]=a['art_direction']
    generated["portraits"][key]["generation_inputs"]=a["inputs"]
    generated["portraits"][key]["request_journal"]=file.relative_to(ROOT).as_posix()
    if recovered:
        generated['portraits'][key]['import_recovery']={'observed_at_utc':utc_now(),'machine_id':machine_id(),'reason':'Completed interrupted import of the exact already returned image; no new generation or art revision','fullsize_sha256':fullsize_sha}
    write_json(MOD/"data/generated.json",generated)
    a.update(status="generated_pending_visual_review",generated_at_utc=utc_now(),fullsize_sha256=file_sha256(Path(image)),fullsize_image=generated["portraits"][key]["generated_fullsize_image"],
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
    p.add_argument("--replacement-reason",help="Explicit pre-call reason for an original-based replacement without an edit target")
    p.add_argument("--opaque-canvas-reason",help="Explicit visual evidence for a complete painted source canvas; new requests only")
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
    elif args.command=="prepare":write_json(ROOT/"runtime/prepared-image-job.json",prepare(args.key,args.prompt_file.read_text(encoding="utf-8"),args.edit_existing,replacement_reason=args.replacement_reason,opaque_canvas_reason=args.opaque_canvas_reason))
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
                    "journal_attempt_number":a['number'],
                    "retry":"Continue unrelated sources. When allowed and tool-permitted, wait at least eight hours after EACH refusal and reuse the exact prompt and inputs; stop on success or after eight cumulative source retries. No alternate route."})
                held=failures.setdefault("held_source_paths",[])
                if asset["path"] not in held:held.append(asset["path"])
                write_json(failures_path,failures)
        write_json(file,data)
        if args.command=="fail":
            from mod_nailong.tools.image_retries import sync
            sync() # Sole producer applies the policy and the new refusal's full CD.

if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8");main()
