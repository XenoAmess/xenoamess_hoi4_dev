import copy
import importlib
import json
from pathlib import Path
import unittest

from runtime import high131_run_batch as shared_batch

BATCH_FIELDS = (
    "ROOT", "EXPERIMENT", "PREPARED_PATH", "SCOPE_PATH", "RELEASE_PATH", "PROMPTS_DIR",
    "OUTPUTS_DIR", "LOGS_DIR", "EXECUTIONS_DIR", "CLIENT_PATH", "collect_batch", "write_json_new", "replace_execution_json",
)
ORIGINAL_BATCH_STATE = {name: getattr(shared_batch, name) for name in BATCH_FIELDS}
prepare = importlib.import_module("mod_nailong.experiments.evolink-low2-20261030.tools.low2_prepare")
runner = importlib.import_module("mod_nailong.experiments.evolink-low2-20261030.tools.low2_run_batch")
LOW2_BATCH_STATE = dict(runner.LOW2_BATCH_STATE)
archive = importlib.import_module("mod_nailong.experiments.evolink-low2-20261030.tools.low2_archive")
importer = importlib.import_module("mod_nailong.experiments.evolink-low2-20261030.tools.low2_import")


class Low2PreparationTests(unittest.TestCase):
    def test_exact_two_sources_prompt_inputs_and_zero_retries(self):
        entries = prepare.validated_entries()
        self.assertEqual([row["source_sha256"] for row in entries], prepare.KEYS)
        for entry in entries:
            self.assertEqual(entry["builtin_retries_used"], 0)
            self.assertEqual([row["role"] for row in entry["reference_set"]], ["original source portrait", "user mascot reference"])
            self.assertEqual([row["sha256"] for row in entry["reference_set"]], [entry["converted_png_sha256"], prepare.MASCOT["sha256"]])
            prompt_path = prepare.EXPERIMENT / "prompts" / f"{entry['source_sha256']}-01.txt"
            self.assertEqual(prompt_path.read_bytes(), entry["prompt"].encode("utf-8"))
            self.assertEqual(prepare.file_sha256(prompt_path), entry["prompt_sha256"])

    def test_shared_batch_state_is_restored_at_import(self):
        for name, expected in ORIGINAL_BATCH_STATE.items():
            self.assertEqual(getattr(shared_batch, name), expected)
        self.assertEqual(runner.batch, shared_batch)

    def test_completed_execution_uses_low2_schema(self):
        target = prepare.ROOT / "runtime/low2-test-execution-schema.json"
        captured = []
        original = runner.original_write_json_new
        try:
            runner.original_write_json_new = lambda path, value: captured.append((path, value))
            runner.write_json_new(target, {"schema": "naiwa-evolink-high131-execution-v1"})
        finally:
            runner.original_write_json_new = original
        self.assertEqual(captured, [(target, {"schema": "low2-kimi-evolink-execution-v1"})])
        self.assertFalse(target.exists())


class Low2RunnerTests(unittest.TestCase):
    def setUp(self):
        for name, value in LOW2_BATCH_STATE.items():
            setattr(runner.batch, name, value)

    def tearDown(self):
        for name, value in ORIGINAL_BATCH_STATE.items():
            setattr(runner.batch, name, value)

    def test_changed_model_or_zero_builtin_counter_blocks_dispatch(self):
        context = runner.batch.load_context()
        key = next(iter(context["prepared_entries"]))
        entry = copy.deepcopy(context["prepared_entries"][key])
        state = {"entry": entry}
        entry["model"] = "unexpected-model"
        with self.assertRaisesRegex(runner.batch.BatchError, "parameter differs"):
            runner.require_scope(context, state)
        entry["model"] = runner.EXPECTED_PARAMETERS["model"]
        queue = {"sources": {row["source_sha256"]: {"retries_used": 1} for row in context["scope"]["entries"]}}
        actual_read_json = runner.read_json
        def read_test_json(path):
            return queue if Path(path).name == "image-retry-queue.json" else actual_read_json(path)
        original_read_json = runner.read_json
        try:
            runner.read_json = read_test_json
            with self.assertRaisesRegex(runner.batch.BatchError, "counter changed"):
                runner.require_scope(context, state)
        finally:
            runner.read_json = original_read_json


