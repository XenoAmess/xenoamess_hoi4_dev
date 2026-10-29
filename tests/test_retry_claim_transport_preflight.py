import unittest
from unittest.mock import patch

from tools import retry_scheduler_claim as subject


class RoutingPreflightTests(unittest.TestCase):
    def check_missing_metadata(self, candidate):
        with patch.object(subject, 'read_json', return_value=[candidate]), patch.object(subject, 'claim') as claim:
            with self.assertRaisesRegex(AssertionError, 'routing metadata'):
                subject.claim_candidates('186', 'unused-proof.json')
            claim.assert_not_called()

    def test_missing_source_does_not_consume_allowance(self):
        self.check_missing_metadata({'original': 'original.png', 'references': ['original.png']})

    def test_missing_original_does_not_consume_allowance(self):
        self.check_missing_metadata({'source': 'portrait.dds', 'references': ['original.png']})

    def test_original_outside_ordered_inputs_does_not_consume_allowance(self):
        self.check_missing_metadata({'source': 'portrait.dds', 'original': 'other.png', 'references': ['original.png']})


if __name__ == '__main__':
    unittest.main()
