"""Prepare up to eight actual rejected masters as soon as a known report arrives.

Invoked only by the sole producer after its durable previous-window barrier.
No image calls, service retry claims or automatic visual decisions occur here.
"""
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT,read_json,write_json,file_sha256,machine_id,utc_now
from mod_nailong.tools.ready_art_reports import reports as inbox_reports,independent_art_holds
from tools.portrait_dispatch_guard import same_service_family
from tools.accepted_retry_art import accepted_retry_art_proofs


def eligible_entries(reports,rows,latest,held_keys=(),priority=None):
    selected=[];seen=set()
    for report,body in sorted(reports,key=lambda item:item[1].get('reviewed_at_utc',''),reverse=True):
        for entry in body.get('decisions',[]):
            key=entry.get('source_sha256');row=rows.get(key,{})
            if (entry.get('decision')!='rejected' or key in seen or key in held_keys
                    or entry.get('generated_fullsize_sha256')!=row.get('generated_fullsize_sha256')
                    or row.get('review') not in {'pending','rejected'}
                    or latest.get(key,{}).get('status') not in {'generated_pending_visual_review','generated_rejected_visual_review','cancelled_before_generation'}):continue
            selected.append((report,entry));seen.add(key)
            if len(selected)==8 and priority is None:return selected
    if priority is not None:selected.sort(key=lambda item:not priority[item[1]['source_sha256']]['high_priority'])
    return selected[:8]



def latest_current_rejections(root, reports, rows):
    """Read each relevant journal once per selection, never cache across boundaries.

    Obsolete raw SHAs and already approved portraits cannot be selected by
    eligible_entries. Their old report occurrences need no journal lookup.
    Current pending/rejected outputs retain the complete latest-attempt gate.
    """
    latest = {}
    for _, body in reports:
        for entry in body.get('decisions', []):
            key = entry.get('source_sha256')
            row = rows.get(key, {})
            if (entry.get('decision') == 'rejected' and key not in latest
                    and row.get('review') in {'pending', 'rejected'}
                    and entry.get('generated_fullsize_sha256') == row.get('generated_fullsize_sha256')
                    and key in rows):
                latest[key] = read_json(root / row['request_journal'])['attempts'][-1]
    return latest


def service_held_keys(keys,priority,failures,accepted_retry_keys=()):
    blocked={f['source_sha256'] for f in failures if f.get('status')=='blocked' and not f.get('resolved_by_retry')}
    return {key for key in keys if key in priority and any(
        same_service_family(key,other,priority[key],priority[other])
        and not (key==other and key in accepted_retry_keys) for other in blocked)}


def reviewed_canvas_reasons(root, chosen):
    """Reuse explicit SHA-bound source observations for NEW art preparations."""
    path=root/'mod_nailong/data/reviewed-source-canvas.json'
    if not path.exists():return {}
    registry=read_json(path)
    assert registry['machine_id']==machine_id()
    result={}
    for _,entry in chosen:
        key=entry['source_sha256'];proof=registry['sources'].get(key)
        if proof is None:continue
        assert proof['actually_viewed'] is True and proof['complete_painted_rectangle'] is True
        assert isinstance(proof['opaque_canvas_reason'],str) and proof['opaque_canvas_reason'].strip()
        source=root/f'runtime/references/{key}.png'
        assert file_sha256(source)==proof['original_png_sha256']==entry['original_png_sha256']
        from PIL import Image
        with Image.open(source) as opened:extrema=list(opened.convert('RGBA').getchannel('A').getextrema())
        assert extrema==proof['original_alpha_extrema'] and extrema[0]>0
        assert proof['evidence'],'An explicit manual source observation is required'
        for evidence in proof['evidence']:
            target=(root/evidence['path']).resolve()
            assert target.is_relative_to(root.resolve()) and file_sha256(target)==evidence['sha256']
        result[key]={'opaque_canvas_reason':proof['opaque_canvas_reason']}
    return result


