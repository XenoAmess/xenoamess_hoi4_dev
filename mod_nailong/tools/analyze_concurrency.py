"""Summarize recorded built-in tool calls; never submits image requests."""
from pathlib import Path
import sys
from datetime import datetime
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT, read_json, write_json, machine_id, utc_now

folder = ROOT / 'mod_nailong/data/concurrency-tests'
rows = []
for path in sorted(folder.glob('*-c*.json')):
    test = read_json(path)
    if test['status'] != 'calls_completed':
        continue
    calls = test['calls']
    start = datetime.fromisoformat(test['started_at_utc'].replace('Z', '+00:00'))
    offsets = [(datetime.fromisoformat(c['finished_at_utc'].replace('Z', '+00:00'))-start).total_seconds() for c in calls]
    gaps = [round(b-a, 3) for a,b in zip([0]+sorted(offsets)[:-1], sorted(offsets))]
    successes = sum(c['status'] == 'generated' for c in calls)
    errors = [c.get('error', '') for c in calls if c['status'] != 'generated']
    rate_limits = sum('429' in e or 'rate_limit_exceeded' in e or 'too many concurrent' in e.lower() for e in errors)
    rows.append({
        'receipt': path.relative_to(ROOT).as_posix(), 'requested_concurrency': test['requested_concurrency'],
        'started_at_utc': test['started_at_utc'], 'finished_at_utc': test['finished_at_utc'],
        'attempts': len(calls), 'generated': successes, 'moderation_rejections': sum('moderation_blocked' in e for e in errors),
        'explicit_rate_limit_errors': rate_limits, 'wall_seconds': test['wall_ms']/1000,
        'completion_offsets_seconds': [round(v,3) for v in offsets], 'completion_gaps_seconds': gaps,
        'attempts_per_hour': round(len(calls)*3600000/test['wall_ms'],2),
        'generated_per_hour': round(successes*3600000/test['wall_ms'],2),
        'call_start_spread_ms': round((max(datetime.fromisoformat(c['started_at_utc'].replace('Z','+00:00')) for c in calls)-min(datetime.fromisoformat(c['started_at_utc'].replace('Z','+00:00')) for c in calls)).total_seconds()*1000)
    })
summary = {
    'schema': 'naiwa-builtin-concurrency-summary-v1', 'machine_id': machine_id(), 'observed_at_utc': utc_now(),
    'evidence': 'Per-call client timestamps in referenced receipts; no server-side scheduling visibility',
    'measurements': rows, 'largest_tested_outstanding_requests': max(r['requested_concurrency'] for r in rows),
    'hard_outstanding_request_limit': None, 'server_parallel_execution_limit': None,
    'observed_effective_generation_lanes': 'Approximately one: concurrent request completions remain spaced by one image duration',
    'production_choice': 'One continuous built-in call at a time; prepare/review/docs overlap during waits. Do not pile up requests without measured throughput gains.',
    'stop_escalation_reason': '4 and 8 show no material throughput gain over single-call control; a larger queue would add latency without an established benefit',
    'risk_control_guarantee': False, 'api_cli_used': False
}
write_json(folder / 'summary.json', summary)
for r in rows:
    print({k:r[k] for k in ['requested_concurrency','attempts','generated','moderation_rejections','explicit_rate_limit_errors','wall_seconds','generated_per_hour','call_start_spread_ms']})
