"""Verify portrait provenance, complete prompts, frozen A/B inputs and current art gate."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT,read_json,file_sha256
from PIL import Image
MOD=ROOT/'mod_nailong'

def verify_request_inputs(inputs, reference_path, reference_digest, hasher=None):
    """Verify every expected hash against bytes read in this audit invocation.

    The shared reference was fully read immediately before the portrait loop.
    Its digest is an invocation-local snapshot, never a persisted/mtime cache.
    Other paths retain a complete byte read, even if their names imply a hash.
    A supplied checkpoint verifier may reuse bytes fully read earlier in that
    same process only after rechecking the unchanged file version. It has no
    persisted cache and never substitutes a previous checkpoint's digest.
    """
    for source in inputs:
        if source.get('path'):
            path=ROOT/source['path']
            actual=hasher(path) if hasher else reference_digest if path==reference_path else file_sha256(path)
            assert actual==source['sha256'],str(path)

def audit(hasher=None):
    hash_file=hasher or file_sha256
    catalog=read_json(MOD/'data/catalog.json')
    source_sizes={a['source_sha256']:a['size'] for a in catalog['assets']}
    records=read_json(MOD/'data/generated.json')['portraits']
    failures=read_json(MOD/'data/generation-failures.json')
    blocked={a['source_sha256'] for a in failures.get('attempts',[]) if a.get('status')=='blocked' and not a.get('resolved_by_retry')}
    reference_path=MOD/'assets/reference/naiwa.png'
    reference=hash_file(reference_path)
    approved=0
    for key,row in records.items():
        assert key in source_sizes and row['source_sha256']==key,key
        assert row['prompt'].strip() and row['reference_sha256']==reference,key
        path=ROOT/row['image']
        assert hash_file(path)==row['image_sha256'],str(path)
        with Image.open(path) as im:assert list(im.size)==source_sizes[key],key
        if row['review']=='approved':
            from mod_nailong.tools.art_contract import portrait_ready
            assert portrait_ready(row),'Missing/current-image-mismatched collar review: '+key
            assert row.get('art_direction')=='hair-features-v1',key
            assert key not in blocked,key
            approved+=1
            if row.get('request_journal'):
                a=read_json(ROOT/row['request_journal'])['attempts'][-1]
                assert a['status']=='approved' and a['output_sha256']==row['image_sha256'],key
        for old in row.get('revision_history',[]):assert old.get('previous_prompt',old.get('initial_prompt','')).strip(),key
    requests=0
    for path in sorted((MOD/'data/generation-requests').glob('*.json')):
        journal=read_json(path)
        for a in journal['attempts']:
            promptfile=ROOT/a['prompt_file']
            assert promptfile.read_bytes()==a['prompt'].encode('utf-8'),str(promptfile)
            assert hash_file(promptfile)==a['prompt_sha256'],str(promptfile)
            if a.get('intended_prompt_file'):
                intended=ROOT/a['intended_prompt_file']
                assert intended.read_bytes()==a['intended_prompt'].encode('utf-8'),str(intended)
                assert hash_file(intended)==a['intended_prompt_sha256'],str(intended)
            assert a['inputs'] and a['machine_id'],str(path)
            assert a['prepared_at_utc'] or (a.get('recovered_at_utc') and a.get('recording_boundary')),str(path)
            verify_request_inputs(a['inputs'],reference_path,reference,hasher=hasher)
            requests+=1
    experiment=read_json(MOD/'experiments/hair-features-v1/manifest.json')
    assert len(experiment['assets'])==26 and len(experiment['jobs'])==23
    for job in experiment['jobs']:
        assert hash_file(ROOT/job['a'])==job['a_sha256'],job['key']
        assert hash_file(ROOT/job['b'])==job['b_sha256'],job['key']
        for a in job['attempts']:
            promptfile=ROOT/a['prompt_file']
            assert promptfile.read_bytes()==a['prompt'].encode('utf-8'),str(promptfile)
            assert hash_file(promptfile)==a['prompt_sha256'],str(promptfile)
            if a.get('output'):assert hash_file(ROOT/a['output'])==a['output_sha256'],str(path)
    print(f'PASS: {len(records)} canonical files, {approved} approved current-style images, {requests} complete prompt records and 26 frozen A/B resources')
    from mod_nailong.tools.master_files import audit_files, master_path
    masters=audit_files(hasher=hasher) if hasher else audit_files()
    for row in records.values():
        assert row['generated_fullsize_image']==master_path(row['generated_fullsize_sha256'])
    print(f'HD files: {masters["count"]} original PNGs present with matching SHA/size, including history and experiments; {len(records)} current masters. Remote Git verification and art qualification are separate.')
    recovered=sum(bool(a.get('prompt_transport_correction')) for path in (MOD/'data/generation-requests').glob('*.json') for a in read_json(path)['attempts'])
    if recovered:print(f'Prompt recording boundary: {recovered} actual prompts recovered after a transport mismatch; intended pre-call files and correction evidence retained.')

if __name__=='__main__':audit()
