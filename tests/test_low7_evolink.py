import copy
import importlib
from pathlib import Path
import unittest
from unittest.mock import patch

from runtime import high131_run_batch as shared_batch

BATCH_FIELDS = (
    "ROOT", "EXPERIMENT", "PREPARED_PATH", "SCOPE_PATH", "RELEASE_PATH", "PROMPTS_DIR",
    "OUTPUTS_DIR", "LOGS_DIR", "EXECUTIONS_DIR", "CLIENT_PATH", "collect_batch", "write_json_new",
)
ORIGINAL_BATCH_STATE = {name: getattr(shared_batch, name) for name in BATCH_FIELDS}
from runtime import high131_run_repairs as shared_repairs
REPAIR_FIELDS = ("ROOT", "EXPERIMENT", "REPAIR_PATH", "PROGRESS_PATH", "OUTPUTS_DIR", "PROMPTS_DIR")
ORIGINAL_REPAIR_STATE = {name: getattr(shared_repairs, name) for name in REPAIR_FIELDS}
prepare = importlib.import_module("mod_nailong.experiments.evolink-low7-20261030.tools.low7_prepare")
runner = importlib.import_module("mod_nailong.experiments.evolink-low7-20261030.tools.low7_run_batch")
LOW7_BATCH_STATE = dict(runner.LOW7_BATCH_STATE)


class Low7PreparationTests(unittest.TestCase):
    def test_exact_seven_sources_and_prompt_bindings(self):
        _auth, entries = prepare.validated_entries()
        self.assertEqual(len(entries), 7)
        self.assertEqual([row["index"] for row in entries], list(range(1, 8)))
        for entry in entries:
            prompt_path = prepare.ROOT / "mod_nailong/experiments/evolink-low7-20261030/prompts" / f"{entry['source_sha256']}-01.txt"
            self.assertEqual(prompt_path.read_bytes(), entry["prompt"].encode("utf-8"))
            self.assertEqual(prepare.file_sha256(prompt_path), entry["prompt_sha256"])
            self.assertEqual(entry["builtin_retries_used"], 9)
            self.assertEqual(len(entry["reference_set"]), 3 if entry["index"] == 6 else 2)

    def test_import_preserves_shared_batch_state(self):
        for name, expected in ORIGINAL_BATCH_STATE.items():
            self.assertEqual(getattr(shared_batch, name), expected)
        importlib.import_module("mod_nailong.experiments.evolink-low7-20261030.tools.low7_repair")
        for name, expected in ORIGINAL_BATCH_STATE.items():
            self.assertEqual(getattr(shared_batch, name), expected)

    def test_navy2_preserves_rejected_hd_target_first(self):
        _auth, entries = prepare.validated_entries()
        navy = entries[5]
        self.assertEqual(navy["source_sha256"], "1f66d040d3ea98c01ad0d0c91bc6a150d379c89d2a4840f604bad60984cab616")
        self.assertEqual([row["role"] for row in navy["reference_set"]], [
            "previous generated fullsize edit target", "original source portrait", "user mascot reference",
        ])
        self.assertEqual(navy["reference_set"][0]["sha256"], prepare.EDIT_TARGET["sha256"])
        self.assertIn("323e50248b85560678710b986836f82b3b1ac596", navy["reference_set"][0]["url"])

    def test_public_download_rejects_wrong_bytes_without_caching(self):
        reference = {"url": "https://example.invalid/reference.png", "sha256": "0" * 64, "cache_name": "wrong.png"}
        result = type("Result", (), {"returncode": 0, "stdout": b"\x89PNG\r\n\x1a\nwrong", "stderr": b""})()
        with patch("subprocess.run", return_value=result) as call:
            with self.assertRaisesRegex(ValueError, "SHA differs"):
                prepare.download_public(reference)
        self.assertEqual(call.call_count, 1)
        self.assertNotIn("EVOLINK_API_KEY", str(call.call_args))


