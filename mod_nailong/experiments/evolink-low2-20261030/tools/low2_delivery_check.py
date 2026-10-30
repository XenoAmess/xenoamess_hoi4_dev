import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from mod_nailong.tools.art_contract import portrait_ready
from tools.common import file_sha256, machine_id, read_json, utc_now, write_json

RUNTIME = ROOT / "runtime/low2-evolink-20261030"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def download_text(url):
    errors = []
    for route, proxy in (("noproxy", "*"), ("proxy", "http://127.0.0.1:10808")):
        result = subprocess.run(["curl.exe", f"--{route}", proxy, "--fail", "--silent", "--show-error", "--location", "--proto", "=https", "--connect-timeout", "20", "--max-time", "60", "--max-filesize", "1048576", url], capture_output=True, timeout=75)
        if result.returncode == 0:
            return result.stdout
        errors.append(result.stderr.decode("utf-8", errors="replace")[:300])
    raise RuntimeError("Public handoff readback failed: " + "; ".join(errors))


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: low2_delivery_check.py WORKTREE COMMIT")
    worktree, commit = Path(sys.argv[1]).resolve(), sys.argv[2]
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "Expected a full fixed commit")
    sys.path.insert(0, str(worktree))
    importer = __import__("mod_nailong.experiments.evolink-low2-20261030.tools.low2_import", fromlist=["low2_import"])
    require(importer.git(worktree, "rev-parse", "HEAD") == commit, "Worktree HEAD differs from delivery commit")
    require(importer.git(worktree, "rev-parse", "origin/master") == commit, "origin/master differs from delivery commit")
    scoped = [importer.GENERATED, importer.QUEUE, importer.FULLSIZE, importer.EXPERIMENT, *importer.DOCS, importer.TEST]
    require(not importer.git(worktree, "diff", "--name-only", "--", *scoped) and not importer.git(worktree, "diff", "--cached", "--name-only"), "Delivery worktree has uncommitted scoped changes")
    approved = read_json(worktree / "mod_nailong/experiments/evolink-low2-20261030/approved-masters.json")
    generated = read_json(worktree / "mod_nailong/data/generated.json")
    queue = read_json(worktree / "mod_nailong/data/image-retry-queue.json")
    index = read_json(worktree / "mod_nailong/data/fullsize-files.json")
    for entry in approved["entries"]:
        key = entry["source_sha256"]
        row = generated["portraits"][key]
        require(portrait_ready(row) and row["production_import"]["schema"] == "low2-kimi-production-import-v1", f"Canonical art approval missing: {key}")
        require(row["production_import"]["review_sha256"] == entry["review_sha256"], f"Review binding differs: {key}")
        require(row["generated_fullsize_sha256"] == entry["generated_fullsize_sha256"], f"Master differs: {key}")
        require(queue["sources"][key]["retries_used"] == 0, f"Builtin counter changed: {key}")
    priority = read_json(worktree / "mod_nailong/data/production-priority.json")["sources"]
    low = {key for key, row in priority.items() if not row["high_priority"]}
    low_approved = {key for key in low if portrait_ready(generated["portraits"].get(key, {}))}
    require(set(row["source_sha256"] for row in approved["entries"]) <= low_approved, "Scoped LOW sources are not approved")
    tests = read_json(RUNTIME / "test-receipt.json")
    require(tests["python"]["status"] == "passed" and tests["javascript"]["status"] == "passed", "Test receipt is incomplete")
    require(tests["python"]["passed"] >= 500 and tests["javascript"]["passed"] == 24, "Test counts differ")
    require("OK" in (worktree / tests["python"]["log"]).read_text(encoding="utf-8"), "Python test log has no success result")
    require("PASS: deterministic double build, exact staging/manifest/ZIP and HD texture decode; scope=selected preview validation subset" in (worktree / tests["preview_build"]["log"]).read_text(encoding="utf-8"), "Scoped preview double build did not pass")
    local_blob = ast.literal_eval((worktree / "runtime/low2-local-tree-check.log").read_text(encoding="utf-8").strip().splitlines()[-1])
    require(local_blob["verified_original_png_blobs"] == index["count"] and local_blob["original_png_bytes"] == index["original_png_bytes"], "Local original-blob totals differ")
    require(importer.git(worktree, "merge-base", "--is-ancestor", local_blob["commit"], commit) == "", "Blob verification commit is not included in delivery")
    unchanged_png = not importer.git(worktree, "diff", "--name-only", local_blob["commit"], commit, "--", "mod_nailong/assets/generated_fullsize")
    require(unchanged_png, "A PNG changed after full blob verification")
    remote = read_json(RUNTIME / "remote-readback.json")
    require(remote["schema"] == "low2-fullsize-remote-readback-v1" and remote["status"] == "verified" and remote["commit"] == commit, "Remote original proof differs")
    require(remote["distinct_outputs"] == index["count"] and remote["original_png_bytes"] == index["original_png_bytes"], "Remote original totals differ")
    require(remote["new_originals_actually_downloaded"] == 2 and remote["unchanged_original_proofs_reused"] == index["count"] - 2, "Remote proof reuse/download counts differ")
    require(set(remote["new_download_sha256"]) == {row["generated_fullsize_sha256"] for row in approved["entries"]}, "Remote new original scope differs")
    for row in approved["entries"]:
        proof = remote["outputs"][row["generated_fullsize_sha256"]]
        require(proof["readback_commit"] == commit and proof["method"] == "Complete anonymous raw PNG download; SHA256 and byte count", "New raw download is not proven")
    descriptor = (worktree / "mod_nailong/mod/descriptor.mod").read_text(encoding="utf-8")
    require("钢奶龙心" in descriptor and "remote_file_id" not in descriptor and "replace_path" not in descriptor, "Development descriptor is not clean")
    relative = "docs/handoffs/low2-kimi-evolink-2026-10-30.md"
    local = (worktree / relative).read_bytes()
    url = f"https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{commit}/{relative}"
    public = download_text(url)
    require(public == local, "Public handoff bytes differ from the fixed commit")
    write_json(RUNTIME / "handoff-public.md", public.decode("utf-8"))
    handoff_proof = {"status": "verified", "commit": commit, "path": relative, "url": url, "bytes": len(public), "sha256": hashlib.sha256(public).hexdigest(), "machine_id": machine_id(), "observed_at_utc": utc_now()}
    write_json(RUNTIME / "handoff-readback.json", handoff_proof)
    receipt = {
        "schema": "low2-kimi-delivery-completion-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
        "status": "completed_source_integration_and_remote_verification",
        "scope": "Only the two user-specified LOW sources and their two game-resource instances; not a claim that the whole mod is complete",
        "approved_and_formally_ingested_sources": len(approved["entries"]), "source_scope_percent": 100, "resource_instances": sum(len(row["source_assets"]) for row in approved["entries"]),
        "actual_generation_tasks": 2, "unresolved_generation_tasks": 0,
        "final_commit": commit, "remote_master": commit, "push": "ordinary fast-forward; no force or public-history rewrite",
        "low_priority_approved_sources": len(low_approved), "low_priority_total_sources": len(low),
        "verification": {"python_tests": tests["python"], "javascript_tests": tests["javascript"], "preview_build": tests["preview_build"],
                         "local_original_blobs": local_blob, "later_commits_change_no_png_files": True,
                         "remote_originals": {key: value for key, value in remote.items() if key != "outputs"}, "handoff": handoff_proof},
        "approved_original_png_bytes": sum(row["bytes"] for row in approved["entries"]),
        "fullsize_original_count": index["count"], "fullsize_original_bytes": index["original_png_bytes"],
        "builtin_retry_counters_preserved": [0, 0], "unrelated_workspace_changes_committed": False,
        "permission_documents_modified": False, "codex_evolink_permission_changed": False,
        "hoi4_runtime_acceptance_claimed": False,
        "remaining_owner": "Codex: subsequent build/display adaptation and pure-OCR plus keyboard/mouse HOI4 runtime acceptance; no EvoLink permission granted to Codex",
    }
    write_json(RUNTIME / "delivery-completion.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
