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

if __name__=='__main__':unittest.main()
