import tempfile
from pathlib import Path
import unittest

from tools.common import read_json
from tools.production_plan_state import append_state


class ProductionPlanStateTest(unittest.TestCase):
    def test_idle_queue_can_wait_and_resume_with_history_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transitions = [
                ('running', 'important-test', 1),
                ('batch_completed', 'important-test', 1),
                ('waiting_for_prepared_jobs', 'important-test', 2),
                ('running', '钢奶龙心-next', 2),
                ('producer_stopped_at_batch_boundary', '钢奶龙心-next', 3),
            ]
            for state, batch, index in transitions:
                append_state('after128-20261020', state, batch, index, root=root)
            data = read_json(root / 'runtime' / 'after128-20261020-state.json')
            self.assertEqual([e['state'] for e in data['history']],
                             [e[0] for e in transitions])
            self.assertEqual(data['current'], data['history'][-1])
            self.assertEqual(data['current']['batch'], '钢奶龙心-next')
            self.assertEqual(list((root / 'runtime').glob('*.writing.json')), [])

    def test_invalid_transition_does_not_overwrite_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            append_state('after128-20261020', 'running', 'important-test', 1, root=root)
            path = root / 'runtime' / 'after128-20261020-state.json'
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                append_state('after128-20261020', 'unknown', 'important-test', 2, root=root)
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
