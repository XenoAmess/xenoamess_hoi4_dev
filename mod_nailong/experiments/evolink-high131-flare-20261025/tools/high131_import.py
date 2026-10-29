import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.high131_io import write_json
from runtime import high131_model_policy as model_policy
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now

EXPERIMENT = "mod_nailong/experiments/evolink-high131-flare-20261025"
GENERATED = "mod_nailong/data/generated.json"
QUEUE = "mod_nailong/data/image-retry-queue.json"
METHOD = "EvoLink gpt-image-2.5-flare"
ALPHA_METHOD = "source-alpha-resize-bilinear-rgb-unchanged-v1"
NONPERSON_INDICES = {78, 125, 129, 131}


class ImportGateError(RuntimeError):
    def __init__(self, message, **report):
        super().__init__(message)
        self.report = report


def require(condition, message):
    if not condition:
        raise ImportGateError(message)


def accessible_path(path):
    path = Path(path).resolve()
    if sys.platform == "win32" and not str(path).startswith("\\\\?\\"):
        return Path("\\\\?\\" + str(path))
    return path


def project_path(root, value):
    require(isinstance(value, str) and value and not Path(value).is_absolute(), f"Invalid repository-relative evidence path: {value}")
    root = Path(root).resolve()
    candidate = (root / value).resolve()
    candidate.relative_to(root)
    if not accessible_path(candidate).exists() and root != ROOT.resolve():
        candidate = (ROOT / value).resolve()
        candidate.relative_to(ROOT.resolve())
    return candidate


def evidence_json(root, value):
    return read_json(accessible_path(project_path(root, value)))


def bound_file(root, value, expected_sha):
    path = project_path(root, value)
    require(accessible_path(path).is_file() and file_sha256(accessible_path(path)) == expected_sha, f"Evidence SHA mismatch: {value}")
    return path


def restore_original_json_bytes(root, support_root, value, expected_sha):
    if support_root is None or Path(root).resolve() == Path(support_root).resolve():
        return False
    root = Path(root).resolve()
    target = (root / value).resolve()
    target.relative_to(root)
    require(Path(value).suffix == ".json" and accessible_path(target).is_file(), f"Tracked JSON receipt is missing: {value}")
    if file_sha256(accessible_path(target)) == expected_sha:
        return False
    source = bound_file(support_root, value, expected_sha)
    original = accessible_path(source).read_bytes()
    result = subprocess.run(["git", "show", f"HEAD:{value}"], cwd=root, capture_output=True)
    require(result.returncode == 0, f"Cannot read committed JSON receipt: {value}: {result.stderr.decode('utf-8', errors='replace')}")
    require(original.replace(b"\r\n", b"\n") == result.stdout and json.loads(original) == json.loads(result.stdout), f"JSON receipt differs beyond Git LF normalization: {value}")
    accessible_path(target).write_bytes(original)
    require(file_sha256(accessible_path(target)) == expected_sha, f"Original JSON receipt restoration failed: {value}")
    for arguments in (["git", "add", "--renormalize", "--", value], ["git", "diff", "--cached", "--quiet", "--", value], ["git", "status", "--porcelain", "--", value]):
        result = subprocess.run(arguments, cwd=root, capture_output=True)
        require(result.returncode == 0 and (arguments[1] != "status" or not result.stdout), f"JSON receipt normalization changed its committed evidence: {value}: {result.stderr.decode('utf-8', errors='replace')}")
    return True


def option_values(arguments, option):
    return [arguments[i + 1] for i, value in enumerate(arguments[:-1]) if value == option]


def image_info(path):
    with Image.open(path) as image:
        image.load()
        return list(image.size), image.mode, list(image.convert("RGBA").getchannel("A").getextrema())


def alpha_proof(source_path, parent_path, output_path):
    with Image.open(source_path) as source, Image.open(parent_path) as parent, Image.open(output_path) as output:
        source_alpha = source.convert("RGBA").getchannel("A")
        resized = source_alpha.resize(parent.size, Image.Resampling.BILINEAR)
        rgba = output.convert("RGBA")
        corners = lambda channel: [channel.getpixel(point) for point in ((0, 0), (channel.width - 1, 0), (0, channel.height - 1), (channel.width - 1, channel.height - 1))]
        return {
            "source_sha256": file_sha256(source_path),
            "base_sha256": file_sha256(parent_path),
            "output_sha256": file_sha256(output_path),
            "source_size": list(source.size),
            "base_size": list(parent.size),
            "source_mode": source.mode,
            "base_mode": parent.mode,
            "output_mode": output.mode,
            "source_corner_alpha_tl_tr_bl_br": corners(source_alpha),
            "resized_corner_alpha_tl_tr_bl_br": corners(resized),
            "output_corner_alpha_tl_tr_bl_br": corners(rgba.getchannel("A")),
            "resized_alpha_sha256": hashlib.sha256(resized.tobytes()).hexdigest(),
            "rgb_unchanged": parent.convert("RGB").tobytes() == rgba.convert("RGB").tobytes(),
            "alpha_matches_resized_source": rgba.getchannel("A").tobytes() == resized.tobytes(),
        }


def actual_inputs(root, support_root, scope, source, execution, request):
    from runtime import high131_hd_proof as hd

    key = source["source_sha256"]
    source_path = bound_file(support_root, source["source_png"], source["converted_png_sha256"])
    mascot = scope["mascot_reference"]
    bound_file(support_root, mascot["path"], mascot["sha256"])
    source_url = f"https://github.com/XenoAmess/xenoamess_hoi4_dev/releases/download/{scope['source_release_tag']}/{key}.png"
    inputs = [
        {"role": "original source portrait", "path": source["source_png"], "raw_sha256": key, "converted_png_sha256": source["converted_png_sha256"], "url": source_url},
        {"role": "user mascot reference", "path": mascot["path"], "sha256": mascot["sha256"], "url": mascot["url"]},
    ]
    expected_urls = [source_url, mascot["url"]]
    expected_shas = [source["converted_png_sha256"], mascot["sha256"]]
    mode = execution.get("repair_input_mode") if execution is not None else None
    mask_url = None
    if mode is not None:
        require(mode in hd.HD_INPUT_MODES, f"Unsupported raw-HD input mode for {key}")
        require(execution.get("edit_target_sha256") == execution.get("rejected_output_sha256"), f"Edit target is not the rejected output for {key}")
        target_path = bound_file(support_root, execution.get("edit_target_image"), execution["edit_target_sha256"])
        commit = execution.get("remote_commit")
        require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit), f"Missing target proof commit for {key}")
        proof, index = hd.load_remote_proof(commit, execution.get("remote_readback"), root=support_root)
        target_url = hd.validate_remote_target(proof, commit, target_path, execution["edit_target_sha256"], index=index, root=support_root)
        inputs.insert(0, {"role": "previous generated fullsize edit target", "path": execution["edit_target_image"], "sha256": execution["edit_target_sha256"], "url": target_url})
        expected_urls.insert(0, target_url)
        expected_shas.insert(0, execution["edit_target_sha256"])
        if mode in (hd.NOTE_DETAIL_MODE, hd.MASK_NOTE_MODE):
            detail = execution.get("note_detail", {})
            require(detail.get("source_png_sha256") == source["converted_png_sha256"], f"Source-detail parent mismatch for {key}")
            detail_path = bound_file(support_root, detail.get("path"), detail.get("sha256"))
            detail_url = hd.validate_remote_reference(proof, commit, detail_path, detail["sha256"], source_path, root=support_root)
            require(detail.get("url") == detail_url and detail.get("not_generated_or_game_payload") is True, f"Source-detail URL or role mismatch for {key}")
            inputs.append({"role": "source-note-detail-reference", "path": detail["path"], "sha256": detail["sha256"], "url": detail_url, "source_png_sha256": source["converted_png_sha256"], "not_generated_or_game_payload": True})
            expected_urls.append(detail_url)
            expected_shas.append(detail["sha256"])
        if mode == hd.MASK_NOTE_MODE:
            mask = execution.get("mask", {})
            mask_path = bound_file(support_root, mask.get("path"), mask.get("sha256"))
            mask_url = hd.validate_remote_mask(proof, commit, mask_path, mask["sha256"], target_path, execution["edit_target_sha256"], root=support_root)
            require(mask.get("url") == mask_url and execution.get("mask_url") == mask_url, f"Mask URL mismatch for {key}")
            require(mask.get("target_sha256") == execution["edit_target_sha256"], f"Mask target mismatch for {key}")
            bound_file(support_root, mask.get("manifest"), mask.get("manifest_sha256"))
    require(request.get("image_urls") == expected_urls, f"Ordered input URLs differ for {key}")
    if execution is None:
        require(request.get("mask_url") is None, f"Request-only evidence cannot prove an edit mask for {key}")
        return inputs
    require(execution.get("ordered_input_sha256") == expected_shas, f"Ordered input bytes differ for {key}")
    require(option_values(execution["arguments"], "--image-url") == expected_urls, f"Executed input URLs differ for {key}")
    executed_mask = option_values(execution["arguments"], "--mask-url")
    require(executed_mask == ([] if mask_url is None else [mask_url]), f"Executed mask URL differs for {key}")
    require(request.get("mask_url") == mask_url, f"Request mask URL differs for {key}")
    return inputs


