import unittest
from datetime import datetime, timedelta, timezone
from tools.production_benchmark import measure


class BenchmarkTests(unittest.TestCase):
    def test_counts_return_time_and_keeps_preparation_and_tail_idle_in_denominator(self):
        start = datetime(2026, 10, 24, tzinfo=timezone.utc)
        row = lambda a, b, status, batch: {'start': start + timedelta(seconds=a),
                                         'end': start + timedelta(seconds=b),
                                         'status': status, 'batch': batch, 'ledger': batch}
        rows = [row(-10, 5, 'returned_image', 'before'), row(20, 30, 'tool_error', 'error'),
                row(50, 70, 'returned_image', 'after')]
        r = measure(rows, start, start + timedelta(seconds=60))
        self.assertEqual(r['actual_png_returns'], 1)
        self.assertEqual(r['actual_tool_errors'], 1)
        self.assertEqual(r['actual_dispatches'], 2)
        self.assertEqual(r['png_per_wall_hour'], 60)
        self.assertEqual(r['client_recorded_occupied_seconds'], 25)
        self.assertEqual(r['client_recorded_unoccupied_seconds'], 35)
        self.assertIsNone(r['success_call_median_seconds'])

    def test_overlapping_recorded_spans_are_not_double_counted(self):
        start = datetime(2026, 10, 24, tzinfo=timezone.utc)
        rows = [{'start': start, 'end': start + timedelta(seconds=30), 'status': 'returned_image', 'batch': 'a', 'ledger': 'a'},
                {'start': start + timedelta(seconds=20), 'end': start + timedelta(seconds=40), 'status': 'returned_image', 'batch': 'b', 'ledger': 'b'}]
        r = measure(rows, start, start + timedelta(seconds=60))
        self.assertEqual(r['client_recorded_occupied_seconds'], 40)
        self.assertEqual(r['client_recorded_unoccupied_seconds'], 20)
        self.assertEqual(r['actual_png_returns'], 2)


if __name__ == '__main__':
    unittest.main()
