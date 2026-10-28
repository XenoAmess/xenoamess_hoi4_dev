import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import high131_run_batch as batch
from runtime import high131_hd_proof as hd_proof

ROOT = batch.ROOT
EXPERIMENT = batch.EXPERIMENT
OUTPUTS_DIR = batch.OUTPUTS_DIR
PROMPTS_DIR = batch.PROMPTS_DIR
REPAIR_PATH = EXPERIMENT / "card-repair-preparation.json"
PROGRESS_PATH = EXPERIMENT / "progress.json"
ROUTE_FIELDS = ("model", "size", "background", "resolution", "quality")
PROTECTED_FIELDS = ("source_png", "converted_png_sha256", "image_urls", "ordered_input_sha256")


def attempt_number(value, label="attempt"):
    if not isinstance(value, str):
        raise batch.BatchError("invalid_input", f"{label} must be external-NN")
    match = re.fullmatch(r"external-(\d+)", value)
    if not match:
        raise batch.BatchError("invalid_input", f"{label} must be external-NN: {value}")
    number = int(match.group(1))
    if number < 1 or value != f"external-{number:02}":
        raise batch.BatchError("invalid_input", f"{label} must use zero-padded external-NN form: {value}")
    return number


def output_paths(key, number):
    stem = f"{key}-{number:02}"
    return OUTPUTS_DIR / f"{stem}.png", OUTPUTS_DIR / f"{stem}.result.json"


def completed_output(output, result):
    output_exists = output.exists()
    result_exists = result.exists()
    if not output_exists and not result_exists:
        return None
    if not output.is_file() or not result.is_file():
        raise batch.BatchError(
            "incomplete_result_output",
            f"Output and complete result must both exist; reconcile before any new POST: {output}",
        )
    try:
        result_value = batch.read_json(result)
        if not isinstance(result_value.get("task_id"), str) or not result_value["task_id"]:
            raise RuntimeError("task_id is missing")
        if not isinstance(result_value.get("downloaded_at_utc"), str) or not result_value["downloaded_at_utc"]:
            raise RuntimeError("downloaded_at_utc is missing")
        if result_value.get("png_signature_verified") is not True:
            raise RuntimeError("result does not confirm the PNG signature")
        with output.open("rb") as stream:
            if stream.read(len(batch.PNG_SIGNATURE)) != batch.PNG_SIGNATURE:
                raise RuntimeError("output PNG signature is invalid")
        output_sha = batch.file_sha256(output)
        output_bytes = output.stat().st_size
        if result_value.get("sha256") != output_sha:
            raise RuntimeError("output SHA differs from result.json")
        if result_value.get("bytes") != output_bytes:
            raise RuntimeError("output byte count differs from result.json")
        result_sha = batch.file_sha256(result)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError) as exc:
        raise batch.BatchError(
            "invalid_result_output",
            f"Existing output/result is not complete and verified; no new POST is allowed for {output}: {exc}",
        ) from exc
    return {
        "output_sha256": output_sha,
        "result_sha256": result_sha,
        "result": result_value,
    }


def scan_actual_attempts(key):
    outputs = {}
    results = {}
    for pattern, suffix, destination in (
        (f"{key}-*.png", ".png", outputs),
        (f"{key}-*.result.json", ".result.json", results),
    ):
        for path in OUTPUTS_DIR.glob(pattern):
            match = re.fullmatch(re.escape(key) + r"-(\d+)" + re.escape(suffix), path.name)
            if not match:
                continue
            number = int(match.group(1))
            if match.group(1) != f"{number:02}":
                raise batch.BatchError("invalid_actual_attempt", f"Non-frozen attempt filename requires review: {path}")
            destination[number] = path
    return outputs, results


def later_dispatch_artifacts(key, previous_number):
    found = []
    for directory, suffixes in (
        (OUTPUTS_DIR, ("request.json", "task.json", "prompt.txt")),
        (batch.EXECUTIONS_DIR, ("json",)),
        (batch.LOGS_DIR, ("log",)),
    ):
        for suffix in suffixes:
            for path in directory.glob(f"{key}-*.{suffix}"):
                match = re.match(re.escape(key) + r"-(\d+)(?=[-.]|$)", path.name)
                if not match:
                    continue
                raw_number = match.group(1)
                if len(raw_number) != 2:
                    raise batch.BatchError("invalid_actual_attempt", f"Non-frozen attempt filename requires review: {path}")
                number = int(raw_number)
                if number > previous_number:
                    found.append(path)
    return sorted(found)


def latest_actual_attempt(outputs, results):
    numbers = set(outputs) | set(results)
    return max(numbers) if numbers else None


