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
        (ROOT/'runtime').mkdir(exist_ok=True)
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

    def add_supplemental_original(self):
        stream=io.BytesIO()
        Image.new('RGBA',(3,2),(103,75,12,255)).save(stream,format='DDS')
        raw=stream.getvalue();key=sha256(raw);virtual='gfx/leaders/PHI/portrait_PHI_back_soon.dds'
        original=self.root/'game'/virtual;original.parent.mkdir(parents=True,exist_ok=True);original.write_bytes(raw)
        asset={'id':'supplemental-103','package':'base','path':virtual,'size':[3,2],'source_sha256':key}
        catalog=read_json(self.mod/'data/catalog.json');catalog['assets'].append(asset);write_json(self.mod/'data/catalog.json',catalog)
        self.source_index[asset['id']]={'path':str(original),'member':None};write_json(self.root/'runtime/source-index.json',self.source_index)
        observation=self.mod/'data/update-reviews/synthetic-103.json'
        write_json(observation,{'schema':'nailong-update-nonperson-observation-v1','source_sha256':key,'source_index':103,'source_size':[3,2],'source_png_sha256':'a'*64,'actual_image_calls':0,'art_qualification_claimed':False,'observation':'Synthetic nonperson scene; no visual acceptance of game art is claimed by this test.'})
        row={'decision_id':'synthetic-103','machine_id':machine_id(),'decision':'preserved_original_nonperson_exception','user_selection':{'selected_option':'沿用非人物例外（推荐）','answer_received_in_current_session':True},'index':103,'index_basis':'hoi4-1.19.5-update-plan-1-based','source_sha256':key,'source_assets':[virtual],'catalog_assets':[{name:asset[name] for name in ('id','package','path','size')}],'source_size':[3,2],'source_png_sha256':'a'*64,'prior_visual_review':observation.relative_to(self.root).as_posix(),'prior_visual_review_sha256':file_sha256(observation),'observed_subject':read_json(observation)['observation'],'no_image_call_created_for_this_decision':True,'generated_output_required':False,'original_assets_retained':True,'canonical_generated_row_must_not_be_fabricated':True}
        registry=self.mod/'data/nonperson-preservation-decisions.json';write_json(registry,{'schema':'nailong-additional-nonperson-preservation-decisions-v1','decisions':[row]})
        return key,virtual,raw,registry,observation

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

    def test_subset_manifest_only_claims_selected_exceptions(self):
        _, manifest = builder.payload(preview=True, validation_keys=self.keys[:2])
        self.assertEqual(manifest["preserved_original_nonperson_exceptions"], [78, 125])
        self.assertEqual(len(manifest["bindings"]), 2)
        self.assertFalse(manifest["art_complete"])

    def test_fresh_checkout_can_verify_original_bytes_without_exported_reference_png(self):
        scope=read_json(self.experiment/'scope.json')
        (self.root/scope['entries'][0]['source_png']).unlink()
        _,manifest=builder.payload(preview=True,validation_keys=self.keys)
        self.assertEqual(len(manifest['bindings']),4)

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

    def test_supplemental_original_preserves_bytes_without_ai_row_or_legacy_rewrite(self):
        legacy=self.experiment/'nonperson-scope-decision.json';before=legacy.read_bytes()
        key,virtual,raw,_,_=self.add_supplemental_original()
        out=self.root/'supplemental-build';manifest=builder.build(out,preview=True,validation_keys=[key])
        self.assertEqual(legacy.read_bytes(),before)
        self.assertEqual(manifest['preserved_original_nonperson_exceptions'],[103])
        self.assertEqual(manifest['preserved_original_nonperson_sources'],[{'source_sha256':key,'index':103,'index_basis':'hoi4-1.19.5-update-plan-1-based'}])
        self.assertEqual(manifest['bindings'][0]['fullsize_master_sha256'],None)
        self.assertEqual((out/'staging'/virtual).read_bytes(),raw)
        with zipfile.ZipFile(out/'gangnailongxin.zip') as archive:self.assertEqual(archive.read(virtual),raw)
        self.assertNotIn(key,read_json(self.mod/'data/generated.json')['portraits'])
        self.assertFalse(manifest['art_complete'])

    def test_supplemental_decision_requires_recorded_user_selection(self):
        _,_,_,registry,_=self.add_supplemental_original();body=read_json(registry)
        body['decisions'][0]['user_selection']['selected_option']='暂不豁免，保持待处理';write_json(registry,body)
        with self.assertRaises(AssertionError):builder.nonperson_scope()

    def test_supplemental_observation_tampering_is_rejected(self):
        _,_,_,_,observation=self.add_supplemental_original();body=read_json(observation);body['observation']='Changed';write_json(observation,body)
        with self.assertRaisesRegex(AssertionError,'observation changed'):builder.nonperson_scope()

    def test_supplemental_catalog_binding_change_is_rejected(self):
        key,_,_,_,_=self.add_supplemental_original();catalog=read_json(self.mod/'data/catalog.json')
        next(a for a in catalog['assets'] if a['source_sha256']==key)['path']='gfx/leaders/PHI/different.dds';write_json(self.mod/'data/catalog.json',catalog)
        with self.assertRaisesRegex(AssertionError,'catalog identity changed'):builder.nonperson_scope()

    def test_supplemental_original_cannot_be_presented_as_generated_art(self):
        key,_,_,_,_=self.add_supplemental_original();path=self.mod/'data/generated.json';body=read_json(path);body['portraits'][key]={'review':'approved'};write_json(path,body)
        with self.assertRaisesRegex(SystemExit,'must not have a generated row'):builder.payload(preview=True,validation_keys=[key])

    def test_preserved_source_is_processed_but_not_art_approved(self):
        from mod_nailong.tools.nonperson_exceptions import annotate_update_plan
        key,_,_,_,_=self.add_supplemental_original();exceptions,_=builder.nonperson_scope()
        plan={'sources':[{'source_sha256':source,'new_unique_source':True,'generated':False,'portrait_ready':False,'release_excluded':excluded} for source,excluded in [(key,False),('person',False),('archive-person',True)]]}
        annotate_update_plan(plan,exceptions)
        self.assertFalse(plan['sources'][0]['portrait_ready']);self.assertFalse(plan['sources'][0]['generated']);self.assertFalse(plan['sources'][0]['release_art_required'])
        self.assertEqual(plan['processing_counts']['new_sources_art_approved'],0)
        self.assertEqual(plan['processing_counts']['new_sources_preserved_nonperson'],1)
        self.assertEqual(plan['processing_counts']['new_sources_unprocessed'],2)
        self.assertEqual(plan['processing_counts']['new_release_art_missing'],1)


if __name__ == "__main__":
    unittest.main()
