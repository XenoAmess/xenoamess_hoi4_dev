import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import high131_hd_proof as hd_proof
from runtime import high131_model_policy as policy
from runtime import high131_run_batch as batch
from runtime import high131_run_repairs as repairs
from tools.common import file_sha256, machine_id, utc_now


def prepare():
    context = repairs.load_repair_context()
    matches = [row for row in context["repair_entries"] if row.get("source_sha256") == policy.NANO_KEY and row.get("attempt") == policy.NANO_ATTEMPT]
    if len(matches) != 1:
        raise batch.BatchError("invalid_nano_preparation", "Expected exactly one source-65 external-07 preparation")
    repair = matches[0]
    state = repairs.repair_state(context, repair)
    state["dispatch_gate"] = True
    return context, state


def validate(context, state):
    repair = state["repair"]
    entry = state["entry"]
    key = state["key"]
    if state["index"] != 65 or key != policy.NANO_KEY or entry.get("attempt") != policy.NANO_ATTEMPT:
        raise batch.BatchError("invalid_nano_scope", "Only source-65 external-07 is authorized for this runner")
    authorization = policy.require_nano(batch.ROOT, key, entry.get("attempt"), entry.get("model"))
    previous_refusal = policy.retained_previous_refusal(batch.ROOT, key)
    if repair.get("model_authorization") != policy.AUTHORIZATION or state.get("repair_input_mode") != hd_proof.NOTE_DETAIL_MODE:
        raise batch.BatchError("invalid_nano_scope", "The exact model authorization and four-input note-detail mode are required")
    if state["previous_attempt"] != "external-05" or state["previous_number"] != 5:
        raise batch.BatchError("invalid_nano_parent", "The new model edit must be based on the actual rejected external-05, not refused external-06")
    if repair.get("mask") is not None or repair.get("mask_url") is not None or entry.get("mask_url") is not None:
        raise batch.BatchError("invalid_nano_protocol", "Nano Banana 2.1 does not accept the GPT mask parameter")
    if authorization.get("previous_rejected_output_sha256") != repair.get("rejected_output_sha256"):
        raise batch.BatchError("invalid_nano_parent", "The rejected raw-HD target differs from the user-authorized source-65 target")
    if authorization.get("size") != entry.get("size") or authorization.get("quality_from_resolution") != entry.get("resolution"):
        raise batch.BatchError("invalid_nano_protocol", "The authorized size or resolution mapping differs")
    protocol = repair.get("protocol")
    if protocol != {
        "quality_from_resolution": "2K", "background_parameter_sent": False,
        "n_parameter_sent": False, "gpt_resolution_parameter_sent": False,
        "mask_parameter_sent": False, "one_image_per_request": True,
    }:
        raise batch.BatchError("invalid_nano_protocol", "The actual protocol boundary differs from the authorized Nano route")
    repairs.validate_repair_binding(context, state)
    expected_inputs, expected_urls = repairs.repair_input_contract(context, state)
    if len(expected_urls) != 4 or entry.get("image_urls") != expected_urls or entry.get("ordered_input_sha256") != expected_inputs:
        raise batch.BatchError("invalid_nano_inputs", "The four ordered input URLs and SHA256 values differ")
    original = state["original_entry"]
    if file_sha256(batch.project_path(original["source_png"])) != original["converted_png_sha256"]:
        raise batch.BatchError("invalid_nano_inputs", "Original source bytes changed")
    mascot = context["scope"]["mascot_reference"]
    if file_sha256(batch.project_path(mascot["path"])) != mascot["sha256"]:
        raise batch.BatchError("invalid_nano_inputs", "Mascot reference bytes changed")
    if file_sha256(state["prompt_path"]) != entry.get("prompt_sha256"):
        raise batch.BatchError("invalid_nano_prompt", "Frozen prompt SHA differs")
    command = [
        sys.executable, str(batch.CLIENT_PATH),
        "--prompt-file", str(state["prompt_path"]), "--output", str(state["output"]),
        "--model", policy.NANO_MODEL, "--size", entry["size"], "--resolution", entry["resolution"],
    ]
    for url in expected_urls:
        command.extend(("--image-url", url))
    parameters = {
        "model": policy.NANO_MODEL, "size": entry["size"],
        "image_urls": expected_urls, "quality": entry["resolution"],
    }
    if any(field in parameters for field in ("background", "n", "resolution", "mask_url")):
        raise batch.BatchError("invalid_nano_protocol", "GPT-only fields leaked into the Nano request")
    return command, parameters, previous_refusal


