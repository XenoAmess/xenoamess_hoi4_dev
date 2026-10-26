import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from runtime import high131_checkpoint as checkpoint
from runtime import high131_prepare_card_repairs as prepare
from tools.common import file_sha256


class High131PrepareCardRepairsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.experiment = self.root / "exp"
        patch.object(prepare, "ROOT", self.root).start()
        patch.object(prepare, "EXPERIMENT", self.experiment).start()
        self.addCleanup(patch.stopall)
        self.key = "a" * 64
        self.prompt_path = self.experiment / "prompts" / f"{self.key}-04.txt"
        self.prompt_path.parent.mkdir(parents=True)
        self.prompt_path.write_bytes(b"old complete prompt")
        self.row = {
            "source_sha256": self.key,
            "attempt": "external-04",
            "prompt_sha256": file_sha256(self.prompt_path),
        }

    def test_undispatched_revision_preserves_full_prior_prompt_and_record(self):
        replacement = "old complete prompt\n\nExactly two irregular groups in each row."
        replacement_sha = hashlib.sha256(replacement.encode()).hexdigest()
        prepare.revise_undispatched_prompt(self.prompt_path, self.row, replacement, replacement_sha)
        self.assertEqual(self.prompt_path.read_text(encoding="utf-8"), replacement)
        self.assertEqual(self.row["prompt_sha256"], replacement_sha)
        receipt = prepare.read_json(self.root / self.row["undispatched_revision_receipt"])
        self.assertEqual(receipt["prior_full_prompt"], "old complete prompt")
        self.assertEqual(receipt["prior_preparation"]["prompt_sha256"], file_sha256(self.root / receipt["preserved_prompt"]))
        self.assertEqual((self.root / receipt["preserved_prompt"]).read_bytes(), b"old complete prompt")
        self.assertEqual(receipt["new_image_generation_calls"], 0)
        self.assertTrue(receipt["actual_artifacts_absent_before_revision"])

    def test_attempted_prompt_cannot_be_revised(self):
        artifact = self.experiment / "outputs" / f"{self.key}-04.request.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "Refusing to revise"):
            prepare.revise_undispatched_prompt(self.prompt_path, self.row, "new prompt", "b" * 64)
        self.assertEqual(self.prompt_path.read_bytes(), b"old complete prompt")
        self.assertNotIn("undispatched_revision_receipt", self.row)
        self.assertFalse((self.experiment / "undispatched-prompt-revisions").exists())

    def test_unchanged_prompt_is_a_noop(self):
        old_sha = self.row["prompt_sha256"]
        prepare.revise_undispatched_prompt(self.prompt_path, self.row, "old complete prompt", old_sha)
        self.assertEqual(self.prompt_path.read_bytes(), b"old complete prompt")
        self.assertEqual(self.row["prompt_sha256"], old_sha)
        self.assertNotIn("undispatched_revision_receipt", self.row)


class High131CheckpointCopyTests(unittest.TestCase):
    def test_png_copy_uses_verified_same_volume_hardlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.png"
            target = root / "worktree" / "source.png"
            source.write_bytes(b"\x89PNG\r\n\x1a\n")
            checkpoint.copy_stable(source, target)
            self.assertEqual((source.stat().st_dev, source.stat().st_ino), (target.stat().st_dev, target.stat().st_ino))
            self.assertEqual(target.read_bytes(), source.read_bytes())

    def test_mutable_text_copy_is_not_linked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "record.json"
            target = root / "worktree" / "record.json"
            source.write_text('{"status":"original"}', encoding="utf-8")
            checkpoint.copy_stable(source, target)
            source.write_text('{"status":"changed"}', encoding="utf-8")
            self.assertEqual(target.read_text(encoding="utf-8"), '{"status":"original"}')

    def test_failed_text_replace_preserves_old_file_and_complete_temp(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "record.json"
            target = root / "worktree" / "record.json"
            target.parent.mkdir(parents=True)
            source.write_text("new complete bytes", encoding="utf-8")
            target.write_text("old complete bytes", encoding="utf-8")
            with patch.object(Path, "replace", side_effect=PermissionError("locked")), self.assertRaises(PermissionError):
                checkpoint.copy_stable(source, target)
            self.assertEqual(target.read_text(encoding="utf-8"), "old complete bytes")
            temporary_files = list(target.parent.glob("*.tmp"))
            self.assertEqual(len(temporary_files), 1)
            self.assertEqual(temporary_files[0].read_text(encoding="utf-8"), "new complete bytes")
    @unittest.skipUnless(os.name == "nt", "Windows extended-length path behavior")
    def test_extended_length_checkpoint_copy_preserves_bytes(self):
        root = Path(tempfile.mkdtemp(dir=checkpoint.ROOT / "runtime"))
        source = root / "source.json"
        source.write_text('{"complete":true}', encoding="utf-8")
        target = root / ("a" * 230) / "nested" / "target.json"

        def cleanup():
            for path, directory in ((target, False), (target.parent, True), (target.parent.parent, True), (source, False), (root, True)):
                try:
                    io_path = checkpoint.windows_io_path(path)
                    if directory:
                        io_path.rmdir()
                    else:
                        io_path.unlink()
                except FileNotFoundError:
                    pass

        self.addCleanup(cleanup)
        self.assertGreater(len(str(target)), 260)
        checkpoint.copy_stable(source, target)
        io_target = checkpoint.windows_io_path(target)
        self.assertTrue(str(io_target).startswith("\\\\?\\"))
        self.assertEqual(io_target.read_bytes(), source.read_bytes())
        self.assertEqual(file_sha256(io_target), file_sha256(source))
        self.assertEqual(checkpoint.read_json(checkpoint.windows_io_root(root) / ("a" * 230) / "nested" / "target.json"), {"complete": True})


if __name__ == "__main__":
    unittest.main()
