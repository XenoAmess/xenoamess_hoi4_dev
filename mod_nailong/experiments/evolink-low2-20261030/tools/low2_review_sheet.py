from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025/tools"))
import high131_review_sheet as review

review.ROOT = ROOT
review.EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-low2-20261030"
original_write_json = review.write_json


def write_json(path, body):
    if body.get("schema") == "naiwa-evolink-high131-review-evidence-v1":
        body = {**body, "schema": "low2-kimi-evolink-review-evidence-v1"}
    original_write_json(path, body)


review.write_json = write_json

if __name__ == "__main__":
    review.main()