class Low2ReviewTests(unittest.TestCase):
    def test_two_actual_outputs_have_bound_visual_approval(self):
        approved = prepare.read_json(prepare.EXPERIMENT / "approved-masters.json")
        self.assertEqual(approved["schema"], "low2-kimi-approved-masters-v1")
        self.assertEqual(approved["count"], len(approved["entries"]))
        self.assertIn(approved["formal_canonical_import_count"], {0, 2})
        for entry in approved["entries"]:
            master = prepare.ROOT / entry["generated_fullsize_image"]
            self.assertEqual(prepare.file_sha256(master), entry["generated_fullsize_sha256"])
            self.assertEqual(master.stat().st_size, entry["bytes"])
            self.assertEqual(entry["import_schema"], "low2-kimi-production-import-v1")
            self.assertEqual(entry["attempt"], "external-01")
            self.assertIsNone(entry["recovery"])
            review = prepare.read_json(prepare.ROOT / entry["review"])
            self.assertEqual(prepare.file_sha256(prepare.ROOT / entry["review"]), entry["review_sha256"])
            self.assertEqual(prepare.file_sha256(prepare.ROOT / entry["evidence"]), entry["evidence_sha256"])
            decision = next(row for row in review["entries"] if row["source_sha256"] == entry["source_sha256"])
            self.assertEqual(decision["decision"], "approved_for_production")
            self.assertEqual(decision["task_id"], entry["task_id"])
            self.assertEqual(decision["source_alpha_extrema"], [255, 255])
            self.assertIsNone(decision["returned_alpha_extrema"])
            self.assertFalse(decision["source_alpha_repair_performed"])
            self.assertTrue(decision["rgb_art_approved"])

    def test_scope_is_exactly_two_single_resource_instances(self):
        scope = prepare.read_json(prepare.EXPERIMENT / "scope.json")
        self.assertEqual(scope["source_count"], 2)
        self.assertEqual(sum(len(row["source_assets"]) for row in scope["entries"]), 2)
        self.assertFalse(scope["codex_tool_permission_changed"])
        self.assertFalse(scope["permission_documents_modified"])
        self.assertEqual(importer.DOCS, ["docs/handoffs/2026-10-30-low-two-pending.md", "docs/handoffs/low2-kimi-evolink-2026-10-30.md"])
        self.assertEqual(importer.TEST, "tests/test_low2_evolink.py")

    def test_shared_mapping_preserves_unrelated_remote_rows(self):
        base = {"schema": "same", "rows": {"mine": {"value": 1}, "other": {"value": 1}}}
        ours = {"schema": "same", "rows": {"mine": {"value": 2}, "other": {"value": 1}}}
        theirs = {"schema": "same", "rows": {"mine": {"value": 1}, "other": {"value": 3}}}
        merged = importer.shared.merge_mapping(base, ours, theirs, "rows")
        self.assertEqual(merged["rows"], {"mine": {"value": 2}, "other": {"value": 3}})
        with self.assertRaisesRegex(importer.ImportErrorWithEvidence, "Conflicting shared row"):
            importer.shared.merge_mapping(base, ours, {"schema": "same", "rows": {"mine": {"value": 3}, "other": {"value": 1}}}, "rows")

    def test_master_sync_retains_every_previously_indexed_original(self):
        from unittest.mock import patch
        previous = {
            "old": {"path": "mod_nailong/assets/generated_fullsize/old.png", "provenance": [{"record": "published"}]},
            "rejected": {"path": "mod_nailong/assets/generated_fullsize/rejected.png", "provenance": [{"record": "retained rejection"}]},
        }
        candidates = {"masters": [
            {"sha256": "old", "path": "old.png", "bytes": 1, "size": [1, 1], "mode": "RGB"},
            {"sha256": "rejected", "path": "rejected.png", "bytes": 3, "size": [3, 3], "mode": "RGB"},
            {"sha256": "new", "path": "new.png", "bytes": 2, "size": [2, 2], "mode": "RGB"},
        ]}
        def test_json(path):
            if Path(path).name == "fullsize-files.json":
                return {"outputs": {"old": previous["old"]}}
            if Path(path).name == "outputs-index.json":
                return {"entries": [{"output_sha256": "new", "review": "review.json", "decision": "approved_for_production"}]}
            raise AssertionError(path)
        with patch.object(importer.master_archive, "recorded_outputs", return_value=({"old", "new"}, {}, {"old": [], "new": []})), \
             patch.object(importer.master_files, "recorded_master_candidates", return_value=candidates), \
             patch.object(importer.shared, "extended_path", side_effect=lambda value: value), \
             patch.object(importer, "read_json", side_effect=test_json), \
             patch.object(importer, "git", return_value=json.dumps({"outputs": previous})), \
             patch.object(importer.master_files, "sync_git", return_value={"count": 3}) as sync:
            result = importer.sync_fullsize(Path("runtime/test-worktree"), Path("runtime/test-support"))
        snapshot = sync.call_args.args[0]
        self.assertEqual({row["sha256"] for row in snapshot["masters"]}, {"old", "rejected", "new"})
        self.assertEqual(next(row for row in snapshot["masters"] if row["sha256"] == "rejected")["provenance"], [{"record": "retained rejection"}])
        self.assertEqual(result["count"], 3)


if __name__ == "__main__":
    unittest.main()
