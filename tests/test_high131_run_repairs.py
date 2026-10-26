import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from runtime import high131_run_repairs as repairs
from tools.common import file_sha256, write_json


class High131RunRepairsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        patch.object(repairs.batch, "ROOT", root).start()
        self.addCleanup(patch.stopall)
        self.key = "a" * 64
        stem = f"{self.key}-04"
        self.state = {
            "index": 60,
            "key": self.key,
            "stem": stem,
            "entry": {"attempt": "external-04"},
            "execution": root / "executions" / f"{stem}.json",
            "request": root / "outputs" / f"{stem}.request.json",
            "task": root / "outputs" / f"{stem}.task.json",
            "output": root / "outputs" / f"{stem}.png",
            "result": root / "outputs" / f"{stem}.result.json",
        }
        self.execution = {
            "index": 60,
            "source_sha256": self.key,
            "attempt": "external-04",
            "status": "failed",
            "started_at_utc": "2026-01-01T00:00:00+00:00",
            "finished_at_utc": "2026-01-01T00:00:01+00:00",
            "task_id": None,
            "output_sha256": None,
            "result": None,
            "error": "Connection refused before a task ID was returned",
        }
        write_json(self.state["execution"], self.execution)
        write_json(self.state["request"], {"prompt": "retained complete prompt"})

    def test_finished_no_task_failure_is_held_not_completed(self):
        hold = repairs.unresolved_hold(self.state)
        self.assertEqual(hold["reason"], "unresolved_repair_execution_hold_retained")
        self.assertEqual(hold["execution_sha256"], file_sha256(self.state["execution"]))
        self.assertEqual(hold["request_sha256"], file_sha256(self.state["request"]))
        self.assertFalse(hold["completion_claimed"])
        self.assertFalse(hold["retry_or_resume_attempted"])

    def test_task_record_blocks_hold(self):
        write_json(self.state["task"], {"task_id": "existing-task"})
        with self.assertRaisesRegex(repairs.batch.BatchError, "repair hold requires"):
            repairs.unresolved_hold(self.state)

    def test_collect_requires_verified_hold_and_filters_indices(self):
        context = {"repair_entries": [{"source_sha256": self.key, "attempt": "external-04"}]}
        with (
            patch.object(repairs, "repair_state", return_value=self.state),
            patch.object(repairs.batch, "artifact_action", return_value=("stop", "pending_request_requires_manual_check")),
        ):
            selected, skipped, failed = repairs.collect_repairs(context, 1, only_indices={60}, acknowledged_holds={60})
            self.assertEqual(selected, [])
            self.assertEqual(failed, [])
            self.assertEqual(len(skipped), 1)
            self.assertFalse(skipped[0]["completion_claimed"])
            selected, skipped, failed = repairs.collect_repairs(context, 1, only_indices={61}, acknowledged_holds={60})
            self.assertEqual((selected, failed), ([], []))
            self.assertEqual(len(skipped), 1)
            self.assertFalse(skipped[0]["completion_claimed"])
            selected, skipped, failed = repairs.collect_repairs(context, 1, only_indices={61})
            self.assertEqual((selected, skipped, failed), ([], [], []))

    def test_hold_cli_cannot_overlap_dispatch_or_stand_alone(self):
        with patch("sys.argv", ["high131_run_repairs.py", "--limit", "1", "--acknowledge-hold", "60"]), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            repairs.parse_args()
        with patch("sys.argv", ["high131_run_repairs.py", "--limit", "1", "--index", "60", "--acknowledge-hold", "60"]), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            repairs.parse_args()
        with patch("sys.argv", ["high131_run_repairs.py", "--limit", "1", "--index", "61", "--acknowledge-hold", "60"]):
            args = repairs.parse_args()
        self.assertEqual(args.index, [61])
        self.assertEqual(args.acknowledge_hold, [60])


class HDRepairInputContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        patch.object(repairs.batch, "ROOT", self.root).start()
        self.addCleanup(patch.stopall)
        source = self.root / "source.png"
        mascot = self.root / "mascot.png"
        source.write_bytes(b"source")
        mascot.write_bytes(b"mascot")
        self.key = "a" * 64
        self.commit = "c" * 40
        target = self.root / "target.png"
        target.write_bytes(b"target")
        self.digest = file_sha256(target)
        self.master = self.root / "mod_nailong/assets/generated_fullsize" / f"{self.digest}.png"
        self.master.parent.mkdir(parents=True)
        self.master.write_bytes(target.read_bytes())
        self.master_relative = self.master.relative_to(self.root).as_posix()
        self.proof_path = self.root / "runtime/proof.json"
        write_json(self.proof_path, {
            "status": "verified",
            "commit": self.commit,
            "machine_id": repairs.batch.machine_id(),
            "distinct_outputs": 1,
            "original_png_bytes": target.stat().st_size,
        })
        self.target_url = f"https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{self.commit}/{self.master_relative}"
        self.context = {
            "release_assets": {self.key: {"url": "source-url"}},
            "scope": {"mascot_reference": {"sha256": file_sha256(mascot), "url": "mascot-url"}},
        }
        self.state = {
            "key": self.key,
            "repair_input_mode": "raw-hd-edit-v1",
            "original_entry": {"converted_png_sha256": file_sha256(source)},
            "repair": {
                "repair_input_mode": "raw-hd-edit-v1",
                "remote_commit": self.commit,
                "remote_readback": "runtime/proof.json",
                "edit_target_image": self.master_relative,
                "edit_target_sha256": self.digest,
                "rejected_output_sha256": self.digest,
                "remote_target_url": self.target_url,
                "image_urls": [self.target_url, "source-url", "mascot-url"],
                "ordered_input_sha256": [self.digest, file_sha256(source), file_sha256(mascot)],
            },
        }

    def index(self):
        return {
            "count": 1,
            "original_png_bytes": self.master.stat().st_size,
            "outputs": {self.digest: {"path": self.master_relative, "bytes": self.master.stat().st_size}},
        }

    def test_verified_raw_hd_binding_returns_three_ordered_inputs(self):
        completed = repairs.batch.subprocess.CompletedProcess(args=["git"], returncode=0, stdout=json.dumps(self.index()))
        with patch.object(repairs.batch.subprocess, "run", return_value=completed) as run:
            inputs, urls = repairs.repair_input_contract(self.context, self.state)
        self.assertEqual(inputs, [self.digest, file_sha256(self.root / "source.png"), file_sha256(self.root / "mascot.png")])
        self.assertEqual(urls, [self.target_url, "source-url", "mascot-url"])
        self.assertEqual(run.call_args.args[0], ["git", "show", f"{self.commit}:mod_nailong/data/fullsize-files.json"])

    def test_unverified_proof_or_target_mismatch_is_blocked(self):
        proof = repairs.batch.read_json(self.proof_path)
        proof["status"] = "running"
        write_json(self.proof_path, proof)
        with self.assertRaisesRegex(repairs.batch.BatchError, "Remote original proof"):
            repairs.repair_input_contract(self.context, self.state)
        proof["status"] = "verified"
        write_json(self.proof_path, proof)
        self.state["repair"]["edit_target_sha256"] = "0" * 64
        with self.assertRaisesRegex(repairs.batch.BatchError, "exact rejected output"):
            repairs.repair_input_contract(self.context, self.state)


class MaskRepairInputContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        patch.object(repairs.batch, "ROOT", self.root).start()
        self.addCleanup(patch.stopall)
        self.key = "a" * 64
        self.source_sha = "1" * 64
        self.target_sha = "2" * 64
        self.mascot_sha = "3" * 64
        self.mask_sha = "4" * 64
        self.detail_sha = "5" * 64
        self.manifest_sha = "6" * 64
        self.commit = "c" * 40
        self.target_relative = f"mod_nailong/assets/generated_fullsize/{self.target_sha}.png"
        self.mask_relative = "mod_nailong/experiments/evolink-high131-flare-20261025/review-masks/mask.png"
        self.detail_relative = "mod_nailong/experiments/evolink-high131-flare-20261025/review-source-details/detail.png"
        self.manifest_relative = "mod_nailong/experiments/evolink-high131-flare-20261025/review-masks/mask.json"
        prefix = f"https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{self.commit}"
        self.target_url = f"{prefix}/{self.target_relative}"
        self.mask_url = f"{prefix}/{self.mask_relative}"
        self.detail_url = f"{prefix}/{self.detail_relative}"
        self.mask = {
            "path": self.mask_relative,
            "sha256": self.mask_sha,
            "url": self.mask_url,
            "target_sha256": self.target_sha,
            "manifest": self.manifest_relative,
            "manifest_sha256": self.manifest_sha,
        }
        self.note_detail = {
            "path": self.detail_relative,
            "sha256": self.detail_sha,
            "url": self.detail_url,
            "source_png_sha256": self.source_sha,
        }
        self.repair = {
            "repair_input_mode": repairs.hd_proof.MASK_NOTE_MODE,
            "remote_commit": self.commit,
            "remote_readback": "runtime/proof.json",
            "edit_target_image": self.target_relative,
            "edit_target_sha256": self.target_sha,
            "rejected_output_sha256": self.target_sha,
            "remote_target_url": self.target_url,
            "image_urls": [self.target_url, "source-url", "mascot-url", self.detail_url],
            "ordered_input_sha256": [self.target_sha, self.source_sha, self.mascot_sha, self.detail_sha],
            "note_detail": self.note_detail,
            "mask": self.mask,
            "mask_url": self.mask_url,
        }
        self.proof = {
            "targets": {
                self.mask_sha: {
                    "mask_manifest": self.manifest_relative,
                    "mask_manifest_sha256": self.manifest_sha,
                },
            },
        }
        self.state = {
            "key": self.key,
            "repair_input_mode": repairs.hd_proof.MASK_NOTE_MODE,
            "original_entry": {
                "source_sha256": self.key,
                "index": 65,
                "converted_png_sha256": self.source_sha,
                "source_png": "runtime/references/source.png",
            },
            "entry": {"mask_url": self.mask_url},
            "repair": self.repair,
            "mask": self.mask,
        }
        self.context = {
            "release_assets": {self.key: {"url": "source-url"}},
            "scope": {"mascot_reference": {"sha256": self.mascot_sha, "url": "mascot-url"}},
        }

    def validated_contract(self, state):
        with (
            patch.object(repairs.hd_proof, "load_remote_proof", return_value=(self.proof, None)),
            patch.object(repairs.hd_proof, "validate_remote_target", return_value=self.target_url),
            patch.object(repairs.hd_proof, "validate_remote_reference", return_value=self.detail_url) as detail_check,
            patch.object(repairs.hd_proof, "validate_remote_mask", return_value=self.mask_url) as mask_check,
        ):
            result = repairs.repair_input_contract(self.context, state)
        return result, detail_check, mask_check

    def test_mask_mode_uses_note_detail_and_binds_independent_mask(self):
        (inputs, urls), detail_check, mask_check = self.validated_contract(self.state)
        self.assertEqual(inputs, self.repair["ordered_input_sha256"])
        self.assertEqual(urls, self.repair["image_urls"])
        self.assertNotIn(self.mask_url, urls)
        detail_check.assert_called_once()
        mask_check.assert_called_once_with(
            self.proof,
            self.commit,
            self.root / self.mask_relative,
            self.mask_sha,
            self.root / self.target_relative,
            self.target_sha,
            root=self.root,
        )

    def test_mask_url_target_and_manifest_mismatches_fail_closed(self):
        for field, value in (
            ("mask_url", "https://example.invalid/other-mask.png"),
            ("target_sha256", "0" * 64),
            ("manifest", "mod_nailong/experiments/evolink-high131-flare-20261025/review-masks/other.json"),
            ("manifest_sha256", "0" * 64),
        ):
            with self.subTest(field=field):
                state = dict(self.state)
                repair = dict(self.repair)
                mask = dict(self.mask)
                state["repair"] = repair
                repair["mask"] = mask
                if field == "mask_url":
                    repair["mask_url"] = value
                else:
                    mask[field] = value
                with self.assertRaises(repairs.batch.BatchError):
                    self.validated_contract(state)

    def test_non_mask_mode_cannot_carry_mask_metadata(self):
        state = dict(self.state)
        state["repair_input_mode"] = repairs.hd_proof.NOTE_DETAIL_MODE
        with self.assertRaisesRegex(repairs.batch.BatchError, "only valid for raw-hd-mask-note-v1"):
            repairs.repair_input_contract(self.context, state)

    def test_repair_state_forwards_mask_metadata_without_adding_an_image_input(self):
        experiment = self.root / "exp"
        repair = {
            **self.repair,
            "source_sha256": self.key,
            "attempt": "external-02",
            "prompt_file": f"exp/prompts/{self.key}-02.txt",
            "prompt_sha256": "7" * 64,
            "output": f"exp/outputs/{self.key}-02.png",
            "previous_prompt": f"exp/outputs/{self.key}-01.prompt.txt",
            "review": "exp/review.json",
            "review_sha256": "8" * 64,
        }
        context = {
            "prepared_entries": {self.key: self.state["original_entry"]},
            "scope_entries": {self.key: {"index": 65}},
            "progress_entries": {self.key: {}},
            "repair_preparation_sha256": "9" * 64,
        }
        with (
            patch.object(repairs, "EXPERIMENT", experiment),
            patch.object(repairs, "PROMPTS_DIR", experiment / "prompts"),
            patch.object(repairs, "OUTPUTS_DIR", experiment / "outputs"),
            patch.object(repairs, "REPAIR_PATH", experiment / "repairs.json"),
            patch.object(repairs.batch, "LOGS_DIR", experiment / "logs"),
            patch.object(repairs.batch, "EXECUTIONS_DIR", experiment / "executions"),
        ):
            state = repairs.repair_state(context, repair)
        self.assertEqual(state["entry"]["mask_url"], self.mask_url)
        self.assertEqual(state["mask_url"], self.mask_url)
        self.assertEqual(state["mask"], self.mask)
        self.assertEqual(state["note_detail"], self.note_detail)
        self.assertNotIn(self.mask_url, state["entry"]["image_urls"])


class LaterRepairArtifactTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name, directory_name in (("OUTPUTS_DIR", "outputs"), ("EXECUTIONS_DIR", "executions"), ("LOGS_DIR", "logs")):
            directory = self.root / directory_name
            directory.mkdir()
            patch.object(repairs.batch, name, directory).start()
        patch.object(repairs, "OUTPUTS_DIR", self.root / "outputs").start()
        self.addCleanup(patch.stopall)
        self.key = "a" * 64
        self.state = {
            "index": 60,
            "key": self.key,
            "stem": f"{self.key}-04",
            "entry": {"attempt": "external-04"},
            "previous_number": 3,
            "previous_attempt": "external-03",
            "progress_entry": {"attempts_returned": []},
        }

    def test_every_later_dispatch_artifact_blocks_new_post(self):
        for suffix, directory in (
            ("request.json", "outputs"),
            ("task.json", "outputs"),
            ("prompt.txt", "outputs"),
            ("json", "executions"),
            ("log", "logs"),
        ):
            with self.subTest(suffix=suffix):
                for child in self.root.iterdir():
                    if child.is_dir():
                        for path in child.iterdir():
                            path.unlink()
                    else:
                        child.unlink()
                artifact = self.root / directory / f"{self.key}-05.{suffix}"
                artifact.write_text("pending evidence", encoding="utf-8")
                context = {"repair_entries": [{"source_sha256": self.key, "attempt": "external-04"}]}
                with (
                    patch.object(repairs, "repair_state", return_value=self.state),
                    patch.object(repairs.batch, "artifact_action", return_value=("dispatch", None)),
                ):
                    selected, skipped, failed = repairs.collect_repairs(context, 1)
                self.assertEqual(selected, [])
                self.assertEqual(skipped, [])
                self.assertEqual(len(failed), 1)
                self.assertEqual(failed[0]["status"], "existing_or_later_attempt_requires_manual_check")
                self.assertIn(str(artifact), failed[0]["error"])

    def test_missing_or_invalid_alpha_extrema_fail_closed(self):
        for extrema in (None, [], [0], [0, "255"], [True, 255], [-1, 255], [0, 256]):
            with self.subTest(extrema=extrema):
                state = {
                    "original_entry": {"n": 1, "source_alpha_extrema": extrema},
                    "repair": {"background": "transparent"},
                    "entry": {"background": "transparent"},
                    "repair_input_mode": "raw-hd-edit-v1",
                }
                with patch.object(repairs, "require_file_sha", return_value=None):
                    with self.assertRaises(repairs.batch.BatchError) as caught:
                        repairs.validate_repair_binding({"repair_preparation_sha256": "test", "progress_sha256": "test"}, state)
                self.assertEqual(caught.exception.status, "repair_input_mismatch")


if __name__ == "__main__":
    unittest.main()
