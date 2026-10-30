import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.common import machine_id, read_json, utc_now, write_json

importer = importlib.import_module("mod_nailong.experiments.evolink-low2-20261030.tools.low2_import")


def main():
    if len(sys.argv) not in {2, 3}:
        raise SystemExit("usage: low2_commit_receipt.py WORKTREE [IMPORT_COMMIT]")
    worktree = Path(sys.argv[1]).resolve()
    original = sys.argv[2] if len(sys.argv) == 3 else importer.git(worktree, "rev-parse", "HEAD")
    importer.require(importer.git(worktree, "merge-base", "--is-ancestor", original, "HEAD") == "", "Import commit is not contained in HEAD")
    parent = importer.git(worktree, "show", "-s", "--format=%P", original)
    importer.require(parent == "398db2a4959364c4303f9d912397b58df5fe907a", "Unexpected original parent; refusing to create a duplicate import commit")
    plan = importer.build_plan(worktree, ROOT)
    importer.verify_import(worktree, plan)
    index = read_json(worktree / importer.FULLSIZE)
    base_index = json.loads(importer.git(worktree, "show", f"{parent}:{importer.FULLSIZE}"))
    importer.require(index["count"] == base_index["count"] + 2 == 7422, "Final original count differs")
    importer.require(index["original_png_bytes"] == base_index["original_png_bytes"] + sum(row["bytes"] for row in plan["entries"]), "Final original bytes differ")
    synchronization_error = None
    try:
        final_commit = importer.synchronize(worktree, original)
    except importer.ImportErrorWithEvidence as error:
        final_commit = original
        synchronization_error = str(error)
    importer.verify_import(worktree, plan)
    changed = set(importer.git(worktree, "diff", "--name-only", parent, original).splitlines())
    allowed = {importer.GENERATED, importer.QUEUE, importer.FULLSIZE, *importer.DOCS, importer.TEST,
               *(f"mod_nailong/assets/generated_fullsize/{row['generated_fullsize_sha256']}.png" for row in plan["entries"]),
               *(f"mod_nailong/assets/portraits/{row['source_sha256']}.png" for row in plan["entries"]),
               *(f"mod_nailong/data/generation-requests/{row['source_sha256']}.json" for row in plan["entries"])}
    importer.require(all(relative in allowed or relative.startswith(importer.EXPERIMENT + "/") for relative in changed), "Original commit contains an unrelated path")
    receipt = {
        "schema": "low2-kimi-production-import-receipt-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
        "status": "committed_push_pending", "parent_commit": parent, "original_import_commit": original,
        "import_commit": final_commit, "worktree": str(worktree), "imported_sources": [row["source_sha256"] for row in plan["entries"]],
        "approved_person_sources": 2, "resource_instances": sum(len(row["source_assets"]) for row in plan["entries"]),
        "fullsize_original_count": index["count"], "fullsize_original_bytes": index["original_png_bytes"],
        "new_generation_calls_for_import": 0, "unrelated_rows_preserved": True,
        "builtin_retry_counts_preserved": [0, 0],
        "commit_method": "Verified scoped index; git write-tree + commit-tree + old-value-guarded update-ref after porcelain timeouts; original single parent, no history rewrite",
        "fetch_proxy_after_tls_failure": "http://127.0.0.1:10808",
        "synchronization_error": synchronization_error,
        "ordinary_git_commit": True, "push_performed": False, "remote_original_verification_claimed": False, "runtime_acceptance_claimed": False,
    }
    write_json(ROOT / "runtime/low2-evolink-20261030/import-receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
