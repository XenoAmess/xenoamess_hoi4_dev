import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from runtime import high131_record_review as recorder
from runtime import high131_status as status
from tools.common import file_sha256, write_json


class High131RecordReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.experiment = self.root / "exp"
        self.outputs = self.experiment / "outputs"
        self.outputs.mkdir(parents=True)
        for name, value in (("ROOT", self.root), ("EXPERIMENT", self.experiment), ("machine_id", lambda: "fixture-machine"), ("utc_now", lambda: "2026-01-01T00:00:00+00:00")):
            patch.object(recorder, name, value).start()
            self.addCleanup(patch.stopall)
        self.key = "a" * 64
        self.draft_path = self.root / "draft.json"

    def fixture(self, derived):
        source_path = self.root / "source.png"
        source = Image.new("RGBA", (2, 2))
        source.putdata([(255, 220, 0, 0), (255, 220, 0, 255), (255, 220, 0, 128), (255, 220, 0, 64)])
        source.save(source_path)
        source_sha = file_sha256(source_path)
        source_alpha = source.getchannel("A")
        corners = [source_alpha.getpixel(point) for point in ((0, 0), (1, 0), (0, 1), (1, 1))]
        stem = f"{self.key}-01"
        parent = self.outputs / f"{stem}.png"
        Image.new("RGB", (2, 2), (20, 30, 40)).save(parent)
        parent_sha = file_sha256(parent)
        suffix = "-alpha-repaired-bilinear" if derived else ""
        output = self.outputs / f"{stem}{suffix}.png"
        if derived:
            with Image.open(parent) as parent_image:
                candidate = parent_image.convert("RGBA")
            candidate.putalpha(source_alpha)
            candidate.save(output)
        output_sha = file_sha256(output)
        with Image.open(output) as opened:
            mode = opened.mode
            alpha_extrema = list(opened.getchannel("A").getextrema()) if "A" in opened.getbands() else None
        task_path = self.outputs / f"{stem}.task.json"
        prompt_path = self.outputs / f"{stem}.prompt.txt"
        request_path = self.outputs / f"{stem}.request.json"
        result_path = self.outputs / f"{stem}.result.json"
        write_json(task_path, {"task_id": "fixture-task"})
        prompt_path.write_text("complete fixture prompt", encoding="utf-8")
        write_json(request_path, {"prompt": "complete fixture prompt"})
        write_json(result_path, {"task_id": "fixture-task", "sha256": parent_sha})
        sheet = self.root / "sheet.png"
        Image.new("RGB", (1, 1)).save(sheet)
        proof = {
            "index": 2,
            "source_sha256": self.key,
            "source_png": "source.png",
            "source_png_sha256": source_sha,
            "source_info": {"alpha_extrema": [0, 255]},
            "generation_output": f"exp/outputs/{stem}.png",
            "generation_output_sha256": parent_sha,
            "output": f"exp/outputs/{stem}{suffix}.png",
            "output_sha256": output_sha,
            "output_info": {"size": [2, 2], "mode": mode, "alpha_extrema": alpha_extrema},
            "task": f"exp/outputs/{stem}.task.json",
            "task_sha256": file_sha256(task_path),
            "task_id": "fixture-task",
            "prompt": f"exp/outputs/{stem}.prompt.txt",
            "prompt_sha256": file_sha256(prompt_path),
            "request": f"exp/outputs/{stem}.request.json",
            "request_sha256": file_sha256(request_path),
            "result": f"exp/outputs/{stem}.result.json",
            "result_sha256": file_sha256(result_path),
        }
        write_json(self.experiment / "evidence.json", {
            "schema": "naiwa-evolink-high131-review-evidence-v1",
            "review_sheet": "sheet.png",
            "review_sheet_sha256": file_sha256(sheet),
            "entries": [proof],
        })
        write_json(self.experiment / "scope.json", {"entries": [{"index": 7, "source_sha256": self.key, "source_png": "source.png"}]})
        write_json(self.experiment / "parent.json", {
            "model": "gpt-image-2.5-flare",
            "entries": [{"source_sha256": self.key, "attempt": "external-01", "decision": "approved_for_alpha_repair", "rgb_art_approved": True, "output_sha256": parent_sha}],
        })
        write_json(self.experiment / "receipt.json", {
            "index": 7,
            "source_key_sha256": self.key,
            "status": "completed",
            "new_image_generation_calls": 0,
            "parent_review": "exp/parent.json",
            "parent_review_sha256": file_sha256(self.experiment / "parent.json"),
            "parent_output_sha256": parent_sha,
            "result": {
                "method": recorder.METHOD,
                "base_sha256": parent_sha,
                "output_sha256": output_sha,
                "source_sha256": source_sha,
                "source_corner_alpha_tl_tr_bl_br": corners,
                "resized_corner_alpha_tl_tr_bl_br": corners,
                "output_corner_alpha_tl_tr_bl_br": corners,
                "resized_alpha_sha256": hashlib.sha256(source_alpha.tobytes()).hexdigest(),
                "rgb_unchanged": True,
                "alpha_matches_resized_source": True,
            },
        })
        draft = {
            "schema": "naiwa-evolink-high131-review-observations-v1",
            "index": 7,
            "evidence": "exp/evidence.json",
            "evidence_entry_index": 2,
            "target": "review-test.json",
            "alpha_repair_receipt": "exp/receipt.json",
            "reviewer": "Actually viewed the fixture source, complete candidate and alpha comparisons.",
            "entry": {
                "attempt": "external-01-alpha-repaired-bilinear" if derived else "external-01",
                "decision": "approved_for_production",
                "rgb_art_approved": True,
                "hair_features": {"policy": "hair-features-v1", "status": "approved"},
                "collar_fit": {"policy": "collar-fit-v1", "status": "approved"},
                "positive_observation": "Actual fixture observation.",
                "alpha_decision": "Actual fixture alpha observation.",
                "visible_limitations": "Fixture limits.",
            },
        }
        write_json(self.draft_path, draft)
        return self.draft_path

    def record(self, draft):
        with patch("sys.argv", ["high131_record_review.py", "--draft", str(draft)]), contextlib.redirect_stdout(io.StringIO()):
            recorder.main()

    def test_derived_approval_preserves_source_key_not_source_png_sha(self):
        self.record(self.fixture(derived=True))
        body = json.loads((self.experiment / "review-test.json").read_text(encoding="utf-8"))
        entry = body["entries"][0]
        self.assertEqual(entry["source_sha256"], self.key)
        self.assertEqual(entry["source_sha256"], "a" * 64)
        self.assertNotEqual(entry["source_sha256"], file_sha256(self.root / "source.png"))
        self.assertTrue(entry["source_alpha_repair_performed"])
        self.assertTrue(entry["rgb_unchanged"])
        self.assertTrue(entry["alpha_matches_resized_source"])
        self.assertFalse(entry["production_imported"])

    def test_rgb_working_master_cannot_bypass_final_alpha_review(self):
        with self.assertRaisesRegex(RuntimeError, "RGB working master"):
            self.record(self.fixture(derived=False))
        self.assertFalse((self.experiment / "review-test.json").exists())


    def test_current_attempt_review_uses_timestamp_not_discovery_order(self):
        older = {'reviewed_at_utc': '2026-10-25T19:59:37+00:00', 'review': 'review-recovery-old.json'}
        newer = {'reviewed_at_utc': '2026-10-27T10:40:12+00:00', 'review': 'review-hd-new.json'}
        for reviews in ([older, newer], [newer, older]):
            with self.subTest(reviews=reviews):
                self.assertIs(status.latest_attempt_review(reviews), newer)
        self.assertIsNone(status.latest_attempt_review([]))


if __name__ == "__main__":
    unittest.main()