def find_execution(root, approved, base_attempt, task_id, stem):
    key = approved["source_sha256"]
    ordinary = f"{EXPERIMENT}/executions/{stem}.json"
    if accessible_path(project_path(root, ordinary)).is_file():
        return ordinary, evidence_json(root, ordinary)
    matches = []
    for path in (project_path(root, f"{EXPERIMENT}/executions")).glob(f"{key}-*.json"):
        body = read_json(path)
        if body.get("schema") != "naiwa-evolink-high131-execution-v1":
            continue
        if (body.get("index"), body.get("source_sha256"), body.get("attempt"), body.get("task_id")) == (approved["index"], key, base_attempt, task_id):
            matches.append((path, body))
    if not matches:
        return None, None
    require(len(matches) == 1, f"Expected one aliased generation execution for {key}")
    path, body = matches[0]
    return path.relative_to(root).as_posix(), body


def validate_execution_recovery(root, relative, execution, approved, base_attempt, task_id, proof, result):
    key = approved["source_sha256"]
    require(execution.get("machine_id") == machine_id(), f"Execution machine mismatch for {key}")
    for field, expected in (("index", approved["index"]), ("source_sha256", key), ("attempt", base_attempt), ("task_id", task_id), ("prompt_sha256", proof["prompt_sha256"])):
        require(execution.get(field) == expected, f"Execution binding mismatch for {key}: {field}")
    require(execution.get("output") == proof["generation_output"], f"Execution output mismatch for {key}")
    if execution.get("status") == "completed":
        require(execution.get("exit_code") == 0 and execution.get("output_sha256") == proof["generation_output_sha256"] and execution.get("result") == result, f"Generation execution did not complete for {key}")
        return None
    require(execution.get("status") == "resume_existing_task_required" and execution.get("result") is None and execution.get("output_sha256") is None, f"Generation execution has no complete result or recovery for {key}")
    recoveries = []
    for path in (project_path(root, f"{EXPERIMENT}/executions")).glob(f"{key}-{base_attempt.removeprefix('external-')}-retrieve*.json"):
        candidate = read_json(path)
        if candidate.get("status") == "completed":
            recoveries.append((path, candidate))
    require(len(recoveries) <= 1, f"Multiple completed retrieval receipts need reconciliation for {key}")
    if recoveries:
        path, recovery = recoveries[0]
        for field, expected in (
            ("schema", "naiwa-evolink-high131-existing-task-retrieval-v1"), ("machine_id", machine_id()),
            ("index", approved["index"]), ("source_sha256", key), ("attempt", base_attempt),
            ("status", "completed"), ("exit_code", 0), ("prior_execution", relative),
            ("prior_execution_sha256", file_sha256(project_path(root, relative))),
            ("task_id", task_id), ("request_sha256", proof["request_sha256"]), ("prompt_sha256", proof["prompt_sha256"]),
            ("new_generation_tasks_created", 0), ("output", proof["generation_output"]),
            ("output_sha256", proof["generation_output_sha256"]), ("result", result),
        ):
            require(recovery.get(field) == expected, f"Existing-task recovery mismatch for {key}: {field}")
        command = recovery.get("command", [])
        require(len(command) >= 2 and Path(command[1]).name == "evolink_image.py", f"Unexpected recovery client for {key}")
        require(option_values(command, "--task-id") == [task_id] and "--prompt-file" not in command, f"Recovery must not create another generation for {key}")
        require(project_path(root, recovery.get("log")).is_file(), f"Recovery log is missing for {key}")
        return {"path": path.relative_to(root).as_posix(), "sha256": file_sha256(path)}
    manual = []
    for path in (project_path(root, f"{EXPERIMENT}/executions")).glob(f"{key}-{base_attempt.removeprefix('external-')}-resume*.json"):
        candidate = read_json(path)
        if candidate.get("schema") == "naiwa-evolink-high131-execution-recovery-v1":
            manual.append((path, candidate))
    if manual:
        require(len(manual) == 1, f"Multiple manual task recovery receipts need reconciliation for {key}")
        path, recovery = manual[0]
        for field, expected in (
            ("machine_id", machine_id()), ("source_sha256", key), ("attempt", base_attempt),
            ("initial_execution", relative), ("initial_execution_sha256", file_sha256(project_path(root, relative))),
            ("task_id", task_id), ("same_task_id_verified", True), ("new_generation_post_created", False),
            ("result", proof["result"]), ("output", proof["generation_output"]),
            ("output_sha256", proof["generation_output_sha256"]), ("downloaded_at_utc", result["downloaded_at_utc"]),
        ):
            require(recovery.get(field) == expected, f"Manual task recovery mismatch for {key}: {field}")
        require(isinstance(recovery.get("recovery_action"), str) and "No new generation POST" in recovery["recovery_action"], f"Manual recovery permits another generation for {key}")
        bound_file(root, recovery.get("resume_log"), recovery.get("resume_log_sha256"))
        return {"path": path.relative_to(root).as_posix(), "sha256": file_sha256(path)}
    return {"path": None, "sha256": None, "status": "same_task_result_without_retrieval_receipt"}


