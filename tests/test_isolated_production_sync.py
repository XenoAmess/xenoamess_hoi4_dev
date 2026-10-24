import tempfile
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import isolated_production_sync as sync


class IsolatedProductionSyncTests(unittest.TestCase):
    def exercise(self, rebased=None, batch='test-checkpoint'):
        commit = 'a' * 40
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args, cwd=None):
                calls.append((args, cwd))
                if args == ('branch', '--show-current'):
                    return 'master'
                if args == ('remote', 'get-url', 'origin'):
                    return 'https://github.com/XenoAmess/xenoamess_hoi4_dev.git'
                if args[:2] == ('rev-parse', '--verify'):
                    return commit
                if args == ('rev-parse', 'origin/master'):
                    return 'b' * 40
                if args == ('rev-parse', 'HEAD'):
                    return rebased or commit
                if args[:2] == ('worktree', 'add'):
                    Path(args[-2]).mkdir()
                return ''

            with patch.object(sync, 'ROOT', root), patch.object(sync, '_git', side_effect=git):
                if rebased:
                    with self.assertRaisesRegex(RuntimeError, 'validate that result'):
                        sync.rebase_validated_commit(commit, batch)
                else:
                    result = sync.rebase_validated_commit(commit, batch)
                    self.assertEqual(result['synchronized_commit'], commit)
            rebase = [(args, cwd) for args, cwd in calls if args[0] == 'rebase']
            self.assertEqual(len(rebase), 1)
            self.assertTrue(rebase[0][1].is_relative_to(root / 'runtime/production-sync'))
            self.assertEqual(rebase[0][0], ('rebase', 'origin/master'))
            self.assertFalse(any(args[0] in ('stash', 'reset', 'push') for args, _ in calls))
            self.assertFalse(any(args[0] == 'rebase' and cwd is None for args, cwd in calls))
            sparse = [args for args, _ in calls if args[0] == 'sparse-checkout'][0]
            self.assertEqual(sparse[-3:], ('/AGENTS.md', '/README.md', '/.gitignore'))

    def test_live_worktree_is_not_rebased_or_stashed(self):
        self.exercise()

    def test_actual_fresh_source_batch_with_utc_T_is_a_safe_identifier(self):
        self.exercise(batch='resume-fresh-observed-20261024T123727-b-f506cb99-network-2')

    def test_changed_commit_requires_revalidation_before_any_push(self):
        self.exercise('c' * 40)

    def test_identifier_cannot_escape_runtime(self):
        with patch.object(sync, '_git') as git:
            with self.assertRaises(ValueError):
                sync.rebase_validated_commit('a' * 40, '../outside')
            git.assert_not_called()

    @unittest.skipUnless(shutil.which('git'), 'Git is required for sparse worktree integration')
    def test_real_git_populates_sparse_index_without_copying_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repo'
            root.mkdir()

            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root, text=True,
                                               encoding='utf-8', stderr=subprocess.STDOUT).strip()

            git('init', '--initial-branch=master')
            git('config', 'user.name', 'Checkpoint fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            for name in ('AGENTS.md', 'README.md'):
                (root / name).write_text('small fixture\n', encoding='utf-8')
            (root / '.gitignore').write_text('/runtime/\n', encoding='utf-8')
            (root / 'notes.txt').write_text('committed\n', encoding='utf-8')
            (root / 'assets').mkdir()
            (root / 'assets/test.png').write_bytes(b'fixture-only' * 65536)
            git('add', '.')
            git('commit', '-m', 'Create fixture')
            commit = git('rev-parse', 'HEAD')
            git('remote', 'add', 'origin', 'https://github.com/XenoAmess/xenoamess_hoi4_dev.git')
            git('update-ref', 'refs/remotes/origin/master', commit)
            (root / 'notes.txt').write_text('active production write\n', encoding='utf-8')
            before = git('status', '--porcelain')
            real_git = sync._git

            def local_git(*args, cwd=None):
                # This fixture exercises real Git indexing/rebase, with no network.
                return '' if args == ('fetch', 'origin') else real_git(*args, cwd=cwd)

            with patch.object(sync, 'ROOT', root), patch.object(sync, '_git', side_effect=local_git):
                result = sync.rebase_validated_commit(commit, 'integration-fixture')
            tree = Path(result['isolated_worktree'])
            self.assertTrue((tree / 'README.md').is_file())
            self.assertFalse((tree / 'assets/test.png').exists())
            self.assertEqual(git('status', '--porcelain'), before)
            self.assertEqual((root / 'notes.txt').read_text(encoding='utf-8'), 'active production write\n')
            self.assertEqual(result['synchronized_commit'], commit)


if __name__ == '__main__':
    unittest.main()
