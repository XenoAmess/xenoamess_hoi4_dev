import argparse
import copy
import importlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from mod_nailong.tools import master_archive, master_files, portraits
from mod_nailong.tools.art_contract import portrait_ready
from tools.common import file_sha256, machine_id, read_json, utc_now, write_json

shared = importlib.import_module("mod_nailong.experiments.evolink-low7-20261030.tools.low7_import")
require = shared.require
bound = shared.bound
git = shared.git
ImportErrorWithEvidence = shared.ImportErrorWithEvidence


def path(root, value):
    return shared.path(root, str(value))


EXPERIMENT = "mod_nailong/experiments/evolink-low2-20261030"
GENERATED = "mod_nailong/data/generated.json"
QUEUE = "mod_nailong/data/image-retry-queue.json"
FULLSIZE = "mod_nailong/data/fullsize-files.json"
DOCS = ["docs/handoffs/2026-10-30-low-two-pending.md", "docs/handoffs/low2-kimi-evolink-2026-10-30.md"]
TEST = "tests/test_low2_evolink.py"
RUNTIME = Path("runtime/low2-evolink-20261030")


def build_plan(worktree, support=ROOT):
    worktree = Path(worktree).resolve()
    approved_relative = f"{EXPERIMENT}/approved-masters.json"
    approved = read_json(path(support, approved_relative))
    scope = read_json(path(support, f"{EXPERIMENT}/scope.json"))
    verification = read_json(path(support, RUNTIME / "final-verification.json"))
    require(verification["status"] in {"two_sources_generated_reviewed_and_archived_pending_canonical_import_and_git_publication", "two_sources_generated_reviewed_integrated_pending_publication"}, "Generation/art verification is incomplete")
    require(verification["unresolved_generation_tasks"] == 0 and verification["scoped_tests"]["passed"] >= 6, "Unresolved calls or scoped tests remain")
    require(approved["schema"] == "low2-kimi-approved-masters-v1" and approved["count"] == len(approved["entries"]) == scope["source_count"] == 2, "Scope must contain exactly two approved sources")
    require(approved["formal_canonical_import_count"] == 0, "Input already claims canonical import")
    require(file_sha256(path(support, scope["handoff"])) == scope["handoff_sha256"], "Handoff binding changed")
    delivery_relative = f"{EXPERIMENT}/delivery-authorization.json"
    delivery = read_json(path(support, delivery_relative))
    require(delivery["user_instruction_quote"] == "现在开始恢复允许你使用git。做完后自己提交、推送。", "Git resume authorization is missing")
    require(delivery["source_count"] == 2 and delivery["unrelated_workspace_changes_must_not_be_committed"] is True, "Delivery scope differs")
    require(delivery["codex_tool_permission_changed"] is False and delivery["permission_documents_modified"] is False, "Permission boundary changed")
    catalog = read_json(path(worktree, "mod_nailong/data/catalog.json"))
    generated = read_json(path(support, GENERATED))
    queue = read_json(path(support, QUEUE))
    entries = []
    for entry in approved["entries"]:
        key = entry["source_sha256"]
        source = next(row for row in scope["entries"] if row["source_sha256"] == key)
        assets = [row for row in catalog["assets"] if row["source_sha256"] == key]
        require(sorted(row["path"] for row in assets) == sorted(entry["source_assets"]), f"Catalog assets differ: {key}")
        require(source["source_assets"] == entry["source_assets"], f"Scope assets differ: {key}")
        master = bound(support, entry["generated_fullsize_image"], entry["generated_fullsize_sha256"])
        require(master.stat().st_size == entry["bytes"], f"Master byte count differs: {key}")
        for field in ("request", "result", "execution", "review", "evidence"):
            bound(support, entry[field], entry[field + "_sha256"])
        require(file_sha256(path(support, entry["prompt_file"])) == entry["prompt_sha256"], f"Prompt binding differs: {key}")
        request = read_json(path(support, entry["request"]))
        result = read_json(path(support, entry["result"]))
        execution = read_json(path(support, entry["execution"]))
        review = read_json(path(support, entry["review"]))
        require(request["model"] == "gpt-image-2.5-flare" and request["background"] == "opaque" and request["n"] == 1, f"Generation route differs: {key}")
        require(request["prompt"] == entry["prompt"] and request["image_urls"] == [row["url"] for row in entry["inputs"]], f"Request/prompt/inputs differ: {key}")
        require(result["task_id"] == entry["task_id"] and result["sha256"] == entry["generated_fullsize_sha256"] and result["bytes"] == entry["bytes"], f"Result binding differs: {key}")
        require(execution["status"] == "completed" and execution["exit_code"] == 0 and execution["attempt"] == "external-01", f"Execution incomplete: {key}")
        require(execution["task_id"] == entry["task_id"] and execution["output_sha256"] == entry["generated_fullsize_sha256"], f"Execution binding differs: {key}")
        decisions = [row for row in review["entries"] if row["source_sha256"] == key]
        require(len(decisions) == 1, f"Missing current review: {key}")
        decision = decisions[0]
        require(decision["decision"] == "approved_for_production" and decision["output_sha256"] == entry["generated_fullsize_sha256"], f"Review output differs: {key}")
        require(decision["remaining_reasons"] == [] and decision["production_import_pending"] is True and decision["rgb_art_approved"] is True, f"Unresolved art issue: {key}")
        require(decision["hair_features"] == {"policy": "hair-features-v1", "status": "approved"}, f"Hair approval missing: {key}")
        require(decision["collar_fit"] == {"policy": "collar-fit-v1", "status": "approved"}, f"Collar approval missing: {key}")
        require(decision["source_alpha_extrema"] == [255, 255] and decision["returned_alpha_extrema"] is None and decision["source_alpha_repair_performed"] is False, f"Alpha decision differs: {key}")
        for item in entry["inputs"]:
            bound(support, item["path"], item["sha256"])
        require(queue["sources"][key]["retries_used"] == 0, f"Builtin retry count changed: {key}")
        current = generated["portraits"].get(key)
        require(current is None or current.get("generated_fullsize_sha256") != entry["generated_fullsize_sha256"], f"Input is already canonically imported: {key}")
        require(entry["import_schema"] == "low2-kimi-production-import-v1" and entry["edit_existing"] is False and entry["recovery"] is None, f"Unexpected LOW2 import route: {key}")
        entries.append({**entry, "previous_generated_row": copy.deepcopy(current), "previous_queue_row": copy.deepcopy(queue["sources"][key])})
    require(len({row["source_sha256"] for row in entries}) == 2, "Duplicate sources")
    return {
        "schema": "low2-production-import-plan-v1", "root": str(worktree), "support_root": str(Path(support).resolve()),
        "source_count": len(entries), "resource_instances": sum(len(row["source_assets"]) for row in entries),
        "approved_manifest": approved_relative, "approved_manifest_sha256": file_sha256(path(support, approved_relative)),
        "delivery_authorization": delivery_relative, "delivery_authorization_sha256": file_sha256(path(support, delivery_relative)), "entries": entries,
    }


