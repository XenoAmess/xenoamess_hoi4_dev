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
from mod_nailong.tools.ready_art_reports import reports as inbox_reports


def eligible_entries(reports,rows,latest):
    selected=[];seen=set()
    for report,body in reports:
        for entry in body.get('decisions',[]):
            key=entry.get('source_sha256');row=rows.get(key,{})
            if (entry.get('decision')!='rejected' or key in seen
                    or entry.get('generated_fullsize_sha256')!=row.get('generated_fullsize_sha256')
                    or row.get('review') not in {'pending','rejected'}
                    or latest.get(key,{}).get('status') not in {'generated_pending_visual_review','generated_rejected_visual_review','cancelled_before_generation'}):continue
            selected.append((report,entry));seen.add(key)
            if len(selected)==8:return selected
    return selected


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
        rows=read_json(ROOT/'mod_nailong/data/generated.json')['portraits'];latest={}
        for p,body in reports:
            assert body.get('machine_id')==machine_id()
            for entry in body.get('decisions',[]):
                key=entry.get('source_sha256')
                if entry.get('decision')=='rejected' and key in rows:
                    latest[key]=read_json(ROOT/rows[key]['request_journal'])['attempts'][-1]
        chosen=eligible_entries(reports,rows,latest)
        if chosen:break
        time.sleep(1)
    subprocess.run([sys.executable,'mod_nailong/tools/production_queue.py','apply-reviews'],cwd=ROOT,check=True)
    keys=[e['source_sha256'] for p,e in chosen];write_json(selection,keys)
    canvas=ROOT/f'runtime/ready-art-{batch}-canvas.json';assert not canvas.exists();write_json(canvas,{'sources':{}})
    used=list(dict.fromkeys(p for p,e in chosen))
    receipt=ROOT/f'mod_nailong/data/production-ready-refills/{batch}.json';assert not receipt.exists()
    write_json(receipt,{'machine_id':machine_id(),'claimed_at_utc':utc_now(),'source_keys':keys,'report_evidence':[{'path':p.relative_to(ROOT).as_posix(),'sha256':file_sha256(p)} for p in used],'inbox_evidence':[proof for path,proof in inbox if path in used],'scope':'Sole executor selects existing actual SHA-bound rejections immediately when a known or explicitly queued manual report is ready. Does not wait for other reports, infer art approval or change failed requests. Full canonical/raw/boundary checks remain in the preparer.'})
    subprocess.run([sys.executable,'tools/prepare_reviewed_art_repairs.py',batch,','.join(p.name for p in used),str(len(keys)),index,canvas.relative_to(ROOT).as_posix(),selection.relative_to(ROOT).as_posix()],cwd=ROOT,check=True)


if __name__=='__main__':main()