def main():
    batch,index,*names=sys.argv[1:]
    use_inbox='--inbox' in names;names=[name for name in names if name!='--inbox']
    assert batch.replace('-','').isalnum() and index.isdigit() and (names or use_inbox)
    fixed_paths=[ROOT/'mod_nailong/data'/name for name in names]
    assert all(path.parent==ROOT/'mod_nailong/data' for path in fixed_paths)
    selection=ROOT/f'runtime/ready-art-{batch}-selection.json'
    assert not selection.exists(),'Never replay a claimed ready-art preparation'
    assert not any(read_json(p).get('status')=='calling' for p in (ROOT/'runtime/production-queue/dispatch').glob('*.json'))
    deadline=time.monotonic()+900
    last_reports=None
    while True:
        if time.monotonic()>deadline:raise TimeoutError('No actual current eligible rejection in known reports; no image or retry dispatched')
        # Explicitly queued shared reports remain available to later batches;
        # current output SHA/latest-attempt checks prevent replay after use.
        inbox=(inbox_reports(batch)+inbox_reports('global')) if use_inbox else []
        paths=list(dict.fromkeys(fixed_paths+[path for path,proof in inbox]))
        # Only the sole producer may mutate canonical state at this boundary.
        # Wake on report content changes; do not repeatedly parse the large
        # unchanged generated inventory while waiting for an immutable report.
        # These hashes only wake the reader: the preparer still revalidates
        # actual current masters, journals and complete prompt/input bytes.
        signatures=tuple((p,file_sha256(p)) for p in paths if p.exists())
        if not signatures or signatures==last_reports:
            time.sleep(1)
            continue
        last_reports=signatures
        reports=[(p,read_json(p)) for p in paths if p.exists()]
        rows=read_json(ROOT/'mod_nailong/data/generated.json')['portraits']
        for _,body in reports:
            assert body.get('machine_id')==machine_id()
        latest=latest_current_rejections(ROOT,reports,rows)
        priority=read_json(ROOT/'mod_nailong/data/production-priority.json')['sources']
        failures=read_json(ROOT/'mod_nailong/data/generation-failures.json')['attempts']
        accepted=accepted_retry_art_proofs(ROOT,rows,latest)
        held=service_held_keys(latest,priority,failures,accepted['proofs'])|independent_art_holds()
        chosen=eligible_entries(reports,rows,latest,held,priority)
        if chosen:break
        time.sleep(1)
    subprocess.run([sys.executable,'mod_nailong/tools/production_queue.py','apply-reviews'],cwd=ROOT,check=True)
    keys=[e['source_sha256'] for p,e in chosen]
    write_json(selection,{'schema':'naiwa-exact-art-review-selection-v1','entries':[{'source_sha256':e['source_sha256'],'generated_fullsize_sha256':e['generated_fullsize_sha256'],'report':p.relative_to(ROOT).as_posix(),'report_sha256':file_sha256(p)} for p,e in chosen]})
    canvas=ROOT/f'runtime/ready-art-{batch}-canvas.json';assert not canvas.exists();write_json(canvas,{'sources':reviewed_canvas_reasons(ROOT,chosen)})
    used=list(dict.fromkeys(p for p,e in chosen))
    receipt=ROOT/f'mod_nailong/data/production-ready-refills/{batch}.json';assert not receipt.exists()
    write_json(receipt,{'machine_id':machine_id(),'claimed_at_utc':utc_now(),'source_keys':keys,'report_evidence':[{'path':p.relative_to(ROOT).as_posix(),'sha256':file_sha256(p)} for p in used],'inbox_evidence':[proof for path,proof in inbox if path in used],'accepted_exact_retry_art_proofs':{k:accepted['proofs'][k] for k in keys if k in accepted['proofs']},'scope':'Sole executor selects existing actual SHA-bound rejections immediately when a known or explicitly queued manual report is ready. Does not wait for other reports, infer art approval or change failed requests. Exact retries which actually returned the current rejected PNG may reach the existing editable-service proof; other unresolved family failures remain blocking. Full canonical/raw/boundary checks remain in the preparer.'})
    subprocess.run([sys.executable,'tools/prepare_reviewed_art_repairs.py',batch,','.join(p.name for p in used),str(len(keys)),index,canvas.relative_to(ROOT).as_posix(),selection.relative_to(ROOT).as_posix()],cwd=ROOT,check=True)


if __name__=='__main__':main()