def progress_latest(state):
    rows = state["progress_entry"].get("attempts_returned")
    if not isinstance(rows, list):
        raise batch.BatchError("invalid_progress", "progress attempts_returned must be a list")
    previous = 0
    for row in rows:
        if not isinstance(row, dict):
            raise batch.BatchError("invalid_progress", "progress contains an invalid attempt record")
        number = attempt_number(row.get("attempt"), "progress attempt")
        if number <= previous:
            raise batch.BatchError("invalid_progress", "progress attempts are duplicated or out of order")
        previous = number
    return (rows[-1], previous) if rows else (None, None)


def validate_progress_record(state, record, number, outputs, results):
    if number not in outputs or number not in results:
        raise batch.BatchError(
            "progress_stale_run_status",
            "progress names an ordinary attempt whose output/result is incomplete; run high131_status.py and reconcile",
        )
    proof = completed_output(outputs[number], results[number])
    expected_output, expected_result = output_paths(state["key"], number)
    if outputs[number] != expected_output or results[number] != expected_result:
        raise batch.BatchError("progress_binding_mismatch", "Actual attempt paths differ from ordinary external-NN naming")
    if record.get("output") != batch.relative_path(expected_output) or record.get("result") != batch.relative_path(expected_result):
        raise batch.BatchError("progress_binding_mismatch", "progress output/result paths differ from the ordinary attempt")
    if record.get("output_sha256") != proof["output_sha256"] or record.get("result_sha256") != proof["result_sha256"]:
        raise batch.BatchError(
            "progress_binding_mismatch",
            "progress SHA binding differs from the actual ordinary output/result; run status and reconcile",
        )
    return proof


def read_review(path, expected_sha, key):
    try:
        body, actual_sha = batch.read_json_with_sha(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError) as exc:
        raise batch.BatchError("review_binding_mismatch", f"Unable to read bound review {path}: {exc}") from exc
    if actual_sha != expected_sha:
        raise batch.BatchError("review_sha256_mismatch", f"Review SHA mismatch: {path}")
    entries = body.get("entries")
    if not isinstance(entries, list):
        raise batch.BatchError("review_binding_mismatch", f"Review entries must be a list: {path}")
    matches = [row for row in entries if isinstance(row, dict) and row.get("source_sha256") == key]
    if len(matches) != 1:
        raise batch.BatchError("review_binding_mismatch", f"Review must contain exactly one decision for {key}: {path}")
    return body, matches[0]


def require_file_sha(path, expected, label):
    try:
        actual = batch.file_sha256(path)
    except OSError as exc:
        raise batch.BatchError("manifest_changed", f"Unable to recheck {label}: {exc}") from exc
    if actual != expected:
        raise batch.BatchError("manifest_changed", f"{label} changed after repair collection; reload before dispatch")


def validate_dispatch_progress(context, state):
    del context
    outputs, results = scan_actual_attempts(state["key"])
    latest_actual = latest_actual_attempt(outputs, results)
    record, latest_progress = progress_latest(state)
    if latest_actual != latest_progress:
        raise batch.BatchError(
            "progress_stale_run_status",
            "Actual ordinary attempts differ from progress.json; run high131_status.py before any repair dispatch",
        )
    if latest_actual != state["previous_number"]:
        raise batch.BatchError(
            "progress_attempt_order_mismatch",
            f"Repair requires actual and progress latest {state['previous_attempt']}; found {latest_actual}; no POST is allowed",
        )
    validate_progress_record(state, record, latest_progress, outputs, results)
    progress = state["progress_entry"]
    current = progress.get("current_review")
    repair = state["repair"]
    if (
        progress.get("status") != "rejected_latest_attempt"
        or progress.get("current_decision") != "rejected_for_production"
        or not isinstance(current, dict)
        or current.get("attempt") != state["previous_attempt"]
        or current.get("decision") != "rejected_for_production"
        or current.get("review") != repair.get("review")
        or current.get("review_sha256") != repair.get("review_sha256")
        or current.get("review_output_sha256") != repair.get("rejected_output_sha256")
    ):
        raise batch.BatchError(
            "progress_review_stale_run_status",
            "progress current_review is not the exact bound rejection; run high131_status.py before dispatch",
        )