def validate_person(root, support_root, scope, progress, approved, generated):
    from runtime.high131_hd_proof import HD_INPUT_MODES

    key = approved["source_sha256"]
    source = next(row for row in scope["entries"] if row["index"] == approved["index"])
    current = progress["entries"][approved["index"] - 1]
    require(source["source_sha256"] == key == current["source_sha256"], f"Source identity mismatch at {approved['index']}")
    require(current["status"] in {"approved_pending_import", "approved_imported"}, f"Person is not approved: {approved['index']}")
    imported = current["status"] == "approved_imported"
    require(approved["source_assets"] == source["source_assets"], f"Approved-master scope mismatch for {key}")
    require(approved.get("production_imported", False) is imported and approved["production_import_pending"] is (not imported), f"Approved-master import state mismatch for {key}")
    review_path = approved["review"]
    restore_original_json_bytes(root, support_root, review_path, approved["review_sha256"])
    review = evidence_json(root, review_path)
    require(file_sha256(accessible_path(project_path(root, review_path))) == approved["review_sha256"], f"Review SHA mismatch for {key}")
    require(review.get("machine_id") == machine_id() and review.get("production_import_pending") is True, f"Review machine or state mismatch for {key}")
    entries = [row for row in review["entries"] if row.get("source_sha256") == key]
    require(len(entries) == 1, f"Expected one review entry for {key}")
    decision = entries[0]
    require(decision.get("decision") == "approved_for_production", f"Missing actual art approval for {key}")
    opaque_rgb = (decision.get("mode") == "RGB" and source["source_alpha_extrema"] == [255, 255]
                  and decision.get("returned_alpha_extrema") is None and decision.get("source_alpha_repair_performed") is False)
    derived_rgb = decision.get("rgb_unchanged") is True and decision.get("alpha_matches_resized_source") is True
    require(decision.get("rgb_art_approved") is True or decision.get("native_alpha_accepted") is True or opaque_rgb or derived_rgb, f"Missing RGB art or visible-alpha approval for {key}")
    require(decision.get("production_import_pending") is True and decision.get("remaining_reasons", []) == [], f"Unresolved art reason for {key}")
    for field in ("hair_features", "collar_fit"):
        require(decision[field]["status"] in {"approved", "pass"}, f"Missing {field} approval for {key}")
    require(decision["hair_features"]["policy"] == "hair-features-v1" and decision["collar_fit"]["policy"] == "collar-fit-v1", f"Wrong art policy for {key}")
    for field in ("positive_observation", "alpha_decision"):
        require(isinstance(decision.get(field), str) and decision[field], f"Missing visible review field {field} for {key}")
    limitations = decision.get("visible_limitations")
    require((isinstance(limitations, str) and bool(limitations)) or (isinstance(limitations, list) and limitations and all(isinstance(row, str) and row for row in limitations)), f"Missing visible limitations for {key}")
    require(isinstance(review.get("reviewer"), str) and review["reviewer"], f"Missing reviewer for {key}")
    require(current["current_review"]["review"] == review_path and current["current_review"]["review_sha256"] == approved["review_sha256"], f"Current review is stale for {key}")
    require(current["current_review"]["attempt"] == approved["approved_attempt"] == decision["attempt"], f"Approved attempt mismatch for {key}")
    match = re.fullmatch(r"external-(\d{2})(-alpha-repaired-bilinear)?", approved["approved_attempt"])
    require(match is not None, f"Unsupported approved attempt for {key}")
    number, derived = match.group(1), bool(match.group(2))
    base_attempt = f"external-{number}"
    attempts = current["attempts_returned"]
    require(attempts and attempts[-1]["attempt"] == base_attempt, f"Latest ordinary attempt is not the approved parent for {key}")
    latest = attempts[-1]
    stem = f"{key}-{number}"
    suffix = "-alpha-repaired-bilinear" if derived else ""
    expected_output = f"{EXPERIMENT}/outputs/{stem}{suffix}.png"
    require(decision.get("output") == expected_output and decision.get("output_sha256") == approved["generated_fullsize_sha256"], f"Approved output mismatch for {key}")
    require(decision.get("task_id", decision.get("parent_task_id")) == approved["task_id"] == latest["task_id"] and decision.get("prompt_sha256", latest["prompt_sha256"]) == approved["prompt_sha256"] == latest["prompt_sha256"], f"Task or prompt mismatch for {key}")
    output_path = bound_file(root, expected_output, approved["generated_fullsize_sha256"])
    size, mode, alpha = image_info(output_path)
    master_relative = f"mod_nailong/assets/generated_fullsize/{approved['generated_fullsize_sha256']}.png"
    master_path = bound_file(root, master_relative, approved["generated_fullsize_sha256"])
    require(master_path.read_bytes() == output_path.read_bytes(), f"Archived master is not byte-identical for {key}")
    require(approved["generated_fullsize_image"] == master_relative and approved["bytes"] == master_path.stat().st_size, f"Master path or bytes mismatch for {key}")
    require(approved["size"] == decision["size"] == size and approved["mode"] == decision["mode"] == mode, f"Final image metadata mismatch for {key}")
    require(mode == "RGBA" or opaque_rgb, f"Unexpected RGB output for a source with transparency for {key}")
    require(decision["returned_alpha_extrema"] == (None if mode == "RGB" else alpha), f"Visible alpha evidence changed for {key}")
    evidence = evidence_json(root, review["review_evidence"])
    require(file_sha256(project_path(root, review["review_evidence"])) == review["review_evidence_sha256"], f"Review evidence SHA mismatch for {key}")
    sheet = review.get("review_sheet", evidence.get("review_sheet"))
    sheet_sha = review.get("review_sheet_sha256", evidence.get("review_sheet_sha256"))
    require(evidence.get("machine_id") == machine_id() and evidence.get("review_sheet") == sheet, f"Review evidence scope mismatch for {key}")
    require(sheet_sha == evidence.get("review_sheet_sha256"), f"Review sheet SHA mismatch for {key}")
    bound_file(root, sheet, sheet_sha)
    proofs = [row for row in evidence["entries"] if row.get("source_sha256") == key]
    require(len(proofs) == 1, f"Expected one evidence entry for {key}")
    proof = proofs[0]
    require(proof["source_png"] == source["source_png"] and proof["source_png_sha256"] == source["converted_png_sha256"], f"Evidence source mismatch for {key}")
    source_path = bound_file(root, source["source_png"], source["converted_png_sha256"])
    source_size, source_mode, source_alpha = image_info(source_path)
    require(proof["source_info"]["size"] == source_size == source["source_size"] and proof["source_info"]["alpha_extrema"] == source_alpha == source["source_alpha_extrema"] == decision["source_alpha_extrema"], f"Source alpha evidence mismatch for {key}")
    require(proof["source_info"]["mode"] == source_mode, f"Source image mode mismatch for {key}")
    require(proof["output_info"]["size"] == size and proof["output_info"]["mode"] == mode and proof["output_info"]["alpha_extrema"] == (None if mode == "RGB" else alpha), f"Evidence output metadata mismatch for {key}")
    for field in ("generation_output", "output", "task", "prompt", "request", "result"):
        require(project_path(root, proof[field]).parent == project_path(root, f"{EXPERIMENT}/outputs"), f"Evidence path is outside outputs for {key}: {field}")
        if field in {"task", "request", "result"}:
            restore_original_json_bytes(root, support_root, proof[field], proof[field + "_sha256"])
        bound_file(root, proof[field], proof[field + "_sha256"])
    parent_path = project_path(root, proof["generation_output"])
    require(parent_path == project_path(root, f"{EXPERIMENT}/outputs/{stem}.png"), f"Generation parent path mismatch for {key}")
    result = evidence_json(root, proof["result"])
    task = evidence_json(root, proof["task"])
    request = evidence_json(root, proof["request"])
    prompt = accessible_path(project_path(root, proof["prompt"])).read_bytes().decode("utf-8")
    execution_relative, execution = find_execution(root, approved, base_attempt, result["task_id"], stem)
    recovery = validate_execution_recovery(root, execution_relative, execution, approved, base_attempt, result["task_id"], proof, result) if execution is not None else None
    require(result.get("task_id") == task.get("task_id") == proof["task_id"] and result.get("sha256") == proof["generation_output_sha256"], f"Task/result binding mismatch for {key}")
    require(result.get("bytes") == parent_path.stat().st_size and result.get("png_signature_verified") is True and result.get("downloaded_at_utc"), f"Result is incomplete for {key}")
    require(request.get("endpoint") == "https://api.evolink.ai/v1/images/generations", f"Wrong generation endpoint for {key}")
    model = request.get("model")
    method = model_policy.production_method(root, key, base_attempt, model)
    if model == "gpt-image-2.5-flare":
        require(request.get("n") == 1, f"Wrong generation route for {key}")
    else:
        for field in ("background", "n", "resolution", "mask_url"):
            require(request.get(field) is None, f"Nano request contains a GPT-only field for {key}: {field}")
        require(request.get("quality") in {"1K", "2K", "4K"}, f"Nano quality mapping mismatch for {key}")
    require(request.get("prompt") == prompt, f"Actual prompt differs from request for {key}")
    if execution is not None:
        frozen_prompt = bound_file(root, execution.get("prompt_file"), execution["prompt_sha256"])
        require(frozen_prompt.read_bytes().decode("utf-8") == prompt, f"Frozen prompt differs from client sidecar for {key}")
        arguments = execution["arguments"]
        require(Path(arguments[0]).name == "evolink_image.py", f"Unexpected generator for {key}")
        if model == "gpt-image-2.5-flare":
            for option, field in (("--model", "model"), ("--size", "size"), ("--resolution", "resolution"), ("--quality", "quality"), ("--background", "background")):
                require(option_values(arguments, option) == [request[field]], f"Executed route differs for {key}: {option}")
        else:
            require(option_values(arguments, "--model") == [model] and option_values(arguments, "--size") == [request["size"]], f"Executed Nano model/size mismatch for {key}")
            require(option_values(arguments, "--resolution") == [request["quality"]], f"Executed Nano resolution mapping mismatch for {key}")
            for option in ("--background", "--mask-url", "--quality"):
                require(not option_values(arguments, option), f"Executed Nano request contains a GPT-only option for {key}: {option}")
    inputs = actual_inputs(root, support_root, scope, source, execution, request)
    alpha_repair = None
    if derived:
        require(decision.get("source_alpha_repair_performed") is True or (decision.get("rgb_unchanged") is True and decision.get("alpha_matches_resized_source") is True), f"Missing alpha derivation declaration for {key}")
        require(decision.get("alpha_repair_method") == ALPHA_METHOD or review.get("model") in {method + " + " + ALPHA_METHOD, "gpt-image-2.5-flare + " + ALPHA_METHOD}, f"Alpha method declaration mismatch for {key}")
        require(decision.get("parent_output", proof["generation_output"]) == proof["generation_output"] and decision.get("parent_output_sha256") == proof["generation_output_sha256"] and decision.get("parent_task_id") == result["task_id"], f"Alpha parent mismatch for {key}")
        raw = None
        if review.get("alpha_repair_receipt") is not None:
            restore_original_json_bytes(root, support_root, review["alpha_repair_receipt"], review.get("alpha_repair_receipt_sha256"))
            receipt_path = bound_file(root, review["alpha_repair_receipt"], review.get("alpha_repair_receipt_sha256"))
            receipt = read_json(accessible_path(receipt_path))
            if "result" in receipt:
                for field, expected in (("index", approved["index"]), ("source_key_sha256", key), ("attempt", base_attempt), ("parent_output_sha256", proof["generation_output_sha256"]), ("status", "completed"), ("new_image_generation_calls", 0), ("exit_code", 0), ("output", expected_output), ("output_sha256", approved["generated_fullsize_sha256"])):
                    require(receipt.get(field) == expected, f"Alpha receipt mismatch for {key}: {field}")
                if receipt.get("parent_review"):
                    restore_original_json_bytes(root, support_root, receipt["parent_review"], receipt.get("parent_review_sha256"))
                    bound_file(root, receipt["parent_review"], receipt.get("parent_review_sha256"))
                raw = receipt["result"]
            else:
                raw = receipt
        expected_proof = alpha_proof(project_path(root, source["source_png"]), parent_path, output_path)
        require(expected_proof["rgb_unchanged"] and expected_proof["alpha_matches_resized_source"], f"Alpha derivative pixels differ for {key}")
        if raw is not None:
            require(raw.get("method") == ALPHA_METHOD, f"Alpha method mismatch for {key}")
            for field, expected in expected_proof.items():
                require(raw.get(field) == expected, f"Alpha receipt proof mismatch for {key}: {field}")
        for field in ("source_corner_alpha_tl_tr_bl_br", "resized_corner_alpha_tl_tr_bl_br", "output_corner_alpha_tl_tr_bl_br"):
            require(decision.get(field) == expected_proof[field], f"Alpha review proof mismatch for {key}: {field}")
        if "resized_alpha_sha256" in decision:
            require(decision["resized_alpha_sha256"] == expected_proof["resized_alpha_sha256"], f"Alpha review hash mismatch for {key}")
        alpha_repair = {
            "method": ALPHA_METHOD,
            "parent_fullsize_sha256": proof["generation_output_sha256"],
            "source_alpha_png_sha256": source["converted_png_sha256"],
            "resized_alpha_sha256": expected_proof["resized_alpha_sha256"],
            "rgb_unchanged": True,
            "alpha_matches_resized_source": True,
            "generation_task_id": result["task_id"],
            "review_record": review_path,
            "receipt": review.get("alpha_repair_receipt"),
            "receipt_sha256": review.get("alpha_repair_receipt_sha256"),
            "proof_source": "bound-review-evidence-and-direct-pixel-validation",
        }
    else:
        require(decision.get("source_alpha_repair_performed") is False, f"Native RGBA is mislabeled as derived for {key}")
    return {
        "index": approved["index"], "source_sha256": key, "source_assets": source["source_assets"],
        "attempt": approved["approved_attempt"], "task_id": result["task_id"], "method": method + (" + " + ALPHA_METHOD if derived else ""),
        "prompt_file": execution["prompt_file"] if execution is not None else proof["prompt"], "prompt_sha256": proof["prompt_sha256"], "prompt": prompt,
        "request": proof["request"], "request_sha256": proof["request_sha256"], "result": proof["result"], "result_sha256": proof["result_sha256"],
        "execution": execution_relative, "execution_sha256": file_sha256(project_path(root, execution_relative)) if execution_relative else None,
        "recovery": recovery,
        "recovery_status": "archived_request_only_no_execution_record" if execution is None else "direct_completed_execution" if recovery is None else recovery.get("status", "existing_task_recovery_verified"),
        "inputs": inputs, "generated_fullsize_image": master_relative, "generated_fullsize_sha256": approved["generated_fullsize_sha256"],
        "generated_at_utc": result["downloaded_at_utc"], "prepared_at_utc": execution.get("started_at_utc") if execution is not None else None,
        "edit_existing": (execution or {}).get("repair_input_mode") in HD_INPUT_MODES,
        "review": review_path, "review_sha256": approved["review_sha256"], "reviewed_at_utc": review["reviewed_at_utc"], "reviewer": review["reviewer"],
        "evidence": review["review_evidence"], "evidence_sha256": review["review_evidence_sha256"],
        "review_decision": decision, "alpha_repair": alpha_repair,
    }


