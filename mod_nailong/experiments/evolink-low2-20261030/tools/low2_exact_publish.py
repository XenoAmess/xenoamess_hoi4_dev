import argparse
import importlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from runtime import high131_exact_api_publish as exact
from tools.common import machine_id, read_json, utc_now, write_json

BASE = "398db2a4959364c4303f9d912397b58df5fe907a"
EXPECTED_TARGET = "4f1e415988ccf2164fab0d6fad851d616a367387"
EXPECTED_IMPORT = "c17f5089f15042141c18295d5e6c939eaf997182"
EXPERIMENT = "mod_nailong/experiments/evolink-low2-20261030"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def scoped_paths(worktree, base, target):
    changed = set(exact.git_text("-C", str(worktree), "diff", "--name-only", base, target).splitlines())
    approved = read_json(worktree / EXPERIMENT / "approved-masters.json")
    keys = {row["source_sha256"] for row in approved["entries"]}
    digests = {row["generated_fullsize_sha256"] for row in approved["entries"]}
    allowed = {
        "mod_nailong/data/generated.json", "mod_nailong/data/image-retry-queue.json", "mod_nailong/data/fullsize-files.json",
        "docs/handoffs/2026-10-30-low-two-pending.md", "docs/handoffs/low2-kimi-evolink-2026-10-30.md", "tests/test_low2_evolink.py",
        *(f"mod_nailong/data/generation-requests/{key}.json" for key in keys),
        *(f"mod_nailong/assets/portraits/{key}.png" for key in keys),
        *(f"mod_nailong/assets/generated_fullsize/{digest}.png" for digest in digests),
    }
    require(all(relative in allowed or relative.startswith(EXPERIMENT + "/") for relative in changed), f"Unexpected LOW2 publication path: {sorted(changed)}")
    require(not any(Path(relative).name == "AGENTS.md" for relative in changed), "Permission document changed")
    return changed


def prepare(worktree, base, target):
    worktree = Path(worktree).resolve()
    require(worktree.parent == (ROOT / "runtime").resolve(), "Publish only from the isolated runtime worktree")
    require(re.fullmatch(r"[0-9a-f]{40}", base) and re.fullmatch(r"[0-9a-f]{40}", target), "Expected full fixed commits")
    require(base == BASE and target == EXPECTED_TARGET, "Unexpected LOW2 publication endpoints")
    require(exact.git_text("-C", str(worktree), "rev-parse", "HEAD") == target, "Worktree HEAD differs from target")
    require(exact.git_text("-C", str(worktree), "show", "-s", "--format=%P", EXPECTED_IMPORT) == base, "Import parent differs")
    require(exact.git_text("-C", str(worktree), "merge-base", "--is-ancestor", EXPECTED_IMPORT, target) == "", "Import is not contained in target")
    exact.ROOT = worktree
    exact.DELIVERY_PATHS = scoped_paths(worktree, base, target)
    api = exact.Api(runner=exact.Api._run_gh)
    receipt = worktree / "runtime/low2-evolink-20261030/exact-object-publish.json"
    publisher = exact.ExactApiPublisher(base, target, "delivery", "low2-20261030", api=api, receipt_path=receipt)
    require(len(publisher.commits) == 3, "Expected exactly the import, documentation and validation-evidence commits")
    return publisher


def main():
    parser = argparse.ArgumentParser(description="Publish the two exact LOW2 commits through the official GitHub object API, with force=false.")
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    publisher = prepare(args.worktree, BASE, EXPECTED_TARGET)
    if args.check:
        print(json.dumps({"status": "ready_for_exact_nonforced_publication", "commits": len(publisher.commits), "changed_files": len(publisher.allowed), "network_or_ref_changes": 0}))
        return 0
    result = publisher.publish()
    require(result["remote_master_observed"] == EXPECTED_TARGET and result["status"] in {"published_pending_original_readback", "already_public_pending_original_readback"}, "Exact publication is not confirmed")
    receipt = {
        "schema": "low2-kimi-exact-api-publish-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
        "status": result["status"], "base_commit": BASE, "import_commit": EXPECTED_IMPORT, "final_commit": EXPECTED_TARGET,
        "remote_master": result["remote_master_observed"], "ref_updated": result["ref_updated"],
        "method": "Official GitHub Git Data API through gh; exact blob/tree/commit SHA and one-parent lineage verified; PATCH refs/heads/master with force=false",
        "forced_push": False, "merge_commit": False, "history_rewrite": False,
        "helper_receipt": "runtime/low2-delivery-20261030/runtime/low2-evolink-20261030/exact-object-publish.json",
        "helper_schema_note": "The reused exact-object helper has a high131 schema label; this receipt is only for the two scoped LOW2 commits",
        "new_image_generation_calls": 0, "original_png_readback_claimed": False, "runtime_acceptance_claimed": False,
    }
    write_json(ROOT / "runtime/low2-evolink-20261030/publish-receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
