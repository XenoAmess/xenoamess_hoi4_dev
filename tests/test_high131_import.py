import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from runtime import high131_import as importer
from runtime import high131_model_policy as model_policy
from tools.common import ROOT, file_sha256, machine_id, write_json
from mod_nailong.tools.art_contract import portrait_ready


class ImportFixture:
    root = None

    @classmethod
    def create(cls):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / "runtime")
        root = Path(temporary.name) / "fixture"
        root.mkdir()
        cls.root = root
        cls.temporary = temporary
        exp = importer.EXPERIMENT
        mascot = root / "mod_nailong/assets/reference/naiwa.png"
        cls.png(mascot, (20, 120, 30, 255))
        mascot_sha = file_sha256(mascot)
        scope = {"schema": "naiwa-evolink-high131-scope-v1", "machine_id": machine_id(), "source_count": 131,
                 "source_release_tag": "test-source", "mascot_reference": {"path": "mod_nailong/assets/reference/naiwa.png", "sha256": mascot_sha, "url": "https://example.invalid/mascot.png"}, "entries": []}
        progress = {"schema": "naiwa-evolink-high131-progress-v1", "machine_id": machine_id(), "source_count": 131, "entries": []}
        approved = {"schema": "naiwa-evolink-high131-approved-masters-v1", "machine_id": machine_id(), "count": 127, "entries": []}
        prepared = {"entries": []}
        catalog = {"assets": [], "unresolved_references": [], "game_version": "test"}
        nonperson = {"schema": "naiwa-evolink-high131-nonperson-scope-decision-v1", "machine_id": machine_id(), "decision": "preserved_original_nonperson_exception",
                     "user_selection": {"selected_option": "保留原图并登记例外（推荐）"}, "no_image_call_created_for_this_decision": True,
                     "generated_output_required": False, "original_assets_retained": True, "canonical_generated_row_must_not_be_fabricated": True,
                     "prior_visual_review": f"{exp}/nonperson-scope-review.json", "entries": []}
        for index in range(1, 132):
            key = model_policy.NANO_KEY if index == 65 else hashlib.sha256(f"source-{index}".encode()).hexdigest()
            if index == 65:
                write_json(root / model_policy.AUTHORIZATION, json.loads((ROOT / model_policy.AUTHORIZATION).read_text(encoding="utf-8")))
            source_relative = f"runtime/references/{key}.png"
            source_path = root / source_relative
            cls.png(source_path, (12, 34, 56, 255 if index == 4 else 250))
            source_sha = file_sha256(source_path)
            source_size, source_mode, source_alpha = importer.image_info(source_path)
            asset = f"gfx/leaders/test/{index:03}.dds"
            scope["entries"].append({"index": index, "source_sha256": key, "source_assets": [asset], "source_size": source_size,
                                     "source_png": source_relative, "converted_png_sha256": source_sha, "source_alpha_extrema": source_alpha})
            catalog["assets"].append({"id": asset, "path": asset, "source_sha256": key, "size": source_size, "package": "base"})
            prepared["entries"].append({"source_sha256": key, "status": "nonperson_scope_review_required" if index in importer.NONPERSON_INDICES else "existing_dispatch_record"})
            if index in importer.NONPERSON_INDICES:
                progress["entries"].append({"index": index, "source_sha256": key, "source_assets": [asset], "status": "preserved_original_nonperson_exception", "attempts_returned": []})
                nonperson["entries"].append({"index": index, "source_sha256": key, "source_assets": [asset], "source_size": source_size,
                                             "source_png": source_relative, "source_png_sha256": source_sha, "converted_png_sha256": source_sha,
                                             "source_alpha_extrema": source_alpha, "observed_subject": "No person"})
                continue
            derived = index in (1, 10)
            stem = f"{key}-{'07' if index == 65 else '01'}"
            attempt = "external-07" if index == 65 else "external-01"
            prompt = f"Complete actual synthetic request for source {index}\n"
            prompt_relative = f"{exp}/prompts/{stem}.txt"
            cls.text(root / prompt_relative, prompt)
            base_relative = f"{exp}/outputs/{stem}.png"
            base_path = root / base_relative
            cls.png(base_path, (50, 60, 70, 254), "RGB" if derived or index == 4 else "RGBA")
            base_sha = file_sha256(base_path)
            output_relative = f"{exp}/outputs/{stem}{'-alpha-repaired-bilinear' if derived else ''}.png"
            output_path = root / output_relative
            if derived:
                with Image.open(source_path) as source, Image.open(base_path) as base:
                    rgba = base.convert("RGBA")
                    rgba.putalpha(source.convert("RGBA").getchannel("A").resize(base.size, Image.Resampling.BILINEAR))
                    rgba.save(output_path)
            output_sha = file_sha256(output_path)
            size, mode, alpha = importer.image_info(output_path)
            if mode == "RGB":
                alpha = None
            master_relative = f"mod_nailong/assets/generated_fullsize/{output_sha}.png"
            (root / master_relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(output_path, root / master_relative)
            for suffix in ("prompt.txt",):
                shutil.copyfile(root / prompt_relative, root / f"{exp}/outputs/{stem}.{suffix}")
            source_url = f"https://github.com/XenoAmess/xenoamess_hoi4_dev/releases/download/test-source/{key}.png"
            request = {"endpoint": "https://api.evolink.ai/v1/images/generations", "model": "gpt-image-2.5-flare", "prompt": prompt,
                       "size": "1:1", "image_urls": [source_url, scope["mascot_reference"]["url"]], "resolution": "2K", "quality": "high", "background": "transparent", "n": 1}
            task = {"task_id": f"task-test-{index}"}
            result = {"task_id": task["task_id"], "sha256": base_sha, "bytes": base_path.stat().st_size, "downloaded_at_utc": "2026-10-28T00:00:00+00:00", "png_signature_verified": True}
            execution = {"schema": "naiwa-evolink-high131-execution-v1", "machine_id": machine_id(), "index": index, "source_sha256": key,
                         "attempt": attempt, "status": "completed", "started_at_utc": "2026-10-27T23:00:00+00:00", "finished_at_utc": "2026-10-28T00:00:00+00:00", "exit_code": 0,
                         "arguments": ["evolink_image.py", "--prompt-file", prompt_relative, "--output", base_relative, "--model", "gpt-image-2.5-flare", "--size", "1:1", "--resolution", "2K", "--quality", "high", "--background", "transparent", "--image-url", source_url, "--image-url", scope["mascot_reference"]["url"]],
                         "prompt_file": prompt_relative, "prompt_sha256": file_sha256(root / prompt_relative), "ordered_input_sha256": [source_sha, mascot_sha],
                         "output": base_relative, "output_sha256": base_sha, "task_id": task["task_id"], "result": result}
            if index == 65:
                request = {"endpoint": "https://api.evolink.ai/v1/images/generations", "model": model_policy.NANO_MODEL,
                           "prompt": prompt, "size": "1:1", "image_urls": [source_url, scope["mascot_reference"]["url"]], "quality": "2K"}
                execution["arguments"][6] = model_policy.NANO_MODEL
                del execution["arguments"][11:15]
            if index == 2:
                target = root / "mod_nailong/assets/generated_fullsize/target.png"
                cls.png(target, (9, 8, 7, 255))
                target_sha = file_sha256(target)
                target_relative = f"mod_nailong/assets/generated_fullsize/{target_sha}.png"
                target.rename(root / target_relative)
                commit = "1" * 40
                target_url = f"https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{commit}/{target_relative}"
                remote_proof = {"schema": "high131-hd-target-readback-v1", "machine_id": machine_id(), "status": "verified", "commit": commit, "complete_archive_verified": False,
                                "targets": {target_sha: {"path": target_relative, "sha256": target_sha, "bytes": (root / target_relative).stat().st_size, "url": target_url, "readback_commit": commit,
                                            "verified_at_utc": "2026-10-27T00:00:00+00:00", "method": "Complete anonymous raw PNG download; SHA256 and byte count", "remote_tree_blob_match": True, "local_original_matches": True, "png_signature_verified": True}}}
                write_json(root / "runtime/hd-proof.json", remote_proof)
                execution.update(repair_input_mode="raw-hd-edit-v1", edit_target_image=target_relative, edit_target_sha256=target_sha,
                                 rejected_output_sha256=target_sha, remote_commit=commit, remote_readback="runtime/hd-proof.json", ordered_input_sha256=[target_sha, source_sha, mascot_sha])
                request["image_urls"].insert(0, target_url)
                image_url_index = execution["arguments"].index("--image-url")
                execution["arguments"][image_url_index:image_url_index] = ["--image-url", target_url]
            sidecars = {}
            for name, body in (("task", task), ("request", request), ("result", result)):
                relative = f"{exp}/outputs/{stem}.{name}.json"
                write_json(root / relative, body)
                sidecars[name] = (relative, file_sha256(root / relative))
            execution_relative = f"{exp}/executions/{stem}.json"
            if index == 5:
                execution_relative = f"{exp}/executions/{stem}-transparent.json"
            if index in (6, 8, 9):
                execution.update(status="resume_existing_task_required", exit_code=1, output_sha256=None, result=None)
            if index != 7:
                write_json(root / execution_relative, execution)
            if index == 8:
                log_relative = f"{exp}/logs/{stem}-resume1.log"
                cls.text(root / log_relative, "Manual recovery of the same task\n")
                recovery = {"schema": "naiwa-evolink-high131-execution-recovery-v1", "machine_id": machine_id(), "source_sha256": key, "attempt": attempt,
                            "recorded_at_utc": "2026-10-28T00:02:00+00:00", "initial_execution": execution_relative, "initial_execution_sha256": file_sha256(root / execution_relative),
                            "initial_failure": "Polling failed without an output", "recovery_action": "Resume only the existing task ID with the original archived prompt/request/output path. No new generation POST, new task, changed prompt or changed ordered inputs.",
                            "task_id": task["task_id"], "same_task_id_verified": True, "new_generation_post_created": False, "resume_log": log_relative, "resume_log_sha256": file_sha256(root / log_relative),
                            "result": sidecars["result"][0], "output": base_relative, "output_sha256": base_sha, "downloaded_at_utc": result["downloaded_at_utc"], "status": "returned_pending_visual_review"}
                write_json(root / f"{exp}/executions/{stem}-resume1.json", recovery)
            if index == 6:
                log_relative = f"{exp}/logs/{stem}-retrieve1.log"
                cls.text(root / log_relative, "Existing task retrieved without another generation\n")
                recovery = {"schema": "naiwa-evolink-high131-existing-task-retrieval-v1", "machine_id": machine_id(), "index": index, "source_sha256": key,
                            "attempt": attempt, "status": "completed", "started_at_utc": "2026-10-28T00:01:00+00:00",
                            "prior_execution": execution_relative, "prior_execution_sha256": file_sha256(root / execution_relative), "task_id": task["task_id"],
                            "request_sha256": sidecars["request"][1], "prompt_sha256": execution["prompt_sha256"], "new_generation_tasks_created": 0,
                            "command": ["python", "evolink_image.py", "--task-id", task["task_id"], "--output", base_relative], "log": log_relative,
                            "finished_at_utc": "2026-10-28T00:02:00+00:00", "exit_code": 0, "output": base_relative, "output_sha256": base_sha, "result": result}
                write_json(root / f"{exp}/executions/{stem}-retrieve1.json", recovery)
            sheet_relative = f"{exp}/review-{index:03}.png"
            cls.png(root / sheet_relative, (255, 255, 255, 255))
            evidence_relative = f"{exp}/review-{index:03}-evidence.json"
            evidence = {"schema": "naiwa-evolink-high131-review-evidence-v1", "machine_id": machine_id(), "review_sheet": sheet_relative, "review_sheet_sha256": file_sha256(root / sheet_relative),
                        "entries": [{"source_sha256": key, "source_png": source_relative, "source_png_sha256": source_sha,
                                     "source_info": {"size": source_size, "mode": source_mode, "alpha_extrema": source_alpha},
                                     "generation_output": base_relative, "generation_output_sha256": base_sha,
                                     "output": output_relative, "output_sha256": output_sha, "output_info": {"size": size, "mode": mode, "alpha_extrema": alpha},
                                     "task": sidecars["task"][0], "task_sha256": sidecars["task"][1], "task_id": task["task_id"],
                                     "prompt": f"{exp}/outputs/{stem}.prompt.txt", "prompt_sha256": file_sha256(root / prompt_relative),
                                     "request": sidecars["request"][0], "request_sha256": sidecars["request"][1], "result": sidecars["result"][0], "result_sha256": sidecars["result"][1]}]}
            write_json(root / evidence_relative, evidence)
            decision = {"source_sha256": key, "attempt": "external-01-alpha-repaired-bilinear" if derived else attempt, "task_id": task["task_id"], "prompt_sha256": execution["prompt_sha256"],
                        "output": output_relative, "output_sha256": output_sha, "size": size, "mode": mode, "source_alpha_extrema": source_alpha, "returned_alpha_extrema": alpha,
                        "decision": "approved_for_production", "rgb_art_approved": True, "hair_features": {"policy": "hair-features-v1", "status": "approved"},
                        "collar_fit": {"policy": "collar-fit-v1", "status": "approved"}, "positive_observation": "Actual visible source features retained",
                        "alpha_decision": "Actual white/cyan/alpha comparisons viewed", "visible_limitations": "Synthetic fixture limitation",
                        "source_alpha_repair_performed": derived, "production_imported": False, "production_import_pending": True, "raw_output_retained": True}
            if index in (1, 3, 4):
                del decision["rgb_art_approved"]
            if index == 1:
                decision["rgb_unchanged"] = True
                del decision["task_id"], decision["source_alpha_repair_performed"], decision["prompt_sha256"]
            if index == 3:
                decision["native_alpha_accepted"] = True
            if index == 4:
                decision["native_alpha_accepted"] = None
                decision["visible_limitations"] = ["Fine details remain limited by the source"]
            review = {"schema": "naiwa-evolink-experiment-manual-review-v1", "machine_id": machine_id(), "model": model_policy.NANO_MODEL if index == 65 else "gpt-image-2.5-flare", "reviewed_at_utc": "2026-10-28T01:00:00+00:00",
                      "reviewer": "Synthetic reviewer actually viewed exact original, full raw and alpha evidence", "review_evidence": evidence_relative,
                      "review_evidence_sha256": file_sha256(root / evidence_relative), "review_sheet": sheet_relative, "review_sheet_sha256": file_sha256(root / sheet_relative),
                      "production_imported": False, "production_import_pending": True, "entries": [decision]}
            if index == 3:
                del review["review_sheet"], review["review_sheet_sha256"]
            if derived:
                review["model"] = importer.METHOD + " + " + importer.ALPHA_METHOD
                proof = importer.alpha_proof(source_path, base_path, output_path)
                decision.update(parent_task_id=task["task_id"], parent_output_sha256=base_sha, alpha_matches_resized_source=True,
                                **{field: proof[field] for field in ("source_corner_alpha_tl_tr_bl_br", "resized_corner_alpha_tl_tr_bl_br", "output_corner_alpha_tl_tr_bl_br")})
                receipt_relative = f"{exp}/review-{index:03}-alpha-receipt.json"
                write_json(root / receipt_relative, {"method": importer.ALPHA_METHOD, **proof})
                review.update(alpha_repair_receipt=receipt_relative, alpha_repair_receipt_sha256=file_sha256(root / receipt_relative))
            if index == 10:
                del review["alpha_repair_receipt"], review["alpha_repair_receipt_sha256"]
            review_relative = f"{exp}/review-{index:03}.json"
            write_json(root / review_relative, review)
            progress["entries"].append({"index": index, "source_sha256": key, "source_assets": [asset], "status": "approved_pending_import", "current_decision": "approved_for_production",
                                        "current_review": {"attempt": decision["attempt"], "decision": "approved_for_production", "reviewed_at_utc": review["reviewed_at_utc"], "review": review_relative, "review_sha256": file_sha256(root / review_relative)},
                                        "attempts_returned": [{"attempt": attempt, "output": base_relative, "output_sha256": base_sha, "task_id": task["task_id"], "downloaded_at_utc": result["downloaded_at_utc"],
                                                              "result": sidecars["result"][0], "result_sha256": sidecars["result"][1], "task": sidecars["task"][0], "task_sha256": sidecars["task"][1],
                                                              "prompt": f"{exp}/outputs/{stem}.prompt.txt", "prompt_sha256": execution["prompt_sha256"], "request": sidecars["request"][0], "request_sha256": sidecars["request"][1], "reviews": []}]})
            approved["entries"].append({"index": index, "source_sha256": key, "source_assets": [asset], "approved_attempt": decision["attempt"], "source_output": output_relative,
                                        "generated_fullsize_image": master_relative, "generated_fullsize_sha256": output_sha, "bytes": output_path.stat().st_size, "size": size, "mode": mode,
                                        "task_id": task["task_id"], "prompt_sha256": execution["prompt_sha256"], "review": review_relative, "review_sha256": file_sha256(root / review_relative),
                                        "reviewed_at_utc": review["reviewed_at_utc"], "production_imported": False, "production_import_pending": True})
        write_json(root / f"{exp}/scope.json", scope)
        write_json(root / f"{exp}/prepared.json", prepared)
        write_json(root / f"{exp}/approved-masters.json", approved)
        write_json(root / f"{exp}/nonperson-scope-decision.json", nonperson)
        write_json(root / f"{exp}/nonperson-scope-review.json", {"entries": [{"source_sha256": row["source_sha256"]} for row in nonperson["entries"]]})
        progress["nonperson_scope_decision"] = {"path": f"{exp}/nonperson-scope-decision.json", "sha256": file_sha256(root / f"{exp}/nonperson-scope-decision.json")}
        write_json(root / f"{exp}/progress.json", progress)
        write_json(root / "mod_nailong/data/catalog.json", catalog)
        write_json(root / "mod_nailong/data/generated.json", {"schema": "naiwa-generated-portraits-v1", "portraits": {"low-sentinel": {"preserved": "unchanged"}}})
        write_json(root / "mod_nailong/data/image-retry-queue.json", {"sources": {"low-sentinel": {"state": "untouched"}}})
        write_json(root / "mod_nailong/data/generation-failures.json", {"attempts": []})
        first = approved["entries"][0]["source_sha256"]
        old_preview = root / f"mod_nailong/assets/portraits/{first}.png"
        cls.png(old_preview, (1, 2, 3, 255))
        old_master = root / "mod_nailong/assets/generated_fullsize/old.png"
        cls.png(old_master, (1, 2, 3, 255))
        generated = {"schema": "naiwa-generated-portraits-v1", "portraits": {"low-sentinel": {"preserved": "unchanged"}, first: {
            "source_sha256": first, "method": "built-in imagegen", "prompt": "old prompt", "image": f"mod_nailong/assets/portraits/{first}.png", "image_sha256": file_sha256(old_preview),
            "generated_fullsize_sha256": file_sha256(old_master), "review": "approved", "revision_history": []}}}
        write_json(root / "mod_nailong/data/generated.json", generated)
        write_json(root / f"mod_nailong/data/generation-requests/{first}.json", {"schema": "naiwa-generation-requests-v1", "source_sha256": first, "attempts": [{"number": 1, "status": "failed", "prompt_sha256": "prior-prompt"}]})
        queue = {"sources": {"low-sentinel": {"state": "untouched"}, first: {"state": "failed", "retries_used": 4}}}
        write_json(root / "mod_nailong/data/image-retry-queue.json", queue)

    @staticmethod
    def png(path, color, mode="RGBA"):
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new(mode, (2, 3), color).save(path)

    @staticmethod
    def text(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8", newline="\n")


class High131ImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ImportFixture.create()

    @classmethod
    def tearDownClass(cls):
        ImportFixture.temporary.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "runtime")
        self.root = Path(self.temporary.name) / "case"
        shutil.copytree(ImportFixture.root, self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_complete_gate_and_apply_preserve_provenance_and_nonperson(self):
        plan = importer.build_plan(self.root)
        self.assertEqual(len(plan["entries"]), 127)
        import subprocess

        def git(*args):
            return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()

        (self.root / ".gitignore").write_text("runtime/\n", encoding="utf-8")
        git("init", "-b", "master")
        git("config", "user.name", "HIGH131 test")
        git("config", "user.email", "high131@example.invalid")
        original_bytes = sum((self.root / entry["generated_fullsize_image"]).stat().st_size for entry in plan["entries"])
        index_outputs = {entry["generated_fullsize_sha256"]: {"path": entry["generated_fullsize_image"], "bytes": (self.root / entry["generated_fullsize_image"]).stat().st_size} for entry in plan["entries"]}
        importer.write_json(self.root / "mod_nailong/data/fullsize-files.json", {"schema": "naiwa-fullsize-git-files-v1", "outputs": index_outputs, "count": 127, "original_png_bytes": original_bytes})
        git("add", "--", ".gitignore", "mod_nailong")
        git("commit", "-m", "Synthetic evidence baseline")
        baseline = git("rev-parse", "HEAD")
        proof_outputs = {entry["generated_fullsize_sha256"]: {
            "path": entry["generated_fullsize_image"], "bytes": (self.root / entry["generated_fullsize_image"]).stat().st_size,
            "sha256": entry["generated_fullsize_sha256"], "git_blob_sha1": git("rev-parse", f"{baseline}:{entry['generated_fullsize_image']}"),
            "readback_commit": baseline, "method": "Complete anonymous raw PNG download; SHA256 and byte count",
        } for entry in plan["entries"]}
        proof_path = self.root / "runtime/parent-readback.json"
        importer.write_json(proof_path, {"schema": "naiwa-fullsize-git-checkpoint-v1", "machine_id": machine_id(), "commit": baseline,
            "verification": "Remote Git tree blob SHA/size match plus complete anonymous raw PNG download SHA256/size for every output; unchanged blobs may retain their earlier pinned readback commit/time",
            "distinct_outputs": 127, "original_png_bytes": original_bytes, "outputs": proof_outputs})
        self.assertEqual(importer.validate_parent_readback(self.root, baseline, plan, proof_path)["approved_original_pngs"], 127)
        bad_proof = importer.read_json(proof_path)
        bad_proof["commit"] = "0" * 40
        bad_proof_path = self.root / "runtime/bad-parent-readback.json"
        importer.write_json(bad_proof_path, bad_proof)
        with self.assertRaisesRegex(importer.ImportGateError, "exact isolated parent"):
            importer.validate_parent_readback(self.root, baseline, plan, bad_proof_path)
        imported = importer.write_import(plan, self.root)
        self.assertEqual(len(imported), 127)
        generated = importer.read_json(self.root / importer.GENERATED)["portraits"]
        self.assertEqual(generated["low-sentinel"], {"preserved": "unchanged"})
        for entry in plan["entries"]:
            key = entry["source_sha256"]
            row = generated[key]
            self.assertTrue(portrait_ready(row))
            self.assertEqual(row["method"], entry["method"])
            self.assertEqual(row["prompt"], entry["prompt"])
            self.assertEqual(row["generation_inputs"], entry["inputs"])
            self.assertEqual(row["reviewed_at_utc"], entry["reviewed_at_utc"])
            journal = importer.read_json(self.root / row["request_journal"])["attempts"]
            self.assertEqual(journal[-1]["external_task_id"], entry["task_id"])
            self.assertEqual(journal[-1]["prompt"], entry["prompt"])
            self.assertEqual(journal[-1]["status"], "approved")
        for exception in importer.read_json(self.root / f"{importer.EXPERIMENT}/nonperson-scope-decision.json")["entries"]:
            self.assertNotIn(exception["source_sha256"], generated)
        first = plan["entries"][0]
        first_journal = importer.read_json(self.root / f"mod_nailong/data/generation-requests/{first['source_sha256']}.json")["attempts"]
        self.assertEqual(first_journal[0], {"number": 1, "status": "failed", "prompt_sha256": "prior-prompt"})
        self.assertEqual(first_journal[-1]["method"], importer.METHOD + " + " + importer.ALPHA_METHOD)
        self.assertEqual(first_journal[-1]["alpha_repair"]["parent_fullsize_sha256"], first["alpha_repair"]["parent_fullsize_sha256"])
        second_journal = importer.read_json(self.root / f"mod_nailong/data/generation-requests/{plan['entries'][1]['source_sha256']}.json")["attempts"]
        self.assertTrue(second_journal[-1]["edit_existing"])
        self.assertEqual(second_journal[-1]["inputs"][0]["sha256"], second_journal[-1]["inputs"][0]["sha256"])
        self.assertTrue(plan["entries"][4]["execution"].endswith("-transparent.json"))
        self.assertIsNone(plan["entries"][4]["recovery"])
        recovery_journal = importer.read_json(self.root / f"mod_nailong/data/generation-requests/{plan['entries'][5]['source_sha256']}.json")["attempts"][-1]
        self.assertEqual(recovery_journal["external_recovery"], plan["entries"][5]["recovery"]["path"])
        self.assertEqual(recovery_journal["external_recovery_sha256"], plan["entries"][5]["recovery"]["sha256"])
        self.assertIsNone(plan["entries"][6]["execution"])
        self.assertEqual(plan["entries"][6]["recovery_status"], "archived_request_only_no_execution_record")
        self.assertTrue(plan["entries"][7]["recovery"]["path"].endswith("-resume1.json"))
        self.assertIsNone(plan["entries"][8]["recovery"]["path"])
        self.assertEqual(plan["entries"][8]["recovery_status"], "same_task_result_without_retrieval_receipt")
        for entry in plan["entries"][6:9]:
            journal = importer.read_json(self.root / f"mod_nailong/data/generation-requests/{entry['source_sha256']}.json")["attempts"][-1]
            self.assertEqual(journal["recovery_status"], entry["recovery_status"])
        self.assertEqual(generated[plan["entries"][3]["source_sha256"]]["generated_fullsize_size"], [2, 3])
        self.assertIsNone(plan["entries"][9]["alpha_repair"]["receipt"])
        self.assertTrue(plan["entries"][9]["alpha_repair"]["rgb_unchanged"])
        queue = importer.read_json(self.root / importer.QUEUE)["sources"]
        self.assertEqual(queue[first["source_sha256"]]["retries_used"], 4)
        self.assertEqual(queue["low-sentinel"], {"state": "untouched"})
        progress = importer.read_json(self.root / f"{importer.EXPERIMENT}/progress.json")
        self.assertEqual(sum(row["status"] == "approved_imported" for row in progress["entries"]), 127)
        archived = importer.read_json(self.root / f"{importer.EXPERIMENT}/approved-masters.json")
        self.assertTrue(all(row["production_imported"] and not row["production_import_pending"] for row in archived["entries"]))
        self.assertEqual(importer.write_import(importer.build_plan(self.root), self.root), [])
        after = importer.read_json(self.root / f"mod_nailong/data/generation-requests/{first['source_sha256']}.json")["attempts"]
        self.assertEqual(after, first_journal)
        from mod_nailong.tools import portraits
        from runtime import high131_status
        self.assertEqual(portraits.ROOT, ROOT)
        self.assertEqual(high131_status.ROOT, ROOT)
        remote = self.root.parent / "remote.git"
        git("init", "--bare", str(remote))
        git("remote", "add", "origin", str(remote))
        git("push", "-u", "origin", "master")
        high_commit = importer.stage_and_commit(self.root, plan)
        self.assertNotEqual(high_commit, baseline)
        git("checkout", "-b", "other-owner", baseline)
        other_generated = importer.read_json(self.root / importer.GENERATED)
        other_generated["portraits"]["low-sentinel"]["preserved"] = "other-owner"
        importer.write_json(self.root / importer.GENERATED, other_generated)
        other_queue = importer.read_json(self.root / importer.QUEUE)
        other_queue["sources"]["low-sentinel"]["state"] = "other-owner"
        importer.write_json(self.root / importer.QUEUE, other_queue)
        git("add", "--", importer.GENERATED, importer.QUEUE)
        git("commit", "-m", "Concurrent unrelated source update")
        other_commit = git("rev-parse", "HEAD")
        git("push", "origin", "other-owner:master")
        git("checkout", "--detach", high_commit)
        final_commit = importer.rebase_import(self.root, high_commit, plan)
        self.assertNotEqual(final_commit, high_commit)
        self.assertEqual(git("rev-parse", "HEAD^"), other_commit)
        merged = importer.read_json(self.root / importer.GENERATED)["portraits"]
        self.assertEqual(merged["low-sentinel"]["preserved"], "other-owner")
        self.assertTrue(portrait_ready(merged[first["source_sha256"]]))
        self.assertEqual(importer.read_json(self.root / importer.QUEUE)["sources"]["low-sentinel"]["state"], "other-owner")
        self.assertEqual(importer.read_json(self.root / importer.QUEUE)["sources"][first["source_sha256"]]["retries_used"], 4)

    def test_incomplete_gate_has_no_production_writes(self):
        progress_path = self.root / f"{importer.EXPERIMENT}/progress.json"
        progress = importer.read_json(progress_path)
        for index in (52, 60, 65, 117):
            progress["entries"][index - 1]["status"] = "rejected_latest_attempt"
        importer.write_json(progress_path, progress)
        before = [(self.root / path).read_bytes() for path in (importer.GENERATED, importer.QUEUE)]
        with self.assertRaises(importer.ImportGateError) as caught:
            importer.build_plan(self.root)
        self.assertEqual(caught.exception.report["approved_person_sources"], 123)
        self.assertEqual([row["index"] for row in caught.exception.report["pending_sources"]], [52, 60, 65, 117])
        self.assertFalse(caught.exception.report["production_writes_performed"])
        self.assertEqual(before, [(self.root / path).read_bytes() for path in (importer.GENERATED, importer.QUEUE)])

    def test_tampered_output_and_missing_alpha_review_fail(self):
        for mutate, message in ((lambda: (self.root / importer.read_json(self.root / f"{importer.EXPERIMENT}/approved-masters.json")["entries"][0]["source_output"]).write_bytes(b"broken"), "Evidence SHA"),
                                (self._remove_alpha_observation, "Review SHA")):
            with self.subTest(message=message):
                mutate()
                with self.assertRaisesRegex(importer.ImportGateError, message):
                    importer.build_plan(self.root)
                shutil.rmtree(self.root)
                shutil.copytree(ImportFixture.root, self.root)

    def _remove_alpha_observation(self):
        path = self.root / f"{importer.EXPERIMENT}/review-001.json"
        body = importer.read_json(path)
        body["entries"][0]["alpha_decision"] = ""
        importer.write_json(path, body)

    def test_broken_alpha_chain_and_request_order_fail(self):
        receipt_path = self.root / f"{importer.EXPERIMENT}/review-001-alpha-receipt.json"
        receipt = importer.read_json(receipt_path)
        receipt["base_sha256"] = "0" * 64
        importer.write_json(receipt_path, receipt)
        review_path = self.root / f"{importer.EXPERIMENT}/review-001.json"
        review = importer.read_json(review_path)
        review["alpha_repair_receipt_sha256"] = file_sha256(receipt_path)
        importer.write_json(review_path, review)
        for relative in (f"{importer.EXPERIMENT}/approved-masters.json", f"{importer.EXPERIMENT}/progress.json"):
            path = self.root / relative
            body = importer.read_json(path)
            row = body["entries"][0] if relative.endswith("approved-masters.json") else body["entries"][0]["current_review"]
            row["review_sha256"] = file_sha256(review_path)
            importer.write_json(path, body)
        with self.assertRaisesRegex(importer.ImportGateError, "base_sha256"):
            importer.build_plan(self.root)
        shutil.rmtree(self.root)
        shutil.copytree(ImportFixture.root, self.root)
        request_path = self.root / importer.read_json(self.root / f"{importer.EXPERIMENT}/progress.json")["entries"][0]["attempts_returned"][0]["request"]
        request = importer.read_json(request_path)
        request["image_urls"].reverse()
        importer.write_json(request_path, request)
        evidence_path = self.root / f"{importer.EXPERIMENT}/review-001-evidence.json"
        evidence = importer.read_json(evidence_path)
        evidence["entries"][0]["request_sha256"] = file_sha256(request_path)
        importer.write_json(evidence_path, evidence)
        review_path = self.root / f"{importer.EXPERIMENT}/review-001.json"
        review = importer.read_json(review_path)
        review["review_evidence_sha256"] = file_sha256(evidence_path)
        importer.write_json(review_path, review)
        for relative in (f"{importer.EXPERIMENT}/approved-masters.json", f"{importer.EXPERIMENT}/progress.json"):
            path = self.root / relative
            body = importer.read_json(path)
            row = body["entries"][0] if relative.endswith("approved-masters.json") else body["entries"][0]["current_review"]
            row["review_sha256"] = file_sha256(review_path)
            importer.write_json(path, body)
        with self.assertRaisesRegex(importer.ImportGateError, "Ordered input URLs"):
            importer.build_plan(self.root)

    def test_nonperson_row_and_concurrent_high_change_are_rejected(self):
        generated_path = self.root / importer.GENERATED
        generated = importer.read_json(generated_path)
        exception = importer.read_json(self.root / f"{importer.EXPERIMENT}/nonperson-scope-decision.json")["entries"][0]
        generated["portraits"][exception["source_sha256"]] = {"fabricated": True}
        importer.write_json(generated_path, generated)
        with self.assertRaisesRegex(importer.ImportGateError, "must not be fabricated"):
            importer.build_plan(self.root)
        base = {"portraits": {"high": {"image": "old"}, "low": {"image": "base"}}}
        remote = {"portraits": {"high": {"image": "old"}, "low": {"image": "other-owner"}}}
        planned = {"portraits": {"high": {"image": "approved"}, "low": {"image": "base"}}}
        merged = importer.merge_shared_mapping(remote, planned, base, {"high"}, "portraits")
        self.assertEqual(merged["portraits"]["high"]["image"], "approved")
        self.assertEqual(merged["portraits"]["low"]["image"], "other-owner")
        remote["portraits"]["high"]["image"] = "unexpected"
        with self.assertRaisesRegex(importer.ImportGateError, "Concurrent HIGH"):
            importer.merge_shared_mapping(remote, planned, base, {"high"}, "portraits")


if __name__ == "__main__":
    unittest.main()
