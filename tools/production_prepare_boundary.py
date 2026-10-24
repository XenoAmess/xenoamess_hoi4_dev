"""Consume one SHA-bound art-preparation intent at the sole producer's safe boundary."""
import argparse
from contextlib import redirect_stdout
import io
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json


def consume(root, expected_machine, runner=None):
    folder = root / 'runtime/production-queue/preparation'
    pending = sorted((folder / 'pending').glob('*.json'))
    from tools.production_priority_gate import low_enabled
    if pending and low_enabled(root):
        priority=read_json(root/'mod_nailong/data/production-priority.json')['sources']
        pending.sort(key=lambda p:not any(priority[k]['high_priority'] for k in read_json(p)['expected_source_keys']))
    if not pending:
        return {'prepared': False, 'reason': 'no_pending_intent'}
    for path in (root / 'runtime/production-queue/dispatch').glob('*.json'):
        if read_json(path).get('status') == 'calling':
            return {'prepared': False, 'reason': 'actual_call_in_progress'}
    # Invoked only after the producer's checkpoint barrier and imports have cleared.
    path = pending[0]
    intent = read_json(path)
    scripts={'reviewed_art_repairs':'tools/prepare_reviewed_art_repairs.py',
             'reviewed_original_replacements':'tools/prepare_reviewed_original_replacements.py',
             'reviewed_fresh_sources':'tools/prepare_reviewed_fresh_sources.py',
             'reviewed_transport_retry':'tools/prepare_reviewed_transport_retry.py'}
    script = root / scripts.get(intent.get('kind'),'tools/invalid-preparation-kind')
    claimed = folder / 'claimed' / path.name
    claimed.parent.mkdir(parents=True, exist_ok=True)
    assert not claimed.exists(), 'Never replay a claimed preparation intent'
    path.rename(claimed)
    receipt = {'machine_id': expected_machine, 'intent': intent,
               'claimed_at_utc': utc_now(), 'scope': 'Local preparation only; no image call or retry claim.'}
    try:
        assert intent['machine_id'] == expected_machine
        assert intent['kind'] in scripts
        assert file_sha256(script) == intent['preparer_sha256']
        assert isinstance(intent['arguments'], list) and all(isinstance(a, str) for a in intent['arguments'])
        for proof in intent['evidence']:
            target = (root / proof['path']).resolve()
            assert target.is_relative_to(root.resolve())
            assert file_sha256(target) == proof['sha256']
        if runner is None:
            result = subprocess.run([sys.executable, str(script), *intent['arguments']], cwd=root,
                                    capture_output=True, text=True, encoding='utf-8', errors='replace')
        else:
            result = runner(intent)
        receipt.update(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
        assert result.returncode == 0, 'Preparation failed; preserve claimed intent for reconciliation'
        jobs = root / intent['expected_jobs_file']
        assert jobs.resolve().is_relative_to(root.resolve())
        assert [j['key'] for j in read_json(jobs)] == intent['expected_source_keys']
        receipt.update(status='prepared', jobs_sha256=file_sha256(jobs), completed_at_utc=utc_now())
    except Exception as error:
        receipt.update(status='preparation_requires_reconciliation', error=str(error), completed_at_utc=utc_now())
    output = root / 'mod_nailong/data/production-preparation-receipts' / path.name
    assert not output.exists()
    write_json(output, receipt)
    return {'prepared': receipt['status'] == 'prepared', 'status': receipt['status'],
            'receipt': output.relative_to(root).as_posix()}


def run_boundary(root, expected_machine, *, apply_reviews=None, runner=None, refill=None):
    """Apply staged reviews, then consume an intent in one sole-writer process."""
    if apply_reviews is None:
        return consume(root, expected_machine, runner)
    for path in (root / 'runtime/production-queue/dispatch').glob('*.json'):
        if read_json(path).get('status') == 'calling':
            return {'prepared': False, 'reason': 'actual_call_in_progress',
                    'reviews_applied': False}
    review_stdout = io.StringIO()
    with redirect_stdout(review_stdout):
        review_result = apply_reviews()
    result = consume(root, expected_machine, runner)
    if result.get('status') != 'preparation_requires_reconciliation':
        if refill is None and root == ROOT:
            from tools.rolling_production_queue import refill_reviewed_backlog
            refill = refill_reviewed_backlog
        if refill is not None:
            result['backlog_refill'] = refill(root, expected_machine)
    result['review_application'] = review_result
    if review_stdout.getvalue():
        result['review_application_stdout'] = review_stdout.getvalue()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply-reviews', action='store_true')
    args = parser.parse_args()
    applier = None
    if args.apply_reviews:
        from mod_nailong.tools.production_queue import apply_reviews
        applier = apply_reviews
    print(json.dumps(run_boundary(ROOT, machine_id(), apply_reviews=applier), ensure_ascii=True))
