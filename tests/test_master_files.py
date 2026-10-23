"""Original bytes must survive ordinary Git storage, including old revisions."""
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from tools.common import write_json, read_json
from mod_nailong.tools.master_files import sync_git, verify_tree, master_path
from mod_nailong.tools import master_archive


class MasterFilesTests(unittest.TestCase):
    def fixture(self, root):
        mod = root/'mod_nailong'
        output = root/'output.png'
        Image.new('RGBA',(23,31),(233,182,40,128)).save(output)
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        write_json(mod/'data/generated.json',{'portraits': {'source': {
            'generated_fullsize_sha256': digest,
            'revision_history': [{'previous_fullsize_sha256':digest}]}}})
        write_json(mod/'data/generation-requests/source.json',{'attempts':[
            {'number':1,'fullsize_sha256':digest,'prompt_sha256':'frozen-prompt-sha'}]})
        snap={'current_masters_missing':[], 'historical_fullsize_sha_missing':[], 'masters':[
            {'path':str(output),'sha256':digest,'bytes':output.stat().st_size,
             'size':[23,31],'mode':'RGBA','provenance':[{'journal':'data/generation-requests/source.json','attempt':1}]}]}
        return mod, output, digest, snap

    def test_git_blob_is_complete_original_and_history_has_stable_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            mod, original, digest, snap = self.fixture(root)
            index=sync_git(snap,root)
            self.assertEqual(index['count'],1)
            self.assertEqual((root/master_path(digest)).read_bytes(),original.read_bytes())
            row=read_json(mod/'data/generated.json')['portraits']['source']
            self.assertEqual(row['generated_fullsize_image'],row['revision_history'][0]['previous_fullsize_image'])
            self.assertEqual(read_json(mod/'data/generation-requests/source.json')['attempts'][0]['fullsize_image'],master_path(digest))
            for args in (['init'],['add','.'],['-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','Store originals']):
                subprocess.run(['git',*args],cwd=root,check=True,capture_output=True)
            commit, blobs=verify_tree(root=root)
            self.assertEqual(len(blobs),1)
            # An immutable-commit readback must survive a new or absent worktree
            # asset, so production imports can overlap the remote verification.
            target=root/master_path(digest)
            target.unlink()
            _,pinned_blobs=verify_tree(commit,root=root,index=index)
            self.assertEqual(pinned_blobs,blobs)
            target.write_bytes(original.read_bytes())
            subprocess.run(['git','rm',master_path(digest)],cwd=root,check=True,capture_output=True)
            (root/master_path(digest)).parent.mkdir(parents=True,exist_ok=True)
            (root/master_path(digest)).write_bytes(original.read_bytes())
            subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid','commit','-m','Remove Git blob'],cwd=root,check=True,capture_output=True)
            # A local PNG alone cannot pass a real Git tree check.
            with self.assertRaisesRegex(ValueError,'Git PNG blob'):
                verify_tree(root=root)

    def test_missing_output_and_changed_source_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            mod, original, digest, snap=self.fixture(root)
            original.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'changed before'):
                sync_git(snap,root)
            snap['historical_fullsize_sha_missing']=['missing']
            with self.assertRaisesRegex(ValueError,'missing'):
                sync_git(snap,root)

    def test_repeated_sync_preserves_unchanged_journals_but_repairs_stale_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            mod, original, digest, snap=self.fixture(root)
            sync_git(snap,root)
            journal_path=mod/'data/generation-requests/source.json'
            generated_path=mod/'data/generated.json'
            with patch('mod_nailong.tools.master_files.write_json',wraps=write_json) as writes:
                sync_git(snap,root)
                targets=[call.args[0] for call in writes.call_args_list]
                self.assertNotIn(journal_path,targets)
                self.assertNotIn(generated_path,targets)
            journal=read_json(journal_path)
            journal['attempts'][0]['fullsize_image']='stale/path.png'
            write_json(journal_path,journal)
            with patch('mod_nailong.tools.master_files.write_json',wraps=write_json) as writes:
                sync_git(snap,root)
                self.assertEqual(sum(call.args[0]==journal_path for call in writes.call_args_list),1)
                self.assertNotIn(generated_path,[call.args[0] for call in writes.call_args_list])
            self.assertEqual(read_json(journal_path)['attempts'][0]['fullsize_image'],master_path(digest))
            self.assertEqual(read_json(journal_path)['attempts'][0]['prompt_sha256'],'frozen-prompt-sha')

    def test_independent_existing_target_is_not_trusted_by_name(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            _, original, digest, snap=self.fixture(root)
            target=root/master_path(digest);target.parent.mkdir(parents=True)
            raw=bytearray(original.read_bytes());raw[-1]^=1;target.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'Git master bytes'):
                sync_git(snap,root)

    def test_inventory_prefers_complete_project_masters_and_recovers_missing_ones(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);mod, original, digest, _=self.fixture(root)
            retained=root/master_path(digest);retained.parent.mkdir(parents=True)
            retained.write_bytes(original.read_bytes())
            cache=root/'.codex/generated_images/session/output.png';cache.parent.mkdir(parents=True)
            cache.write_bytes(original.read_bytes())
            write_json(root/'runtime/generated-origins/source.json',{'source':str(cache)})
            real_hash=master_archive.file_sha256
            with patch.object(master_archive,'ROOT',root),patch.object(master_archive,'MOD',mod),patch.object(master_archive,'INVENTORY',root/'runtime/inventory.json'),patch.object(master_archive,'recorded_outputs',return_value=({digest},{'source':digest},{digest:[]})):
                with patch.object(master_archive,'file_sha256',wraps=real_hash) as hashes:
                    result=master_archive.inventory()
                    self.assertEqual(result['historical_fullsize_sha_missing'],[])
                    self.assertEqual(Path(result['masters'][0]['path']),retained)
                    self.assertEqual(hashes.call_count,1)
                retained.unlink()
                recovered=master_archive.inventory()
                self.assertEqual(recovered['historical_fullsize_sha_missing'],[])
                self.assertEqual(Path(recovered['masters'][0]['path']),cache)


if __name__=='__main__':unittest.main()
