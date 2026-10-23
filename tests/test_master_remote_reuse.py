import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.common import read_json,write_json,file_sha256
from mod_nailong.tools import master_git_remote as remote


class ReusedPinnedReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.commit='2'*40;self.digest='a'*64;self.blob='b'*40
        self.path=f'mod_nailong/assets/generated_fullsize/{self.digest}.png'
        self.index={'count':1,'original_png_bytes':64,'outputs':{self.digest:{'path':self.path,'bytes':64}}}
        self.old={'path':self.path,'bytes':64,'sha256':self.digest,'git_blob_sha1':self.blob,'readback_commit':'1'*40,'verified_at_utc':'2026-10-20T00:00:00+00:00','method':'Complete anonymous raw PNG download; SHA256 and byte count'}
        self.checkpoint=self.root/'mod_nailong/data/fullsize-git-checkpoint.json'
        write_json(self.checkpoint,{'machine_id':'fixture','commit':'1'*40,'outputs':{self.digest:self.old}})
        self.tree={'tree':[{'path':self.path,'type':'blob','sha':self.blob,'size':64}]}
        self.receipt=self.root/f'runtime/fullsize-git-readbacks/{self.commit}.json'
        self.addCleanup(patch.stopall)
        patch.object(remote,'ROOT',self.root).start();patch.object(remote,'CHECKPOINT',self.checkpoint).start()
        patch.object(remote,'machine_id',return_value='fixture').start()
        patch.object(remote,'verify_tree',return_value=(self.commit,{self.digest:self.blob})).start()
        patch.object(remote,'json_api',side_effect=lambda endpoint:copy.deepcopy(self.tree)).start()
        patch.object(remote.subprocess,'check_output',side_effect=self.git).start()
        self.download=patch.object(remote.requests,'get',side_effect=AssertionError('An unchanged verified blob must not be redownloaded')).start()

    def git(self,command,**kwargs):
        if command[1]=='rev-parse':return self.commit+'\n'
        if command[1]=='show' and command[2].endswith(':mod_nailong/data/fullsize-files.json'):return json.dumps(self.index)
        if command[1]=='show' and command[2].endswith(':mod_nailong/data/generated.json'):return json.dumps({'portraits':{'source':{'generated_fullsize_sha256':self.digest}}})
        raise AssertionError(command)

    def test_all_reused_outputs_persist_pinned_proof_and_keep_original_download_time(self):
        result=remote.verify_remote(self.commit)
        saved=read_json(self.receipt)
        self.assertEqual(saved['commit'],self.commit)
        self.assertEqual(saved['outputs'][self.digest]['verified_at_utc'],self.old['verified_at_utc'])
        self.assertEqual(saved['outputs'][self.digest]['readback_commit'],self.old['readback_commit'])
        self.assertEqual(saved['outputs'][self.digest]['unchanged_blob_confirmed_at_commit'],self.commit)
        self.assertEqual(result['earlier_complete_readbacks_reused_after_remote_blob_match'],1)
        self.download.assert_not_called()

    def test_existing_pinned_proof_survives_a_later_verification_without_download(self):
        write_json(self.receipt,{'machine_id':'fixture','commit':self.commit,'outputs':{self.digest:self.old}})
        before=read_json(self.receipt)['outputs'];remote.verify_remote(self.commit)
        self.assertEqual(read_json(self.receipt)['outputs'],before);self.download.assert_not_called()

    def test_remote_blob_mismatch_cannot_reuse_or_publish_a_successful_proof(self):
        self.tree['tree'][0]['sha']='c'*40;before=file_sha256(self.checkpoint)
        with self.assertRaises(ValueError):remote.verify_remote(self.commit)
        self.assertFalse(self.receipt.exists());self.assertEqual(file_sha256(self.checkpoint),before)
        self.download.assert_not_called()


if __name__=='__main__':unittest.main()