class Low7RunnerTests(unittest.TestCase):
    def setUp(self):
        for name, value in LOW7_BATCH_STATE.items():
            setattr(runner.batch, name, value)

    def tearDown(self):
        for name, value in ORIGINAL_BATCH_STATE.items():
            setattr(runner.batch, name, value)

    def test_frozen_request_and_builtin_counters_pass_without_mutation(self):
        context = runner.batch.load_context()
        entry = context["prepared_entries"][
            "1f66d040d3ea98c01ad0d0c91bc6a150d379c89d2a4840f604bad60984cab616"
        ]
        scope = next(row for row in context["scope"]["entries"] if row["source_sha256"] == entry["source_sha256"])
        state = runner.batch.entry_state(entry, scope)
        state["input_validation"] = runner.ordered_inputs
        state["frozen_validator"] = runner.require_scope
        validated = runner.batch.validate_frozen_entry(context, state)
        self.assertEqual(validated["parameters"]["model"], "gpt-image-2.5-flare")
        self.assertEqual(validated["parameters"]["background"], "opaque")
        self.assertEqual(len(validated["parameters"]["image_urls"]), 3)
        self.assertNotIn("mask_url", validated["parameters"])

    def test_changed_model_or_builtin_counter_blocks_dispatch(self):
        context = runner.batch.load_context()
        key = next(iter(context["prepared_entries"]))
        entry = copy.deepcopy(context["prepared_entries"][key])
        scope = next(row for row in context["scope"]["entries"] if row["source_sha256"] == key)
        state = {"entry": entry}
        entry["model"] = "unexpected-model"
        with self.assertRaisesRegex(runner.batch.BatchError, "parameter differs"):
            runner.require_scope(context, state)
        entry["model"] = runner.EXPECTED_PARAMETERS["model"]
        queue = {"sources": {row["source_sha256"]: {"retries_used": 0} for row in context["scope"]["entries"]}}
        actual_read_json = runner.read_json
        def read_test_json(path):
            return queue if Path(path).name == "image-retry-queue.json" else actual_read_json(path)
        with patch.object(runner, "read_json", side_effect=read_test_json):
            with self.assertRaisesRegex(runner.batch.BatchError, "counter changed"):
                runner.require_scope(context, state)

    def test_execution_receipt_uses_low7_schema(self):
        target = prepare.ROOT / "runtime/low7-test-execution-schema.json"
        payload = {"schema": "naiwa-evolink-high131-execution-v1"}
        original = runner.original_write_json_new
        captured = []
        try:
            runner.original_write_json_new = lambda path, value: captured.append((path, value))
            runner.write_json_new(target, payload)
        finally:
            runner.original_write_json_new = original
        self.assertEqual(captured, [(target, {"schema": "low7-kimi-evolink-execution-v1"})])
        self.assertFalse(target.exists())