def repair_input_contract(context, state):
    original = state["original_entry"]
    mascot = context["scope"]["mascot_reference"]
    source_url = context["release_assets"][state["key"]]["url"]
    repair = state["repair"]
    mode = state.get("repair_input_mode")
    if mode != hd_proof.MASK_NOTE_MODE and (repair.get("mask") is not None or repair.get("mask_url") is not None):
        raise batch.BatchError("repair_input_mismatch", "Mask metadata is only valid for raw-hd-mask-note-v1")
    if mode is None:
        return [original["converted_png_sha256"], mascot["sha256"]], [source_url, mascot["url"]]
    if mode not in hd_proof.HD_INPUT_MODES:
        raise batch.BatchError("repair_input_mismatch", "Unsupported repair input mode")
    commit = repair.get("remote_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise batch.BatchError("remote_input_mismatch", "Raw-HD repair requires a full pinned remote commit")
    digest = repair.get("edit_target_sha256")
    if digest != repair.get("rejected_output_sha256"):
        raise batch.BatchError("rejected_output_binding_mismatch", "Raw-HD edit target must be the exact rejected output")
    master_path = batch.project_path(repair.get("edit_target_image"), batch.ROOT / "mod_nailong/assets/generated_fullsize")
    try:
        proof, index = hd_proof.load_remote_proof(commit, repair.get("remote_readback"), root=batch.ROOT)
        target_url = hd_proof.validate_remote_target(proof, commit, master_path, digest, index=index, root=batch.ROOT)
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        raise batch.BatchError("remote_input_mismatch", str(exc)) from exc
    expected_inputs = [digest, original["converted_png_sha256"], mascot["sha256"]]
    expected_urls = [target_url, source_url, mascot["url"]]
    if mode in (hd_proof.NOTE_DETAIL_MODE, hd_proof.MASK_NOTE_MODE):
        detail = repair.get("note_detail")
        if not isinstance(detail, dict) or detail.get("source_png_sha256") != original["converted_png_sha256"]:
            raise batch.BatchError("repair_input_mismatch", "Source-detail reference is missing or bound to another original")
        detail_path = batch.project_path(detail.get("path"), batch.ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025/review-source-details")
        try:
            detail_url = hd_proof.validate_remote_reference(proof, commit, detail_path, detail.get("sha256"), batch.project_path(original["source_png"], batch.ROOT / "runtime/references"), root=batch.ROOT)
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            raise batch.BatchError("remote_input_mismatch", str(exc)) from exc
        if detail.get("url") != detail_url:
            raise batch.BatchError("repair_input_mismatch", "Source-detail URL differs from the verified pinned reference")
        expected_inputs.append(detail["sha256"])
        expected_urls.append(detail_url)
    if mode == hd_proof.MASK_NOTE_MODE:
        mask = repair.get("mask")
        if not isinstance(mask, dict):
            raise batch.BatchError("repair_input_mismatch", "Mask-note repair lacks its mask binding")
        mask_path = batch.project_path(mask.get("path"), batch.ROOT / hd_proof.NOTE_MASK_DIR)
        try:
            mask_url = hd_proof.validate_remote_mask(
                proof, commit, mask_path, mask.get("sha256"), master_path, digest, root=batch.ROOT,
            )
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            raise batch.BatchError("remote_input_mismatch", str(exc)) from exc
        mask_proof = proof.get("targets", {}).get(mask.get("sha256"))
        if not isinstance(mask_proof, dict):
            raise batch.BatchError("repair_input_mismatch", "Mask proof record is missing")
        if (
            mask.get("url") != mask_url
            or repair.get("mask_url") != mask_url
            or mask.get("target_sha256") != digest
            or mask.get("manifest") != mask_proof.get("mask_manifest")
            or mask.get("manifest_sha256") != mask_proof.get("mask_manifest_sha256")
        ):
            raise batch.BatchError("repair_input_mismatch", "Mask URL, target or visual-review manifest binding differs")
    if repair.get("remote_target_url") != target_url or repair.get("image_urls") != expected_urls or repair.get("ordered_input_sha256") != expected_inputs:
        raise batch.BatchError("repair_input_mismatch", "Raw-HD target, original, mascot and declared reference input binding differs")
    return expected_inputs, expected_urls


def validate_repair_binding(context, state):
    require_file_sha(REPAIR_PATH, context["repair_preparation_sha256"], "card-repair-preparation.json")
    require_file_sha(PROGRESS_PATH, context["progress_sha256"], "progress.json")
    original = state["original_entry"]
    repair = state["repair"]
    entry = state["entry"]
    hd_edit = state.get("repair_input_mode") in hd_proof.HD_INPUT_MODES
    for name in ROUTE_FIELDS:
        if hd_edit and name == "background":
            continue
        if repair.get(name) != original.get(name) or entry.get(name) != original.get(name):
            raise batch.BatchError(
                "repair_route_mismatch",
                f"Repair {name} must inherit the original prepared route for {state['key']}",
            )
    for name in PROTECTED_FIELDS:
        if hd_edit and name in {"image_urls", "ordered_input_sha256"}:
            continue
        if entry.get(name) != original.get(name):
            raise batch.BatchError("repair_input_mismatch", f"Repair must preserve original {name}")
    if hd_edit:
        extrema = original.get("source_alpha_extrema")
        valid_extrema = (
            isinstance(extrema, (list, tuple))
            and len(extrema) == 2
            and all(type(value) in (int, float) and 0 <= value <= 255 for value in extrema)
        )
        if (
            repair.get("background") != "transparent"
            or entry.get("background") != repair.get("background")
            or not valid_extrema
            or extrema[0] == 255
        ):
            raise batch.BatchError("repair_input_mismatch", "Raw-HD note repairs require native transparency and a genuinely transparent source exterior with two numeric alpha extrema")
    if original.get("n") != 1 or entry.get("n") != 1:
        raise batch.BatchError("repair_input_mismatch", "Repair must preserve n=1")

    _, decision = read_review(state["review_path"], repair.get("review_sha256"), state["key"])
    if decision.get("decision") != "rejected_for_production":
        raise batch.BatchError("review_decision_mismatch", "Repair requires rejected_for_production")
    if decision.get("attempt") != state["previous_attempt"]:
        decision_attempt = decision.get("attempt")
        status = (
            "derived_attempt_requires_manual_review"
            if isinstance(decision_attempt, str) and re.match(r"external-\d+-", decision_attempt)
            else "review_attempt_mismatch"
        )
        raise batch.BatchError(
            status,
            f"Review is not bound to ordinary {state['previous_attempt']}; derived alpha/failed attempts cannot authorize a normal repair",
        )
    if decision.get("output_sha256") != repair.get("rejected_output_sha256"):
        raise batch.BatchError("rejected_output_binding_mismatch", "Review and repair rejected output SHA differ")
    previous_output, previous_result = output_paths(state["key"], state["previous_number"])
    decision_output = batch.project_path(decision.get("output"), OUTPUTS_DIR)
    if decision_output != previous_output:
        raise batch.BatchError("rejected_output_binding_mismatch", "Review output is not the ordinary previous attempt PNG")
    previous_proof = completed_output(previous_output, previous_result)
    if previous_proof is None or previous_proof["output_sha256"] != repair.get("rejected_output_sha256"):
        raise batch.BatchError(
            "rejected_output_binding_mismatch",
            "Ordinary previous output/result is missing or does not match the rejected SHA",
        )
    if decision.get("task_id") != previous_proof["result"].get("task_id"):
        raise batch.BatchError("rejected_output_binding_mismatch", "Review task_id differs from the previous result")

    expected_previous_prompt = previous_output.with_name(f"{previous_output.stem}.prompt.txt")
    if state["previous_prompt_path"] != expected_previous_prompt:
        raise batch.BatchError("previous_prompt_mismatch", "previous_prompt is not the ordinary previous client sidecar")
    try:
        previous_prompt = state["previous_prompt_path"].read_bytes()
        previous_prompt.decode("utf-8")
        previous_prompt_sha = batch.sha256_bytes(previous_prompt)
    except (OSError, UnicodeDecodeError) as exc:
        raise batch.BatchError("previous_prompt_mismatch", f"Unable to read previous prompt: {exc}") from exc
    if not previous_prompt.strip() or previous_prompt_sha != repair.get("previous_prompt_sha256"):
        raise batch.BatchError("previous_prompt_mismatch", "previous_prompt content or SHA differs from repair preparation")
    if decision.get("prompt_sha256") != previous_prompt_sha:
        raise batch.BatchError("previous_prompt_mismatch", "Review prompt SHA differs from the actual previous prompt")
    if state["dispatch_gate"]:
        validate_dispatch_progress(context, state)


def repair_artifact_action(state, include_dry_run):
    proof = completed_output(state["output"], state["result"])
    if proof is not None:
        state["completed_proof"] = proof
        state["skip_output"] = state["output"]
        return "skip", "completed_result_output_verified"
    for name, reason in (
        ("request", "pending_request_requires_manual_check"),
        ("task", "pending_task_requires_manual_check"),
        ("client_prompt", "client_prompt_sidecar_requires_manual_check"),
        ("execution", "execution_record_exists_requires_manual_check"),
        ("actual_log", "actual_log_exists_requires_manual_check"),
    ):
        if state[name].exists():
            return "stop", reason
    if include_dry_run and state["dry_run_log"].exists():
        return "stop", "dry_run_log_exists_requires_manual_check"
    return "dispatch", None


def approved_completion(state, record, number, outputs, results):
    progress = state["progress_entry"]
    current = progress.get("current_review")
    if progress.get("current_decision") != "approved_for_production":
        return None
    if not isinstance(current, dict) or current.get("decision") != "approved_for_production":
        raise batch.BatchError("approved_progress_mismatch", "Approved progress lacks an approved current review")
    proof = validate_progress_record(state, record, number, outputs, results)
    if current.get("attempt") != record.get("attempt") or current.get("review_output_sha256") != proof["output_sha256"]:
        raise batch.BatchError("approved_progress_mismatch", "Approved review is not bound to the latest verified output")
    review_path = batch.project_path(current.get("review"), EXPERIMENT)
    _, decision = read_review(review_path, current.get("review_sha256"), state["key"])
    output, _ = output_paths(state["key"], number)
    if (
        decision.get("decision") != "approved_for_production"
        or decision.get("attempt") != record.get("attempt")
        or decision.get("output_sha256") != proof["output_sha256"]
        or batch.project_path(decision.get("output"), OUTPUTS_DIR) != output
        or current.get("review_output") != batch.relative_path(output)
    ):
        raise batch.BatchError("approved_progress_mismatch", "Approved review/output binding is invalid")
    return proof


def repair_state(context, repair):
    if not isinstance(repair, dict):
        raise batch.BatchError("invalid_input", "Repair preparation contains a non-object entry")
    key = repair.get("source_sha256")
    if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key):
        raise batch.BatchError("invalid_input", "Repair has an invalid source_sha256")
    number = attempt_number(repair.get("attempt"), "repair attempt")
    if number < 2:
        raise batch.BatchError("invalid_input", "A repair attempt must be external-02 or later")
    original = context["prepared_entries"].get(key)
    scope_entry = context["scope_entries"].get(key)
    progress_entry = context["progress_entries"].get(key)
    if original is None or scope_entry is None or progress_entry is None:
        raise batch.BatchError("invalid_input", f"Repair source is absent from prepared/scope/progress: {key}")
    if original.get("index") != scope_entry.get("index"):
        raise batch.BatchError("invalid_input", f"Prepared/scope index mismatch for {key}")
    stem = f"{key}-{number:02}"
    prompt_path = batch.project_path(repair.get("prompt_file"), PROMPTS_DIR)
    output = batch.project_path(repair.get("output"), OUTPUTS_DIR)
    if prompt_path.stem != stem or output.stem != stem or output.suffix.lower() != ".png":
        raise batch.BatchError("invalid_input", f"Repair prompt/output must use the frozen {stem} stem")
    previous_number = number - 1
    previous_attempt = f"external-{previous_number:02}"
    previous_prompt_path = batch.project_path(repair.get("previous_prompt"), OUTPUTS_DIR)
    review_path = batch.project_path(repair.get("review"), EXPERIMENT)
    mode = repair.get("repair_input_mode")
    if mode is not None and mode not in hd_proof.HD_INPUT_MODES:
        raise batch.BatchError("repair_input_mismatch", f"Unsupported repair input mode: {mode}")
    entry = {
        **original,
        "prompt_file": repair.get("prompt_file"),
        "prompt_sha256": repair.get("prompt_sha256"),
        "output": repair.get("output"),
        "attempt": repair.get("attempt"),
    }
    if mode is not None:
        entry.update({
            "image_urls": repair.get("image_urls"),
            "ordered_input_sha256": repair.get("ordered_input_sha256"),
            "background": repair.get("background"),
        })
    if mode == hd_proof.MASK_NOTE_MODE:
        entry["mask_url"] = repair.get("mask_url")
    state_extras = {"repair_input_mode": mode} if mode is not None else {}
    if mode is not None:
        state_extras.update({name: repair.get(name) for name in ("edit_target_image", "edit_target_sha256", "remote_commit", "remote_readback")})
    if mode in (hd_proof.NOTE_DETAIL_MODE, hd_proof.MASK_NOTE_MODE):
        state_extras["note_detail"] = repair.get("note_detail")
    if mode == hd_proof.MASK_NOTE_MODE:
        state_extras.update({"mask": repair.get("mask"), "mask_url": repair.get("mask_url")})
    return {
        "entry": entry,
        **state_extras,
        "input_validation": repair_input_contract,
        "original_entry": original,
        "repair": repair,
        "scope_entry": scope_entry,
        "progress_entry": progress_entry,
        "index": original["index"],
        "key": key,
        "stem": stem,
        "previous_number": previous_number,
        "previous_attempt": previous_attempt,
        "prompt_path": prompt_path,
        "output": output,
        "request": output.with_name(f"{stem}.request.json"),
        "task": output.with_name(f"{stem}.task.json"),
        "result": output.with_name(f"{stem}.result.json"),
        "client_prompt": output.with_name(f"{stem}.prompt.txt"),
        "dry_run_log": batch.LOGS_DIR / f"{stem}-dryrun.log",
        "actual_log": batch.LOGS_DIR / f"{stem}.log",
        "execution": batch.EXECUTIONS_DIR / f"{stem}.json",
        "history_logs": (),
        "history_executions": (),
        "previous_prompt_path": previous_prompt_path,
        "review_path": review_path,
        "repair_preparation": batch.relative_path(REPAIR_PATH),
        "repair_preparation_sha256": context["repair_preparation_sha256"],
        "review": batch.relative_path(review_path),
        "review_sha256": repair.get("review_sha256"),
        "rejected_output_sha256": repair.get("rejected_output_sha256"),
        "artifact_action": repair_artifact_action,
        "frozen_validator": validate_repair_binding,
        "dispatch_gate": False,
    }


def skip_row(state, reason):
    proof = state.get("completed_proof") or {}
    row = {
        **batch.identity(state),
        "attempt": state["entry"].get("attempt"),
        "reason": reason,
        "output_sha256": proof.get("output_sha256"),
        "result_sha256": proof.get("result_sha256"),
    }
    if state.get("skip_output") is not None:
        row["output"] = batch.relative_path(state["skip_output"])
    if state.get("approved_attempt") is not None:
        row["approved_attempt"] = state["approved_attempt"]
    return row


def failure_row(context, repair, state, status, message):
    if state is not None:
        row = {**batch.identity(state), "attempt": state["entry"].get("attempt")}
    else:
        key = repair.get("source_sha256") if isinstance(repair, dict) else None
        original = context["prepared_entries"].get(key) if isinstance(key, str) else None
        row = {
            "index": original.get("index") if original else None,
            "source_sha256": key,
            "attempt": repair.get("attempt") if isinstance(repair, dict) else None,
        }
    row.update(status=status, error=message)
    return row


def load_repair_context():
    context = batch.load_context()
    try:
        preparation, preparation_sha = batch.read_json_with_sha(REPAIR_PATH)
        progress, progress_sha = batch.read_json_with_sha(PROGRESS_PATH)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise batch.BatchError("invalid_input", f"Unable to read repair preparation/progress: {exc}") from exc
    if preparation.get("schema") != "naiwa-evolink-high131-card-repair-preparation-v1":
        raise batch.BatchError("invalid_input", "Unexpected card repair preparation schema")
    if progress.get("schema") != "naiwa-evolink-high131-progress-v1":
        raise batch.BatchError("invalid_input", "Unexpected progress schema; run high131_status.py")
    entries = preparation.get("entries")
    if not isinstance(entries, list):
        raise batch.BatchError("invalid_input", "Repair preparation entries must be a list")
    context.update({
        "repair_entries": entries,
        "repair_preparation_sha256": preparation_sha,
        "progress_sha256": progress_sha,
        "scope_entries": batch.unique_rows(context["scope"].get("entries"), "scope entries"),
        "progress_entries": batch.unique_rows(progress.get("entries"), "progress entries"),
    })
    return context


def unresolved_hold(state):
    execution, execution_sha = batch.read_json_with_sha(state["execution"])
    request_sha = batch.file_sha256(state["request"])
    valid = (
        execution.get("status") == "failed"
        and execution.get("index") == state["index"]
        and execution.get("source_sha256") == state["key"]
        and execution.get("attempt") == state["entry"]["attempt"]
        and execution.get("task_id") is None
        and execution.get("output_sha256") is None
        and execution.get("result") is None
        and isinstance(execution.get("started_at_utc"), str)
        and isinstance(execution.get("finished_at_utc"), str)
        and bool(execution.get("error"))
        and not state["task"].exists()
        and not state["output"].exists()
        and not state["result"].exists()
    )
    if not valid:
        raise batch.BatchError(
            "invalid_unresolved_repair_hold",
            "A repair hold requires a finished failed execution with no task ID, output or result and matching retained request",
        )
    return {
        **batch.identity(state),
        "attempt": state["entry"]["attempt"],
        "reason": "unresolved_repair_execution_hold_retained",
        "execution": batch.relative_path(state["execution"]),
        "execution_sha256": execution_sha,
        "request_sha256": request_sha,
        "completion_claimed": False,
        "retry_or_resume_attempted": False,
    }


def authorized_repost_hold(state):
    hold = unresolved_hold(state)
    previous_execution = batch.read_json(state["execution"])
    number = attempt_number(state["entry"]["attempt"]) + 1
    attempt = f"external-{number:02}"
    authorization_path = batch.EXPERIMENT / "authorized-repost-20261028.json"
    authorization = batch.read_json(authorization_path)
    relative_authorization = batch.relative_path(authorization_path)
    if (
        authorization.get("schema") != "high131-authorized-repost-v1"
        or authorization.get("machine_id") != batch.machine_id()
        or authorization.get("allowed_new_attempts", {}).get(str(state["index"])) != attempt
        or authorization.get("one_new_attempt_per_source") is not True
        or authorization.get("preserve_full_prompt_input_order_bytes_and_route") is not True
        or authorization.get("executor") != "Kimi"
    ):
        raise batch.BatchError("unresolved_repost_requires_reconciliation", "No exact user-authorized repost covers this unresolved request")
    stem = f"{state['key']}-{number:02}"
    execution_path = state["execution"].with_name(stem + ".json")
    request_path = state["request"].with_name(stem + ".request.json")
    result_path = state["result"].with_name(stem + ".result.json")
    output_path = state["output"].with_name(stem + ".png")
    execution = batch.read_json(execution_path)
    request = batch.read_json(request_path)
    proof = completed_output(output_path, result_path)
    if proof is None:
        raise batch.BatchError("authorized_repost_result_missing", "The explicitly authorized repost lacks its completed returned output")
    expected = {
        "index": state["index"], "source_sha256": state["key"], "attempt": attempt,
        "status": "completed", "repost_authorization": relative_authorization,
        "previous_attempt": state["entry"]["attempt"],
        "previous_execution": batch.relative_path(state["execution"]),
        "previous_execution_sha256": hold["execution_sha256"],
        "previous_request": batch.relative_path(state["request"]),
        "previous_request_sha256": hold["request_sha256"],
        "new_attempt_not_old_task_recovery": True,
        "possible_duplicate_billing_acknowledged": True,
        "new_generation_tasks_created": 1, "one_new_attempt_limit": 1,
        "prompt_sha256": previous_execution.get("prompt_sha256"),
        "ordered_input_sha256": previous_execution.get("ordered_input_sha256"),
        "output": batch.relative_path(output_path),
        "output_sha256": proof["output_sha256"], "result": proof["result"],
        "task_id": proof["result"]["task_id"],
    }
    for field, value in expected.items():
        if execution.get(field) != value:
            raise batch.BatchError("authorized_repost_binding_mismatch", f"Authorized repost field differs: {field}")
    if batch.file_sha256(request_path) != hold["request_sha256"] or request != batch.read_json(state["request"]):
        raise batch.BatchError("authorized_repost_binding_mismatch", "The authorized repost changed the original request")
    return {
        **hold,
        "reason": "authorized_repost_returned_historical_request_remains_unresolved",
        "authorized_repost_receipt": relative_authorization,
        "authorized_repost_receipt_sha256": batch.file_sha256(authorization_path),
        "authorized_repost_attempt": attempt,
        "authorized_repost_execution": batch.relative_path(execution_path),
        "authorized_repost_execution_sha256": batch.file_sha256(execution_path),
        "authorized_repost_task_id": proof["result"]["task_id"],
        "authorized_repost_output_sha256": proof["output_sha256"],
        "historical_task_id_not_fabricated": True,
        "historical_output_or_old_task_recovery_claimed": False,
        "new_generation_tasks_created_by_this_reconciliation": 0,
    }


def collect_repairs(context, limit, only_indices=None, acknowledged_holds=None):
    acknowledged_holds = acknowledged_holds or set()
    selected = []
    skipped = []
    failed = []
    seen = set()
    for repair in context["repair_entries"]:
        state = None
        try:
            if not isinstance(repair, dict):
                raise batch.BatchError("invalid_input", "Repair preparation contains a non-object entry")
            identity = (repair.get("source_sha256"), repair.get("attempt"))
            if not all(isinstance(value, str) for value in identity):
                raise batch.BatchError("invalid_input", "Repair source/attempt must be strings")
            if identity in seen:
                raise batch.BatchError("invalid_input", f"Duplicate repair source/attempt: {identity}")
            seen.add(identity)
            state = repair_state(context, repair)
            if only_indices is not None and state["index"] not in only_indices | acknowledged_holds:
                continue
            action, reason = batch.artifact_action(state, include_dry_run=True)
            if action == "skip":
                skipped.append(skip_row(state, reason))
                continue
            if action == "stop":
                if reason == "pending_request_requires_manual_check":
                    skipped.append(unresolved_hold(state) if state["index"] in acknowledged_holds else authorized_repost_hold(state))
                    continue
                raise batch.BatchError(reason, batch.stop_message(reason))

            outputs, results = scan_actual_attempts(state["key"])
            latest_actual = latest_actual_attempt(outputs, results)
            record, latest_progress = progress_latest(state)
            pending_artifacts = later_dispatch_artifacts(state["key"], state["previous_number"])
            if (
                latest_actual is not None
                and latest_actual > state["previous_number"]
                or latest_progress is not None
                and latest_progress > state["previous_number"]
                or pending_artifacts
            ):
                if latest_actual != latest_progress:
                    raise batch.BatchError(
                        "progress_stale_run_status",
                        "Actual and progress attempts differ at/after the repair target; run high131_status.py and reconcile",
                    )
                proof = approved_completion(state, record, latest_progress, outputs, results)
                if proof is not None and not later_dispatch_artifacts(state["key"], latest_progress):
                    state["completed_proof"] = proof
                    state["skip_output"], _ = output_paths(state["key"], latest_progress)
                    state["approved_attempt"] = record.get("attempt")
                    skipped.append(skip_row(state, "approved_attempt_verified"))
                    continue
                raise batch.BatchError(
                    "existing_or_later_attempt_requires_manual_check",
                    "Target or a later attempt exists without verified completion/approval; reconcile without a new POST"
                    + (f"; first pending artifact: {pending_artifacts[0]}" if pending_artifacts else ""),
                )
            state["dispatch_gate"] = True
            batch.validate_frozen_entry(context, state)
            selected.append(state)
            if len(selected) == limit:
                break
        except batch.BatchError as exc:
            failed.append(failure_row(context, repair, state, exc.status, str(exc)))
            break
        except (OSError, ValueError, RuntimeError) as exc:
            failed.append(failure_row(context, repair, state, "invalid_input", f"{type(exc).__name__}: {exc}"))
            break
    return selected, skipped, failed


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run SHA-bound HIGH131 card repairs serially, with no automatic repost or task resume.",
    )
    parser.add_argument("--limit", required=True, type=batch.limit_argument, help="Maximum new actual repair calls (1..8)")
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Only validate and list candidates; do not invoke the client, read credentials, access the network, or write logs",
    )
    parser.add_argument("--index", action="append", type=int, help="Only process this original scope index; repeat for multiple indices")
    parser.add_argument("--acknowledge-hold", action="append", type=int, default=[], help="Retain a verified unresolved repair execution as held, never completed; requires --index")
    args = parser.parse_args(argv)
    if args.acknowledge_hold and not args.index:
        parser.error("--acknowledge-hold requires at least one explicit --index")
    if set(args.acknowledge_hold) & set(args.index or []):
        parser.error("An index cannot be both dispatched and acknowledged as an unresolved hold")
    if args.index and any(index < 1 for index in args.index + args.acknowledge_hold):
        parser.error("Scope indices must be positive")
    return args


