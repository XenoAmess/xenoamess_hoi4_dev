import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from runtime import high131_checkpoint as checkpoint
from runtime import high131_transport_split as transport
from tools.common import ROOT, write_json

SCRIPT = ROOT / 'runtime/verify-production-commit.py'
spec = importlib.util.spec_from_file_location('scoped_readback_checkpoint', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ScopedReadbackCheckpointTests(unittest.TestCase):
    def test_scoped_copy_preserves_seed_and_parent_directories(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
            seed = Path(directory) / 'seed.json'
            scoped = Path(directory) / 'nested' / 'checkpoint.json'
            seed.write_text('{"prior_verified_outputs": true}', encoding='utf-8')
            with patch.object(module.master_git_remote, 'CHECKPOINT', seed), patch.dict(os.environ, {'XAR_READBACK_CHECKPOINT': str(scoped)}):
                self.assertEqual(module.scoped_readback_checkpoint(), scoped)
            self.assertEqual(scoped.read_text(encoding='utf-8'), '{"prior_verified_outputs": true}')
            self.assertEqual(seed.read_text(encoding='utf-8'), '{"prior_verified_outputs": true}')

    def test_missing_override_uses_legacy_behavior(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('XAR_READBACK_CHECKPOINT', None)
            self.assertIsNone(module.scoped_readback_checkpoint())

    def test_shared_pointer_and_out_of_runtime_paths_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
            shared = Path(directory) / 'shared.json'
            with patch.object(module.master_git_remote, 'CHECKPOINT', shared), patch.dict(os.environ, {'XAR_READBACK_CHECKPOINT': str(shared)}):
                with self.assertRaisesRegex(ValueError, 'shared checkpoint'):
                    module.scoped_readback_checkpoint()
            with patch.dict(os.environ, {'XAR_READBACK_CHECKPOINT': '../outside.json'}):
                with self.assertRaises(ValueError):
                    module.scoped_readback_checkpoint()


class TransportCheckpointCompatibilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.config = transport.TransportConfig(
            original_commit='a' * 40,
            base_commit='b' * 40,
            batch='high131-test',
            plan_path=root / 'plan.json',
            checkpoint_path=root / 'checkpoint.json',
            readback_path=root / 'readback.json',
        )
        self.plan = {
            'original_commit': self.config.original_commit,
            'base': self.config.base_commit,
            'final_commit': 'c' * 40,
            'final_tree': 'd' * 40,
            'path_count': 0,
            'group_byte_limit': 1,
            'bytes_basis': 'test',
            'path_order': 'test',
            'paths': [],
            'groups': [],
            'commit_identity': {},
            'commit_message_template': 'test',
            'final_tree_verification': {'identical': True},
            'pushed_at_utc': '2026-01-01T00:00:00+00:00',
        }
        self.plan['layout_sha256'] = transport.layout_fingerprint(self.plan)

    def test_matching_pending_checkpoint_can_resume(self):
        write_json(self.config.checkpoint_path, {
            'commit': self.config.original_commit,
            'parent_commit': self.config.base_commit,
            'status': 'committed_push_pending',
        })
        with patch.object(transport, 'commit_info', return_value={'tree': self.plan['final_tree']}), patch.object(transport, 'machine_id', return_value='test-machine'):
            transport.write_checkpoint(self.plan, self.config)
        receipt = transport.read_json(self.config.checkpoint_path)
        self.assertEqual(receipt['commit'], self.plan['final_commit'])
        self.assertEqual(receipt['status'], 'committed_and_pushed')
        self.assertEqual(self.plan['status'], 'standard_publish_pending')

    def test_other_pending_checkpoint_is_not_overwritten(self):
        write_json(self.config.checkpoint_path, {
            'commit': self.config.original_commit,
            'parent_commit': 'e' * 40,
            'status': 'committed_push_pending',
        })
        with self.assertRaisesRegex(transport.ToolError, 'another commit'):
            transport.write_checkpoint(self.plan, self.config)
        self.assertEqual(transport.read_json(self.config.checkpoint_path)['status'], 'committed_push_pending')


class CheckpointPublicationLockTests(unittest.TestCase):
    def test_checkpoint_lock_uses_mapping_plan_and_releases_only_its_token(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
            lock_path = Path(directory) / 'publish.lock'
            lock = checkpoint.checkpoint_publish_lock('checkpoint-test')
            with patch.object(transport, 'PUBLISH_LOCK_PATH', lock_path):
                lock.acquire()
                try:
                    owner = transport.read_json(lock_path)
                    self.assertIsInstance(lock.plan, dict)
                    self.assertEqual(owner['batch'], 'checkpoint-test')
                    self.assertIsNone(owner['original_commit'])
                    self.assertIsNone(owner['final_commit'])
                    self.assertEqual(owner['machine_id'], checkpoint.machine_id())
                finally:
                    lock.release()
                self.assertFalse(lock_path.exists())


class CheckpointRemoteRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.parent = '1' * 40
        self.previous = '2' * 40
        self.prefix = '3' * 40
        self.approved = {
            'count': 1,
            'entries': [{'source_sha256': 'a' * 64, 'generated_fullsize_sha256': 'b' * 64}],
        }

    def validate(self, remote_entries=None, remote_paths=None):
        experiment = checkpoint.EXPERIMENT.relative_to(checkpoint.ROOT).as_posix()
        remote = {'count': len(remote_entries or self.approved['entries']), 'entries': remote_entries or self.approved['entries']}

        def fake_git(*args, **kwargs):
            if args[0] == 'merge-base':
                return b''
            if args[0] == 'rev-parse':
                return (Path(args[1].split(':', 1)[1]).name + '-blob\n').encode()
            if args[0] == 'hash-object':
                return (Path(args[1]).name + '-blob\n').encode()
            if args[:2] == ('diff', '--quiet'):
                return b''
            if args[0] == 'ls-tree':
                paths = remote_paths or [f'{experiment}/scope.json']
                return ('\n'.join(paths) + '\n').encode()
            if args[0] == 'show':
                return json.dumps(remote).encode()
            raise AssertionError(args)

        with patch.object(checkpoint, 'git', side_effect=fake_git):
            return checkpoint.validate_remote_recovery(self.parent, self.approved, self.previous, self.prefix)

    def test_remote_files_and_approvals_must_be_retained(self):
        result = self.validate()
        self.assertTrue(result['published_prefix_is_ancestor'])
        self.assertTrue(result['every_remote_approval_retained_at_the_same_source_and_sha'])
        self.assertEqual(result['remote_files_absent_locally'], [])

    def test_unknown_remote_approval_blocks_snapshot(self):
        unknown = {'source_sha256': 'c' * 64, 'generated_fullsize_sha256': 'd' * 64}
        with self.assertRaisesRegex(RuntimeError, 'approvals'):
            self.validate(remote_entries=[unknown])

    def test_unknown_remote_experiment_file_blocks_snapshot(self):
        experiment = checkpoint.EXPERIMENT.relative_to(checkpoint.ROOT).as_posix()
        with self.assertRaisesRegex(RuntimeError, 'absent locally'):
            self.validate(remote_paths=[f'{experiment}/outputs/new-result.png'])


class CheckpointPathTests(unittest.TestCase):
    def test_budget_path_uses_batch_once_and_only_empty_workdir_is_reused(self):
        self.assertEqual(checkpoint.storage_precheck_path('high131-test').name, 'high131-test-storage-precheck.json')
        with tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
            with patch.object(checkpoint, 'ROOT', Path(directory)):
                folder = checkpoint.checkpoint_workdir('unit')
                self.assertTrue(folder.is_dir())
                checkpoint.checkpoint_workdir('unit')
                marker = folder / 'receipt.json'
                marker.write_text('keep', encoding='utf-8')
                with self.assertRaisesRegex(RuntimeError, 'nonempty'):
                    checkpoint.checkpoint_workdir('unit')
                self.assertEqual(marker.read_text(encoding='utf-8'), 'keep')
    def test_checkpoint_git_enables_windows_longpaths(self):
        completed = checkpoint.subprocess.CompletedProcess(args=[], returncode=0, stdout=b'', stderr=b'')
        with patch.object(checkpoint.subprocess, 'run', return_value=completed) as run:
            checkpoint.git('add', '--', 'example')
        self.assertEqual(run.call_args.args[0][:3], ['git', '-c', 'core.longpaths=true'])


if __name__ == '__main__':
    unittest.main()