def build_plan(root=ROOT, support_root=None):
    root = Path(root).resolve()
    support_root = Path(support_root).resolve() if support_root is not None else root
    scope = evidence_json(root, f"{EXPERIMENT}/scope.json")
    progress = evidence_json(root, f"{EXPERIMENT}/progress.json")
    approved = evidence_json(root, f"{EXPERIMENT}/approved-masters.json")
    for body in (scope, progress, approved):
        require(body.get("machine_id") == machine_id(), "HIGH evidence belongs to a different machine")
    require(scope.get("source_count") == progress.get("source_count") == 131, "HIGH scope must contain 131 sources")
    require(len(scope["entries"]) == len(progress["entries"]) == 131, "HIGH scope/progress length mismatch")
    require([row["index"] for row in scope["entries"]] == list(range(1, 132)) == [row["index"] for row in progress["entries"]], "HIGH indices are not exactly 1..131")
    catalog = evidence_json(root, "mod_nailong/data/catalog.json")
    generated = evidence_json(root, GENERATED)
    for source in scope["entries"]:
        assets = [row for row in catalog["assets"] if row["source_sha256"] == source["source_sha256"]]
        require(source["source_assets"] == [row["path"] for row in assets], f"Catalog assets mismatch for {source['source_sha256']}")
        require({tuple(row["size"]) for row in assets} == {tuple(source["source_size"])}, f"Catalog size mismatch for {source['source_sha256']}")
        bound_file(support_root, source["source_png"], source["converted_png_sha256"])
    nonperson_relative = f"{EXPERIMENT}/nonperson-scope-decision.json"
    nonperson = evidence_json(root, nonperson_relative)
    require(progress.get("nonperson_scope_decision") == {"path": nonperson_relative, "sha256": file_sha256(project_path(root, nonperson_relative))}, "Non-person scope binding mismatch")
    require(nonperson.get("decision") == "preserved_original_nonperson_exception" and nonperson.get("machine_id") == machine_id(), "Non-person exception decision mismatch")
    require(nonperson.get("no_image_call_created_for_this_decision") is True and nonperson.get("generated_output_required") is False and nonperson.get("original_assets_retained") is True and nonperson.get("canonical_generated_row_must_not_be_fabricated") is True, "Non-person exception terms changed")
    require({row["index"] for row in nonperson["entries"]} == NONPERSON_INDICES and len(nonperson["entries"]) == 4, "Non-person exceptions must be exactly 78, 125, 129 and 131")
    for exception in nonperson["entries"]:
        index = exception["index"]
        source = scope["entries"][index - 1]
        require(progress["entries"][index - 1]["status"] == "preserved_original_nonperson_exception", f"Missing non-person exception at {index}")
        for field in ("source_sha256", "source_assets", "source_size", "source_png", "source_alpha_extrema"):
            require(source[field] == exception[field], f"Non-person source mismatch at {index}: {field}")
        require(source["converted_png_sha256"] == exception["source_png_sha256"], f"Non-person conversion mismatch at {index}")
        bound_file(support_root, source["source_png"], exception["source_png_sha256"])
        require(exception["source_sha256"] not in generated["portraits"], f"Non-person generated row must not be fabricated at {index}")
    pending = [{"index": row["index"], "source_sha256": row["source_sha256"], "status": row["status"]} for row in progress["entries"] if row["status"] not in {"approved_pending_import", "approved_imported", "preserved_original_nonperson_exception"}]
    approved_count = sum(row["status"] in {"approved_pending_import", "approved_imported"} for row in progress["entries"])
    if pending:
        raise ImportGateError(
            f"HIGH131 import requires 127/127 approved persons; found {approved_count}",
            status="blocked_incomplete_high131", approved_person_sources=approved_count,
            person_source_count=127, preserved_nonperson_exceptions=4,
            pending_sources=pending, production_writes_performed=False,
        )
    expected = {row["source_sha256"] for row in scope["entries"] if row["index"] not in NONPERSON_INDICES}
    require(approved.get("count") == len(approved["entries"]) == len({row["source_sha256"] for row in approved["entries"]}) == 127, "Approved-master count is not 127 unique persons")
    require({row["source_sha256"] for row in approved["entries"]} == expected, "Approved-master sources differ from the 127 persons")
    require([row["index"] for row in approved["entries"]] == sorted(row["index"] for row in approved["entries"]), "Approved masters are not source-ordered")
    entries = [validate_person(root, support_root, scope, progress, row, generated) for row in approved["entries"]]
    return {"schema": "high131-import-plan-v1", "root": str(root), "person_count": 127, "nonperson_count": 4, "entries": entries}


