"""Rebase a validated checkpoint in a small isolated Git worktree.

Production may keep writing call journals in the primary worktree. Never stash,
reset, rebase or replace that live worktree to publish an immutable checkpoint.
"""
from pathlib import Path
import hashlib
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, machine_id, utc_now, write_json


def publication_identifier(batch, sequence):
    """Bound only the worktree label; keep the complete batch in its receipt."""
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*', batch):
        raise ValueError('Invalid publication batch identifier')
    if type(sequence) is not int or sequence < 1:
        raise ValueError('Expected a positive publication sequence')
    label = batch + '-network-' + str(sequence)
    if len(label) > 101:
        label = label[:80] + '-' + hashlib.sha256(label.encode('ascii')).hexdigest()[:20]
    return label


def _git(*args, cwd=None):
    result = subprocess.run(
        ['git', '-c', 'gc.auto=0', '-c', 'maintenance.auto=false', *args],
        cwd=cwd or ROOT, capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=180,
    )
    if result.returncode:
        raise RuntimeError(result.stdout + '\n' + result.stderr)
    return result.stdout.strip()


def rebase_validated_commit(commit, batch):
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Expected the full immutable validated commit SHA')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,100}', batch):
        raise ValueError('Invalid checkpoint identifier')
    assert _git('branch', '--show-current') == 'master'
    origin = _git('remote', 'get-url', 'origin').rstrip('/').lower()
    assert origin in {
        'https://github.com/xenoamess/xenoamess_hoi4_dev.git',
        'git@github.com:xenoamess/xenoamess_hoi4_dev.git',
    }, 'Verify the HOI4 repository before synchronizing'
    assert _git('rev-parse', '--verify', commit + '^{commit}') == commit
    parent = (ROOT / 'runtime/production-sync').resolve()
    path = (parent / (batch + '-' + commit[:12])).resolve()
    assert path.parent == parent and parent.is_relative_to(ROOT.resolve())
    parent.mkdir(parents=True, exist_ok=True)
    assert not path.exists(), 'Existing isolated synchronization needs reconciliation'
    receipt = {
        'machine_id': machine_id(), 'started_at_utc': utc_now(),
        'validated_commit': commit, 'batch': batch,
        'primary_worktree_untouched': True,
        'isolated_worktree': str(path),
        'sparse_checkout_paths': ['/AGENTS.md', '/README.md', '/.gitignore'],
        'scope': 'Bounded root-file checkout; raw PNGs remain in shared Git objects and are not materialized here. No stash, reset, force push or public history rewrite.',
    }
    receipt_path = parent / (batch + '-' + commit[:12] + '-receipt.json')
    write_json(receipt_path, receipt)
    try:
        _git('fetch', 'origin')
        receipt['origin_master'] = _git('rev-parse', 'origin/master')
        _git('worktree', 'add', '--detach', '--no-checkout', str(path), commit)
        _git('sparse-checkout', 'set', '--no-cone', '--no-sparse-index',
             '/AGENTS.md', '/README.md', '/.gitignore', cwd=path)
        # --no-checkout leaves a new worktree's index empty. Populate it with
        # sparse rules already active, so raw PNGs are never checked out.
        _git('read-tree', '-mu', 'HEAD', cwd=path)
        assert not _git('status', '--porcelain', cwd=path)
        receipt['rebase_output'] = _git('rebase', 'origin/master', cwd=path)
        synchronized = _git('rev-parse', 'HEAD', cwd=path)
        receipt['synchronized_commit'] = synchronized
        if synchronized != commit:
            receipt['status'] = 'revalidation_required_after_remote_rebase'
            raise RuntimeError('Remote changes produced a different commit; validate that result before publishing. The live primary worktree is unchanged.')
        _git('merge-base', '--is-ancestor', 'origin/master', commit)
        receipt['status'] = 'validated_commit_rebased_unchanged_fast_forward_eligible'
        receipt['completed_at_utc'] = utc_now()
        write_json(receipt_path, receipt)
        return dict(receipt, receipt_file=receipt_path.relative_to(ROOT).as_posix())
    except Exception as error:
        receipt.setdefault('status', 'synchronization_failed')
        receipt.update(error=str(error), observed_at_utc=utc_now())
        write_json(receipt_path, receipt)
        raise


if __name__ == '__main__':
    import json
    print(json.dumps(rebase_validated_commit(sys.argv[1], sys.argv[2]), ensure_ascii=True))
