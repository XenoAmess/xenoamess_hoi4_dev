import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from tools.common import ROOT, machine_id, read_json, utc_now
from runtime import high131_import as importer
from runtime.high131_io import write_json


def main():
    worktree = (ROOT/'runtime/high131-import-20261028').resolve()
    parent = importer.git(worktree,'rev-parse','HEAD')
    plan = importer.build_plan(worktree,ROOT)
    completed = []
    for entry in plan['entries']:
        reference = {'review':entry['review'],'review_sha256':entry['review_sha256'],'attempt':entry['attempt'],'task_id':entry['task_id']}
        if importer.production_import_completed(worktree,entry['source_sha256'],reference):
            completed.append(entry['index'])
    if not 0<len(completed)<127:
        raise importer.ImportGateError('Parent recovery requires a verified partial import; use ordinary apply otherwise')
    importer.refresh_normalized_receipts(worktree,plan)
    recovery_commit = importer.stage_and_commit(worktree,plan,'Checkpoint HIGH131 import recovery',partial=True)
    commit = importer.rebase_import(worktree,recovery_commit,plan,complete_required=False)
    receipt = {
        'schema':'high131-parent-recovery-v1','machine_id':machine_id(),'observed_at_utc':utc_now(),
        'previous_parent':parent,'recovery_commit':recovery_commit,'commit':commit,
        'verified_complete_rows_before_rebase':len(completed),'completed_indices':completed,
        'remaining_person_sources':127-len(completed),'status':'local_recovery_rebased_push_pending',
        'new_image_generation_calls':0,'formal_import_complete':False,'LOW_history_preserved':True,
    }
    write_json(ROOT/'runtime/high131-parent-recovery.json',receipt)
    print(receipt)


if __name__=='__main__':
    main()
