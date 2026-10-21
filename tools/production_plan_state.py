"""Record the sole image producer's batch boundary and idle states atomically."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, machine_id, read_json, utc_now, write_json

RUN_IDS = frozenset({'after124-20261020', 'after128-20261020'})
STATES = frozenset({
    'running', 'batch_completed', 'plan_drained',
    'stopped_requires_reconciliation', 'waiting_for_prepared_jobs',
    'producer_stopped_at_batch_boundary',
})


def append_state(run_id: str, state: str, batch: str, index: int,
                 *, root: Path = ROOT) -> dict:
    if run_id not in RUN_IDS or state not in STATES:
        raise ValueError('Unknown production run or state')
    if not isinstance(index, int) or index < 0 or not batch:
        raise ValueError('A nonnegative plan index and batch are required')
    path = root / 'runtime' / f'{run_id}-state.json'
    data = read_json(path) if path.exists() else {'run_id': run_id, 'history': []}
    entry = {'machine_id': machine_id(), 'observed_at_utc': utc_now(),
             'state': state, 'batch': batch, 'index': index}
    data['history'].append(entry)
    data['current'] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=path.stem + '-', suffix='.writing.json',
                                     dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        write_json(temporary, data)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return entry


def main() -> None:
    run_id, state, batch, raw_index = sys.argv[1:]
    append_state(run_id, state, batch, int(raw_index))
    print(state, batch, raw_index)


if __name__ == '__main__':
    main()
