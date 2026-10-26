import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from runtime import high131_run_batch as batch
from tools.common import file_sha256, write_json


class High131RunBatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.experiment = self.root / "exp"
        for name, value in (
            ("ROOT", self.root),
            ("EXPERIMENT", self.experiment),
            ("PROMPTS_DIR", self.experiment / "prompts"),
            ("OUTPUTS_DIR", self.experiment / "outputs"),
            ("LOGS_DIR", self.experiment / "logs"),
            ("EXECUTIONS_DIR", self.experiment / "executions"),
        ):
            patch.object(batch, name, value).start()
            self.addCleanup(patch.stopall)
        self.key117 = "a" * 64
        self.key118 = "b" * 64
        self.context = {
            "scope": {"entries": [self.source(117, self.key117), self.source(118, self.key118)]},
            "prepared_entries": {},
        }
        for index, key in ((117, self.key117), (118, self.key118)):
            self.context["prepared_entries"][key] = {
                **self.source(index, key),
                "status": "prepared_not_dispatched",
                "attempt": "external-01",
                "prompt_file": f"exp/prompts/{key}-01.txt",
                "prompt_sha256": "c" * 64,
                "output": f"exp/outputs/{key}-01.png",
            }
        self.execution_path = self.experiment / "executions" / f"{self.key117}-01.json"
        write_json(self.execution_path, {
            "index": 117,
            "source_sha256": self.key117,
            "attempt": "external-01",
            "status": "failed",
            "finished_at_utc": "2026-01-01T00:00:00+00:00",
            "task_id": None,
            "result": None,
            "output_sha256": None,
        })
        write_json(self.experiment / "outputs" / f"{self.key117}-01.request.json", {"prompt": "retained unknown POST"})

    @staticmethod
    def source(index, key):
        return {"index": index, "source_sha256": key}

    def test_explicit_hold_allows_other_original_without_replaying_unknown_post(self):
        selected, skipped, failed = batch.collect_batch(self.context, 1, only_indices={118}, acknowledged_holds={117})
        self.assertEqual([row["index"] for row in selected], [118])
        self.assertEqual(failed, [])
        self.assertEqual(len(skipped), 1)
        hold = skipped[0]
        self.assertEqual(hold["index"], 117)
        self.assertEqual(hold["reason"], "unresolved_execution_hold_retained")
        self.assertEqual(hold["execution_sha256"], file_sha256(self.execution_path))
        self.assertFalse(hold["completion_claimed"])
        self.assertFalse(hold["retry_or_resume_attempted"])

    def test_unresolved_source_cannot_be_replayed_when_explicitly_selected(self):
        selected, skipped, failed = batch.collect_batch(self.context, 1, only_indices={117})
        self.assertEqual(selected, [])
        self.assertEqual(skipped, [])
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["status"], "pending_request_requires_manual_check")

    def test_hold_requires_a_finished_unresolved_execution(self):
        body = dict(batch.read_json(self.execution_path))
        body["status"] = "completed"
        write_json(self.execution_path, body)
        with self.assertRaisesRegex(batch.BatchError, "finished unresolved"):
            batch.collect_batch(self.context, 1, only_indices={118}, acknowledged_holds={117})

    def test_hold_requires_explicit_other_index_and_cannot_overlap(self):
        with patch("sys.argv", ["high131_run_batch.py", "--limit", "1", "--acknowledge-hold", "117"]), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            batch.parse_args()
        with patch("sys.argv", ["high131_run_batch.py", "--limit", "1", "--index", "117", "--acknowledge-hold", "117"]), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            batch.parse_args()
    def test_hd_input_validation_preserves_target_source_and_mascot_order(self):
        source = self.root / "source.png"
        mascot = self.root / "mascot.png"
        source.write_bytes(b"source")
        mascot.write_bytes(b"mascot")
        source_sha = file_sha256(source)
        mascot_sha = file_sha256(mascot)
        target_sha = "d" * 64
        expected_inputs = [target_sha, source_sha, mascot_sha]
        expected_urls = ["https://example.invalid/target.png", "https://example.invalid/source.png", "https://example.invalid/mascot.png"]
        key = self.key118
        prompt_path = self.experiment / "prompts" / f"{key}-03.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text("complete precise edit prompt", encoding="utf-8")
        entry = {
            "source_sha256": key,
            "source_png": "source.png",
            "converted_png_sha256": source_sha,
            "prompt_sha256": batch.sha256_bytes(prompt_path.read_bytes()),
            "ordered_input_sha256": expected_inputs,
            "image_urls": expected_urls,
            "model": "model",
            "size": "1:1",
            "resolution": "2K",
            "quality": "high",
            "background": "transparent",
            "n": 1,
            "attempt": "external-03",
        }
        state = {
            "entry": entry,
            "index": 118,
            "key": key,
            "stem": f"{key}-03",
            "output": self.experiment / "outputs" / f"{key}-03.png",
            "scope_entry": {"source_png": "source.png", "converted_png_sha256": source_sha},
            "prompt_path": prompt_path,
            "input_validation": lambda context, current: (expected_inputs, expected_urls),
            "dry_run_log": self.experiment / "logs" / f"{key}-03-dryrun.log",
            "actual_log": self.experiment / "logs" / f"{key}-03.log",
            "execution": self.experiment / "executions" / f"{key}-03.json",
        }
        context = {
            "scope": {"model": "model", "mascot_reference": {"path": "mascot.png", "sha256": mascot_sha, "url": expected_urls[2]}},
            "release_assets": {key: {"url": expected_urls[1], "converted_png_sha256": source_sha, "public_unauthenticated_sha256_verified": True}},
            "prepared_sha256": "1" * 64,
            "scope_sha256": "2" * 64,
            "input_release_sha256": "3" * 64,
        }
        with patch.object(batch, "require_context_unchanged", return_value=None):
            result = batch.validate_frozen_entry(context, state)
        self.assertEqual(result["parameters"]["image_urls"], expected_urls)
        self.assertNotIn("mask_url", result["parameters"])
        self.assertNotIn("--mask-url", result["command"])
        self.assertEqual(entry["ordered_input_sha256"], expected_inputs)
        command = result["command"]
        self.assertEqual([command[offset + 1] for offset, value in enumerate(command[:-1]) if value == "--image-url"], expected_urls)

        mask_url = "https://example.invalid/mask.png"
        mask = {
            "path": "exp/review-masks/mask.png",
            "sha256": "4" * 64,
            "url": mask_url,
            "target_sha256": target_sha,
            "manifest": "exp/review-masks/mask.json",
            "manifest_sha256": "5" * 64,
        }
        entry["mask_url"] = mask_url
        state["mask"] = mask
        state["mask_url"] = mask_url
        with patch.object(batch, "require_context_unchanged", return_value=None):
            masked = batch.validate_frozen_entry(context, state)
        self.assertEqual(masked["parameters"]["mask_url"], mask_url)
        self.assertEqual(masked["command"][-2:], ["--mask-url", mask_url])
        self.assertEqual(masked["parameters"]["image_urls"], expected_urls)

        with (
            patch.object(batch, "artifact_action", return_value=("dispatch", None)),
            patch.object(batch, "validate_frozen_entry", return_value=masked),
            patch.object(batch, "require_disk_space", return_value=100 * 1024 ** 3),
            patch.object(batch, "run_to_log", return_value=0),
            patch.object(batch, "validate_dry_run", return_value=None),
            patch.object(batch, "machine_id", return_value="test-machine"),
            patch.object(batch, "write_json_new") as write_execution,
            patch.object(batch, "finish_actual_execution", return_value="6" * 64),
        ):
            self.assertEqual(batch.dispatch_one(context, state), ("completed", "6" * 64))
        record = write_execution.call_args.args[1]
        self.assertEqual(record["mask"], mask)
        self.assertEqual(record["mask_url"], mask_url)
        self.assertEqual(record["arguments"][-2:], ["--mask-url", mask_url])


if __name__ == "__main__":
    unittest.main()
