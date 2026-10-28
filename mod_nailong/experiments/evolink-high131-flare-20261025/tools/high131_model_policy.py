from tools.common import ROOT, file_sha256, machine_id, read_json

NANO_MODEL = "gemini-nano-banana-2.1"
NANO_KEY = "889edc5a10979a25b5507640325ac122112474d07a0ca1efe99d067d5d4a5f28"
NANO_ATTEMPT = "external-07"
AUTHORIZATION = "mod_nailong/experiments/evolink-high131-flare-20261025/source65-nano-banana-authorization-20261028.json"
USER_TEXT = '我要求你，对于65，换用 "model": "gemini-nano-banana-2.1",执行任务'
EXPERIMENT = "mod_nailong/experiments/evolink-high131-flare-20261025"


def authorized_nano(root, key, attempt, model):
    if (key, attempt, model) != (NANO_KEY, NANO_ATTEMPT, NANO_MODEL):
        return False
    try:
        body = read_json(root / AUTHORIZATION)
    except (OSError, ValueError, RuntimeError):
        return False
    expected = {
        "schema": "source65-model-authorization-v1",
        "machine_id": machine_id(),
        "user_authorization_text": USER_TEXT,
        "executor": "Kimi",
        "source_index": 65,
        "source_sha256": key,
        "attempt": attempt,
        "model": model,
        "one_new_generation_task": True,
        "actual_calls_must_be_serial": True,
        "new_task_not_old_task_recovery": True,
        "previous_rejected_attempt": "external-05",
        "refused_previous_attempt": "external-06",
        "previous_content_refusal_preserved": True,
        "repair_input_mode": "raw-hd-edit-note-detail-v1",
        "mask_supported": False,
        "mask_parameter_sent": False,
        "background_parameter_sent": False,
        "n_parameter_sent": False,
        "gpt_resolution_parameter_sent": False,
        "quality_from_resolution": "2K",
        "one_image_per_request": True,
        "manual_art_review_required": True,
        "LOW_excluded": True,
        "other_HIGH_routes_unchanged": True,
        "permission_documents_not_modified": True,
    }
    return all(body.get(field) == value for field, value in expected.items())


def require_nano(root, key, attempt=NANO_ATTEMPT, model=NANO_MODEL):
    if not authorized_nano(root, key, attempt, model):
        raise RuntimeError("This source, attempt and model lack the exact source-65 Nano Banana 2.1 authorization")
    return read_json(root / AUTHORIZATION)


def production_method(root, key, attempt, model):
    if model == "gpt-image-2.5-flare":
        return "EvoLink gpt-image-2.5-flare"
    if authorized_nano(root, key, attempt, model):
        return f"EvoLink {model}"
    raise RuntimeError(f"Unsupported model for {key}: {model}")


def retained_previous_refusal(root, key):
    require_nano(root, key)
    experiment = root / EXPERIMENT
    stem = f"{key}-06"
    execution = read_json(experiment / "executions" / f"{stem}.json")
    task = read_json(experiment / "outputs" / f"{stem}.task.json")
    request_path = experiment / "outputs" / f"{stem}.request.json"
    prompt_path = experiment / "outputs" / f"{stem}.prompt.txt"
    detail = read_json(experiment / "executions" / f"{stem}-failure-detail-retrieve2.json")
    retrieval = read_json(experiment / "executions" / f"{stem}-retrieve3.json")
    expected_task = "task-unified-1793026637-5rav7z1v"
    if (
        execution.get("status") != "resume_existing_task_required"
        or execution.get("index") != 65
        or execution.get("source_sha256") != key
        or execution.get("attempt") != "external-06"
        or execution.get("task_id") != expected_task
        or execution.get("output_sha256") is not None
        or execution.get("result") is not None
        or task.get("task_id") != expected_task
        or detail.get("response", {}).get("error", {}).get("code") != "content_policy_violation"
        or detail.get("response", {}).get("id") != expected_task
        or detail.get("result_url_count") != 0
        or retrieval.get("status") != "resume_existing_task_required"
        or retrieval.get("task_id") != expected_task
        or retrieval.get("new_generation_tasks_created") != 0
        or retrieval.get("output_sha256") is not None
        or retrieval.get("result") is not None
        or retrieval.get("request_sha256") != file_sha256(request_path)
        or retrieval.get("prompt_sha256") != file_sha256(prompt_path)
        or (experiment / "outputs" / f"{stem}.png").exists()
        or (experiment / "outputs" / f"{stem}.result.json").exists()
    ):
        raise RuntimeError("The previous external-06 content refusal is not intact and cannot be used to scope the new model task")
    return {
        "task_id": expected_task,
        "provider_error": "content_policy_violation",
        "output_sha256": None,
        "new_generation_tasks_created": 0,
        "old_task_recovery_or_art_approval_claimed": False,
    }