def copy_scoped_files(worktree, support, plan):
    worktree = Path(worktree).resolve()
    destination = path(worktree, EXPERIMENT)
    source_directory = path(support, EXPERIMENT)
    if destination.exists():
        expected = {item.relative_to(source_directory) for item in source_directory.rglob("*") if item.is_file() and "__pycache__" not in item.parts and item.suffix not in {".pyc", ".tmp"}}
        actual = {item.relative_to(destination) for item in destination.rglob("*") if item.is_file() and "__pycache__" not in item.parts and item.suffix not in {".pyc", ".tmp"}}
        require(not (actual - expected), "Unexpected scoped evidence file; reconcile before resume")
        for relative in expected:
            target = destination / relative
            if target.exists() and target.read_bytes() != (source_directory / relative).read_bytes():
                require(relative.parts[0] == "tools" and relative.suffix == ".py", f"Scoped evidence changed: {relative}")
                target.write_bytes((source_directory / relative).read_bytes())
            elif not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_directory / relative, target)
    else:
        shutil.copytree(source_directory, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.tmp"))
    for relative in [*DOCS, TEST]:
        target, original = path(worktree, relative), path(support, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != original.read_bytes():
            require(relative == TEST, f"Existing scoped file differs: {relative}")
            target.write_bytes(original.read_bytes())
        elif not target.exists():
            shutil.copyfile(original, target)
    for entry in plan["entries"]:
        target = path(worktree, entry["generated_fullsize_image"])
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(path(support, entry["generated_fullsize_image"]), target)
        bound(worktree, entry["generated_fullsize_image"], entry["generated_fullsize_sha256"])
    write_json(ROOT / RUNTIME / "evidence-copy.json", {
        "schema": "low2-scoped-evidence-copy-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
        "worktree": str(worktree), "approved_manifest_sha256": plan["approved_manifest_sha256"],
        "delivery_authorization_sha256": plan["delivery_authorization_sha256"], "sources": plan["source_count"], "unrelated_workspace_files_copied": False,
    })


def import_sources(worktree, plan):
    worktree = Path(worktree).resolve()
    require(Path(plan["root"]) == worktree, "Plan belongs to a different worktree")
    support = Path(plan["support_root"])
    shared.configure_portraits(worktree)
    generated = read_json(path(worktree, GENERATED))
    queue = read_json(path(worktree, QUEUE))
    keys = {row["source_sha256"] for row in plan["entries"]}
    outside_generated = {key: copy.deepcopy(row) for key, row in generated["portraits"].items() if key not in keys}
    outside_queue = {key: copy.deepcopy(row) for key, row in queue["sources"].items() if key not in keys}
    imported = []
    for entry in plan["entries"]:
        key = entry["source_sha256"]
        require(entry["previous_generated_row"] is None and entry["previous_queue_row"]["retries_used"] == 0, f"Unexpected existing production or changed builtin count: {key}")
        current = generated["portraits"].get(key)
        if current is not None and current.get("generated_fullsize_sha256") == entry["generated_fullsize_sha256"]:
            verify_import(worktree, {"entries": [entry]})
            imported.append(key)
            continue
        relative, journal = shared.merged_journal(worktree, support, key, entry)
        prior_attempts = copy.deepcopy(journal["attempts"])
        require(len(prior_attempts) == 1 and prior_attempts[0]["status"] == "failed" and not prior_attempts[0].get("fullsize_sha256"), f"Builtin history differs: {key}")
        require(current is None, f"Canonical row already exists; inspect before resuming: {key}")
        queue["sources"][key] = copy.deepcopy(entry["previous_queue_row"])
        queue["sources"][key].update(state="generated_pending_visual_review", output_sha256=None, generated_at_utc=entry["generated_at_utc"])
        write_json(path(worktree, QUEUE), queue)
        shared.configure_portraits(worktree)
        portraits.ingest(key, path(support, entry["generated_fullsize_image"]), path(support, entry["prompt_file"]), None, entry["method"])
        generated = read_json(path(worktree, GENERATED))
        row = generated["portraits"][key]
        queue["sources"][key]["output_sha256"] = row["image_sha256"]
        write_json(path(worktree, QUEUE), queue)
        marker = {
            "schema": entry["import_schema"], "machine_id": machine_id(), "source_sha256": key,
            "fullsize_sha256": entry["generated_fullsize_sha256"], "approved_attempt": entry["attempt"], "task_id": entry["task_id"],
            "review": entry["review"], "review_sha256": entry["review_sha256"], "evidence": entry["evidence"], "evidence_sha256": entry["evidence_sha256"],
            "execution": entry["execution"], "execution_sha256": entry["execution_sha256"], "request": entry["request"], "request_sha256": entry["request_sha256"],
            "imported_at_utc": utc_now(),
        }
        row.update({
            "generation_inputs": entry["inputs"], "request_journal": relative,
            "reviewed_at_utc": entry["reviewed_at_utc"], "review_method": f"Kimi actual SHA-bound visual review: {entry['review']}; reviewer: {entry['reviewer']}",
            "production_import": marker,
        })
        write_json(path(worktree, GENERATED), generated)
        number = max([item["number"] for item in journal["attempts"]], default=0) + 1
        journal["attempts"].append({
            "number": number, "status": "generated_pending_visual_review", "method": entry["method"], "art_direction": "hair-features-v1",
            "prompt": entry["prompt"], "prompt_file": entry["prompt_file"], "prompt_sha256": entry["prompt_sha256"],
            "inputs": entry["inputs"], "edit_existing": False, "machine_id": machine_id(),
            "prepared_at_utc": read_json(path(support, entry["execution"]))["started_at_utc"], "generated_at_utc": entry["generated_at_utc"],
            "fullsize_sha256": entry["generated_fullsize_sha256"], "fullsize_image": entry["generated_fullsize_image"],
            "output": row["image"], "output_sha256": row["image_sha256"],
            "external_task_id": entry["task_id"], "external_execution": entry["execution"], "external_execution_sha256": entry["execution_sha256"],
            "external_request": entry["request"], "external_request_sha256": entry["request_sha256"],
            "external_result": entry["result"], "external_result_sha256": entry["result_sha256"],
            "external_review": entry["review"], "external_review_sha256": entry["review_sha256"],
            "external_evidence": entry["evidence"], "external_evidence_sha256": entry["evidence_sha256"], "external_reviewer": entry["reviewer"],
        })
        require(journal["attempts"][:-1] == prior_attempts, f"Historical request attempts changed: {key}")
        write_json(path(worktree, relative), journal)
        shared.configure_portraits(worktree)
        portraits.approve([key])
        generated = read_json(path(worktree, GENERATED))
        row = generated["portraits"][key]
        row["collar_fit"].update(reviewed_at_utc=entry["reviewed_at_utc"], review_method=f"Kimi collar-fit-v1 actual visual approval: {entry['review']}")
        write_json(path(worktree, GENERATED), generated)
        journal = read_json(path(worktree, relative))
        journal["attempts"][-1].update(status="approved", reviewed_at_utc=entry["reviewed_at_utc"], review="approved")
        write_json(path(worktree, relative), journal)
        queue["sources"][key].update(state="approved_external_native_rgb", approved_at_utc=entry["reviewed_at_utc"], approved_image_sha256=row["image_sha256"], external_task_id=entry["task_id"], external_execution=entry["execution"], external_review=entry["review"])
        require(queue["sources"][key]["retries_used"] == entry["previous_queue_row"]["retries_used"] == 0, f"Builtin retry counter reset: {key}")
        write_json(path(worktree, QUEUE), queue)
        imported.append(key)
    generated = read_json(path(worktree, GENERATED))
    queue = read_json(path(worktree, QUEUE))
    require(all(generated["portraits"].get(key) == row for key, row in outside_generated.items()), "An unrelated production portrait changed")
    require(all(queue["sources"].get(key) == row for key, row in outside_queue.items()), "An unrelated retry-queue row changed")
    return imported


def sync_fullsize(worktree, support):
    expected, _current, provenance = master_archive.recorded_outputs(shared.extended_path(path(worktree, "mod_nailong")))
    published = json.loads(git(worktree, "show", f"HEAD:{FULLSIZE}"))["outputs"]
    current_index = read_json(path(worktree, FULLSIZE))["outputs"]
    for recorded in (published, current_index):
        expected.update(recorded)
        for digest, row in recorded.items():
            references = provenance.setdefault(digest, [])
            for reference in row["provenance"]:
                if reference not in references:
                    references.append(copy.deepcopy(reference))
    for row in read_json(path(worktree, f"{EXPERIMENT}/outputs-index.json"))["entries"]:
        expected.add(row["output_sha256"])
        provenance.setdefault(row["output_sha256"], []).append({"experiment": f"{EXPERIMENT}/outputs-index.json", "review": row["review"], "decision": row["decision"]})
    index = read_json(path(worktree, FULLSIZE))
    if set(index["outputs"]) == expected:
        require(index["schema"] == "naiwa-fullsize-git-files-v1" and index["storage"] == "ordinary Git blobs containing original PNG bytes", "Original index storage differs")
        require(index["count"] == len(expected) and index["original_png_bytes"] == sum(row["bytes"] for row in index["outputs"].values()), "Original index totals differ")
        for digest, row in index["outputs"].items():
            require(row["path"] == master_files.master_path(digest), f"Original index path differs: {digest}")
            previous = published.get(digest)
            if previous is not None:
                require(all(row[field] == previous[field] for field in ("path", "bytes", "size", "mode")), f"Published original metadata differs: {digest}")
        print({"masters": index["count"], "original_png_bytes": index["original_png_bytes"], "index_reused_after_exact_set_and_metadata_match": True, "full_blob_verification_pending": True})
        return index
    candidates = master_files.recorded_master_candidates(shared.extended_path(support))
    require(candidates is not None, "Support workspace lacks a complete recorded-master candidate set")
    by_sha = {row["sha256"]: row for row in candidates["masters"]}
    from PIL import Image
    for digest in sorted(expected - by_sha.keys()):
        candidate = path(support, master_files.master_path(digest))
        require(candidate.is_file() and file_sha256(candidate) == digest, f"Original master candidate missing: {digest}")
        with Image.open(candidate) as image:
            size, mode = list(image.size), image.mode
        by_sha[digest] = {"path": str(candidate), "sha256": digest, "bytes": candidate.stat().st_size, "size": size, "mode": mode}
    return master_files.sync_git({"masters": [{**by_sha[digest], "provenance": provenance[digest]} for digest in sorted(expected)], "current_masters_missing": [], "historical_fullsize_sha_missing": []}, root=worktree, normalize_paths=False)


def verify_import(worktree, plan):
    generated = read_json(path(worktree, GENERATED))
    queue = read_json(path(worktree, QUEUE))
    for entry in plan["entries"]:
        key = entry["source_sha256"]
        row = generated["portraits"][key]
        require(row["generated_fullsize_sha256"] == entry["generated_fullsize_sha256"] and row["method"] == "EvoLink gpt-image-2.5-flare", f"Canonical master/method differs: {key}")
        require(file_sha256(path(worktree, row["generated_fullsize_image"])) == entry["generated_fullsize_sha256"], f"Canonical master bytes differ: {key}")
        require(file_sha256(path(worktree, row["image"])) == row["image_sha256"], f"Derived preview differs: {key}")
        require(portrait_ready(row), f"Canonical portrait is not ready: {key}")
        require(row["production_import"]["schema"] == entry["import_schema"] and row["production_import"]["review_sha256"] == entry["review_sha256"], f"Import marker differs: {key}")
        journal = read_json(path(worktree, row["request_journal"]))
        latest = journal["attempts"][-1]
        require(latest["status"] == "approved" and latest["external_task_id"] == entry["task_id"] and latest["output_sha256"] == row["image_sha256"], f"Journal approval differs: {key}")
        require(latest["fullsize_sha256"] == entry["generated_fullsize_sha256"] and latest["external_review_sha256"] == entry["review_sha256"], f"Journal evidence differs: {key}")
        require(queue["sources"][key]["retries_used"] == entry["previous_queue_row"]["retries_used"] and queue["sources"][key]["external_task_id"] == entry["task_id"], f"Queue history/result differs: {key}")
    return True


def stage_and_commit(worktree, plan):
    new_digests = {row["output_sha256"] for row in read_json(path(worktree, f"{EXPERIMENT}/outputs-index.json"))["entries"]}
    allowed = {
        GENERATED, QUEUE, FULLSIZE, EXPERIMENT, *DOCS, TEST,
        *(f"mod_nailong/assets/generated_fullsize/{digest}.png" for digest in new_digests),
        *(f"mod_nailong/assets/portraits/{row['source_sha256']}.png" for row in plan["entries"]),
        *(f"mod_nailong/data/generation-requests/{row['source_sha256']}.json" for row in plan["entries"]),
    }
    changed = set(git(worktree, "diff", "--name-only", "--", *allowed).splitlines()) | set(git(worktree, "diff", "--cached", "--name-only").splitlines())
    require(all(relative in allowed or relative.startswith(EXPERIMENT + "/") for relative in changed), f"Unexpected tracked files in isolated import: {sorted(changed)[:12]}")
    git(worktree, "add", "--sparse", "--", *allowed)
    git(worktree, "diff", "--cached", "--check")
    staged = set(git(worktree, "diff", "--cached", "--name-only").splitlines())
    require(all(relative in allowed or relative.startswith(EXPERIMENT + "/") for relative in staged), "Staged path outside scoped delivery")
    parent = git(worktree, "rev-parse", "HEAD")
    tree = git(worktree, "write-tree")
    commit = git(worktree, "commit-tree", tree, "-p", parent, "-m", "Integrate two reviewed LOW portraits")
    require(git(worktree, "cat-file", "-t", commit) == "commit" and git(worktree, "show", "-s", "--format=%P", commit) == parent, "Created commit identity differs")
    require(set(git(worktree, "diff-tree", "--no-commit-id", "--name-only", "-r", commit).splitlines()) == staged, "Created commit content differs from verified index")
    git(worktree, "update-ref", "HEAD", commit, parent)
    require(git(worktree, "rev-parse", "HEAD") == commit, "HEAD did not advance to the scoped commit")
    return commit


def fetch_origin(worktree):
    try:
        return git(worktree, "fetch", "origin")
    except ImportErrorWithEvidence as direct_error:
        try:
            return git(worktree, "-c", "http.proxy=http://127.0.0.1:10808", "fetch", "origin")
        except ImportErrorWithEvidence as proxy_error:
            raise ImportErrorWithEvidence(f"Direct fetch failed: {direct_error}\nProxy 10808 fetch failed: {proxy_error}")


def synchronize(worktree, original_commit):
    fetch_origin(worktree)
    remote = git(worktree, "rev-parse", "origin/master")
    if remote != original_commit:
        try:
            git(worktree, "rebase", "origin/master")
        except ImportErrorWithEvidence:
            for relative, container in ((GENERATED, "portraits"), (QUEUE, "sources"), (FULLSIZE, "outputs")):
                conflicts = set(git(worktree, "diff", "--name-only", "--diff-filter=U").splitlines())
                require(conflicts <= {GENERATED, QUEUE, FULLSIZE}, f"Unrelated rebase conflict: {sorted(conflicts)}")
                if relative not in conflicts:
                    continue
                base, ours, theirs = (json.loads(git(worktree, "show", f":{number}:{relative}")) for number in (1, 2, 3))
                merged = shared.merge_mapping(base, ours, theirs, container)
                if relative == FULLSIZE:
                    merged["count"] = len(merged["outputs"])
                    merged["original_png_bytes"] = sum(row["bytes"] for row in merged["outputs"].values())
                write_json(path(worktree, relative), merged)
                git(worktree, "add", "--", relative)
            require(not git(worktree, "diff", "--name-only", "--diff-filter=U"), "Unresolved rebase conflicts remain")
            git(worktree, "-c", "core.editor=true", "rebase", "--continue")
    allowed = [GENERATED, QUEUE, FULLSIZE, EXPERIMENT, *DOCS, TEST]
    require(not git(worktree, "diff", "--name-only", "--", *allowed) and not git(worktree, "diff", "--cached", "--name-only"), "Rebase left uncommitted scoped changes")
    return git(worktree, "rev-parse", "HEAD")


def apply(worktree, create=False):
    worktree = Path(worktree).resolve()
    if create:
        parent = shared.create_worktree(worktree)
    else:
        require((worktree / ".git").exists(), "Apply requires an isolated Git worktree")
        scope = read_json(path(ROOT, f"{EXPERIMENT}/scope.json"))["entries"]
        outputs = read_json(path(ROOT, f"{EXPERIMENT}/outputs-index.json"))["entries"]
        allowed = {GENERATED, QUEUE, FULLSIZE, EXPERIMENT, *DOCS, TEST, *(f"mod_nailong/data/generation-requests/{row['source_sha256']}.json" for row in scope), *(f"mod_nailong/assets/portraits/{row['source_sha256']}.png" for row in scope), *(f"mod_nailong/assets/generated_fullsize/{row['output_sha256']}.png" for row in outputs)}
        changed = set(git(worktree, "diff", "--name-only", "--", *allowed).splitlines()) | set(git(worktree, "diff", "--cached", "--name-only").splitlines())
        require(all(relative in allowed or relative.startswith(EXPERIMENT + "/") for relative in changed), f"Unexpected isolated-worktree tracked state: {sorted(changed)}")
        parent = git(worktree, "rev-parse", "HEAD")
    plan = build_plan(worktree, ROOT)
    copy_scoped_files(worktree, ROOT, plan)
    imported = import_sources(worktree, plan)
    index = sync_fullsize(worktree, ROOT)
    verify_import(worktree, plan)
    original_commit = stage_and_commit(worktree, plan)
    final_commit = synchronize(worktree, original_commit)
    verify_import(worktree, plan)
    receipt = {
        "schema": "low2-kimi-production-import-receipt-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
        "status": "committed_push_pending", "parent_commit": parent, "original_import_commit": original_commit,
        "import_commit": final_commit, "worktree": str(worktree), "imported_sources": imported,
        "approved_person_sources": len(imported), "resource_instances": sum(len(row["source_assets"]) for row in plan["entries"]),
        "fullsize_original_count": index["count"], "fullsize_original_bytes": index["original_png_bytes"],
        "new_generation_calls_for_import": 0, "unrelated_rows_preserved": True,
        "builtin_retry_counts_preserved": [entry["previous_queue_row"]["retries_used"] for entry in plan["entries"]],
        "ordinary_git_commit": True, "push_performed": False, "remote_original_verification_claimed": False, "runtime_acceptance_claimed": False,
    }
    write_json(ROOT / RUNTIME / "import-receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False))
    return receipt


def main():
    parser = argparse.ArgumentParser(description="Import exactly two reviewed LOW sources into an isolated worktree; never calls an image API.")
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        plan = build_plan(args.worktree, ROOT)
        print(json.dumps({"status": "ready_for_isolated_import", "source_count": plan["source_count"], "resource_instances": plan["resource_instances"], "new_generation_calls": 0}))
        return 0
    apply(args.worktree, args.create)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
