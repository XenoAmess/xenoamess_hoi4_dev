import argparse
import copy
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from mod_nailong.tools import master_archive, master_files, portraits
from mod_nailong.tools.art_contract import portrait_ready
from tools.common import file_sha256, machine_id, read_json, utc_now, write_json

EXPERIMENT = "mod_nailong/experiments/evolink-low7-20261030"
GENERATED = "mod_nailong/data/generated.json"
QUEUE = "mod_nailong/data/image-retry-queue.json"
FULLSIZE = "mod_nailong/data/fullsize-files.json"
DOCS = [
    "docs/handoffs/2026-10-30-low7-exhausted.md",
    "docs/handoffs/2026-10-30-low7-exhausted.json",
    "docs/handoffs/low7-kimi-evolink-2026-10-30.md",
]
TEST = "tests/test_low7_evolink.py"
OLD_NAVY_MASTER = "mod_nailong/assets/generated_fullsize/fca9eca6c6b5bfc340b9b931f88abc0b1af0a23cb870fadd823eb6663d1b6614.png"


class ImportErrorWithEvidence(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ImportErrorWithEvidence(message)


def path(root, value):
    require(isinstance(value, str) and value and not Path(value).is_absolute(), f"Invalid relative path: {value}")
    candidate = (Path(root) / value).resolve()
    candidate.relative_to(Path(root).resolve())
    return candidate


def bound(root, value, sha):
    candidate = path(root, value)
    require(candidate.is_file() and file_sha256(candidate) == sha, f"Evidence SHA mismatch: {value}")
    return candidate


def git(root, *args):
    result = subprocess.run(["git", "-c", "core.longpaths=true", "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if result.returncode:
        raise ImportErrorWithEvidence(result.stdout + "\n" + result.stderr)
    return result.stdout.strip("\r\n")


def build_plan(worktree, support=ROOT):
    worktree = Path(worktree).resolve()
    approved_relative = f"{EXPERIMENT}/approved-masters.json"
    approved = read_json(path(support, approved_relative))
    scope = read_json(path(support, f"{EXPERIMENT}/scope.json"))
    verification = read_json(path(support, "runtime/low7-evolink-20261030/final-verification.json"))
    require(verification["status"] in {"seven_sources_generated_reviewed_and_archived_pending_canonical_import_and_git_publication", "seven_sources_generated_reviewed_integrated_pending_publication"}, "Generation/art verification is incomplete")
    require(verification["unresolved_generation_tasks"] == 0 and verification["scoped_tests"]["passed"] >= 12, "Unresolved calls or tests remain")
    require(approved["count"] == len(approved["entries"]) == scope["source_count"] == 7, "Scope must contain exactly seven approved sources")
    require(approved["formal_canonical_import_count"] == 0, "Input already claims canonical import")
    require(file_sha256(path(support, scope["handoff"])) == scope["handoff_sha256"], "Handoff binding changed")
    delivery_relative = f"{EXPERIMENT}/delivery-authorization.json"
    delivery = read_json(path(support, delivery_relative))
    require(delivery["user_instruction_quote"] == "现在开始恢复允许你使用git。做完后自己提交、推送。", "Git resume authorization is missing")
    require(delivery["source_count"] == 7 and delivery["unrelated_workspace_changes_must_not_be_committed"] is True, "Delivery scope differs")
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
        require(execution["attempt"] == entry["attempt"] and execution["task_id"] == entry["task_id"], f"Execution binding differs: {key}")
        if execution["status"] == "resume_existing_task_required":
            recovery = read_json(bound(support, entry["recovery"], entry["recovery_sha256"]))
            require(recovery["status"] == "completed" and recovery["new_generation_post_created"] is False and recovery["task_id"] == entry["task_id"], f"Recovery differs: {key}")
        else:
            require(execution["status"] == "completed" and execution["output_sha256"] == entry["generated_fullsize_sha256"], f"Execution incomplete: {key}")
        decisions = [row for row in review["entries"] if row["source_sha256"] == key]
        require(len(decisions) == 1, f"Missing current review: {key}")
        decision = decisions[0]
        require(decision["decision"] == "approved_for_production" and decision["output_sha256"] == entry["generated_fullsize_sha256"], f"Review output differs: {key}")
        require(decision["remaining_reasons"] == [] and decision["production_import_pending"] is True, f"Unresolved art issue: {key}")
        require(decision["hair_features"] == {"policy": "hair-features-v1", "status": "approved"}, f"Hair approval missing: {key}")
        require(decision["collar_fit"] == {"policy": "collar-fit-v1", "status": "approved"}, f"Collar approval missing: {key}")
        for item in entry["inputs"]:
            bound(support, item["path"], item["sha256"])
        require(queue["sources"][key]["retries_used"] == 9, f"Builtin retry count changed: {key}")
        current = generated["portraits"].get(key)
        require(current is None or current.get("generated_fullsize_sha256") != entry["generated_fullsize_sha256"], f"Input is already canonically imported: {key}")
        entries.append({**entry, "previous_generated_row": copy.deepcopy(current), "previous_queue_row": copy.deepcopy(queue["sources"][key])})
    require(len({row["source_sha256"] for row in entries}) == 7, "Duplicate sources")
    return {"schema": "low7-production-import-plan-v1", "root": str(worktree), "support_root": str(Path(support).resolve()), "source_count": 7, "resource_instances": 10, "approved_manifest": approved_relative, "approved_manifest_sha256": file_sha256(path(support, approved_relative)), "delivery_authorization": delivery_relative, "delivery_authorization_sha256": file_sha256(path(support, delivery_relative)), "entries": entries}


def copy_scoped_files(worktree, support, plan):
    worktree = Path(worktree).resolve()
    destination = path(worktree, EXPERIMENT)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.tmp")
    source_directory = path(support, EXPERIMENT)
    if destination.exists():
        expected = {path.relative_to(source_directory) for path in source_directory.rglob("*") if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".tmp"}}
        actual = {path.relative_to(destination) for path in destination.rglob("*") if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".tmp"}}
        require(not (actual - expected), "Unexpected file in existing scoped evidence tree; reconcile before resume")
        for relative in expected:
            target = destination / relative
            if target.exists():
                source_bytes = (source_directory / relative).read_bytes()
                if source_bytes != target.read_bytes():
                    require(relative.parts[0] == "tools" and relative.suffix == ".py", f"Scoped evidence changed: {relative}")
                    target.write_bytes(source_bytes)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_directory / relative, target)
    else:
        shutil.copytree(source_directory, destination, ignore=ignore)
    for relative in [*DOCS, TEST, OLD_NAVY_MASTER]:
        target = path(worktree, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        original = path(support, relative)
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
    write_json(ROOT / "runtime/low7-evolink-20261030/evidence-copy.json", {
        "schema": "low7-scoped-evidence-copy-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
        "worktree": str(worktree), "approved_manifest_sha256": plan["approved_manifest_sha256"],
        "delivery_authorization_sha256": plan["delivery_authorization_sha256"],
        "sources": 7, "unrelated_workspace_files_copied": False,
    })


def merged_journal(worktree, support, key, entry=None):
    relative = f"mod_nailong/data/generation-requests/{key}.json"
    remote_path = path(worktree, relative)
    support_path = path(support, relative)
    remote = read_json(remote_path) if remote_path.exists() else {"schema": "naiwa-generation-requests-v1", "source_sha256": key, "attempts": []}
    historical = read_json(support_path)
    merged = copy.deepcopy(historical)
    by_number = {}
    for attempt in [*remote.get("attempts", []), *historical["attempts"]]:
        number = attempt["number"]
        if number in by_number and by_number[number] != attempt:
            raise ImportErrorWithEvidence(f"Historical attempt differs between remote and handoff: {key} attempt {number}")
        by_number[number] = attempt
    extra = set(by_number) - {row["number"] for row in historical["attempts"]}
    if extra:
        require(entry is not None and len(extra) == 1, f"Remote has a newer unknown attempt: {key}")
        latest = remote["attempts"][-1]
        require(latest["number"] in extra and latest["status"] in {"generated_pending_visual_review", "approved"}, f"Remote has a newer unknown attempt: {key}")
        require(latest["external_task_id"] == entry["task_id"] and latest["fullsize_sha256"] == entry["generated_fullsize_sha256"] and latest["prompt_sha256"] == entry["prompt_sha256"], f"Remote pending attempt is not the scoped external result: {key}")
    merged["attempts"] = [by_number[number] for number in sorted(by_number)]
    return relative, merged


def configure_portraits(worktree):
    portraits.ROOT = Path(worktree).resolve()
    portraits.MOD = portraits.ROOT / "mod_nailong"
    portraits.RECORD = portraits.ROOT / GENERATED
    portraits.CATALOG = portraits.ROOT / "mod_nailong/data/catalog.json"


def import_sources(worktree, plan):
    worktree = Path(worktree).resolve()
    require(Path(plan["root"]) == worktree, "Plan belongs to a different worktree")
    support = Path(plan["support_root"])
    configure_portraits(worktree)
    generated = read_json(path(worktree, GENERATED))
    queue = read_json(path(worktree, QUEUE))
    outside_generated = {key: copy.deepcopy(row) for key, row in generated["portraits"].items() if key not in {row["source_sha256"] for row in plan["entries"]}}
    outside_queue = {key: copy.deepcopy(row) for key, row in queue["sources"].items() if key not in {row["source_sha256"] for row in plan["entries"]}}
    imported = []
    for entry in plan["entries"]:
        key = entry["source_sha256"]
        relative, journal = merged_journal(worktree, support, key, entry)
        prior_attempts = copy.deepcopy(journal["attempts"])
        write_json(path(worktree, relative), journal)
        if entry["previous_queue_row"]["retries_used"] != 9:
            raise ImportErrorWithEvidence(f"Wrong preserved builtin count: {key}")
        current = generated["portraits"].get(key)
        latest = journal["attempts"][-1] if journal["attempts"] else {}
        external_recorded = latest.get("external_task_id") == entry["task_id"]
        resumable = (
            current is not None and current.get("generated_fullsize_sha256") == entry["generated_fullsize_sha256"]
            and current.get("method") == "EvoLink gpt-image-2.5-flare"
            and current.get("production_import", {}).get("schema") in {None, "low7-kimi-production-import-v1"}
            and (current.get("review") == "pending" or current.get("production_import", {}).get("schema") == "low7-kimi-production-import-v1")
            and (external_recorded or not any(row.get("external_task_id") == entry["task_id"] for row in journal["attempts"]))
        )
        if resumable:
            require(current.get("production_import", {}).get("review_sha256") in {None, entry["review_sha256"]}, f"Resume marker differs: {key}")
            if current.get("production_import") is None:
                current["generation_inputs"] = entry["inputs"]
                current["request_journal"] = relative
                current["production_import"] = {
                    "schema": "low7-kimi-production-import-v1", "machine_id": machine_id(), "source_sha256": key,
                    "fullsize_sha256": entry["generated_fullsize_sha256"], "approved_attempt": entry["attempt"], "task_id": entry["task_id"],
                    "review": entry["review"], "review_sha256": entry["review_sha256"], "evidence": entry["evidence"], "evidence_sha256": entry["evidence_sha256"],
                    "execution": entry["execution"], "execution_sha256": entry["execution_sha256"], "request": entry["request"], "request_sha256": entry["request_sha256"],
                    "imported_at_utc": utc_now(), "recovered_from_pre_metadata_stop": True,
                }
                write_json(path(worktree, GENERATED), generated)
            if external_recorded:
                require(latest.get("output_sha256") == current["image_sha256"] and latest.get("prompt_sha256") == entry["prompt_sha256"], f"Resume journal/output differs: {key}")
            if current.get("review") == "approved":
                require(external_recorded and latest.get("status") == "approved" and portrait_ready(current) and queue["sources"][key].get("state") == "approved_external_native_rgb", f"Completed source is inconsistent: {key}")
                imported.append(key)
                continue
            require(current.get("review") == "pending", f"Cannot resume partial source: {key}")
            if external_recorded:
                require(latest.get("status") == "generated_pending_visual_review", f"Cannot resume partial source: {key}")
            else:
                attempt = {
                    "number": max([row["number"] for row in journal["attempts"]], default=0) + 1,
                    "status": "generated_pending_visual_review", "method": entry["method"], "art_direction": "hair-features-v1",
                    "prompt": entry["prompt"], "prompt_file": entry["prompt_file"], "prompt_sha256": entry["prompt_sha256"],
                    "inputs": entry["inputs"], "edit_existing": entry["edit_existing"], "machine_id": machine_id(),
                    "prepared_at_utc": read_json(path(support, entry["execution"]))["started_at_utc"], "generated_at_utc": entry["generated_at_utc"],
                    "fullsize_sha256": entry["generated_fullsize_sha256"], "fullsize_image": entry["generated_fullsize_image"],
                    "output": current["image"], "output_sha256": current["image_sha256"],
                    "external_task_id": entry["task_id"], "external_execution": entry["execution"], "external_execution_sha256": entry["execution_sha256"],
                    "external_request": entry["request"], "external_request_sha256": entry["request_sha256"],
                    "external_result": entry["result"], "external_result_sha256": entry["result_sha256"],
                    "external_review": entry["review"], "external_review_sha256": entry["review_sha256"],
                    "external_evidence": entry["evidence"], "external_evidence_sha256": entry["evidence_sha256"],
                    "external_reviewer": entry["reviewer"],
                }
                if entry["recovery"]:
                    attempt.update(external_recovery=entry["recovery"], external_recovery_sha256=entry["recovery_sha256"], new_generation_post_created_for_recovery=False)
                if entry["attempt"] == "external-02":
                    preparation = read_json(path(support, f"{EXPERIMENT}/repair-preparation.json"))
                    attempt["external_art_repair"] = next(row for row in preparation["entries"] if row["source_sha256"] == key)
                journal["attempts"].append(attempt)
                require(journal["attempts"][:-1] == prior_attempts, f"Historical attempts changed during resume: {key}")
                write_json(path(worktree, relative), journal)
            queue["sources"][key].update(state="generated_pending_visual_review", output_sha256=current["image_sha256"], generated_at_utc=entry["generated_at_utc"])
            require(queue["sources"][key]["retries_used"] == 9, f"Builtin retry counter changed: {key}")
            write_json(path(worktree, QUEUE), queue)
            configure_portraits(worktree)
            portraits.approve([key])
            generated = read_json(path(worktree, GENERATED))
            row = generated["portraits"][key]
            row.update(reviewed_at_utc=entry["reviewed_at_utc"], review_method=f"Kimi actual SHA-bound visual review: {entry['review']}; reviewer: {entry['reviewer']}")
            row["collar_fit"].update(reviewed_at_utc=entry["reviewed_at_utc"], review_method=f"Kimi collar-fit-v1 actual visual approval: {entry['review']}")
            write_json(path(worktree, GENERATED), generated)
            journal = read_json(path(worktree, relative))
            journal["attempts"][-1].update(status="approved", reviewed_at_utc=entry["reviewed_at_utc"], review="approved")
            write_json(path(worktree, relative), journal)
            queue["sources"][key].update(state="approved_external_native_rgb", approved_at_utc=entry["reviewed_at_utc"], approved_image_sha256=row["image_sha256"], external_task_id=entry["task_id"], external_execution=entry["execution"], external_review=entry["review"])
            write_json(path(worktree, QUEUE), queue)
            imported.append(key)
            continue
        queue["sources"][key] = copy.deepcopy(entry["previous_queue_row"])
        queue["sources"][key].update(state="generated_pending_visual_review", output_sha256=None, generated_at_utc=entry["generated_at_utc"])
        write_json(path(worktree, QUEUE), queue)
        configure_portraits(worktree)
        portraits.ingest(key, path(support, entry["generated_fullsize_image"]), path(support, entry["prompt_file"]), "Kimi LOW7 EvoLink visible-art replacement" if entry["previous_generated_row"] else None, entry["method"])
        generated = read_json(path(worktree, GENERATED))
        row = generated["portraits"][key]
        queue["sources"][key]["output_sha256"] = row["image_sha256"]
        write_json(path(worktree, QUEUE), queue)
        row.update({
            "generation_inputs": entry["inputs"], "request_journal": relative,
            "reviewed_at_utc": entry["reviewed_at_utc"],
            "review_method": f"Kimi actual SHA-bound visual review: {entry['review']}; reviewer: {entry['reviewer']}",
            "production_import": {
                "schema": "low7-kimi-production-import-v1", "machine_id": machine_id(), "source_sha256": key,
                "fullsize_sha256": entry["generated_fullsize_sha256"], "approved_attempt": entry["attempt"], "task_id": entry["task_id"],
                "review": entry["review"], "review_sha256": entry["review_sha256"], "evidence": entry["evidence"], "evidence_sha256": entry["evidence_sha256"],
                "execution": entry["execution"], "execution_sha256": entry["execution_sha256"], "request": entry["request"], "request_sha256": entry["request_sha256"],
                "imported_at_utc": utc_now(),
            },
        })
        write_json(path(worktree, GENERATED), generated)
        journal = read_json(path(worktree, relative))
        number = max([row["number"] for row in journal["attempts"]], default=0) + 1
        attempt = {
            "number": number, "status": "generated_pending_visual_review", "method": entry["method"], "art_direction": "hair-features-v1",
            "prompt": entry["prompt"], "prompt_file": entry["prompt_file"], "prompt_sha256": entry["prompt_sha256"],
            "inputs": entry["inputs"], "edit_existing": entry["edit_existing"], "machine_id": machine_id(),
            "prepared_at_utc": read_json(path(support, entry["execution"]))["started_at_utc"], "generated_at_utc": entry["generated_at_utc"],
            "fullsize_sha256": entry["generated_fullsize_sha256"], "fullsize_image": entry["generated_fullsize_image"],
            "output": row["image"], "output_sha256": row["image_sha256"],
            "external_task_id": entry["task_id"], "external_execution": entry["execution"], "external_execution_sha256": entry["execution_sha256"],
            "external_request": entry["request"], "external_request_sha256": entry["request_sha256"],
            "external_result": entry["result"], "external_result_sha256": entry["result_sha256"],
            "external_review": entry["review"], "external_review_sha256": entry["review_sha256"],
            "external_evidence": entry["evidence"], "external_evidence_sha256": entry["evidence_sha256"],
            "external_reviewer": entry["reviewer"],
        }
        if entry["recovery"]:
            attempt.update(external_recovery=entry["recovery"], external_recovery_sha256=entry["recovery_sha256"], new_generation_post_created_for_recovery=False)
        if entry["attempt"] == "external-02":
            preparation = read_json(path(support, f"{EXPERIMENT}/repair-preparation.json"))
            repair = next(row for row in preparation["entries"] if row["source_sha256"] == key)
            attempt["external_art_repair"] = repair
        journal["attempts"].append(attempt)
        write_json(path(worktree, relative), journal)
        configure_portraits(worktree)
        portraits.approve([key])
        generated = read_json(path(worktree, GENERATED))
        row = generated["portraits"][key]
        row.update(reviewed_at_utc=entry["reviewed_at_utc"], review_method=f"Kimi actual SHA-bound visual review: {entry['review']}; reviewer: {entry['reviewer']}")
        row["collar_fit"].update(reviewed_at_utc=entry["reviewed_at_utc"], review_method=f"Kimi collar-fit-v1 actual visual approval: {entry['review']}")
        write_json(path(worktree, GENERATED), generated)
        journal = read_json(path(worktree, relative))
        journal["attempts"][-1].update(status="approved", reviewed_at_utc=entry["reviewed_at_utc"], review="approved")
        require(journal["attempts"][:-1] == prior_attempts, f"Historical request attempts changed: {key}")
        write_json(path(worktree, relative), journal)
        queue["sources"][key].update(
            state="approved_external_native_rgb", approved_at_utc=entry["reviewed_at_utc"], approved_image_sha256=row["image_sha256"],
            external_task_id=entry["task_id"], external_execution=entry["execution"], external_review=entry["review"],
        )
        require(queue["sources"][key]["retries_used"] == 9, f"Builtin retry counter reset: {key}")
        write_json(path(worktree, QUEUE), queue)
        imported.append(key)
    generated = read_json(path(worktree, GENERATED))
    queue = read_json(path(worktree, QUEUE))
    require(all(generated["portraits"].get(key) == row for key, row in outside_generated.items()), "An unrelated production portrait changed")
    require(all(queue["sources"].get(key) == row for key, row in outside_queue.items()), "An unrelated retry-queue row changed")
    return imported


def extended_path(value):
    resolved = Path(value).resolve()
    if sys.platform == "win32" and not str(resolved).startswith("\\\\?\\"):
        return Path("\\\\?\\" + str(resolved))
    return resolved


def sync_fullsize(worktree, support):
    expected, _current, provenance = master_archive.recorded_outputs(extended_path(path(worktree, "mod_nailong")))
    for row in read_json(path(worktree, f"{EXPERIMENT}/outputs-index.json"))["entries"]:
        expected.add(row["output_sha256"])
        provenance.setdefault(row["output_sha256"], []).append({"experiment": f"{EXPERIMENT}/outputs-index.json", "review": row["review"], "decision": row["decision"]})
    previous_navy_sha = "fca9eca6c6b5bfc340b9b931f88abc0b1af0a23cb870fadd823eb6663d1b6614"
    expected.add(previous_navy_sha)
    provenance.setdefault(previous_navy_sha, []).append({"experiment": f"{EXPERIMENT}/scope.json", "record": "retained previous rejected navy_2 master"})
    candidates = master_files.recorded_master_candidates(extended_path(support))
    require(candidates is not None, "Support workspace lacks a complete recorded-master candidate set; no index substitution allowed")
    by_sha = {row["sha256"]: row for row in candidates["masters"]}
    from PIL import Image
    for digest in sorted(expected - by_sha.keys()):
        candidate = path(support, master_files.master_path(digest))
        require(candidate.is_file() and file_sha256(candidate) == digest, f"Original master candidate missing: {digest}")
        with Image.open(candidate) as image:
            size, mode = list(image.size), image.mode
        by_sha[digest] = {"path": str(candidate), "sha256": digest, "bytes": candidate.stat().st_size, "size": size, "mode": mode}
    masters = []
    for digest in sorted(expected):
        require(digest in by_sha, f"Original master candidate missing: {digest}")
        item = by_sha[digest]
        masters.append({**item, "provenance": provenance[digest]})
    return master_files.sync_git({"masters": masters, "current_masters_missing": [], "historical_fullsize_sha_missing": []}, root=worktree, normalize_paths=False)


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
        require(row["production_import"]["schema"] == "low7-kimi-production-import-v1" and row["production_import"]["review_sha256"] == entry["review_sha256"], f"Import marker differs: {key}")
        journal = read_json(path(worktree, row["request_journal"]))
        latest = journal["attempts"][-1]
        require(latest["status"] == "approved" and latest["external_task_id"] == entry["task_id"] and latest["output_sha256"] == row["image_sha256"], f"Journal approval differs: {key}")
        require(latest["fullsize_sha256"] == entry["generated_fullsize_sha256"] and latest["external_review_sha256"] == entry["review_sha256"], f"Journal evidence differs: {key}")
        require(queue["sources"][key]["retries_used"] == 9 and queue["sources"][key]["external_task_id"] == entry["task_id"], f"Queue history/result differs: {key}")
    return True


def create_worktree(worktree):
    worktree = Path(worktree).resolve()
    worktree.relative_to((ROOT / "runtime").resolve())
    require(not worktree.exists(), f"Worktree already exists: {worktree}")
    git(ROOT, "fetch", "origin")
    base = git(ROOT, "rev-parse", "origin/master")
    git(ROOT, "worktree", "add", "--detach", "--no-checkout", str(worktree), base)
    git(worktree, "sparse-checkout", "set", "--no-cone", "--no-sparse-index", "/AGENTS.md", "/README.md", "/.gitignore", "/.gitattributes", "/docs/", "/tools/", "/tests/", "/mod_nailong/AGENTS.md", "/mod_nailong/README.md", "/mod_nailong/data/", "/mod_nailong/docs/", "/mod_nailong/tools/", "/mod_nailong/experiments/", "/mod_nailong/assets/reference/", "/mod_nailong/assets/prompts/", "/mod_nailong/assets/portraits/", "!/mod_nailong/assets/generated_fullsize/")
    git(worktree, "read-tree", "-mu", "HEAD")
    require(not git(worktree, "status", "--porcelain"), "New isolated worktree is not clean")
    return base


def stage_and_commit(worktree, plan):
    new_digests = {row["output_sha256"] for row in read_json(path(worktree, f"{EXPERIMENT}/outputs-index.json"))["entries"]}
    new_digests.add("fca9eca6c6b5bfc340b9b931f88abc0b1af0a23cb870fadd823eb6663d1b6614")
    allowed = {
        GENERATED, QUEUE, FULLSIZE, EXPERIMENT, *DOCS, TEST,
        *(f"mod_nailong/assets/generated_fullsize/{digest}.png" for digest in new_digests),
        *(f"mod_nailong/assets/portraits/{row['source_sha256']}.png" for row in plan["entries"]),
        *(f"mod_nailong/data/generation-requests/{row['source_sha256']}.json" for row in plan["entries"]),
    }
    changed = set(git(worktree, "status", "--porcelain").splitlines())
    require(all(line[:2] in {" M", "??", "M ", "A ", "MM", "AM"} and (line[3:] in allowed or line[3:].startswith(EXPERIMENT + "/")) for line in changed), f"Unexpected files in isolated import: {sorted(changed)[:12]}")
    git(worktree, "add", "--sparse", "--", *allowed)
    git(worktree, "diff", "--cached", "--check")
    staged = set(git(worktree, "diff", "--cached", "--name-only").splitlines())
    require(all(relative in allowed or relative.startswith(EXPERIMENT + "/") for relative in staged), "Staged path outside scoped delivery")
    git(worktree, "commit", "-m", "Integrate seven reviewed LOW portraits")
    return git(worktree, "rev-parse", "HEAD")


def merge_mapping(base, ours, theirs, container):
    require(set(base) == set(ours) == set(theirs), f"Shared schema changed: {container}")
    result = dict(theirs)
    rows = {}
    for key in set(base[container]) | set(ours[container]) | set(theirs[container]):
        old, local, remote = base[container].get(key), ours[container].get(key), theirs[container].get(key)
        if local == remote or remote == old:
            rows[key] = local
        elif local == old:
            rows[key] = remote
        else:
            raise ImportErrorWithEvidence(f"Conflicting shared row: {container}/{key}")
    result[container] = rows
    return result


def synchronize(worktree, original_commit):
    git(worktree, "fetch", "origin")
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
                merged = merge_mapping(base, ours, theirs, container)
                if relative == FULLSIZE:
                    merged["count"] = len(merged["outputs"])
                    merged["original_png_bytes"] = sum(row["bytes"] for row in merged["outputs"].values())
                write_json(path(worktree, relative), merged)
                git(worktree, "add", "--", relative)
            require(not git(worktree, "diff", "--name-only", "--diff-filter=U"), "Unresolved rebase conflicts remain")
            git(worktree, "-c", "core.editor=true", "rebase", "--continue")
    require(not git(worktree, "status", "--porcelain"), "Rebase left uncommitted changes")
    return git(worktree, "rev-parse", "HEAD")


def apply(worktree, create=False):
    worktree = Path(worktree).resolve()
    if create:
        parent = create_worktree(worktree)
    else:
        require((worktree / ".git").exists(), "Apply requires an isolated Git worktree")
        changes = git(worktree, "status", "--porcelain").splitlines()
        scoped_journals = {f"mod_nailong/data/generation-requests/{row['source_sha256']}.json" for row in read_json(path(ROOT, f"{EXPERIMENT}/scope.json"))["entries"]}
        scoped_previews = {f"mod_nailong/assets/portraits/{row['source_sha256']}.png" for row in read_json(path(ROOT, f"{EXPERIMENT}/scope.json"))["entries"]}
        modified_allowed = {GENERATED, QUEUE, FULLSIZE, *scoped_journals, *scoped_previews}
        valid_changes = []
        for line in changes:
            untracked = line.startswith("?? ") and (line[3:] in {*DOCS, TEST, OLD_NAVY_MASTER} or line[3:].startswith((EXPERIMENT + "/", "mod_nailong/assets/generated_fullsize/", "mod_nailong/assets/portraits/")))
            modified = line[:2] in {" M", "M ", "MM"} and line[3:] in modified_allowed
            valid_changes.append(untracked or modified)
        require(all(valid_changes), "Unexpected isolated-worktree state; reconcile before resume")
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
        "schema": "low7-kimi-production-import-receipt-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
        "status": "committed_push_pending", "parent_commit": parent, "original_import_commit": original_commit,
        "import_commit": final_commit, "worktree": str(worktree), "imported_sources": imported,
        "approved_person_sources": 7, "resource_instances": 10, "fullsize_original_count": index["count"],
        "fullsize_original_bytes": index["original_png_bytes"],
        "new_generation_calls_for_import": 0, "unrelated_rows_preserved": True,
        "builtin_retry_counts_preserved": 9, "ordinary_git_commit": True,
        "push_performed": False, "remote_original_verification_claimed": False, "runtime_acceptance_claimed": False,
    }
    write_json(ROOT / "runtime/low7-evolink-20261030/import-receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False))
    return receipt


def main():
    parser = argparse.ArgumentParser(description="Import exactly seven reviewed LOW sources into an isolated worktree; never calls an image API.")
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        plan = build_plan(args.worktree, ROOT)
        print(json.dumps({"status": "ready_for_isolated_import", "source_count": plan["source_count"], "resource_instances": 10, "new_generation_calls": 0}))
        return 0
    apply(args.worktree, args.create)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