class Low7RepairTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("mod_nailong.experiments.evolink-low7-20261030.tools.low7_repair")
        self.saved = {name: getattr(self.module.batch, name) for name in ("PREPARED_PATH", "SCOPE_PATH", "RELEASE_PATH")}
        self.module.batch.PREPARED_PATH = self.module.REPAIR_PREPARED
        self.module.batch.SCOPE_PATH = prepare.SCOPE
        self.module.batch.RELEASE_PATH = self.module.REPAIR_RELEASE

    def tearDown(self):
        for name, value in ORIGINAL_BATCH_STATE.items():
            setattr(self.module.batch, name, value)

    def test_repair_keeps_target_source_and_mascot_order(self):
        repair = self.module
        context = repair.load_context()
        entry = context["prepared"]["entries"][0]
        state = repair.repair_state(context, entry)
        validated = repair.batch.validate_frozen_entry(context, state)
        self.assertEqual(entry["attempt"], "external-02")
        self.assertEqual(validated["parameters"]["image_urls"], entry["image_urls"])
        self.assertEqual(validated["parameters"]["image_urls"][0], entry["inputs"][0]["url"])
        self.assertEqual(entry["ordered_input_sha256"][0], entry["rejected_output_sha256"])
        self.assertEqual(len(entry["ordered_input_sha256"]), 3)

    def test_repair_rejects_changed_rejected_target(self):
        repair = self.module
        context = repair.load_context()
        entry = copy.deepcopy(context["prepared"]["entries"][0])
        entry["rejected_output_sha256"] = "0" * 64
        state = repair.repair_state(context, entry)
        with self.assertRaisesRegex(repair.batch.BatchError, "Rejected target binding changed"):
            repair.validate_repair(context, state)

    def test_archive_has_only_actual_approved_sources(self):
        archive = prepare.read_json(prepare.EXPERIMENT / "approved-masters.json")
        self.assertEqual(archive["count"], len(archive["entries"]))
        self.assertIn(archive["formal_canonical_import_count"], {0, 7})
        if archive["formal_canonical_import_count"] == 7:
            self.assertTrue(importlib.import_module("mod_nailong.experiments.evolink-low7-20261030.tools.low7_import").verify_import(prepare.ROOT, archive))
        for entry in archive["entries"]:
            master = prepare.ROOT / entry["generated_fullsize_image"]
            self.assertEqual(prepare.file_sha256(master), entry["generated_fullsize_sha256"])
            self.assertEqual(master.stat().st_size, entry["bytes"])
            review = prepare.read_json(prepare.ROOT / entry["review"])
            self.assertEqual(prepare.file_sha256(prepare.ROOT / entry["review"]), entry["review_sha256"])
            decision = next(row for row in review["entries"] if row["source_sha256"] == entry["source_sha256"])
            self.assertEqual(decision["decision"], "approved_for_production")
            self.assertEqual(decision["output_sha256"], entry["generated_fullsize_sha256"])


class Low7ImportTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("mod_nailong.experiments.evolink-low7-20261030.tools.low7_import")

    def test_plan_is_exactly_seven_and_preserves_navy2_rejection(self):
        approved = prepare.read_json(prepare.EXPERIMENT / "approved-masters.json")
        navy = next(row for row in approved["entries"] if row["index"] == 6)
        generated = prepare.read_json(prepare.ROOT / "mod_nailong/data/generated.json")
        current = generated["portraits"].get(navy["source_sha256"], {})
        if current.get("generated_fullsize_sha256") == navy["generated_fullsize_sha256"]:
            self.assertTrue(self.module.verify_import(prepare.ROOT, approved))
        else:
            plan = self.module.build_plan(prepare.ROOT, prepare.ROOT)
            self.assertEqual(plan["source_count"], 7)
            self.assertEqual(plan["resource_instances"], 10)
            previous = next(row for row in plan["entries"] if row["index"] == 6)["previous_generated_row"]
            self.assertEqual(previous["review"], "rejected")
            self.assertEqual(previous["generated_fullsize_sha256"], prepare.EDIT_TARGET["sha256"])
        handoff = prepare.read_json(prepare.ROOT / "docs/handoffs/2026-10-30-low7-exhausted.json")
        historical = next(row for row in handoff["entries"] if row["source_sha256"] == navy["source_sha256"])
        self.assertEqual(historical["current_generated_row_snapshot"]["review"], "rejected")
        self.assertEqual(navy["recovery_sha256"], prepare.file_sha256(prepare.ROOT / navy["recovery"]))

    def test_shared_mapping_preserves_remote_other_rows_and_rejects_real_conflict(self):
        base = {"schema": "same", "rows": {"mine": {"value": 1}, "other": {"value": 1}}}
        ours = {"schema": "same", "rows": {"mine": {"value": 2}, "other": {"value": 1}}}
        theirs = {"schema": "same", "rows": {"mine": {"value": 1}, "other": {"value": 3}}}
        merged = self.module.merge_mapping(base, ours, theirs, "rows")
        self.assertEqual(merged["rows"], {"mine": {"value": 2}, "other": {"value": 3}})
        with self.assertRaisesRegex(self.module.ImportErrorWithEvidence, "Conflicting shared row"):
            self.module.merge_mapping(base, ours, {"schema": "same", "rows": {"mine": {"value": 3}, "other": {"value": 1}}}, "rows")


if __name__ == "__main__":
    unittest.main()
