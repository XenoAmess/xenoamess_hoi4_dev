import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"


def main():
    scope = read_json(EXPERIMENT / "scope.json")
    prepared = read_json(EXPERIMENT / "prepared.json")
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
        "entries": rows,
    })
    print(json.dumps({"observed_at_utc": utc_now(), "counts": dict(sorted(counts.items())), "target": target.relative_to(ROOT).as_posix()}, ensure_ascii=True))


if __name__ == "__main__":
    main()
