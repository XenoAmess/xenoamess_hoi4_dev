"""Prevent duplicate calls, stale approvals and import/review lost updates."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from tools.common import file_sha256, read_json, write_json
from mod_nailong.tools import portraits, production_queue as queue


class ProductionQueueTests(unittest.TestCase):
    def test_unicode_transport_is_lossless_and_corrupted_prompt_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            root=Path(temp)
            mod,image,digest,evidence,job=self.fixture(root,stack)
            prompt='Use the exact 奶龙 identity reference.\n'
            (root/'prompt.txt').write_text(prompt,encoding='utf-8')
            journal=mod/f'data/generation-requests/{job["key"]}.json'
            data=read_json(journal);data['attempts'][0].update(prompt=prompt,prompt_sha256=file_sha256(root/'prompt.txt'));write_json(journal,data)
            job['prompt']=prompt
            jobs=root/'jobs.json';write_json(jobs,[job])
            broken=json.loads(json.dumps(job,ensure_ascii=False).encode('cp936').decode('utf-8',errors='replace'))
            with self.assertRaisesRegex(ValueError,'Frozen prompt changed'):queue.begin(broken)
            self.assertFalse(list((queue.control()/'dispatch').glob('*.json')))
            exported=queue.export_job(jobs,job['key'])
            transported=json.loads(exported.encode('cp936').decode('utf-8'))
            self.assertEqual(transported['prompt'],prompt)
            actual=root/'actual-request.json';write_json(actual,transported)
            dispatch=queue.begin(transported,actual)
            self.assertTrue(read_json(dispatch)['actual_prompt_verified_before_call'])

    def fixture(self, root, stack):
        mod = root / 'mod_nailong'
        for module, name, value in [(queue, 'ROOT', root), (portraits, 'ROOT', root), (portraits, 'MOD', mod), (portraits, 'RECORD', mod/'data/generated.json')]:
            stack.enter_context(patch.object(module, name, value))
        image = root/'portrait.png'; Image.new('RGBA', (3, 3), 'gold').save(image)
        digest = file_sha256(image)
        prompt = root/'prompt.txt'; prompt.write_text('Exact frozen prompt', encoding='utf-8')
        rows = {}
        for key in ['a'*64, 'b'*64]:
            rows[key] = {'image': 'portrait.png', 'image_sha256': digest, 'review': 'pending', 'art_direction': 'hair-features-v1', 'request_journal': f'mod_nailong/data/generation-requests/{key}.json'}
            write_json(mod/f'data/generation-requests/{key}.json', {'attempts': [{'number': 1, 'status': 'prepared', 'prompt': prompt.read_text(), 'prompt_file': 'prompt.txt', 'prompt_sha256': file_sha256(prompt), 'inputs': [{'sha256': digest}], 'output_sha256': digest}]})
        write_json(mod/'data/generated.json', {'portraits': rows})
        write_json(mod/'data/generation-failures.json', {'attempts': []})
        write_json(mod/'data/image-retry-queue.json', {'sources': {}})
        evidence = root/'review.json'
        write_json(evidence, {'pages': [{'path': str(image), 'sha256': digest, 'entries': [{'source_sha256': key, 'image_sha256': digest} for key in rows]}]})
        job = {'key': 'a'*64, 'prompt': prompt.read_text(), 'references': [str(image)]}
        return mod, image, digest, evidence, job

    def test_unknown_call_outcome_blocks_next_call_and_duplicate_claim(self):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            mod, image, digest, evidence, job = self.fixture(Path(temp), stack)
            queue.begin(job)
            with self.assertRaisesRegex(ValueError, 'already claimed'):
                queue.begin(job)
            with self.assertRaisesRegex(ValueError, 'unknown outcome'):
                queue.begin(dict(job, key='b'*64))
            queue.returned(job['key'], image=image)
            queue.begin(dict(job, key='b'*64))

    def test_staged_approval_preserves_a_later_import(self):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            mod, image, digest, evidence, job = self.fixture(Path(temp), stack)
            queue.stage_review(job['key'], digest, 'approved', evidence)
            data = read_json(mod/'data/generated.json')
            data['portraits']['new-import'] = {'sentinel': 'imported while reviewer worked'}
            write_json(mod/'data/generated.json', data)
            self.assertEqual(queue.apply_reviews(), {'applied': 1, 'stale_not_applied': 0})
            result = read_json(mod/'data/generated.json')['portraits']
            self.assertEqual(result['new-import']['sentinel'], 'imported while reviewer worked')
            self.assertEqual(result[job['key']]['collar_fit']['image_sha256'], digest)

    def test_approval_for_old_attempt_does_not_approve_new_attempt(self):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            mod, image, digest, evidence, job = self.fixture(Path(temp), stack)
            queue.stage_review(job['key'], digest, 'approved', evidence)
            journal = mod/f'data/generation-requests/{job["key"]}.json'
            data = read_json(journal); data['attempts'][-1]['number'] = 2; write_json(journal, data)
            self.assertEqual(queue.apply_reviews(), {'applied': 0, 'stale_not_applied': 1})
            self.assertEqual(read_json(mod/'data/generated.json')['portraits'][job['key']]['review'], 'pending')

    def test_identical_retry_payloads_have_distinct_dispatch_identities(self):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            root=Path(temp);mod,image,digest,evidence,job=self.fixture(root,stack)
            first=root/'first-call.json';second=root/'second-call.json';write_json(first,job);write_json(second,job)
            self.assertEqual(file_sha256(first),file_sha256(second))
            queue.begin(job,first);queue.returned(job['key'],image=image)
            journal=mod/f'data/generation-requests/{job["key"]}.json'
            history=read_json(journal);old=history['attempts'][0];old['status']='failed'
            fresh={k:v for k,v in old.items() if k!='actual_request_verification'};fresh.update(number=2,status='prepared')
            history['attempts'].append(fresh);write_json(journal,history)
            queue.begin(job,second)
            self.assertEqual(queue.attempt_for_snapshot(job['key'],first)['number'],1)
            self.assertEqual(queue.attempt_for_snapshot(job['key'],second)['number'],2)
            unclaimed=root/'unclaimed-copy.json';write_json(unclaimed,job)
            with self.assertRaisesRegex(ValueError,'uniquely dispatched'):queue.attempt_for_snapshot(job['key'],unclaimed)
            second.write_bytes(b'changed request bytes')
            with self.assertRaisesRegex(ValueError,'snapshot bytes changed'):queue.attempt_for_snapshot(job['key'],second)

    def test_independent_manual_approvals_share_one_update_and_preserve_other_imports(self):
        with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
            root=Path(temp);mod,image,digest,evidence,job=self.fixture(root,stack)
            keys=['a'*64,'b'*64]
            for key in keys:queue.stage_review(key,digest,'approved',evidence)
            rows=read_json(mod/'data/generated.json');rows['portraits']['later-import']={'sentinel':'preserved'};write_json(mod/'data/generated.json',rows)
            with patch.object(portraits,'approve',wraps=portraits.approve) as approval:
                self.assertEqual(queue.apply_reviews(),{'applied':2,'stale_not_applied':0})
                approval.assert_called_once_with(keys)
            result=read_json(mod/'data/generated.json')['portraits']
            self.assertEqual(result['later-import'],{'sentinel':'preserved'})
            self.assertTrue(all(result[key]['review']=='approved' for key in keys))

    def test_failed_group_update_does_not_consume_queued_decisions(self):
        with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
            root=Path(temp);mod,image,digest,evidence,job=self.fixture(root,stack)
            for key in ['a'*64,'b'*64]:queue.stage_review(key,digest,'approved',evidence)
            with patch.object(portraits,'approve',side_effect=OSError('fixture write failure')):
                with self.assertRaises(OSError):queue.apply_reviews()
            self.assertEqual(len(list((queue.control()/'reviews/pending').glob('*.json'))),2)
            self.assertEqual(len(list((queue.control()/'reviews/completed').glob('*.json'))),0)

    def hd_evidence(self,root,mod,evidence,key):
        master=root/'master.png';Image.new('RGBA',(20,30),'blue').save(master);digest=file_sha256(master)
        rows=read_json(mod/'data/generated.json');rows['portraits'][key].update(generated_fullsize_image='master.png',generated_fullsize_sha256=digest);write_json(mod/'data/generated.json',rows)
        journal=mod/f'data/generation-requests/{key}.json';history=read_json(journal);history['attempts'][-1]['fullsize_sha256']=digest;write_json(journal,history)
        data=read_json(evidence)
        for page in data['pages']:
            for entry in page['entries']:
                if entry['source_sha256']==key:entry.update(generated_fullsize_sha256=digest,attempt_number=1)
        write_json(evidence,data);return master

    def test_hd_review_rejects_a_different_master_with_same_preview(self):
        with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
            root=Path(temp);mod,image,digest,evidence,job=self.fixture(root,stack)
            master=self.hd_evidence(root,mod,evidence,job['key']);Image.new('RGBA',(20,30),'red').save(master)
            with self.assertRaisesRegex(ValueError,'fullsize image changed'):queue.stage_review(job['key'],digest,'approved',evidence)

    def test_staged_hd_review_cannot_approve_master_tampering(self):
        with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
            root=Path(temp);mod,image,digest,evidence,job=self.fixture(root,stack)
            master=self.hd_evidence(root,mod,evidence,job['key'])
            queue.stage_review(job['key'],digest,'approved',evidence);Image.new('RGBA',(20,30),'red').save(master)
            self.assertEqual(queue.apply_reviews(),{'applied':0,'stale_not_applied':1})
            self.assertEqual(read_json(mod/'data/generated.json')['portraits'][job['key']]['review'],'pending')

    def test_changed_master_is_excluded_from_other_valid_grouped_approvals(self):
        with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
            root=Path(temp);mod,image,digest,evidence,job=self.fixture(root,stack)
            master=self.hd_evidence(root,mod,evidence,job['key'])
            for key in ['a'*64,'b'*64]:queue.stage_review(key,digest,'approved',evidence)
            Image.new('RGBA',(20,30),'red').save(master)
            with patch.object(portraits,'approve',wraps=portraits.approve) as approval:
                self.assertEqual(queue.apply_reviews(),{'applied':1,'stale_not_applied':1})
                approval.assert_called_once_with(['b'*64])
            rows=read_json(mod/'data/generated.json')['portraits']
            self.assertEqual(rows['a'*64]['review'],'pending');self.assertEqual(rows['b'*64]['review'],'approved')


if __name__ == '__main__':
    unittest.main()