def validate_parent_readback(worktree, parent, plan, readback_path):
    worktree = Path(worktree).resolve()
    candidate = Path(readback_path).resolve()
    candidate.relative_to((ROOT / "runtime").resolve())
    proof = read_json(candidate)
    require(proof.get("schema") == "naiwa-fullsize-git-checkpoint-v1" and proof.get("machine_id") == machine_id(), "Parent readback schema or machine mismatch")
    require(proof.get("commit") == parent, "Parent readback must bind the exact isolated parent commit")
    require(proof.get("verification") == "Remote Git tree blob SHA/size match plus complete anonymous raw PNG download SHA256/size for every output; unchanged blobs may retain their earlier pinned readback commit/time", "Parent proof is not complete original-byte readback")
    index = evidence_json(worktree, "mod_nailong/data/fullsize-files.json")
    require(proof.get("distinct_outputs") == index.get("count") and proof.get("original_png_bytes") == index.get("original_png_bytes"), "Parent proof does not cover the pinned original index")
    outputs = proof.get("outputs", {})
    for entry in plan["entries"]:
        digest = entry["generated_fullsize_sha256"]
        relative = entry["generated_fullsize_image"]
        row = outputs.get(digest, {})
        indexed = index["outputs"].get(digest, {})
        master = bound_file(worktree, relative, digest)
        require(row.get("path") == relative == indexed.get("path"), f"Parent readback path mismatch for {digest}")
        require(row.get("sha256") == digest and row.get("bytes") == indexed.get("bytes") == master.stat().st_size, f"Parent readback bytes mismatch for {digest}")
        require(row.get("method") == "Complete anonymous raw PNG download; SHA256 and byte count", f"Parent readback method mismatch for {digest}")
        require(row.get("readback_commit") == parent or row.get("unchanged_blob_confirmed_at_commit") == parent, f"Parent readback is not current for {digest}")
        require(row.get("git_blob_sha1") == git(worktree, "rev-parse", f"{parent}:{relative}"), f"Parent readback Git blob mismatch for {digest}")
    return {"commit": parent, "verified_original_pngs": len(outputs), "approved_original_pngs": len(plan["entries"])}


