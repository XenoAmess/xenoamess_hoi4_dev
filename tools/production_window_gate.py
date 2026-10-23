"""Wait for an exact durable window receipt before handing off its sole writer."""
import argparse
import json
import re
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, machine_id, read_json, utc_now


def inspect_window(root, window_id, expected_machine):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', window_id):
        raise ValueError('Unsafe window identity')
    folder = root / 'mod_nailong/data/production-window-timings'
    if any((folder / (window_id + suffix)).exists() for suffix in ['-stopped.json', '-continuation-stopped.json']):
        raise ValueError('Previous window stopped; reconcile before continuation')
    receipt = folder / (window_id + '-completed.json')
    if not receipt.exists():
        return {'ready': False, 'reason': 'waiting_for_exact_completed_receipt'}
    row = read_json(receipt)
    if row.get('machine_id') != expected_machine or row.get('window_id') != window_id or row.get('status') != 'completed':
        raise ValueError('Window identity, machine or completed status mismatch')
    batches = [b['batch'] for b in row['batches']]
    completed = {e['batch'] for e in row['events'] if e['phase'] == 'batch_imports_completed'}
    if not batches or not set(batches).issubset(completed):
        raise ValueError('Window lacks import completion for a planned batch')
    for path in (root / 'runtime/production-queue/dispatch').glob('*.json'):
        if read_json(path).get('status') == 'calling':
            return {'ready': False, 'reason': 'another_actual_call_requires_completion', 'ledger': path.name}
    return {'ready': True, 'window_id': window_id, 'machine_id': expected_machine,
            'receipt': receipt.relative_to(root).as_posix(), 'observed_at_utc': utc_now()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('window_id')
    parser.add_argument('--wait-seconds', type=float, default=0)
    args = parser.parse_args()
    if not 0 <= args.wait_seconds <= 900:
        parser.error('wait-seconds must be between 0 and 900')
    deadline = time.monotonic() + args.wait_seconds
    while True:
        result = inspect_window(ROOT, args.window_id, machine_id())
        if result['ready'] or time.monotonic() >= deadline:
            print(json.dumps(result, ensure_ascii=True))
            return 0 if result['ready'] else 2
        time.sleep(min(1, max(0, deadline - time.monotonic())))


if __name__ == '__main__':
    raise SystemExit(main())
