"""Require a real rejected PNG before new art, including cancelled drafts."""
from pathlib import Path


def validate_art_boundary(history, key, current_sha, dispatch_dir, failures, family_histories):
    latest = history[-1]
    if latest['status'] == 'generated_rejected_visual_review':
        if latest.get('fullsize_sha256') != current_sha:
            raise ValueError('Rejected attempt does not match current raw master')
        return {'boundary': 'actual_returned_rejected_png', 'attempt': latest['number']}
    cancelled = []
    for attempt in reversed(history):
        if attempt['status'] != 'cancelled_before_generation':
            previous = attempt
            break
        cancelled.append(attempt)
    else:
        raise ValueError('Cancelled drafts have no preceding actual rejected PNG')
    if not cancelled or previous['status'] != 'generated_rejected_visual_review' or previous.get('fullsize_sha256') != current_sha:
        raise ValueError('New art requires a preceding actual rejected current PNG; failed requests keep their frozen payload and cooldown')
    blocked = {f['source_sha256'] for f in failures if f.get('status') == 'blocked' and not f.get('resolved_by_retry')}
    if key in blocked:
        raise ValueError('Source still has an unresolved service refusal')
    released = {}
    for attempt in cancelled:
        ledger = Path(dispatch_dir) / f'{key}-{attempt["number"]:03}.json'
        if attempt.get('actual_request_verification') or ledger.exists():
            raise ValueError('Cancelled draft has possible actual dispatch evidence; reconcile before new art')
        for family in attempt.get('deferred_service_families', []):
            other = family['source_sha256']
            evidence = family_histories.get(other, [])
            if other in blocked or not evidence:
                raise ValueError('Original deferred service family is unresolved or lacks evidence')
            returned = evidence[-1]
            if returned['status'] not in {'approved', 'generated_pending_visual_review', 'generated_rejected_visual_review'} or not returned.get('fullsize_sha256'):
                raise ValueError('Original deferred family has no latest actual successful PNG')
            released[other] = {'attempt': returned['number'], 'fullsize_sha256': returned['fullsize_sha256'], 'status': returned['status']}
    return {'boundary': 'uncalled_cancelled_drafts_after_actual_rejected_png',
            'actual_rejected_attempt': previous['number'],
            'cancelled_attempts': [a['number'] for a in reversed(cancelled)],
            'original_service_families_now_returned': released}
