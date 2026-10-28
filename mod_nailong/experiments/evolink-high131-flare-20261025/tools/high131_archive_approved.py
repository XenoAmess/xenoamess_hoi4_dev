import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.high131_io import write_json
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"


def main():
    progress = read_json(EXPERIMENT / "progress.json")
    entries = []
    for source in progress["entries"]:
        if source["status"] not in {"approved_pending_import", "approved_imported"}:
            continue
        key = source["source_sha256"]
        current = source["attempts_returned"][-1]
        review = source["current_review"]
        assert review["decision"] == "approved_for_production"
        review_path = ROOT / review["review"]
        assert file_sha256(review_path) == review["review_sha256"]
        output = ROOT / (review.get("review_output") or current["output"])
        expected_sha = review.get("review_output_sha256") or current["output_sha256"]
        actual_sha = file_sha256(output)
        assert actual_sha == expected_sha
        destination = ROOT / f"mod_nailong/assets/generated_fullsize/{actual_sha}.png"
        if destination.exists():
            assert file_sha256(destination) == actual_sha
        else:
            destination.write_bytes(output.read_bytes())
        assert file_sha256(destination) == actual_sha
        recorded_master = review.get("generated_fullsize_image")
        if recorded_master:
            assert recorded_master == destination.relative_to(ROOT).as_posix()
            assert review["generated_fullsize_sha256"] == actual_sha
        with Image.open(destination) as image:
            size = list(image.size)
            mode = image.mode
        entries.append({
            "index": source["index"],
            "source_sha256": key,
            "source_assets": source["source_assets"],
            "approved_attempt": review["attempt"],
            "source_output": output.relative_to(ROOT).as_posix(),
            "generated_fullsize_image": destination.relative_to(ROOT).as_posix(),
            "generated_fullsize_sha256": actual_sha,
            "bytes": destination.stat().st_size,
            "size": size,
            "mode": mode,
            "task_id": current["task_id"],
            "prompt_sha256": current["prompt_sha256"],
            "review": review["review"],
            "review_sha256": review["review_sha256"],
            "reviewed_at_utc": review["reviewed_at_utc"],
            "production_imported": source["status"] == "approved_imported",
            "production_import_pending": source["status"] == "approved_pending_import",
        })
    entries.sort(key=lambda row: row["index"])
    target = EXPERIMENT / "approved-masters.json"
    write_json(target, {
        "schema": "naiwa-evolink-high131-approved-masters-v1",
        "machine_id": machine_id(),
        "observed_at_utc": utc_now(),
        "count": len(entries),
        "scope": "Only current SHA-bound outputs with actual approved_for_production reviews. Byte-identical archival is checked; canonical generated.json/fullsize-files.json is not written by this utility.",
        "entries": entries,
    })
    print(json.dumps({"approved_masters": len(entries), "target": target.relative_to(ROOT).as_posix(), "indices": [row["index"] for row in entries]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
