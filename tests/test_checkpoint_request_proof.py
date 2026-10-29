import copy
import unittest
from tools.checkpoint_request_proof import classify_returned_attempt

class CheckpointRequestProofTests(unittest.TestCase):
    def setUp(self):
        self.old = {"number":1,"method":"built-in imagegen","fullsize_sha256":"a"*64,"prompt":"frozen","review":"rejected"}
    def test_unchanged_committed_return_has_explicit_legacy_boundary(self):
        self.assertEqual(classify_returned_attempt(self.old,[copy.deepcopy(self.old)],{"a"*64:{}}, "machine"),"unchanged_committed_legacy_return")
    def test_changed_historical_attempt_cannot_borrow_old_index(self):
        changed={**self.old,"prompt":"changed"}
        with self.assertRaises(AssertionError):
            classify_returned_attempt(changed,[self.old],{"a"*64:{}}, "machine")
    def test_new_return_cannot_borrow_legacy_boundary(self):
        with self.assertRaises(AssertionError):
            classify_returned_attempt(self.old,[],{"a"*64:{}}, "machine")
        with self.assertRaises(AssertionError):
            classify_returned_attempt(self.old,[self.old],{}, "machine")
    def test_modern_requires_true_pre_call_and_current_machine(self):
        modern={**self.old,"actual_request_verification":{"actual_recorded_before_call":True,"machine_id":"machine"}}
        self.assertEqual(classify_returned_attempt(modern,[],{},"machine"),"modern_pre_call_proof")
        for proof in ({"actual_recorded_before_call":False,"machine_id":"machine"},{"actual_recorded_before_call":True,"machine_id":"other"}):
            with self.assertRaises(AssertionError):
                classify_returned_attempt({**self.old,"actual_request_verification":proof},[self.old],{"a"*64:{}}, "machine")
    def test_other_tool_is_not_legacy_builtin_evidence(self):
        changed={**self.old,"method":"other"}
        with self.assertRaises(AssertionError):
            classify_returned_attempt(changed,[changed],{"a"*64:{}}, "machine")
