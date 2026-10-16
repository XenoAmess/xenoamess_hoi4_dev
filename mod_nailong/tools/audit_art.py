"""Verify portrait provenance, complete prompts, frozen A/B inputs and current art gate."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT,read_json,file_sha256
from PIL import Image
MOD=ROOT/'mod_nailong'

def audit():
    catalog=read_json(MOD/'data/catalog.json')
    source_sizes={a['source_sha256']:a['size'] for a in catalog['assets']}
    records=read_json(MOD/'data/generated.json')['portraits']
    failures=read_json(MOD/'data/generation-failures.json')
    blocked={a['source_sha256'] for a in failures.get('attempts',[]) if a.get('status')=='blocked' and not a.get('resolved_by_retry')}
    reference=file_sha256(MOD/'assets/reference/naiwa.png')
    approved=0
    for key,row in records.items():
        assert key in source_sizes and row['source_sha256']==key,key
        assert row['prompt'].strip() and row['reference_sha256']==reference,key
        path=ROOT/row['image']
        assert file_sha256(path)==row['image_sha256'],str(path)
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
            assert file_sha256(promptfile)==a['prompt_sha256'],str(promptfile)
            assert a['inputs'] and a['prepared_at_utc'] and a['machine_id'],str(path)
            for source in a['inputs']:
                if source.get('path'):assert file_sha256(ROOT/source['path'])==source['sha256'],str(path)
            requests+=1
    experiment=read_json(MOD/'experiments/hair-features-v1/manifest.json')
    assert len(experiment['assets'])==26 and len(experiment['jobs'])==23
    for job in experiment['jobs']:
        assert file_sha256(ROOT/job['a'])==job['a_sha256'],job['key']
        assert file_sha256(ROOT/job['b'])==job['b_sha256'],job['key']
        for a in job['attempts']:
            promptfile=ROOT/a['prompt_file']
            assert promptfile.read_bytes()==a['prompt'].encode('utf-8'),str(promptfile)
            assert file_sha256(promptfile)==a['prompt_sha256'],str(promptfile)
            if a.get('output'):assert file_sha256(ROOT/a['output'])==a['output_sha256'],str(path)
    print(f'PASS: {len(records)} canonical files, {approved} approved current-style images, {requests} complete prompt records and 26 frozen A/B resources')

if __name__=='__main__':audit()