def main():
    args = parse_args()
    completed = []
    skipped = []
    failed = []
    selected = []
    try:
        context = load_repair_context()
        selected, skipped, failed = collect_repairs(
            context,
            args.limit,
            only_indices=set(args.index) if args.index else None,
            acknowledged_holds=set(args.acknowledge_hold),
        )
    except batch.BatchError as exc:
        failed.append({"status": exc.status, "error": str(exc)})
    except (OSError, ValueError, RuntimeError) as exc:
        failed.append({"status": "invalid_input", "error": str(exc)})

    if args.collect_only or failed:
        batch.emit_summary(args.collect_only, completed, skipped, failed, selected)
        return 1 if failed else 0

    for state in selected:
        try:
            outcome, detail = batch.dispatch_one(context, state)
        except batch.BatchError as exc:
            failed.append({**batch.identity(state), "attempt": state["entry"].get("attempt"), "status": exc.status, "error": str(exc)})
            break
        except Exception as exc:
            status = "resume_existing_task_required" if state["task"].exists() else "batch_execution_failed"
            failed.append({
                **batch.identity(state),
                "attempt": state["entry"].get("attempt"),
                "status": status,
                "error": f"{type(exc).__name__}: {exc}",
            })
            break
        if outcome == "skip":
            skipped.append(skip_row(state, detail))
            continue
        completed.append({
            **batch.identity(state),
            "attempt": state["entry"].get("attempt"),
            "output_sha256": detail,
            "execution": batch.relative_path(state["execution"]),
        })

    batch.emit_summary(False, completed, skipped, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
