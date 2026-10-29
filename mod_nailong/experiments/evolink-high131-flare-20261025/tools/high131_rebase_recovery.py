import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from tools.common import ROOT,machine_id,read_json,utc_now
from runtime import high131_import as importer
from runtime.high131_io import write_json


def main():
    worktree = ROOT/'runtime/high131-import-20261028'
    prior = read_json(ROOT/'runtime/high131-parent-recovery.json')
    in_progress = importer.rebase_in_progress(worktree)
    previous = prior['commit'] if in_progress else importer.git(worktree,'rev-parse','HEAD')
    if in_progress:
        plan = {'entries':read_json(worktree/importer.EXPERIMENT/'approved-masters.json')['entries']}
    else:
        plan = importer.build_plan(worktree,ROOT)
        importer.refresh_normalized_receipts(worktree,plan)
    commit = importer.rebase_import(worktree,previous,plan,complete_required=False)
    if in_progress and commit==previous:
        raise importer.ImportGateError('The partial HIGH recovery was not actually applied')
    receipt = {
        'schema':'high131-recovery-rebase-v1','machine_id':machine_id(),'observed_at_utc':utc_now(),
        'previous_recovery_commit':previous,'commit':commit,
        'verified_complete_rows_from_prior_recovery':prior['verified_complete_rows_before_rebase'],
        'remaining_person_sources':prior['remaining_person_sources'],
        'new_image_generation_calls':0,'formal_import_complete':False,
        'status':'local_recovery_rebased_push_pending',
    }
    write_json(ROOT/'runtime/high131-latest-recovery.json',receipt)
    print(receipt)


if __name__=='__main__':
    main()
