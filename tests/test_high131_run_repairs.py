import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from runtime import high131_prepare_hd_repairs as hd_prompt
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

    def prepare_authorized_repost(self):
        root = repairs.batch.ROOT
        patch.object(repairs.batch, 'EXPERIMENT', root / 'experiment').start()
        self.execution.update(prompt_sha256='b' * 64, ordered_input_sha256=['source', 'mascot'])
        write_json(self.state['execution'], self.execution)
        authorization_path = root / 'experiment/authorized-repost-20261028.json'
        write_json(authorization_path, {
            'schema': 'high131-authorized-repost-v1',
            'machine_id': repairs.batch.machine_id(),
            'allowed_new_attempts': {'60': 'external-05'},
            'one_new_attempt_per_source': True,
            'preserve_full_prompt_input_order_bytes_and_route': True,
            'executor': 'Kimi',
        })
        stem = f'{self.key}-05'
        output = self.state['output'].with_name(stem + '.png')
        output.write_bytes(repairs.batch.PNG_SIGNATURE)
        result = {
            'task_id': 'authorized-repost-task', 'sha256': file_sha256(output),
            'bytes': output.stat().st_size, 'downloaded_at_utc': '2026-01-02T00:00:00Z',
            'png_signature_verified': True,
        }
        write_json(self.state['result'].with_name(stem + '.result.json'), result)
        self.state['request'].with_name(stem + '.request.json').write_bytes(self.state['request'].read_bytes())
        execution = {
            'index': 60, 'source_sha256': self.key, 'attempt': 'external-05',
            'status': 'completed',
            'repost_authorization': 'experiment/authorized-repost-20261028.json',
            'previous_attempt': 'external-04',
            'previous_execution': self.state['execution'].relative_to(root).as_posix(),
            'previous_execution_sha256': file_sha256(self.state['execution']),
            'previous_request': self.state['request'].relative_to(root).as_posix(),
            'previous_request_sha256': file_sha256(self.state['request']),
            'new_attempt_not_old_task_recovery': True,
            'possible_duplicate_billing_acknowledged': True,
            'new_generation_tasks_created': 1, 'one_new_attempt_limit': 1,
            'prompt_sha256': 'b' * 64, 'ordered_input_sha256': ['source', 'mascot'],
            'output': output.relative_to(root).as_posix(), 'output_sha256': result['sha256'],
            'task_id': result['task_id'], 'result': result,
        }
        write_json(self.state['execution'].with_name(stem + '.json'), execution)
        return authorization_path

    def test_authorized_repost_releases_only_new_dispatch_gate(self):
        self.prepare_authorized_repost()
        hold = repairs.authorized_repost_hold(self.state)
        self.assertEqual(hold['reason'], 'authorized_repost_returned_historical_request_remains_unresolved')
        self.assertEqual(hold['authorized_repost_task_id'], 'authorized-repost-task')
        self.assertFalse(hold['completion_claimed'])
        self.assertFalse(hold['historical_output_or_old_task_recovery_claimed'])
        self.assertEqual(repairs.batch.read_json(self.state['execution'])['status'], 'failed')
        context = {'repair_entries': [{'source_sha256': self.key, 'attempt': 'external-04'}]}
        with (
            patch.object(repairs, 'repair_state', return_value=self.state),
            patch.object(repairs.batch, 'artifact_action', return_value=('stop', 'pending_request_requires_manual_check')),
        ):
            selected, skipped, failed = repairs.collect_repairs(context, 1, only_indices={60})
        self.assertEqual((selected, failed), ([], []))
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]['authorized_repost_attempt'], 'external-05')

    def test_unrelated_or_missing_authorized_repost_keeps_hold(self):
        authorization_path = self.prepare_authorized_repost()
        authorization = repairs.batch.read_json(authorization_path)
        authorization['allowed_new_attempts']['60'] = 'external-06'
        write_json(authorization_path, authorization)
        with self.assertRaisesRegex(repairs.batch.BatchError, 'No exact user-authorized repost'):
            repairs.authorized_repost_hold(self.state)

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


