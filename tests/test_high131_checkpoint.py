import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from runtime import high131_checkpoint as checkpoint


class CheckpointStageTests(unittest.TestCase):
    def test_long_master_list_uses_nul_delimited_stdin_pathspec(self):
        worktree = Path('snapshot-worktree')
        masters = [f'mod_nailong/assets/generated_fullsize/{index:064x}.png' for index in range(400)]
        with patch.object(checkpoint, 'git') as git:
            checkpoint.stage_checkpoint(worktree, masters)
        git.assert_called_once()
        args, kwargs = git.call_args
        self.assertEqual(args, ('add', '--pathspec-from-file=-', '--pathspec-file-nul'))
        self.assertEqual(kwargs['cwd'], worktree)
        payload = kwargs['data']
        self.assertGreater(len(payload), 32767)
        self.assertTrue(payload.endswith(b'\0'))
        actual = payload.removesuffix(b'\0').split(b'\0')
        expected = [*checkpoint.CHECKPOINT_STAGE_PATHS, *masters]
        self.assertEqual(actual, [path.encode('utf-8') for path in expected])
        self.assertEqual(len(actual), len(set(actual)))


class FullsizeIndexConflictTests(unittest.TestCase):
    def test_union_preserves_remote_and_validates_added_png(self):
        with tempfile.TemporaryDirectory(dir=checkpoint.ROOT / 'runtime') as temporary:
            master_dir = Path(temporary)
            source = master_dir / 'new.png'
            Image.new('RGBA', (3, 2), (12, 34, 56, 255)).save(source)
            original_bytes = source.read_bytes()
            digest = checkpoint.file_sha256(source)
            source = source.rename(master_dir / f'{digest}.png')
            added = {
                'path': f'mod_nailong/assets/generated_fullsize/{digest}.png',
                'bytes': len(original_bytes),
                'size': [3, 2],
                'mode': 'RGBA',
            }
            existing = {'sha256': 'existing', 'bytes': 11}
            shared = {'sha256': 'shared', 'bytes': 13}
            ours = {
                'schema': 'remote-index',
                'outputs': {'existing': existing, 'shared': shared},
                'count': 2,
                'original_png_bytes': 24,
            }
            theirs = {
                'schema': 'high-index',
                'outputs': {
                    'existing': {'bytes': 999999},
                    'shared': {'bytes': 999999},
                    digest: added,
                },
            }
            merged = checkpoint.merge_fullsize_index(ours, theirs, digest, master_dir)
            self.assertEqual(merged['schema'], 'remote-index')
            self.assertEqual(merged['outputs']['existing'], existing)
            self.assertEqual(merged['outputs']['shared'], shared)
            self.assertEqual(merged['outputs'][digest], added)
            self.assertEqual(merged['count'], 3)
            self.assertEqual(merged['original_png_bytes'], 24 + len(original_bytes))
            self.assertEqual(ours['count'], 2)
            with self.assertRaisesRegex(RuntimeError, 'Unexpected index additions'):
                checkpoint.merge_fullsize_index(ours, theirs, '0' * 64, master_dir)
            Image.new('RGBA', (3, 2), (255, 0, 0, 255)).save(source)
            with self.assertRaisesRegex(RuntimeError, 'archived bytes'):
                checkpoint.merge_fullsize_index(ours, theirs, digest, master_dir)
            self.assertNotEqual(source.read_bytes(), original_bytes)

    def test_real_rebase_conflict_and_completed_rebase_resume(self):
        sync_root = checkpoint.ROOT / 'runtime/production-sync'
        with tempfile.TemporaryDirectory(dir=sync_root) as temporary:
            root = Path(temporary)
            repo = root / 'worktree'
            repo.mkdir()
            master_dir = root / 'masters'
            master_dir.mkdir()

            def git(*args, check=True):
                return subprocess.run(
                    ['git', *args], cwd=repo, check=check,
                    capture_output=True, text=True, encoding='utf-8',
                ).stdout.strip()

            relative = 'mod_nailong/data/fullsize-files.json'

            def write_index(outputs):
                path = repo / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({
                    'schema': 'naiwa-fullsize-git-files-v1',
                    'outputs': outputs,
                    'count': len(outputs),
                    'original_png_bytes': sum(row['bytes'] for row in outputs.values()),
                }), encoding='utf-8')

            git('init', '-b', 'master')
            git('config', 'user.name', 'HIGH131 test')
            git('config', 'user.email', 'high131@example.invalid')
            base_output = 'a' * 64
            remote_output = 'b' * 64
            (repo / 'evidence.txt').write_text('unchanged HIGH evidence\n', encoding='utf-8')
            write_index({base_output: {'bytes': 11}})
            git('add', '--', 'evidence.txt', relative)
            git('commit', '-m', 'Base')
            base = git('rev-parse', 'HEAD')

            source = master_dir / 'new.png'
            Image.new('RGBA', (3, 2), (12, 34, 56, 255)).save(source)
            digest = checkpoint.file_sha256(source)
            source = source.rename(master_dir / f'{digest}.png')
            master = repo / f'mod_nailong/assets/generated_fullsize/{digest}.png'
            master.parent.mkdir(parents=True, exist_ok=True)
            master.write_bytes(source.read_bytes())
            added = {
                'path': f'mod_nailong/assets/generated_fullsize/{digest}.png',
                'bytes': master.stat().st_size,
                'size': [3, 2],
                'mode': 'RGBA',
            }
            write_index({base_output: {'bytes': 11}, digest: added})
            git('add', '--', relative, master.relative_to(repo).as_posix())
            git('commit', '-m', 'HIGH snapshot')
            original = git('rev-parse', 'HEAD')

            git('checkout', '-b', 'remote', base)
            write_index({base_output: {'bytes': 11}, remote_output: {'bytes': 13}})
            git('add', '--', relative)
            git('commit', '-m', 'Remote index')
            remote = git('rev-parse', 'HEAD')
            git('checkout', 'master')
            conflict = git('rebase', 'remote', check=False)
            self.assertNotEqual(conflict, '')
            self.assertEqual(git('diff', '--name-only', '--diff-filter=U'), relative)
            receipt_paths = set()
            try:
                with patch.object(checkpoint, 'MASTER_DIR', master_dir):
                    first = checkpoint.resolve_index_conflict(repo, original, digest)
                    receipt_paths.add(checkpoint.ROOT / first['receipt'])
                    resolved = first['commit']
                    self.assertNotEqual(resolved, original)
                    self.assertEqual(first['parent_commit'], remote)
                    receipt = json.loads((checkpoint.ROOT / first['receipt']).read_text(encoding='utf-8'))
                    self.assertEqual(receipt['new_local_commits_created_by_this_call'], 1)
                    self.assertFalse(receipt['existing_resolved_commit_revalidated'])
                    self.assertEqual(receipt['merged_output_count'], 3)
                    self.assertFalse(receipt['complete_archive_verified'])
                    (checkpoint.ROOT / first['receipt']).unlink()
                    second = checkpoint.resolve_index_conflict(repo, original, digest)
                    receipt_paths.add(checkpoint.ROOT / second['receipt'])
                    self.assertEqual(second['commit'], resolved)
                    receipt = json.loads((checkpoint.ROOT / second['receipt']).read_text(encoding='utf-8'))
                    self.assertTrue(receipt['existing_resolved_commit_revalidated'])
                    self.assertEqual(receipt['new_local_commits_created_by_this_call'], 0)
                index = json.loads((repo / relative).read_text(encoding='utf-8'))
                self.assertEqual(set(index['outputs']), {base_output, remote_output, digest})
                self.assertEqual(index['original_png_bytes'], 24 + source.stat().st_size)
                self.assertEqual(git('status', '--porcelain'), '')
                self.assertEqual(git('rev-parse', 'HEAD'), resolved)
            finally:
                for path in receipt_paths:
                    path.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