def main():
    parser = argparse.ArgumentParser(description="Run only the explicitly authorized source-65 external-07 Nano Banana 2.1 task")
    parser.add_argument("--collect-only", action="store_true")
    args = parser.parse_args()
    try:
        context, state = prepare()
        command, parameters, previous_refusal = validate(context, state)
        action, reason = repairs.repair_artifact_action(state, include_dry_run=True)
        if action != "dispatch":
            raise batch.BatchError(reason or "existing_nano_artifacts", "Existing source-65 external-07 artifacts require reconciliation; no new POST")
        if args.collect_only:
            print(json.dumps({
                "collect_only": True, "candidate": {
                    "index": 65, "source_sha256": state["key"], "attempt": policy.NANO_ATTEMPT,
                    "model": policy.NANO_MODEL, "prompt_sha256": state["entry"]["prompt_sha256"],
                    "ordered_input_sha256": state["entry"]["ordered_input_sha256"],
                    "parameters": parameters, "previous_content_refusal": previous_refusal,
                    "new_generation_tasks_created": 0,
                },
            }, ensure_ascii=True))
            return 0
        free_bytes = batch.require_disk_space()
        if batch.run_to_log(command + ["--dry-run"], state["dry_run_log"]) != 0:
            raise batch.BatchError("dry_run_failed", "Nano dry-run failed; no generation POST was made")
        dry_run = batch.read_json(state["dry_run_log"])
        if (
            dry_run.get("status") != "validated_without_network_or_writes"
            or dry_run.get("endpoint") != batch.GENERATIONS_URL
            or dry_run.get("prompt_sha256") != state["entry"]["prompt_sha256"]
            or dry_run.get("parameters") != parameters
            or Path(dry_run.get("output", "")).resolve() != state["output"]
        ):
            raise batch.BatchError("dry_run_validation_failed", "Nano dry-run does not match the frozen request")
        if validate(context, state)[:2] != (command, parameters):
            raise batch.BatchError("frozen_input_mismatch", "Nano inputs changed between validation and actual dispatch")
        action, reason = repairs.repair_artifact_action(state, include_dry_run=False)
        if action != "dispatch":
            raise batch.BatchError(reason or "existing_nano_artifacts", "Actual Nano artifacts appeared before dispatch; no new POST")
        record = {
            "schema": "naiwa-evolink-high131-execution-v1",
            "machine_id": machine_id(), "index": 65, "source_sha256": state["key"],
            "attempt": policy.NANO_ATTEMPT, "status": "running", "started_at_utc": utc_now(),
            "finished_at_utc": None, "exit_code": None,
            "executable": sys.executable, "arguments": command[1:],
            "prompt_file": batch.relative_path(state["prompt_path"]), "prompt_sha256": state["entry"]["prompt_sha256"],
            "ordered_input_sha256": state["entry"]["ordered_input_sha256"],
            "output": batch.relative_path(state["output"]), "output_sha256": None,
            "task_id": None, "result": None,
            "log": batch.relative_path(state["actual_log"]), "dry_run_log": batch.relative_path(state["dry_run_log"]),
            "prepared_sha256": context["prepared_sha256"], "scope_sha256": context["scope_sha256"],
            "input_release_sha256": context["input_release_sha256"], "disk_free_bytes_c_before_actual": free_bytes,
            "repair_preparation": batch.relative_path(repairs.REPAIR_PATH), "repair_preparation_sha256": context["repair_preparation_sha256"],
            "review": state["review"], "review_sha256": state["review_sha256"],
            "rejected_output_sha256": state["rejected_output_sha256"],
            "repair_input_mode": state["repair_input_mode"], "edit_target_image": state["edit_target_image"],
            "edit_target_sha256": state["edit_target_sha256"], "remote_commit": state["remote_commit"],
            "remote_readback": state["remote_readback"], "note_detail": state["note_detail"],
            "model_authorization": policy.AUTHORIZATION, "protocol": state["repair"]["protocol"],
            "previous_content_refusal": previous_refusal, "new_task_not_old_task_recovery": True,
            "error": None,
        }
        batch.write_json_new(state["execution"], record)
        try:
            returncode = batch.run_to_log(command, state["actual_log"])
        except batch.BatchError as exc:
            record["finished_at_utc"] = utc_now()
            record["task_id"] = batch.readable_task_id(state["task"])
            record["status"] = "resume_existing_task_required" if record["task_id"] or state["task"].exists() else "failed"
            record["error"] = str(exc)
            batch.replace_execution_json(state["execution"], record)
            raise
        record["finished_at_utc"] = utc_now()
        record["exit_code"] = returncode
        output_sha = batch.finish_actual_execution(record, state, returncode)
        print(json.dumps({
            "status": "completed", "index": 65, "attempt": policy.NANO_ATTEMPT,
            "model": policy.NANO_MODEL, "task_id": record["task_id"], "output_sha256": output_sha,
            "execution": batch.relative_path(state["execution"]),
        }, ensure_ascii=True))
        return 0
    except batch.BatchError as exc:
        print(json.dumps({"status": exc.status, "error": str(exc), "new_generation_retry_attempted": False}, ensure_ascii=True))
        return 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "invalid_nano_execution", "error": f"{type(exc).__name__}: {exc}", "new_generation_retry_attempted": False}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