def production_import_completed(root, key, review, row=None):
    if row is None:
        row = evidence_json(root, GENERATED)["portraits"].get(key, {})
    from mod_nailong.tools.art_contract import portrait_ready
    marker = row.get("production_import", {})
    required = {
        "schema": "high131-production-import-v1", "source_sha256": key,
        "fullsize_sha256": row.get("generated_fullsize_sha256"),
        "review": review["review"], "review_sha256": review["review_sha256"],
        "approved_attempt": review["attempt"], "task_id": review.get("task_id"),
    }
    try:
        if any(marker.get(field) != value for field, value in required.items()) or not portrait_ready(row):
            return False
        journal = evidence_json(root, row["request_journal"])["attempts"][-1]
        if row.get("method") != journal.get("method") or file_sha256(project_path(root, row["generated_fullsize_image"])) != row["generated_fullsize_sha256"]:
            return False
        if file_sha256(project_path(root, review["review"])) != review["review_sha256"]:
            return False
        return (journal.get("external_task_id") == review.get("task_id") and journal.get("external_review") == review["review"]
                and journal.get("external_review_sha256") == review["review_sha256"] and journal.get("status") == "approved"
                and journal.get("fullsize_sha256") == row["generated_fullsize_sha256"] and journal.get("output_sha256") == row["image_sha256"])
    except (OSError, KeyError, IndexError, TypeError):
        return False


def preserve_new_remote_high(worktree, remote, planned, base, high_keys):
    from mod_nailong.tools.art_contract import portrait_ready

    planned = json.loads(json.dumps(planned))
    preserved = []
    for key in sorted(high_keys):
        if planned.get(key) is not None or remote.get(key) == base.get(key):
            continue
        row = remote.get(key)
        require(isinstance(row, dict) and portrait_ready(row), f"Remote HIGH row is not actually approved: {key}")
        require(row.get("machine_id") == machine_id(), f"Remote HIGH row belongs to another machine: {key}")
        master_relative = row["generated_fullsize_image"]
        master = bound_file(worktree, master_relative, row["generated_fullsize_sha256"])
        journal_relative = row["request_journal"]
        journal_path = bound_file(worktree, journal_relative, file_sha256(project_path(worktree, journal_relative)))
        journal = evidence_json(worktree, journal_relative)
        attempt = journal["attempts"][-1]
        require(attempt.get("status") == "approved" and attempt.get("method", "").startswith("built-in imagegen") and row.get("method", "").startswith("built-in imagegen"), f"Remote HIGH approval method mismatch: {key}")
        require(attempt.get("fullsize_sha256") == row["generated_fullsize_sha256"] and attempt.get("output_sha256") == row["image_sha256"], f"Remote HIGH output binding mismatch: {key}")
        require(attempt.get("prompt") == row["prompt"] and attempt.get("machine_id") == machine_id() and attempt.get("inputs"), f"Remote HIGH request provenance is incomplete: {key}")
        require(journal.get("source_sha256") == key and row.get("source_sha256") == key, f"Remote HIGH source identity mismatch: {key}")
        planned[key] = row
        preserved.append({
            "source_sha256": key, "fullsize_sha256": row["generated_fullsize_sha256"],
            "fullsize_image": master_relative, "master_bytes": master.stat().st_size,
            "journal": journal_relative, "journal_sha256": file_sha256(journal_path),
            "journal_attempt": len(journal["attempts"]), "prompt_sha256": hashlib.sha256(row["prompt"].encode("utf-8")).hexdigest(),
            "canonical_method": row["method"], "journal_method": attempt["method"],
            "preservation": "Remote approved HIGH row retained during rebase; subsequent approved HIGH131 import appends a revision rather than deleting this master or its request history",
        })
    if preserved:
        write_json(ROOT / "runtime/high131-remote-high-preservation.json", {
            "schema": "high131-remote-high-preservation-v1", "machine_id": machine_id(),
            "observed_at_utc": utc_now(), "new_image_generation_calls": 0,
            "scope": "New approved HIGH rows introduced by another executor and absent from the partial HIGH131 plan",
            "entries": preserved,
        })
    return planned, preserved


def merge_shared_mapping(remote, planned, base, high_keys, container):
    require(set(remote) == set(planned) == set(base), "Shared manifest schemas cannot be merged automatically")
    merged = dict(remote)
    rows = {}
    keys = set(remote[container]) | set(planned[container]) | set(base[container])
    for key in keys:
        remote_row = remote[container].get(key)
        planned_row = planned[container].get(key)
        base_row = base[container].get(key)
        if key in high_keys:
            if planned_row is None:
                require(remote_row == base_row, f"Missing planned HIGH evidence must not delete a remote row: {key}")
                rows[key] = remote_row
            else:
                require(remote_row == base_row or remote_row == planned_row, f"Concurrent HIGH row needs explicit reconciliation: {key}")
                rows[key] = planned_row
        else:
            if planned_row != base_row and remote_row != base_row and planned_row != remote_row:
                raise ImportGateError(f"Unrelated shared row changed on both sides: {key}")
            rows[key] = remote_row if remote_row != base_row else planned_row
    merged[container] = rows
    return merged


