from pathlib import Path
import unittest
from unittest.mock import patch

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


if __name__ == '__main__':
    unittest.main()
