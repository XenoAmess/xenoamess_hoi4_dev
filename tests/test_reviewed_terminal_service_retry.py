"""Terminal recovery must prove the old call ended and retain lifetime limits."""
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import test_image_retries as fixtures
from tools import prepare_reviewed_terminal_service_retry as subject
from tools.common import file_sha256, read_json, write_json


class TerminalServiceRecoveryTests(unittest.TestCase):
    setUp = fixtures.ImageRetryGuards.setUp
    authorize_immediate_wait = fixtures.ImageRetryGuards.authorize_immediate_wait

    def fixture(self):
        self.authorize_immediate_wait()
        subject.image_retries.claim(self.key)
        journal=read_json(self.journal);a=journal['attempts'][-1]
        self.error=self.root/'runtime/error.txt'
        self.error.write_text(next(iter(subject.ERRORS)),encoding='utf-8')
        snapshot=self.root/'runtime/dispatch-actual/job.json'
        job=read_json(self.root/'runtime/cooldown-retry-job.json')
        job.update(source='portrait.dds',original=str(self.original))
        write_json(snapshot,job)
        inputs=[file_sha256(Path(p)) for p in job['references']]
        verification={'actual_recorded_before_call':True,'machine_id':'test-machine','input_sha256':inputs,'transparent_background':job['transparent'],'actual_request_snapshot_sha256':file_sha256(snapshot)}
        a.update(machine_id='test-machine',status='failed',error=self.error.read_text(encoding='utf-8'),actual_request_verification=verification)
        write_json(self.journal,journal)
        self.dispatch=self.root/f'runtime/production-queue/dispatch/{self.key}-002.json'
        write_json(self.dispatch,dict(verification,status='tool_error',source_sha256=self.key,attempt_number=2,actual_prompt_verified_before_call=True,prompt_sha256=a['prompt_sha256'],actual_error_file=str(self.error),actual_error_sha256=file_sha256(self.error),actual_request_snapshot_file=str(snapshot),call_returned_at_utc='2026-10-16T17:00:00+00:00'))
        proof=self.root/'runtime/manual.json';write_json(proof,{'read':True})
        write_json(self.root/'runtime/retry-scheduler/approved-pool.json',{'requests':{self.key:dict(job,policy_reviewed=True,requires_manual_policy_review=True,manual_policy_review={'complete_prompt_actually_read':True},manual_review_source='runtime/manual.json',manual_review_source_sha256=file_sha256(proof),input_sha256=inputs)}})
        self.probe=self.root/'runtime/probe.json'
        write_json(self.probe,{'machine_id':'test-machine','status':'completed','events':[{'phase':'image_resolved','error':None,'observed_at_utc':'2026-10-16T17:00:01Z'}]})
        write_json(self.root/'runtime/retry-scheduler/state.json',{'pending':None})
        write_json(self.root/'runtime/after128-continuous-plan.json',{'batches':[]})
        self.config={'machine_id':'test-machine','source_sha256':self.key,'known_terminal_reviewed':True,'failed_attempt_number':2,'consumed_retries_before':1,'failed_dispatch_sha256':file_sha256(self.dispatch),'actual_request_snapshot_sha256':file_sha256(snapshot),'later_successful_probe_receipt':'runtime/probe.json','later_successful_probe_receipt_sha256':file_sha256(self.probe)}
        self.machine=patch.object(subject,'machine_id',return_value='test-machine');self.machine.start();self.addCleanup(self.machine.stop)
        self.proof_machine=patch('tools.retry_actual_proof.machine_id',return_value='test-machine');self.proof_machine.start();self.addCleanup(self.proof_machine.stop)

    def assert_no_mutation(self):
        paths=[self.journal,subject.image_retries.QUEUE,self.root/'runtime/after128-continuous-plan.json']
        before=[p.read_bytes() for p in paths]
        with self.assertRaises((AssertionError,SystemExit)):
            subject.prepare(self.root,'test-recovery',0,self.config)
        self.assertEqual(before,[p.read_bytes() for p in paths])

    def test_exact_recovery_consumes_one_allowance_and_never_replays(self):
        self.fixture();old=read_json(self.journal)['attempts'][-1]
        subject.prepare(self.root,'test-recovery',0,self.config)
        journal=read_json(self.journal);new=journal['attempts'][-1]
        self.assertEqual(new['terminal_service_transport_retry_of_attempt'],2)
        self.assertEqual(new['cooldown_retry_number'],2)
        self.assertEqual(new['prompt'],old['prompt']);self.assertEqual(new['inputs'],old['inputs'])
        self.assertEqual(read_json(subject.image_retries.QUEUE)['sources'][self.key]['retries_used'],2)
        self.assertEqual(read_json(self.root/'runtime/production-test-recovery-jobs.json')[0]['prompt'],old['prompt'])
        self.assert_no_mutation()

    def test_no_later_success_blocks_without_consuming(self):
        self.fixture();probe=read_json(self.probe);probe['events'][0]['observed_at_utc']='2026-10-16T17:00:00Z';write_json(self.probe,probe)
        self.config['later_successful_probe_receipt_sha256']=file_sha256(self.probe)
        self.assert_no_mutation()

    def test_altered_input_blocks_without_consuming(self):
        self.fixture();self.reference.write_bytes(b'changed');self.assert_no_mutation()

    def test_calling_ledger_blocks_without_consuming(self):
        self.fixture();ledger=read_json(self.dispatch);ledger['status']='calling';write_json(self.dispatch,ledger)
        self.config['failed_dispatch_sha256']=file_sha256(self.dispatch);self.assert_no_mutation()

    def test_exhausted_lifetime_allowance_blocks(self):
        self.fixture();queue=read_json(subject.image_retries.QUEUE);queue['sources'][self.key]['retries_used']=8;write_json(subject.image_retries.QUEUE,queue)
        self.config['consumed_retries_before']=8;self.assert_no_mutation()

    def test_moderation_receipt_is_not_a_terminal_network_error(self):
        self.fixture();journal=read_json(self.journal);journal['attempts'][-1]['error']='moderation_blocked';write_json(self.journal,journal);self.assert_no_mutation()

    def test_retained_review_alias_is_explicit_and_conflicts_stay_held(self):
        self.fixture();path=self.root/'runtime/retry-scheduler/approved-pool.json';pool=read_json(path)
        flags=pool['requests'][self.key]['manual_policy_review'];flags.clear();flags['complete_prompt_read']=True;write_json(path,pool)
        subject.validate(self.root,self.config)
        flags['complete_prompt_actually_read']=False;write_json(path,pool);self.assert_no_mutation()


if __name__=='__main__':unittest.main()