def _write_import_at_root(plan, worktree):
    from mod_nailong.tools import portraits
    from mod_nailong.tools.art_contract import portrait_ready

    worktree = Path(worktree).resolve()
    require(Path(plan["root"]) == worktree, "Import plan belongs to another worktree")
    portraits.ROOT = worktree
    portraits.MOD = worktree / "mod_nailong"
    portraits.RECORD = worktree / GENERATED
    portraits.CATALOG = worktree / "mod_nailong/data/catalog.json"
    generated = read_json(worktree / GENERATED)
    original_non_high = {key: row for key, row in generated["portraits"].items() if key not in {entry["source_sha256"] for entry in plan["entries"]}}
    queue_path = worktree / QUEUE
    queue = read_json(queue_path)
    retry_counts = {entry["source_sha256"]: queue["sources"].get(entry["source_sha256"], {}).get("retries_used", 0) for entry in plan["entries"]}
    imported = []
    for entry in plan["entries"]:
        key = entry["source_sha256"]
        review_reference = {"review": entry["review"], "review_sha256": entry["review_sha256"], "attempt": entry["attempt"], "task_id": entry["task_id"]}
        row = generated["portraits"].get(key)
        if production_import_completed(worktree, key, review_reference, row):
            continue
        journal_path = worktree / f"mod_nailong/data/generation-requests/{key}.json"
        journal = read_json(journal_path) if journal_path.exists() else {"schema": "naiwa-generation-requests-v1", "source_sha256": key, "attempts": []}
        prior_attempts = json.loads(json.dumps(journal["attempts"]))
        replacement = f"HIGH131 actual external approval {entry['attempt']}" if row else None
        portraits.ingest(key, project_path(worktree, entry["generated_fullsize_image"]), project_path(worktree, entry["prompt_file"]), replacement, entry["method"])
        generated = read_json(worktree / GENERATED)
        row = generated["portraits"][key]
        row["generation_inputs"] = entry["inputs"]
        row["request_journal"] = journal_path.relative_to(worktree).as_posix()
        if entry["alpha_repair"]:
            row["alpha_repair"] = entry["alpha_repair"]
        else:
            row.pop("alpha_repair", None)
        queue["sources"].setdefault(key, {}).update(state="generated_pending_visual_review", output_sha256=row["image_sha256"], generated_at_utc=entry["generated_at_utc"])
        write_json(queue_path, queue)
        attempt = {
            "number": len(journal["attempts"]) + 1, "status": "generated_pending_visual_review", "method": entry["method"],
            "art_direction": "hair-features-v1", "prompt": entry["prompt"], "prompt_file": entry["prompt_file"], "prompt_sha256": entry["prompt_sha256"],
            "inputs": entry["inputs"], "edit_existing": entry["edit_existing"], "machine_id": machine_id(),
            "prepared_at_utc": entry["prepared_at_utc"], "generated_at_utc": entry["generated_at_utc"],
            "fullsize_sha256": entry["generated_fullsize_sha256"], "fullsize_image": entry["generated_fullsize_image"],
            "output": row["image"], "output_sha256": row["image_sha256"],
            "external_task_id": entry["task_id"], "external_execution": entry["execution"], "external_execution_sha256": entry["execution_sha256"],
            "external_request": entry["request"], "external_request_sha256": entry["request_sha256"],
            "external_result": entry["result"], "external_result_sha256": entry["result_sha256"],
            "external_review": entry["review"], "external_review_sha256": entry["review_sha256"],
            "external_evidence": entry["evidence"], "external_evidence_sha256": entry["evidence_sha256"],
            "external_reviewer": entry["reviewer"], "recovery_status": entry["recovery_status"],
        }
        if entry["recovery"] and entry["recovery"]["path"]:
            attempt["external_recovery"] = entry["recovery"]["path"]
            attempt["external_recovery_sha256"] = entry["recovery"]["sha256"]
        if entry["alpha_repair"]:
            attempt["alpha_repair"] = entry["alpha_repair"]
        journal["attempts"].append(attempt)
        write_json(journal_path, journal)
        write_json(worktree / GENERATED, generated)
        portraits.approve([key])
        generated = read_json(worktree / GENERATED)
        row = generated["portraits"][key]
        row.update(
            reviewed_at_utc=entry["reviewed_at_utc"],
            review_method=f"Existing actual SHA-bound manual review: {entry['review']}; reviewer: {entry['reviewer']}",
            production_import={
                "schema": "high131-production-import-v1", "machine_id": machine_id(), "source_sha256": key,
                "fullsize_sha256": entry["generated_fullsize_sha256"], "approved_attempt": entry["attempt"], "task_id": entry["task_id"],
                "review": entry["review"], "review_sha256": entry["review_sha256"], "evidence": entry["evidence"], "evidence_sha256": entry["evidence_sha256"],
                "execution": entry["execution"], "execution_sha256": entry["execution_sha256"], "request": entry["request"], "request_sha256": entry["request_sha256"],
                "imported_at_utc": utc_now(),
            },
        )
        row["collar_fit"].update(reviewed_at_utc=entry["reviewed_at_utc"], review_method=f"Existing collar-fit-v1 manual approval: {entry['review']}")
        journal = read_json(journal_path)
        journal["attempts"][-1].update(reviewed_at_utc=entry["reviewed_at_utc"], review="approved")
        write_json(journal_path, journal)
        require(journal["attempts"][:-1] == prior_attempts, f"Historical request attempts changed for {key}")
        queue["sources"][key].update(
            state="approved_external_alpha_repair" if entry["alpha_repair"] else "approved_external_native_rgba",
            approved_at_utc=entry["reviewed_at_utc"], approved_image_sha256=row["image_sha256"],
            external_task_id=entry["task_id"], external_execution=entry["execution"], external_review=entry["review"],
        )
        if entry["alpha_repair"]:
            queue["sources"][key]["external_art_repair"] = entry["alpha_repair"]
        else:
            queue["sources"][key].pop("external_art_repair", None)
        write_json(worktree / GENERATED, generated)
        write_json(queue_path, queue)
        imported.append(key)
    generated = read_json(worktree / GENERATED)
    require(all(generated["portraits"].get(key) == row for key, row in original_non_high.items()), "An unrelated canonical portrait changed")
    for entry in plan["entries"]:
        key = entry["source_sha256"]
        require(queue["sources"][key].get("retries_used", 0) == retry_counts[key], f"Retry count changed for {key}")
        reference = {"review": entry["review"], "review_sha256": entry["review_sha256"], "attempt": entry["attempt"], "task_id": entry["task_id"]}
        require(production_import_completed(worktree, key, reference, generated["portraits"].get(key)), f"Imported evidence/postcondition mismatch for {key}")
        require(portrait_ready(generated["portraits"][key]), f"Imported portrait is not ready for {key}")
    from runtime import high131_archive_approved, high131_status
    from runtime.high131_checkpoint import copy_stable
    nonperson = read_json(worktree / EXPERIMENT / "nonperson-scope-decision.json")
    for exception in nonperson["entries"]:
        copy_stable(project_path(worktree, exception["source_png"]), worktree / exception["source_png"])
    high131_status.ROOT = worktree
    high131_status.EXPERIMENT = worktree / EXPERIMENT
    high131_archive_approved.ROOT = worktree
    high131_archive_approved.EXPERIMENT = worktree / EXPERIMENT
    high131_status.main()
    high131_archive_approved.main()
    return imported


def write_import(plan, worktree):
    from mod_nailong.tools import portraits
    from runtime import high131_archive_approved, high131_status
    state = [(module, field, getattr(module, field)) for module, fields in (
        (portraits, ("ROOT", "MOD", "RECORD", "CATALOG")),
        (high131_status, ("ROOT", "EXPERIMENT")),
        (high131_archive_approved, ("ROOT", "EXPERIMENT")),
    ) for field in fields]
    try:
        return _write_import_at_root(plan, worktree)
    finally:
        for module, field, value in state:
            setattr(module, field, value)


