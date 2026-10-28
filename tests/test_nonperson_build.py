import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from mod_nailong.tools import build_release as builder
from tools.common import ROOT, file_sha256, machine_id, read_json, sha256, write_json


class NonpersonBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "runtime")
        self.root = Path(self.temporary.name) / "case"
        self.mod = self.root / "mod_nailong"
        self.experiment = self.mod / "experiments/evolink-high131-flare-20261025"
        self.keys = []
        self.originals = {}
        self.source_index = {}
        scope_entries = []
        decision_entries = []
        catalog_assets = []
        paths = [
            "gfx/leaders/ENG/portrait_eng_fallen_government.dds",
            "gfx/leaders/POL/portrait_POL_Sejmik_Regency.dds",
            "gfx/leaders/SWI/portrait_SWI_federal_building.dds",
            "gfx/leaders/SWI/Portrait_Switzerland_Federal_assembly.dds",
        ]
        for index, virtual in zip((78, 125, 129, 131), paths, strict=True):
            stream = io.BytesIO()
            Image.new("RGBA", (3, 2), (index, 20, 40, 255)).save(stream, format="DDS")
            raw = stream.getvalue()
            key = sha256(raw)
            self.keys.append(key)
            asset_id = f"nonperson-{index}"
            source_png = f"runtime/references/{key}.png"
            (self.root / source_png).parent.mkdir(parents=True, exist_ok=True)
            with Image.open(io.BytesIO(raw)) as image:
                converted = image.convert("RGBA")
                converted.save(self.root / source_png)
                source_alpha = list(converted.getchannel("A").getextrema())
                size = list(image.size)
            source = {
                "index": index, "source_sha256": key, "source_assets": [virtual], "source_size": size,
                "source_png": source_png, "converted_png_sha256": file_sha256(self.root / source_png),
                "source_alpha_extrema": source_alpha,
            }
            scope_entries.append(source)
            decision_entries.append({**source, "source_png_sha256": source["converted_png_sha256"], "observed_subject": "No person in synthetic original"})
            catalog_assets.append({"id": asset_id, "path": virtual, "source_sha256": key, "size": size, "package": "base"})
            if index == 131:
                archive_path = self.root / "original.zip"
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr(virtual, raw)
                self.source_index[asset_id] = {"path": str(archive_path), "member": virtual}
            else:
                original = self.root / "game" / virtual
                original.parent.mkdir(parents=True, exist_ok=True)
                original.write_bytes(raw)
                self.source_index[asset_id] = {"path": str(original), "member": None}
            self.originals[virtual] = raw
        write_json(self.experiment / "scope.json", {"entries": scope_entries})
        write_json(self.experiment / "nonperson-scope-review.json", {"entries": [{"source_sha256": key} for key in self.keys]})
        write_json(self.experiment / "nonperson-scope-decision.json", {
            "schema": "naiwa-evolink-high131-nonperson-scope-decision-v1", "machine_id": machine_id(),
            "user_selection": {"selected_option": "保留原图并登记例外（推荐）"},
            "decision": "preserved_original_nonperson_exception", "prior_visual_review": "mod_nailong/experiments/evolink-high131-flare-20261025/nonperson-scope-review.json",
            "no_image_call_created_for_this_decision": True, "generated_output_required": False,
            "original_assets_retained": True, "canonical_generated_row_must_not_be_fabricated": True,
            "entries": decision_entries,
        })
        catalog_assets.append({"id": "low-sentinel", "path": "gfx/leaders/other.dds", "source_sha256": "low-sentinel", "size": [1, 1], "package": "base"})
        write_json(self.mod / "data/catalog.json", {"assets": catalog_assets, "game_version": "synthetic", "unresolved_references": []})
        write_json(self.mod / "data/generated.json", {"portraits": {"low-sentinel": {"review": "pending"}}})
        write_json(self.root / "runtime/source-index.json", self.source_index)
        (self.mod / "mod").mkdir(parents=True, exist_ok=True)
        (self.mod / "mod/descriptor.mod").write_text('name="钢奶龙心 (Development)"\n', encoding="utf-8")
        self.root_patch = patch.object(builder, "ROOT", self.root)
        self.mod_patch = patch.object(builder, "MOD", self.mod)
        self.root_patch.start()
        self.mod_patch.start()

    def tearDown(self):
        self.mod_patch.stop()
        self.root_patch.stop()
        self.temporary.cleanup()

    def test_original_exception_preview_preserves_every_byte(self):
        output = self.root / "preview"
        manifest = builder.build(output, preview=True, validation_keys=self.keys)
        self.assertTrue(manifest["preview"])
        self.assertEqual(manifest["preserved_original_nonperson_exceptions"], [78, 125, 129, 131])
        self.assertEqual(len(manifest["bindings"]), 4)
        self.assertEqual(manifest["profile_missing_texture_count"], 0)
        self.assertFalse(manifest["art_complete"])
        self.assertEqual(len(manifest["files"]), 5)
        self.assertNotIn("low-sentinel", manifest["validation_source_keys"])
        for binding in manifest["bindings"]:
            self.assertTrue(binding["preserved_original_nonperson_exception"])
            self.assertFalse(binding["resized"])
            self.assertIsNone(binding["fullsize_master_sha256"])
            self.assertEqual(binding["resolution_policy"], "original-game-file-bytes-preserved")
            self.assertEqual((output / "staging" / binding["path"]).read_bytes(), self.originals[binding["path"]])
            self.assertEqual(binding["sha256"], sha256(self.originals[binding["path"]]))
        with zipfile.ZipFile(output / "gangnailongxin.zip") as archive:
            for binding in manifest["bindings"]:
                self.assertEqual(archive.read(binding["path"]), self.originals[binding["path"]])
        self.assertEqual(read_json(self.mod / "data/generated.json")["portraits"]["low-sentinel"], {"review": "pending"})
        self.assertNotIn(self.keys[0], read_json(self.mod / "data/generated.json")["portraits"])

    def test_original_exception_preview_is_deterministic(self):
        first = builder.build(self.root / "first", preview=True, validation_keys=self.keys)
        second = builder.build(self.root / "second", preview=True, validation_keys=self.keys)
        self.assertEqual(first, second)
        self.assertEqual(file_sha256(self.root / "first/gangnailongxin.zip"), file_sha256(self.root / "second/gangnailongxin.zip"))
        self.assertEqual((self.root / "first/manifest.json").read_bytes(), (self.root / "second/manifest.json").read_bytes())

    def test_tampered_original_is_rejected(self):
        asset_id = next(key for key, value in self.source_index.items() if value["member"] is None)
        Path(self.source_index[asset_id]["path"]).write_bytes(b"not the original")
        with self.assertRaisesRegex(SystemExit, "SHA256 mismatch"):
            builder.payload(preview=True, validation_keys=self.keys)

    def test_generated_row_cannot_replace_original_exception(self):
        path = self.mod / "data/generated.json"
        body = read_json(path)
        body["portraits"][self.keys[0]] = {"review": "approved"}
        write_json(path, body)
        with self.assertRaisesRegex(SystemExit, "must not have a generated row"):
            builder.payload(preview=True, validation_keys=self.keys)

    def test_other_missing_sources_still_block_formal_build(self):
        with self.assertRaisesRegex(SystemExit, "RELEASE BLOCKED"):
            builder.payload(preview=False)


if __name__ == "__main__":
    unittest.main()
