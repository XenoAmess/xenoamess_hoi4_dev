"""Resumable small art ZIP uploads, with full authenticated/anonymous readback."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import quote

from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json
from mod_nailong.tools.master_archive import MOD, INDEX, REPO, BLOCK, StoredZip, inventory

PART_BYTES = 32 * 1024 * 1024


def partition(masters, limit=PART_BYTES):
    groups, group, size = [], [], 0
    for item in sorted(masters, key=lambda item: item['sha256']):
        if group and size + item['bytes'] > limit:
            groups.append(group); group, size = [], 0
        group.append(item); size += item['bytes']
    if group: groups.append(group)
    return groups


def frozen_plan(tag, previous):
    directory = ROOT/'runtime/archive-plans'/tag
    path = directory/'plan.json'
    if path.exists():
        return read_json(path)
    snap = inventory()
    if snap['current_masters_missing'] or snap['historical_fullsize_sha_missing']:
        raise ValueError('Missing recorded HD PNG; no lower-resolution substitution allowed')
    selected = [item for item in snap['masters'] if item['sha256'] not in previous['outputs']]
    if not selected: raise ValueError('No unarchived masters')
    groups = partition(selected)
    base = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    # Freeze prompt snapshots for returned outputs, including superseded ones.
    prompts = {}
    for file in (MOD/'data/generation-requests').glob('*.json'):
        for attempt in read_json(file)['attempts']:
            if attempt.get('fullsize_sha256'):
                prompts[attempt['fullsize_sha256']] = {'prompt': attempt['prompt'], 'prompt_sha256': attempt.get('prompt_sha256'), 'inputs': attempt['inputs'], 'attempt_number': attempt['number']}
    rows = read_json(MOD/'data/generated.json')['portraits']
    for row in rows.values():
        prompts.setdefault(row['generated_fullsize_sha256'], {'prompt': row['prompt']})
        for revision in row.get('revision_history', []):
            if revision.get('previous_fullsize_sha256') and revision.get('previous_prompt'):
                prompts.setdefault(revision['previous_fullsize_sha256'], {'prompt': revision['previous_prompt']})
    plan = {'schema': 'naiwa-art-archive-plan-v2', 'tag': tag, 'machine_id': machine_id(), 'frozen_at_utc': utc_now(), 'repository_base_commit': base, 'snapshot_scope': 'PNG and prompt snapshots independently frozen; base commit does not assert later working-tree reviews', 'png_count': len(selected), 'png_bytes': sum(item['bytes'] for item in selected), 'parts': []}
    for i, group in enumerate(groups, 1):
        name = f'{tag}-part-{i:03}.zip'
        manifest = {'schema': 'naiwa-fullsize-pack-v2', 'tag': tag, 'part': i, 'parts_total': len(groups), 'machine_id': plan['machine_id'], 'frozen_at_utc': plan['frozen_at_utc'], 'repository_base_commit': base, 'snapshot_scope': plan['snapshot_scope'], 'outputs': [dict({k: v for k, v in item.items() if k != 'path'}, **({'generation_request_snapshot': prompts[item['sha256']]} if item['sha256'] in prompts else {})) for item in group]}
        manifest_path = directory/f'part-{i:03}.json'
        write_json(manifest_path, manifest)
        plan['parts'].append({'name': name, 'manifest': manifest_path.relative_to(ROOT).as_posix(), 'masters': group})
    write_json(path, plan)
    return plan


def publish(tag):
    if not re.fullmatch(r'art-masters-[0-9]{3}', tag):
        raise ValueError('Use art-masters-NNN, distinct from a mod release')
    lock = ROOT/'runtime/fullsize-archive.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, json.dumps({'machine_id': machine_id(), 'pid': os.getpid(), 'tag': tag, 'started_at_utc': utc_now()}).encode())
        _publish(tag)
    finally:
        os.close(fd); lock.unlink()


def _publish(tag):
    import requests
    previous = read_json(INDEX) if INDEX.exists() else {'schema': 'naiwa-fullsize-archives-v2', 'archives': [], 'outputs': {}}
    if any(item['tag'] == tag for item in previous['archives']):
        raise ValueError('Archive already registered; new outputs need the next tag')
    plan = frozen_plan(tag, previous)
    token = subprocess.check_output(['gh', 'auth', 'token'], text=True).strip()
    api = 'https://api.github.com/repos/' + REPO

    def client():
        session = requests.Session()
        session.headers.update(Authorization='Bearer '+token, Accept='application/vnd.github+json', **{'X-GitHub-Api-Version': '2022-11-28'})
        return session

    session = client()
    # Draft tags need not yet exist as refs: enumerate the owner's releases.
    candidates, page = [], 1
    while True:
        response = session.get(api+'/releases', params={'per_page':100, 'page':page}, timeout=(30,60)); response.raise_for_status()
        listing = response.json(); candidates.extend(item for item in listing if item['tag_name'] == tag)
        if len(listing) < 100: break
        page += 1
    if len(candidates) > 1: raise ValueError('Multiple drafts for tag; inspect before resuming')
    if candidates:
        release = candidates[0]
    else:
        response = session.post(api+'/releases', json={'tag_name':tag, 'target_commitish':plan['repository_base_commit'], 'name':'Generated portrait masters '+tag[-3:], 'body':'Development art archive; original full-size imagegen PNG bytes, including superseded experiments and images pending visual review. This is not a playable mod release. Each independently readable ZIP part contains its own SHA/provenance index and frozen prompt snapshots where available. All parts are fully downloaded and SHA-verified before registration.', 'draft':True, 'prerelease':True}, timeout=(30,60)); response.raise_for_status(); release=response.json()
    response=session.get(api+f'/releases/{release["id"]}/assets', params={'per_page':100}, timeout=(30,60)); response.raise_for_status()
    assets={item['name']:item for item in response.json()}
    # Only remove the exact empty, incomplete asset left by our failed initial
    # monolithic upload. Never remove an uploaded or unrelated attachment.
    old=assets.get(tag+'.zip')
    if old and release['draft'] and old['state']=='starter' and old['size']==0:
        response=session.delete(old['url'], timeout=(30,60)); response.raise_for_status()
        write_json(ROOT/'runtime/archive-plans'/tag/'aborted-monolithic-upload.json', {'machine_id':machine_id(),'observed_at_utc':utc_now(),'asset_id':old['id'],'name':old['name'],'state':old['state'],'bytes':0,'result':'Removed exact empty starter left by failed proxy upload; no source PNG deleted'})
    print(f'Archiving {plan["png_count"]} PNGs in {len(plan["parts"])} parts; 4 bounded file-transfer workers, image generation remains single-lane', flush=True)

    def make_stream(part):
        body=(ROOT/part['manifest']).read_bytes()
        entries=[('index.json',body,hashlib.sha256(body).hexdigest())]+[('png/'+item['sha256']+'.png',Path(item['path']),item['sha256']) for item in part['masters']]
        stream=StoredZip(entries)
        for _ in stream: pass
        return stream,stream.sha256,hashlib.sha256(body).hexdigest()

    def verify(session, url, size, expected, headers=None):
        digest,count=hashlib.sha256(),0
        with session.get(url,headers=headers,stream=True,timeout=(30,120)) as response:
            response.raise_for_status()
            for chunk in response.iter_content(BLOCK): digest.update(chunk);count+=len(chunk)
        if count!=size or digest.hexdigest()!=expected: raise ValueError('Remote ZIP bytes or SHA mismatch')

    def upload(part):
        stream,expected,manifest_sha=make_stream(part)
        saved=ROOT/'runtime/archive-plans'/tag/(part['name']+'.verified.json')
        with client() as connection:
            asset=assets.get(part['name'])
            if asset and asset['state']=='starter' and asset['size']==0 and release['draft']:
                response=connection.delete(asset['url'],timeout=(30,60));response.raise_for_status();asset=None
            if asset is None:
                url=release['upload_url'].split('{')[0]+'?name='+quote(part['name'])
                response=connection.post(url,data=stream,headers={'Content-Type':'application/zip','Content-Length':str(len(stream))},timeout=(30,120));response.raise_for_status();asset=response.json()
            if asset['size']!=len(stream): raise ValueError('Existing ZIP differs; refusing replacement')
            if saved.exists():
                old=read_json(saved)
                if old['asset_id']==asset['id'] and old['archive_sha256']==expected and old['archive_bytes']==len(stream) and asset.get('digest')=='sha256:'+expected:
                    old['download_url']=asset['browser_download_url']
                    print('Resumed verified immutable asset: '+part['name'],flush=True)
                    return old
            verify(connection,asset['url'],len(stream),expected,{'Accept':'application/octet-stream'})
        receipt={'name':part['name'],'asset_id':asset['id'],'download_url':asset['browser_download_url'],'archive_bytes':len(stream),'archive_sha256':expected,'manifest_sha256':manifest_sha,'png_count':len(part['masters']),'authenticated_verified_at_utc':utc_now()}
        write_json(ROOT/'runtime/archive-plans'/tag/(part['name']+'.verified.json'),receipt)
        print('Uploaded and authenticated SHA verified: '+part['name'],flush=True)
        return receipt

    uploaded=[]
    with ThreadPoolExecutor(max_workers=4) as executor:
        for future in as_completed([executor.submit(upload,part) for part in plan['parts']]):uploaded.append(future.result())
    uploaded.sort(key=lambda item:item['name'])
    body='Development art archive: **'+str(plan['png_count'])+' original full-size PNG outputs**. Includes superseded experiments and images pending review; this is not a playable mod release. Each ZIP part is independent and contains a SHA/provenance index with prompt snapshots where available.\n\n'+'\n'.join('- `'+item['name']+'` SHA-256 `'+item['archive_sha256']+'`' for item in uploaded)
    response=session.patch(api+f'/releases/{release["id"]}',json={'draft':False,'prerelease':True,'make_latest':'false','body':body},timeout=(30,60));response.raise_for_status();release=response.json()
    # Draft browser URLs can contain an untagged-* placeholder. Resolve the
    # actual public asset URLs after publication; never persist those placeholders.
    public_assets={item['id']:item for item in release['assets']}
    for item in uploaded:
        actual=public_assets[item['asset_id']]
        if actual['size']!=item['archive_bytes']: raise ValueError('Published asset changed in size')
        item['download_url']=actual['browser_download_url']

    def anonymous_check(item):
        path=ROOT/'runtime/archive-plans'/tag/(item['name']+'.anonymous-verified.json')
        if path.exists():
            old=read_json(path)
            if all(old[field]==item[field] for field in ('asset_id','archive_bytes','archive_sha256')):
                old['download_url']=item['download_url']
                print('Resumed completed anonymous readback: '+item['name'],flush=True)
                return old
        for attempt in range(3):
            try:
                with requests.Session() as anonymous: verify(anonymous,item['download_url'],item['archive_bytes'],item['archive_sha256'])
                break
            except requests.exceptions.RequestException as error:
                write_json(ROOT/'runtime/archive-plans'/tag/(item['name']+f'.download-error-{attempt+1}.json'),{'machine_id':machine_id(),'observed_at_utc':utc_now(),'asset_id':item['asset_id'],'operation':'Idempotent anonymous GitHub asset GET; never an imagegen retry','error':str(error)})
                if attempt==2: raise
                print('Transient download failed; retrying this ZIP only: '+item['name'],flush=True)
                time.sleep(2**(attempt+1))
        item['anonymous_verified_at_utc']=utc_now()
        write_json(path,item)
        print('Anonymous SHA verified: '+item['name'],flush=True)
        return item

    with ThreadPoolExecutor(max_workers=4) as executor:
        verified=list(executor.map(anonymous_check,uploaded))
    receipt={'tag':tag,'release_url':release['html_url'],'png_count':plan['png_count'],'png_bytes':plan['png_bytes'],'parts':verified,'repository_base_commit':plan['repository_base_commit'],'snapshot_scope':plan['snapshot_scope'],'machine_id':machine_id(),'verified_at_utc':utc_now(),'verification':'Every complete ZIP part downloaded through authenticated and anonymous channels, exact size and SHA256','local_archive_copy_created':False}
    previous['schema']='naiwa-fullsize-archives-v2';previous['archives'].append(receipt)
    for part in plan['parts']:
        for item in part['masters']:
            previous['outputs'][item['sha256']]={'archive_tag':tag,'asset_name':part['name'],'entry':'png/'+item['sha256']+'.png','bytes':item['bytes'],'size':item['size']}
    write_json(INDEX,previous);write_json(ROOT/'runtime'/(tag+'-verification.json'),receipt)
    print(json.dumps({'tag':tag,'png_count':plan['png_count'],'parts':len(verified),'release_url':release['html_url'],'verified_at_utc':receipt['verified_at_utc']}),flush=True)
