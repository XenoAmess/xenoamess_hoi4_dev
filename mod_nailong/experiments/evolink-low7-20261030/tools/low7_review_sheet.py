from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from runtime import high131_review_sheet as review

review.ROOT = ROOT
review.EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-low7-20261030"
write_json = review.write_json


def scoped_write_json(path, value):
    return write_json(path, {**value, "schema": "low7-kimi-evolink-review-evidence-v1"})


review.write_json = scoped_write_json


if __name__ == "__main__":
    review.main()
