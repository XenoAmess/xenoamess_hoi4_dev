"""Frozen inputs must retain byte validation when one shared reference is reused."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mod_nailong.tools import audit_art

class FrozenInputAuditTests(unittest.TestCase):
    def test_repeated_reference_still_rejects_conflicting_expected_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ref=root/'reference.png';ref.write_bytes(b'actual reference')
            digest=hashlib.sha256(ref.read_bytes()).hexdigest()
            with patch.object(audit_art,'ROOT',root):
                audit_art.verify_request_inputs([{'path':'reference.png','sha256':digest}],ref,digest)
                with self.assertRaises(AssertionError):
                    audit_art.verify_request_inputs([{'path':'reference.png','sha256':'0'*64}],ref,digest)

    def test_other_input_is_fully_checked_even_when_named_for_expected_digest(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ref=root/'reference.png';ref.write_bytes(b'reference')
            expected=hashlib.sha256(b'original master bytes').hexdigest()
            master=root/(expected+'.png');master.write_bytes(b'corrupted master bytes')
            with patch.object(audit_art,'ROOT',root):
                with self.assertRaises(AssertionError):
                    audit_art.verify_request_inputs([{'path':master.name,'sha256':expected}],ref,hashlib.sha256(ref.read_bytes()).hexdigest())

    def test_new_invocation_reference_digest_detects_changed_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ref=root/'reference.png';ref.write_bytes(b'old reference')
            expected=audit_art.file_sha256(ref)
            ref.write_bytes(b'changed reference')
            current=audit_art.file_sha256(ref)
            with patch.object(audit_art,'ROOT',root):
                with self.assertRaises(AssertionError):
                    audit_art.verify_request_inputs([{'path':'reference.png','sha256':expected}],ref,current)

    def test_external_resolution_requires_current_sha_and_preserves_retry_history(self):
        failure={'source_sha256':'source','status':'blocked','resolved_by_external_task':{
            'task_id':'task-1','output_sha256':'derived','fullsize_sha256':'raw',
            'original_refusal_preserved':True,'builtin_retry_count_changed':False}}
        row={'image_sha256':'derived','generated_fullsize_sha256':'raw','production_import':{'task_id':'task-1'}}
        self.assertTrue(audit_art.externally_resolved(failure,row))
        self.assertEqual(failure['status'],'blocked')
        self.assertNotIn('resolved_by_retry',failure)
        self.assertFalse(audit_art.externally_resolved(failure,{**row,'image_sha256':'superseded'}))
        self.assertFalse(audit_art.externally_resolved(failure,{**row,'production_import':{'task_id':'other'}}))
        invalid=dict(failure)
        invalid['resolved_by_external_task']={**failure['resolved_by_external_task'],'builtin_retry_count_changed':True}
        self.assertFalse(audit_art.externally_resolved(invalid,row))

    def test_duplicate_history_uses_actual_same_source_retry_resolution(self):
        attempts=[{'source_sha256':'source','status':'blocked'},
                  {'source_sha256':'source','status':'blocked','resolved_by_retry':{'output_sha256':'approved'}}]
        self.assertEqual(audit_art.unresolved_service_sources(attempts,{}),set())
        self.assertEqual(attempts[0],{'source_sha256':'source','status':'blocked'})
        self.assertEqual(audit_art.unresolved_service_sources(attempts[:1],{}),{'source'})

    def test_existing_external_import_requires_current_journal_binding(self):
        failure={'source_sha256':'source','status':'blocked'}
        row={'method':'EvoLink gpt-image-2.5-flare','image_sha256':'derived','generated_fullsize_sha256':'raw','request_journal':'journal.json','production_import':{'task_id':'task-1'}}
        journal={'attempts':[{'status':'approved','external_task_id':'task-1','fullsize_sha256':'raw','output_sha256':'derived'}]}
        with patch.object(audit_art,'read_json',return_value=journal):
            self.assertTrue(audit_art.externally_resolved(failure,row))
            self.assertFalse(audit_art.externally_resolved(failure,{**row,'image_sha256':'superseded'}))
            self.assertFalse(audit_art.externally_resolved(failure,{**row,'production_import':{'task_id':'other'}}))
        self.assertEqual(failure,{'source_sha256':'source','status':'blocked'})

    def test_legacy_external_alpha_repair_still_requires_task_and_current_sha(self):
        failure={'source_sha256':'source','status':'blocked'}
        row={'method':'EvoLink gpt-image-2.5-flare','image_sha256':'derived','generated_fullsize_sha256':'raw','request_journal':'journal.json'}
        journal={'attempts':[{'status':'approved','alpha_repair':{'generation_task_id':'task-1'},'fullsize_sha256':'raw','output_sha256':'derived'}]}
        with patch.object(audit_art,'read_json',return_value=journal):
            self.assertTrue(audit_art.externally_resolved(failure,row))
            self.assertFalse(audit_art.externally_resolved(failure,{**row,'generated_fullsize_sha256':'other'}))
            journal['attempts'][0]['alpha_repair']={}
            self.assertFalse(audit_art.externally_resolved(failure,row))

    def test_retry_then_art_correction_requires_both_sha_links(self):
        attempts=[{'source_sha256':'source','status':'blocked'}]
        row={'image_sha256':'final','request_journal':'journal.json','revision_history':[{'previous_image_sha256':'accepted'}]}
        queue={'sources':{'source':{'state':'approved_after_cooldown_retry_and_art_correction','approved_image_sha256':'final','accepted_retry_output_sha256':'accepted'}}}
        journal={'attempts':[{'status':'generated_rejected_visual_review','output_sha256':'accepted','fullsize_sha256':'raw','actual_request_verification':{'actual_recorded_before_call':True}}]}
        with patch.object(audit_art,'read_json',return_value=journal):
            self.assertEqual(audit_art.unresolved_service_sources(attempts,{'source':row},queue),set())
            self.assertEqual(audit_art.unresolved_service_sources(attempts,{'source':{**row,'image_sha256':'other'}},queue),{'source'})
            self.assertEqual(audit_art.unresolved_service_sources(attempts,{'source':{**row,'revision_history':[]}},queue),{'source'})
        self.assertEqual(attempts[0],{'source_sha256':'source','status':'blocked'})

    def test_original_converted_hash_is_checked_without_sha_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ref=root/'reference.png';source=root/'original.png'
            ref.write_bytes(b'reference');source.write_bytes(b'converted original')
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            with patch.object(audit_art,'ROOT',root):
                audit_art.verify_request_inputs([{'path':'original.png','converted_png_sha256':digest}],ref,audit_art.file_sha256(ref))
                with self.assertRaises(AssertionError):
                    audit_art.verify_request_inputs([{'path':'original.png','converted_png_sha256':'0'*64}],ref,audit_art.file_sha256(ref))
                with self.assertRaises(AssertionError):
                    audit_art.verify_request_inputs([{'path':'original.png'}],ref,audit_art.file_sha256(ref))

    def test_archived_external_request_boundary_does_not_invent_preparation_time(self):
        archived={'prepared_at_utc':None,'recovery_status':'archived_request_only_no_execution_record','generated_at_utc':'time','external_task_id':'task','external_request':'request','external_result':'result'}
        self.assertTrue(audit_art.request_time_boundary(archived))
        self.assertIsNone(archived['prepared_at_utc'])
        self.assertFalse(audit_art.request_time_boundary({**archived,'external_task_id':None}))
        self.assertFalse(audit_art.request_time_boundary({'generated_at_utc':'time'}))
        self.assertTrue(audit_art.request_time_boundary({'recovered_at_utc':'now','recording_boundary':'actual archive'}))

if __name__=='__main__':unittest.main()
