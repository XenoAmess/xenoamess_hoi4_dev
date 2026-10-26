import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.high131_io import write_json
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"


def load_nonperson_exceptions(scope):
    path = EXPERIMENT / "nonperson-scope-decision.json"
    if not path.exists():
        return {}, None
    body = read_json(path)
    assert body["schema"] == "naiwa-evolink-high131-nonperson-scope-decision-v1"
    assert body["machine_id"] == machine_id()
    assert body["decision"] == "preserved_original_nonperson_exception"
    assert body["user_selection"]["selected_option"] == "保留原图并登记例外（推荐）"
    assert body["no_image_call_created_for_this_decision"] is True
    assert body["generated_output_required"] is False
    assert body["original_assets_retained"] is True
    assert body["canonical_generated_row_must_not_be_fabricated"] is True
    prior = ROOT / body["prior_visual_review"]
    assert prior.parent == EXPERIMENT
    prior_entries = read_json(prior)["entries"]
    scope_by_key = {row["source_sha256"]: row for row in scope["entries"]}
    exceptions = {}
    for row in body["entries"]:
        key = row["source_sha256"]
        source = scope_by_key[key]
        assert source["index"] == row["index"]
        assert source["source_assets"] == row["source_assets"]
        assert source["source_size"] == row["source_size"]
        assert source["source_png"] == row["source_png"]
        assert source["source_alpha_extrema"] == row["source_alpha_extrema"]
        assert source["converted_png_sha256"] == row["source_png_sha256"]
        assert file_sha256(ROOT / row["source_png"]) == row["source_png_sha256"]
        assert row["observed_subject"]
        assert key not in exceptions
        exceptions[key] = row
    assert {row["source_sha256"] for row in prior_entries} == set(exceptions)
    assert len(exceptions) == 4
    return exceptions, {"path": path.relative_to(ROOT).as_posix(), "sha256": file_sha256(path)}


def main():
    scope = read_json(EXPERIMENT / "scope.json")
    prepared = read_json(EXPERIMENT / "prepared.json")
    nonperson_exceptions, nonperson_scope_receipt = load_nonperson_exceptions(scope)
    prepared_by_key = {row["source_sha256"]: row for row in prepared["entries"]}
    results = collections.defaultdict(dict)
    for result_path in (EXPERIMENT / "outputs").glob("*.result.json"):
        result = read_json(result_path)
        stem = result_path.name[:-len(".result.json")]
        key = stem[:64]
        suffix = stem[65:]
        match = re.fullmatch(r"(\d+)(?:-.+)?", suffix)
        assert match, result_path
        attempt = f"external-{match.group(1)}"
        output = result_path.with_name(stem + ".png")
        assert file_sha256(output) == result["sha256"]
        task_path = result_path.with_name(stem + ".task.json")
        prompt_path = result_path.with_name(stem + ".prompt.txt")
        request_path = result_path.with_name(stem + ".request.json")
        results[key][attempt] = {
            "attempt": attempt,
            "output": output.relative_to(ROOT).as_posix(),
            "output_sha256": result["sha256"],
            "task_id": result["task_id"],
            "downloaded_at_utc": result["downloaded_at_utc"],
            "result": result_path.relative_to(ROOT).as_posix(),
            "result_sha256": file_sha256(result_path),
            "task": task_path.relative_to(ROOT).as_posix(),
            "task_sha256": file_sha256(task_path),
            "prompt": prompt_path.relative_to(ROOT).as_posix(),
            "prompt_sha256": file_sha256(prompt_path),
            "request": request_path.relative_to(ROOT).as_posix(),
            "request_sha256": file_sha256(request_path),
        }
    reviews = collections.defaultdict(lambda: collections.defaultdict(list))
    for path in EXPERIMENT.glob("review-*.json"):
        if path.name.endswith("-evidence.json"):
            continue
        body = read_json(path)
        for entry in body.get("entries", []):
            key = entry["source_sha256"]
            attempt = entry["attempt"]
            base_attempt = re.match(r"external-\d+", attempt).group(0)
            reviews[key][base_attempt].append({
                "attempt": attempt,
                "decision": entry["decision"],
                "reviewed_at_utc": body["reviewed_at_utc"],
                "review": path.relative_to(ROOT).as_posix(),
                "review_sha256": file_sha256(path),
                "review_output": entry.get("output"),
                "review_output_sha256": entry.get("output_sha256"),
                "generated_fullsize_image": entry.get("generated_fullsize_image"),
                "generated_fullsize_sha256": entry.get("generated_fullsize_sha256"),
            })
    rows = []
    counts = collections.Counter()
    for source in scope["entries"]:
        key = source["source_sha256"]
        prep = prepared_by_key[key]
        attempts = results.get(key, {})
        attempt_history = []
        current = None
        for attempt in sorted(attempts, key=lambda value: int(value.split("-")[1])):
            result = attempts[attempt]
            attempt_reviews = sorted(reviews.get(key, {}).get(attempt, []), key=lambda row: row["reviewed_at_utc"])
            review = attempt_reviews[-1] if attempt_reviews else None
            record = {**result, "reviews": attempt_reviews}
            attempt_history.append(record)
            current = record
        if prep["status"] == "nonperson_scope_review_required":
            if key in nonperson_exceptions:
                assert not attempts
                status = "preserved_original_nonperson_exception"
                decision = status
            else:
                status = "nonperson_scope_review_required"
                decision = None
            review = None
        elif current is None:
            status = prep["status"]
            decision = None
            review = None
        else:
            attempt_reviews = reviews.get(key, {}).get(current["attempt"], [])
            review = attempt_reviews[-1] if attempt_reviews else None
            decision = review["decision"] if review else "returned_pending_visual_review"
            if review is None:
                status = "returned_pending_visual_review"
            elif decision == "approved_for_production":
                status = "approved_pending_import"
            else:
                status = "rejected_latest_attempt"
        counts[status] += 1
        rows.append({
            "index": source["index"],
            "source_sha256": key,
            "source_assets": source["source_assets"],
            "status": status,
            "current_decision": decision,
            "current_review": review,
            "attempts_returned": attempt_history,
            "nonperson_scope_exception": nonperson_scope_receipt if key in nonperson_exceptions else None,
            "planned_route": {field: prep.get(field) for field in ("status", "model", "size", "background", "prompt_file", "prompt_sha256")},
        })
    target = EXPERIMENT / "progress.json"
    write_json(target, {
        "schema": "naiwa-evolink-high131-progress-v1",
        "machine_id": machine_id(),
        "observed_at_utc": utc_now(),
        "source_count": len(rows),
        "counts": dict(sorted(counts.items())),
        "approved_png_returns_are_not_production_imports": True,
        "preserved_original_nonperson_exceptions_are_not_generated_portraits": True,
        "nonperson_scope_decision": nonperson_scope_receipt,
        "entries": rows,
    })
    print(json.dumps({"observed_at_utc": utc_now(), "counts": dict(sorted(counts.items())), "target": target.relative_to(ROOT).as_posix()}, ensure_ascii=True))


if __name__ == "__main__":
    main()
