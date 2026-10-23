"""Fully read back original PNG files from a pinned public Git commit."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import hashlib
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import requests
from tools.common import ROOT, machine_id, read_json, utc_now, write_json
from mod_nailong.tools.master_files import verify_tree

REPO='XenoAmess/xenoamess_hoi4_dev'
CHECKPOINT=ROOT/'mod_nailong/data/fullsize-git-checkpoint.json'


def verify_remote(commit='HEAD'):
    # Bind the proof entirely to immutable committed metadata. New generation
    # imports may continue while these older committed PNGs are downloaded.
    commit=subprocess.check_output(['git','rev-parse',commit+'^{commit}'],cwd=ROOT,text=True).strip()
    def committed_json(path):
        return __import__('json').loads(subprocess.check_output(['git','show',commit+':'+path],cwd=ROOT,text=True,encoding='utf-8'))
    index=committed_json('mod_nailong/data/fullsize-files.json')
    commit,blobs=verify_tree(commit,index=index)
    current=committed_json('mod_nailong/data/generated.json')['portraits']
    if any(row['generated_fullsize_sha256'] not in index['outputs'] for row in current.values()):
        raise ValueError('A current master is absent from the pinned index')
    current_count=len(current)
    api=json_api('repos/'+REPO+'/git/trees/'+commit+'?recursive=1')
    if api.get('truncated'):
        raise ValueError('Remote Git tree is truncated')
    tree={e['path']:e for e in api['tree']}
    for digest,entry in index['outputs'].items():
        remote=tree.get(entry['path'],{})
        if remote.get('type')!='blob' or remote.get('sha')!=blobs[digest] or remote.get('size')!=entry['bytes']:
            raise ValueError('Remote tree differs from verified local Git blob: '+entry['path'])
    receipt_path=ROOT/'runtime/fullsize-git-readbacks'/ (commit+'.json')
    receipt=read_json(receipt_path) if receipt_path.exists() else {'machine_id':machine_id(),'commit':commit,'outputs':{}}
    if receipt['machine_id']!=machine_id() or receipt['commit']!=commit:
        raise ValueError('Readback receipt belongs to another machine or commit')
    # Content-addressed Git blobs are immutable. Reuse a prior complete byte
    # readback only after the new remote tree proves the exact same blob/path/size.
    # Preserve the actual earlier download time and commit instead of renewing it.
    reused=0
    previous=read_json(CHECKPOINT) if CHECKPOINT.exists() else {}
    if previous.get('machine_id')==machine_id():
        for digest,entry in index['outputs'].items():
            old=previous.get('outputs',{}).get(digest,{})
            if (digest not in receipt['outputs'] and old.get('sha256')==digest
                    and old.get('git_blob_sha1')==blobs[digest]
                    and old.get('path')==entry['path'] and old.get('bytes')==entry['bytes']
                    and old.get('method')=='Complete anonymous raw PNG download; SHA256 and byte count'):
                receipt['outputs'][digest]={**old,'unchanged_blob_confirmed_at_commit':commit}
                reused+=1

    def download(pair):
        digest,entry=pair
        url='https://raw.githubusercontent.com/'+REPO+'/'+commit+'/'+entry['path']
        for attempt in range(3):
            try:
                sha=hashlib.sha256();size=0
                with requests.get(url,stream=True,timeout=(30,120)) as response:
                    response.raise_for_status()
                    for block in response.iter_content(1024*1024):
                        sha.update(block);size+=len(block)
                if size!=entry['bytes'] or sha.hexdigest()!=digest:
                    raise ValueError('Remote original PNG byte mismatch: '+entry['path'])
                return digest, {'path':entry['path'],'bytes':size,'sha256':digest,'git_blob_sha1':blobs[digest],
                                'url':url,'readback_commit':commit,'verified_at_utc':utc_now(),'method':'Complete anonymous raw PNG download; SHA256 and byte count'}
            except requests.RequestException:
                if attempt==2:raise
                time.sleep(2**attempt)
    pending=[pair for pair in sorted(index['outputs'].items()) if not (
        receipt['outputs'].get(pair[0],{}).get('git_blob_sha1')==blobs[pair[0]]
        and receipt['outputs'][pair[0]].get('bytes')==pair[1]['bytes'])]
    completed=len(index['outputs'])-len(pending)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(download,pair) for pair in pending]):
            digest,value=future.result()
            receipt['outputs'][digest]=value
            write_json(receipt_path,receipt)
            completed+=1
            if completed%25==0 or completed==index['count']:
                print(f'Full raw PNG readbacks: {completed}/{index["count"]}',flush=True)
    # A fully reused commit has no download completion callbacks. Persist its
    # exact pinned proof too, before the global pointer can move to a newer one.
    write_json(receipt_path,receipt)
    final={'schema':'naiwa-fullsize-git-checkpoint-v1','machine_id':machine_id(),'observed_at_utc':utc_now(),
           'repository':REPO,'commit':commit,'storage':'ordinary Git PNG files; no LFS or Release attachments',
           'verification':'Remote Git tree blob SHA/size match plus complete anonymous raw PNG download SHA256/size for every output; unchanged blobs may retain their earlier pinned readback commit/time',
           'earlier_complete_readbacks_reused_after_remote_blob_match':reused,
           'distinct_outputs':index['count'],'original_png_bytes':index['original_png_bytes'],
           'current_sources':current_count,
           'outputs':dict(sorted(receipt['outputs'].items())),
           'scope':'This pinned commit only; later generated outputs require another sync, commit, push and readback',
           'review_at_utc':(datetime.now(timezone.utc)+timedelta(days=7)).isoformat()}
    write_json(CHECKPOINT,final)
    print({'remote_originals_verified':index['count'],'bytes':index['original_png_bytes'],'commit':commit},flush=True)
    return final


def json_api(endpoint):
    # This is an idempotent metadata read. A truncated transport or TLS timeout
    # must not invalidate a completed push or become an image-service retry.
    transient=('tls handshake timeout','unexpected end of json input',
               'connection reset','connection was reset','unexpected eof',
               'i/o timeout','connection timed out')
    for attempt in range(3):
        try:
            raw=subprocess.check_output(['gh','api',endpoint],cwd=ROOT,text=True,
                                        encoding='utf-8',stderr=subprocess.PIPE,timeout=180)
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as error:
            detail=error.stderr or ''
            if isinstance(detail,bytes):detail=detail.decode('utf-8',errors='replace')
            retryable=isinstance(error,subprocess.TimeoutExpired) or any(t in detail.lower() for t in transient)
            if not retryable or attempt==2:raise
            print(f'Remote Git metadata transport interrupted; bounded read retry {attempt+1}/2',flush=True)
            time.sleep((2,5)[attempt])
        else:
            # A successful command with invalid JSON is not guessed to be a
            # transient network error; parsing/authorization failures surface.
            return __import__('json').loads(raw)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit',default='HEAD')
    verify_remote(parser.parse_args().commit)