class HDRepairPromptTests(unittest.TestCase):
    def prepare_mask_prompt(self, index, key, previous_attempt, mask_name):
        source_experiment = hd_prompt.EXPERIMENT
        attempt = f'external-{int(previous_attempt[-2:]) + 1:02}'
        with tempfile.TemporaryDirectory(dir=repairs.batch.ROOT / 'runtime') as directory:
            experiment = Path(directory)
            (experiment / 'prompts').mkdir()
            for name in ('scope.json', 'prepared.json', 'output-masters.json', f'note-detail-sources-{index}.json', mask_name):
                shutil.copyfile(source_experiment / name, experiment / name)
            details = json.loads((experiment / f'note-detail-sources-{index}.json').read_text(encoding='utf-8'))
            detail = details['entries'][0]
            detail_file = experiment / 'review-source-details' / Path(detail['path']).name
            detail_file.parent.mkdir(parents=True)
            shutil.copyfile(repairs.batch.ROOT / detail['path'], detail_file)
            detail['path'] = detail_file.relative_to(repairs.batch.ROOT).as_posix()
            write_json(experiment / f'note-detail-sources-{index}.json', details)
            mask = json.loads((experiment / mask_name).read_text(encoding='utf-8'))
            mask_file = experiment / 'review-masks' / Path(mask['mask_file']).name
            mask_file.parent.mkdir(parents=True)
            shutil.copyfile(repairs.batch.ROOT / mask['mask_file'], mask_file)
            mask['mask_file'] = mask_file.relative_to(repairs.batch.ROOT).as_posix()
            write_json(experiment / mask_name, mask)
            progress = json.loads((source_experiment / 'progress.json').read_text(encoding='utf-8'))
            current = next(row for row in progress['entries'] if row['source_sha256'] == key)
            current['attempts_returned'] = [row for row in current['attempts_returned'] if row['attempt'] <= previous_attempt]
            current['status'] = 'rejected_latest_attempt'
            current['current_decision'] = 'rejected_for_production'
            current['current_review'] = current['attempts_returned'][-1]['reviews'][-1]
            write_json(experiment / 'progress.json', progress)
            preparation = json.loads((source_experiment / 'card-repair-preparation.json').read_text(encoding='utf-8'))
            preparation['entries'] = [row for row in preparation['entries'] if (row['source_sha256'], row['attempt']) != (key, attempt)]
            write_json(experiment / 'card-repair-preparation.json', preparation)
            old_prompt = experiment / 'outputs' / f'{key}-{previous_attempt[-2:]}.prompt.txt'
            old_prompt.parent.mkdir(parents=True)
            shutil.copyfile(source_experiment / 'outputs' / f'{key}-{previous_attempt[-2:]}.prompt.txt', old_prompt)
            argv = [
                'high131_prepare_hd_repairs.py', '--remote-commit', 'f8521add92e65e4ffd94818b7e085cae0cfbde41',
                '--readback', 'runtime/test-mask-prompt-proof.json', '--index', str(index), '--note-details', '--mask',
                '--mask-revision', '3' if index == 52 else '1',
            ]
            with (
                patch.object(hd_prompt, 'EXPERIMENT', experiment),
                patch.object(sys, 'argv', argv),
                patch.object(hd_prompt.hd_proof, 'load_remote_proof', return_value=({}, {})),
                patch.object(hd_prompt.hd_proof, 'validate_remote_target', return_value='target-url'),
                patch.object(hd_prompt.hd_proof, 'validate_remote_reference', return_value='detail-url'),
                patch.object(hd_prompt.hd_proof, 'validate_remote_mask', return_value='mask-url'),
            ):
                hd_prompt.main()
            prompt_path = experiment / 'prompts' / f'{key}-{attempt[-2:]}.txt'
            prompt = prompt_path.read_text(encoding='utf-8')
            preparation = json.loads((experiment / 'card-repair-preparation.json').read_text(encoding='utf-8'))
            row = next(row for row in preparation['entries'] if (row['source_sha256'], row['attempt']) == (key, attempt))
            self.assertEqual(file_sha256(prompt_path), row['prompt_sha256'])
            return prompt

    def test_source52_revision3_repairs_both_upper_groups_and_preserves_tab(self):
        prompt = self.prepare_mask_prompt(
            52, '581dd8fc38811eeca36e65fcfb5093d743744adbcb44be6f160e63af7e450b90', 'external-07', 'note-mask-52-v3.json',
        )
        self.assertIn('one transparent rectangle covers only the incorrect upper note row', prompt)
        self.assertIn('restore exactly TWO compact irregular upper gray-mark groups', prompt)
        self.assertIn('correct right-edge tab', prompt)
        self.assertNotIn('Keep the upper-left group', prompt)
        self.assertNotIn('second covers the incorrect vertical tab', prompt)

    def test_source53_mask_preserves_corrected_pose_and_restores_note_groups(self):
        prompt = self.prepare_mask_prompt(
            53, '54b4ec4ae9b53cd9fdb29065ddafcd8fea67e1d360023c1d6ae55dc6e2e4162b', 'external-06', 'note-mask-53.json',
        )
        self.assertIn('one transparent rectangle covers only the two incorrect note-mark rows', prompt)
        self.assertIn('corrected viewer-right person', prompt)
        self.assertIn('restore exactly TWO separated source-scale irregular gray-mark groups in EACH row', prompt)
        self.assertIn('not repeated uniform pills', prompt)
        self.assertIn('correct right-edge tab', prompt)
        self.assertNotIn('POSE CORRECTION REQUIRED', prompt)

    def test_source57_mask_limits_changes_to_current_note_defect(self):
        prompt = self.prepare_mask_prompt(
            57, '8f53dc26bec02a7f1a6a617afb171d49e221fad8227b265d94e7384ce17f4bd0', 'external-04', 'note-mask-57.json',
        )
        self.assertIn('one transparent rectangle covers only the two incorrect note-mark rows', prompt)
        self.assertIn('bald-crowned person', prompt)
        self.assertIn('not repeated uniform short dashes', prompt)
        self.assertIn('correct right-edge tab', prompt)
        self.assertNotIn('Remove the added crown hair', prompt)
        self.assertNotIn('long metallic clip', prompt)

    def test_source61_through64_prompts_preserve_source_specific_people(self):
        cases = {
            61: ('5a160dd1e47d2a76dbf153ecf70fed66d73f3dfe21958a284cec3f4971fbfc74', 'white-capped person'),
            62: ('55e631c3aaedeef562ccccf0e31ebd55de03e25b719c3ac197e677f30ecb3675', 'headscarf'),
            63: ('bccaf19c78294b83dc4ab613b8e019a23e77702e342deb376e787b16b0c12336', 'gray-haired person'),
            64: ('f54980009f57be78a2a931afeb1aad7251b370a8c6ca677164a7198c584cbf7d', 'viewer-right person'),
        }
        for index, (key, person) in cases.items():
            with self.subTest(index=index):
                prompt = self.prepare_mask_prompt(index, key, 'external-04', f'note-mask-{index}.json')
                self.assertIn('one transparent rectangle covers only the two incorrect note-mark rows', prompt)
                self.assertIn(person, prompt)
                self.assertIn('restore exactly TWO separated source-scale irregular gray-mark groups in EACH row', prompt)
                self.assertIn('correct right-edge tab', prompt)


if __name__ == "__main__":
    unittest.main()
