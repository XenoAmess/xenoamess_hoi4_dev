"""Observe actual PNG return throughput over a prospectively recorded wall interval."""
import argparse
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, read_json, write_json, utc_now


def dt(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')) if value else None


def measure(rows, start, end):
    seconds = (end - start).total_seconds()
    assert seconds > 0
    returned = [r for r in rows if r['end'] and start <= r['end'] < end]
    calls = [r for r in rows if start <= r['start'] < end]
    images = [r for r in returned if r['status'] == 'returned_image']
    finished = [r for r in calls if r['status'] == 'returned_image' and r['end'] and r['end'] < end]
    spans = sorted((max(start, r['start']), min(end, r['end'] or end))
                   for r in rows if (r['end'] or r['status'] == 'calling')
                   and r['start'] < end and (r['end'] or end) > start)
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    occupied = sum((b - a).total_seconds() for a, b in merged)
    cross = []
    for previous, current in zip(rows, rows[1:]):
        if not previous['end'] or previous['batch'] == current['batch'] or not start <= current['start'] < end:
            continue
        cross.append(max(0, (current['start'] - max(start, previous['end'])).total_seconds()))
    return {'start_utc': start.isoformat(), 'end_utc': end.isoformat(),
            'elapsed_seconds': round(seconds, 3), 'actual_png_returns': len(images),
            'actual_tool_errors': sum(r['status'] == 'tool_error' for r in returned),
            'actual_dispatches': len(calls), 'png_per_wall_hour': round(len(images) * 3600 / seconds, 3),
            'client_recorded_occupied_seconds': round(occupied, 3),
            'client_recorded_unoccupied_seconds': round(seconds - occupied, 3),
            'success_call_median_seconds': round(statistics.median((r['end'] - r['start']).total_seconds() for r in finished), 3) if finished else None,
            'cross_batch_gap_count': len(cross),
            'cross_batch_gap_median_seconds': round(statistics.median(cross), 3) if cross else None,
            'cross_batch_gap_total_seconds': round(sum(cross), 3),
            'png_ledgers': [r['ledger'] for r in images]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-file', required=True)
    parser.add_argument('--minutes', type=int, choices=[15, 30, 60], required=True)
    parser.add_argument('--output')
    parser.add_argument('--require-complete', action='store_true')
    args = parser.parse_args()
    benchmark = read_json(ROOT / args.start_file)
    start = dt(benchmark['started_at_utc'])
    now = datetime.now(timezone.utc)
    target = start + timedelta(minutes=args.minutes)
    if args.require_complete and now < target:
        raise SystemExit('Requested wall interval has not elapsed; no completed measurement recorded')
    rows = []
    for p in (ROOT / 'runtime/production-queue/dispatch').glob('*.json'):
        r = read_json(p)
        if r.get('machine_id') != benchmark['machine_id']:
            continue
        r['start'] = dt(r['call_started_at_utc'])
        r['end'] = dt(r.get('call_returned_at_utc'))
        r['batch'] = Path(r.get('actual_request_snapshot_file', '')).stem.removesuffix('-' + r['source_sha256'])
        r['ledger'] = p.relative_to(ROOT).as_posix()
        rows.append(r)
    rows.sort(key=lambda r: r['start'])
    result = measure(rows, start, min(now, target))
    result.update(machine_id=benchmark['machine_id'], observed_at_utc=utc_now(),
                  requested_minutes=args.minutes, complete=now >= target,
                  comparison_png_per_wall_hour=benchmark['comparison_png_per_wall_hour'],
                  scope='Actual returns in a fixed prospective wall interval; includes queue/preparation/checkpoint gaps. Client timestamps include transport/orchestration. PNG return is not art approval; partial intervals are explicitly marked.')
    result['difference_percent'] = round((result['png_per_wall_hour'] / result['comparison_png_per_wall_hour'] - 1) * 100, 2)
    if args.output:
        out = ROOT / args.output
        assert not out.exists(), 'Never overwrite a prior measurement'
        write_json(out, result)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
