import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.invocation_file_verifier import InvocationFileVerifier
from tools.common import file_sha256

class InvocationFileVerifierTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'input.png';self.path.write_bytes(b'original bytes')
 def test_same_invocation_reuses_actual_complete_read_and_new_invocation_rereads(self):
  first=InvocationFileVerifier()
  with patch('tools.invocation_file_verifier.file_sha256',wraps=file_sha256) as reads:
   self.assertEqual(first(self.path),hashlib.sha256(b'original bytes').hexdigest());first(self.path)
   self.assertEqual(reads.call_count,1)
   InvocationFileVerifier()(self.path);self.assertEqual(reads.call_count,2)
  self.assertEqual(first.summary()['unchanged_same_invocation_reuses'],1)
 def test_same_size_change_is_rehashed_and_not_trusted_by_path(self):
  v=InvocationFileVerifier();previous=v(self.path);st=self.path.stat();self.path.write_bytes(b'changed! bytes');os.utime(self.path,ns=(st.st_atime_ns,st.st_mtime_ns+10000000))
  self.assertNotEqual(v(self.path),previous);self.assertEqual(v.full_reads,2)
 def test_replaced_file_and_missing_file_do_not_reuse_old_digest(self):
  v=InvocationFileVerifier();previous=v(self.path);new=self.path.with_name('new.png');new.write_bytes(b'replacement');new.replace(self.path)
  self.assertNotEqual(v(self.path),previous);self.path.unlink()
  with self.assertRaises(FileNotFoundError):v(self.path)
 def test_change_during_full_read_fails_without_publishing_cache_entry(self):
  v=InvocationFileVerifier()
  def changing(path):
   digest=file_sha256(path);path.write_bytes(b'changed during read');return digest
  with patch('tools.invocation_file_verifier.file_sha256',side_effect=changing):
   with self.assertRaisesRegex(ValueError,'changed during'):v(self.path)
  self.assertEqual(v.full_reads,0);self.assertEqual(v(self.path),file_sha256(self.path))
 def test_expected_input_digest_still_checked_on_reuse(self):
  from mod_nailong.tools import audit_art
  v=InvocationFileVerifier();digest=v(self.path)
  with patch.object(audit_art,'ROOT',self.path.parent):
   audit_art.verify_request_inputs([{'path':self.path.name,'sha256':digest}],self.path,digest,hasher=v)
   with self.assertRaises(AssertionError):audit_art.verify_request_inputs([{'path':self.path.name,'sha256':'0'*64}],self.path,digest,hasher=v)
 def test_sync_then_audit_reuses_only_same_invocation_verified_master(self):
  from tests.test_master_files import MasterFilesTests
  from mod_nailong.tools.master_files import sync_git,audit_files,master_path
  root=Path(self.tmp.name);_,original,digest,snapshot=MasterFilesTests().fixture(root)
  sync_git(snapshot,root);snapshot['masters'][0]['path']=str(root/master_path(digest))
  v=InvocationFileVerifier();sync_git(snapshot,root,hasher=v);audit_files(root,hasher=v)
  self.assertEqual(v.full_reads,1);self.assertEqual(v.reuses,1)
  target=root/master_path(digest);target.write_bytes(b'corrupted')
  with self.assertRaises(ValueError):audit_files(root,hasher=v)

if __name__=='__main__':unittest.main()