def git(worktree, *args):
    result = subprocess.run(["git", "-c", "core.longpaths=true", "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args], cwd=worktree, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise ImportGateError(result.stdout + "\n" + result.stderr)
    return result.stdout.strip("\r\n")


def import_paths(plan):
    keys = {entry["source_sha256"] for entry in plan["entries"]}
    return [GENERATED, QUEUE, f"{EXPERIMENT}/progress.json", f"{EXPERIMENT}/approved-masters.json",
            *[f"mod_nailong/assets/portraits/{key}.png" for key in keys],
            *[f"mod_nailong/data/generation-requests/{key}.json" for key in keys]]


def refresh_normalized_receipts(worktree, plan=None):
    allowed = set(import_paths(plan)) if plan is not None else set()
    allowed_statuses = {" M", "??", "M ", "A ", "MM", "AM"}
    changed = [line for line in git(worktree, "status", "--porcelain", "-z").split("\0") if line]
    paths = []
    for line in changed:
        relative = line[3:]
        if line[:2] in allowed_statuses and relative in allowed:
            continue
        require(line[:2] == " M" and relative.startswith(EXPERIMENT + "/") and relative.endswith(".json"), f"Unexpected isolated-worktree change: {line}")
        paths.append(relative)
    if paths:
        git(worktree, "diff", "--quiet", "--", *paths)
        git(worktree, "add", "--renormalize", "--", *paths)
    require(set(git(worktree, "diff", "--cached", "--name-only").splitlines()) <= allowed, "Unexpected staged files after receipt normalization")
    remaining = [line for line in git(worktree, "status", "--porcelain", "-z").split("\0") if line]
    require(all(line[:2] in allowed_statuses and line[3:] in allowed for line in remaining), "Unexpected changes remain after receipt normalization")
    return paths


def stage_and_commit(worktree, plan, message="Import reviewed HIGH131 portraits", partial=False):
    paths = import_paths(plan)
    if partial:
        paths = [relative for relative in paths if accessible_path(Path(worktree) / relative).is_file()]
    changed = set(git(worktree, "status", "--porcelain").splitlines())
    require(all(line[:2] in {" M", "??", "M ", "A ", "MM", "AM"} and line[3:] in paths for line in changed), f"Unexpected files in isolated import: {sorted(changed)[:10]}")
    git(worktree, "add", "--sparse", "--", *paths)
    git(worktree, "diff", "--cached", "--check")
    staged = set(git(worktree, "diff", "--cached", "--name-only").splitlines())
    require(staged <= set(paths), "Import staged an unrelated file")
    git(worktree, "commit", "-m", message)
    return git(worktree, "rev-parse", "HEAD")


def rebase_in_progress(worktree):
    return Path(git(worktree, "rev-parse", "--git-path", "rebase-merge")).exists()


def rebase_import(worktree, original_commit, plan, complete_required=True):
    git(worktree, "fetch", "origin")
    remote = git(worktree, "rev-parse", "origin/master")
    if remote == original_commit and not rebase_in_progress(worktree):
        return original_commit
    try:
        git(worktree, "rebase", "origin/master")
    except ImportGateError:
        conflicts = set(git(worktree, "diff", "--name-only", "--diff-filter=U").splitlines())
        require(conflicts <= {GENERATED, QUEUE}, f"Unrelated import conflict requires manual review: {sorted(conflicts)}")
        for relative, container in ((GENERATED, "portraits"), (QUEUE, "sources")):
            if relative not in conflicts:
                continue
            remote, planned, base = (json.loads(git(worktree, "show", f":{number}:{relative}")) for number in (2, 3, 1))
            if container == "portraits":
                preserved_rows, _ = preserve_new_remote_high(worktree, remote[container], planned[container], base[container], {entry["source_sha256"] for entry in plan["entries"]})
                planned = dict(planned, portraits=preserved_rows)
            merged = merge_shared_mapping(remote, planned, base, {entry["source_sha256"] for entry in plan["entries"]}, container)
            write_json(worktree / relative, merged)
            git(worktree, "add", "--", relative)
        require(not git(worktree, "diff", "--name-only", "--diff-filter=U"), "Shared import conflicts remain unresolved")
        git(worktree, "-c", "core.editor=true", "rebase", "--continue")
    for entry in plan["entries"] if complete_required else []:
        key = entry["source_sha256"]
        reference = {"review": entry["review"], "review_sha256": entry["review_sha256"], "attempt": entry["attempt"], "task_id": entry["task_id"]}
        restore_original_json_bytes(worktree, ROOT, reference["review"], reference["review_sha256"])
        require(production_import_completed(worktree, key, reference), f"Rebase lost an imported HIGH source: {key}")
    final = git(worktree, "rev-parse", "HEAD")
    original_paths = set(git(worktree, "diff", "--name-only", f"{original_commit}^", original_commit).splitlines())
    for relative in original_paths - {GENERATED, QUEUE}:
        require(git(worktree, "rev-parse", f"{original_commit}:{relative}") == git(worktree, "rev-parse", f"{final}:{relative}"), f"Rebase changed a HIGH evidence blob: {relative}")
    return final


def resolve_import_parent(worktree):
    head = git(worktree, "rev-parse", "HEAD")
    recovery_path = ROOT / "runtime/high131-latest-recovery.json"
    if not recovery_path.is_file():
        return head, head
    recovery = read_json(recovery_path)
    if recovery.get("commit") != head:
        return head, head
    require(recovery.get("machine_id") == machine_id(), "Recovery receipt belongs to another machine")
    require(recovery.get("formal_import_complete") is False and recovery.get("status") == "local_recovery_rebased_push_pending", "Recovery receipt is not a pending partial import")
    parent = git(worktree, "rev-parse", "HEAD^")
    require(re.fullmatch(r"[0-9a-f]{40}", parent), "Recovery has no immutable remote parent")
    return head, parent


def main():
    parser = argparse.ArgumentParser(description="Validate and import only completely reviewed HIGH131 evidence; never calls an image API.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--worktree", type=Path)
    parser.add_argument("--batch")
    parser.add_argument("--readback", type=Path)
    args = parser.parse_args()
    receipt = ROOT / "runtime/high131-import-check.json"
    if args.check:
        require(args.worktree is None and args.batch is None and args.readback is None, "--check does not accept a production worktree, batch or readback")
        try:
            plan = build_plan()
        except ImportGateError as error:
            report = {"schema": "high131-import-check-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(), "status": error.report.get("status", "invalid_evidence"), "error": str(error), **error.report}
            write_json(receipt, report)
            print(json.dumps(report, ensure_ascii=False))
            return 2
        report = {"schema": "high131-import-check-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(), "status": "ready_for_isolated_apply", "approved_person_sources": 127, "preserved_nonperson_exceptions": 4, "production_writes_performed": False}
        write_json(receipt, report)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    require(args.worktree is not None and args.batch and re.fullmatch(r"[A-Za-z0-9-]+", args.batch) and args.readback is not None, "--apply requires --worktree, a valid --batch and --readback")
    worktree = args.worktree.resolve()
    worktree.relative_to((ROOT / "runtime").resolve())
    require((worktree / ".git").exists(), "Apply requires an isolated Git worktree")
    import_start_commit, parent = resolve_import_parent(worktree)
    plan = build_plan(worktree, ROOT)
    refresh_normalized_receipts(worktree, plan)
    parent_proof = validate_parent_readback(worktree, parent, plan, args.readback)
    git(worktree, "fetch", "origin")
    require(git(worktree, "rev-parse", "origin/master") == parent, "Fetch/rebase the isolated parent before applying HIGH131")
    imported = write_import(plan, worktree)
    original = stage_and_commit(worktree, plan)
    commit = rebase_import(worktree, original, plan)
    report = {
        "schema": "high131-production-import-receipt-v1", "machine_id": machine_id(), "batch": args.batch,
        "import_start_commit": import_start_commit, "parent_commit": parent, "original_import_commit": original, "commit": commit,
        "approved_person_sources": 127, "preserved_nonperson_exceptions": 4,
        "newly_imported_sources": imported, "status": "committed_push_pending",
        "evidence_root": str(worktree), "new_image_generation_calls": 0,
        "parent_original_readback": parent_proof, "parent_readback_receipt": str(args.readback),
        "formal_game_build_or_runtime_acceptance_claimed": False,
    }
    write_json(ROOT / f"runtime/checkpoint-{args.batch}.json", report)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
