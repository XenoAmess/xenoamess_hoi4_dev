"""User-authorized LOW work fills idle supply; HIGH retains dispatch precedence."""
import json
import subprocess
import sys
from tools.common import read_json

POLICY = 'high-first-idle-low-v1'


def low_enabled(root):
    path = root / 'mod_nailong/data/production-scheduling-policy.json'
    if not path.exists():
        return False
    body = read_json(path)
    assert body['id'] == POLICY and body['user_authorization_quote']
    return body['allow_low_when_no_immediate_high'] is True


def tier_allowed(root, entry):
    return entry['high_priority'] or low_enabled(root)


def service_retry_allowed(root, entry):
    """The user's HIGH refusal skip affects retries, not coverage or art approval."""
    path = root / 'mod_nailong/data/production-scheduling-policy.json'
    if not path.exists():
        return True
    body = read_json(path)
    assert body['id'] == POLICY and body['user_authorization_quote']
    return not (entry['high_priority'] and body.get('skip_service_refused_high_retries', False))


def low_feedback_enabled(root):
    path = root / 'mod_nailong/data/production-scheduling-policy.json'
    return path.exists() and low_enabled(root) and read_json(path).get('prioritize_ready_low_corrections', False)


def low_correction_in_item(root, item, priority):
    jobs = read_json(root / item['jobs'])
    if any(priority[j['key']]['high_priority'] for j in jobs):
        return False
    return any(j.get('journal') and (
        read_json(root / j['journal'])['attempts'][-1].get('edit_existing')
        or read_json(root / j['journal'])['attempts'][-1].get('replacement_reason')) for j in jobs)


def high_in_item(root, item, priority):
    return any(priority[j['key']]['high_priority'] for j in read_json(root / item['jobs']))


def append_prepared_windows(root, plan, batch, jobs, output):
    """One LOW per window permits HIGH rechecking between every LOW image call."""
    from tools.common import write_json
    write_json(output, jobs)
    priority = read_json(root / 'mod_nailong/data/production-priority.json')['sources']
    high = [j for j in jobs if priority[j['key']]['high_priority']]
    low = [j for j in jobs if not priority[j['key']]['high_priority']]
    if not low:
        plan['batches'].append({'batch': batch, 'jobs': output.relative_to(root).as_posix()})
        return
    assert low_enabled(root)
    groups = ([('high', high)] if high else []) + [('low' + str(n), [j]) for n, j in enumerate(low, 1)]
    for suffix, group in groups:
        name = batch + '-' + suffix
        path = root / ('runtime/production-' + name + '-jobs.json')
        assert not path.exists()
        write_json(path, group)
        plan['batches'].append({'batch': name, 'jobs': path.relative_to(root).as_posix()})


def immediate_high_work(root, expected_machine):
    """Read-only supply inspection, including exact due retries and existing intents."""
    priority = read_json(root / 'mod_nailong/data/production-priority.json')['sources']
    owner = root / 'runtime/rolling-production/owner.json'
    if owner.exists():
        state = read_json(owner.with_name(read_json(owner)['run_id'] + '.json'))
        plan = read_json(root / 'runtime/after128-continuous-plan.json')['batches']
        if any(high_in_item(root, item, priority) for item in plan[state['next_index']:]):
            return {'available': True, 'reason': 'prepared_HIGH'}
    for path in (root / 'runtime/production-queue/preparation/pending').glob('*.json'):
        if any(priority[k]['high_priority'] for k in read_json(path)['expected_source_keys']):
            return {'available': True, 'reason': 'observed_HIGH_preparation_intent'}
    from tools.fresh_source_observation_queue import candidates
    if candidates(root, high_only=True):
        return {'available': True, 'reason': 'allowed_unmade_HIGH_original'}
    from tools.rolling_production_queue import ready_art
    if any(priority[e['source_sha256']]['high_priority'] for _, e in ready_art(root, expected_machine)):
        return {'available': True, 'reason': 'reviewed_HIGH_art_correction'}
    scheduler = root / 'runtime/retry-scheduler/state.json'
    if scheduler.exists():
        result = subprocess.run([sys.executable, 'tools/retry_scheduler_next.py', '--inspect-only', '--high-only', '--limit', '8'],
                                cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace')
        assert result.returncode == 0, result.stderr
        body = json.loads(result.stdout)
        assert not body.get('pending_requires_reconciliation'), body
        if body['count']:
            return {'available': True, 'reason': 'exact_reviewed_due_HIGH_retry', 'count': body['count']}
    return {'available': False, 'reason': 'no_immediate_allowed_HIGH'}
