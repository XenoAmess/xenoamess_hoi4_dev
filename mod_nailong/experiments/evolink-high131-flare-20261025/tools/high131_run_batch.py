import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"
PREPARED_PATH = EXPERIMENT / "prepared.json"
SCOPE_PATH = EXPERIMENT / "scope.json"
RELEASE_PATH = EXPERIMENT / "input-release.json"
PROMPTS_DIR = EXPERIMENT / "prompts"
OUTPUTS_DIR = EXPERIMENT / "outputs"
LOGS_DIR = EXPERIMENT / "logs"
EXECUTIONS_DIR = EXPERIMENT / "executions"
CLIENT_PATH = ROOT / "skills/evolink-imagegen/scripts/evolink_image.py"
GENERATIONS_URL = "https://api.evolink.ai/v1/images/generations"
MINIMUM_FREE_BYTES = 60 * 1024 ** 3
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class BatchError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def machine_id():
    explicit = os.environ.get("XAR_CK3_MACHINE_ID")
    if explicit:
        return re.sub(r"[^a-z0-9]+", "-", explicit.lower()).strip("-")[:64]
    if os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            token = "windows-machine-guid:" + winreg.QueryValueEx(key, "MachineGuid")[0]
    else:
        source = next((path for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")) if path.exists()), None)
        token = "machine-id:" + source.read_text().strip() if source else "node:" + platform.node()
    host = re.sub(r"[^a-z0-9]+", "-", platform.node().lower()).strip("-")[:32].rstrip("-")
    return host + "-" + sha256_bytes(token.encode())[:10]


def read_json_with_sha(path):
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise BatchError("invalid_input", f"Expected a JSON object: {path}")
    return value, sha256_bytes(raw)


def read_json(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object: {path}")
    return value


def relative_path(path):
    return path.relative_to(ROOT).as_posix()


def project_path(value, allowed_directory=None):
    if not isinstance(value, str) or not value:
        raise BatchError("invalid_input", "Manifest paths must be non-empty strings")
    supplied = Path(value)
    if supplied.is_absolute() or supplied.drive:
        raise BatchError("invalid_input", f"Manifest path must be repository-relative: {value}")
    path = (ROOT / supplied).resolve()
    try:
        path.relative_to(ROOT)
        if allowed_directory is not None:
            path.relative_to(allowed_directory.resolve())
    except ValueError:
        raise BatchError("invalid_input", f"Manifest path escapes its authorized directory: {value}") from None
    return path


def unique_rows(rows, label):
    if not isinstance(rows, list):
        raise BatchError("invalid_input", f"{label} must be a list")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("source_sha256"), str):
            raise BatchError("invalid_input", f"{label} contains an invalid entry")
        key = row["source_sha256"]
        if key in result:
            raise BatchError("invalid_input", f"Duplicate source in {label}: {key}")
        result[key] = row
    return result


def load_context():
    try:
        prepared, prepared_sha = read_json_with_sha(PREPARED_PATH)
        scope, scope_sha = read_json_with_sha(SCOPE_PATH)
        release, release_sha = read_json_with_sha(RELEASE_PATH)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BatchError("invalid_input", f"Unable to read frozen batch inputs: {exc}") from exc
    if prepared.get("scope_sha256") != scope_sha:
        raise BatchError("manifest_binding_mismatch", "prepared.json does not match scope.json")
    if prepared.get("input_release_sha256") != release_sha:
        raise BatchError("manifest_binding_mismatch", "prepared.json does not match input-release.json")
    if release.get("scope_sha256") != scope_sha:
        raise BatchError("manifest_binding_mismatch", "input-release.json does not match scope.json")
    release_identity = release.get("release")
    if not isinstance(release_identity, dict) or release_identity.get("tag") != scope.get("source_release_tag"):
        raise BatchError("manifest_binding_mismatch", "Input release tag does not match the frozen scope")
    return {
        "prepared": prepared,
        "scope": scope,
        "release": release,
        "prepared_sha256": prepared_sha,
        "scope_sha256": scope_sha,
        "input_release_sha256": release_sha,
        "prepared_entries": unique_rows(prepared.get("entries"), "prepared entries"),
        "release_assets": unique_rows(release.get("assets"), "input release assets"),
    }


def require_context_unchanged(context):
    bindings = (
        ("prepared.json", PREPARED_PATH, context["prepared_sha256"]),
        ("scope.json", SCOPE_PATH, context["scope_sha256"]),
        ("input-release.json", RELEASE_PATH, context["input_release_sha256"]),
    )
    for label, path, expected in bindings:
        try:
            actual = file_sha256(path)
        except OSError as exc:
            raise BatchError("manifest_changed", f"Unable to recheck {label}: {exc}") from exc
        if actual != expected:
            raise BatchError("manifest_changed", f"{label} changed after batch collection; reload before dispatch")


def entry_state(entry, scope_entry):
    key = entry.get("source_sha256")
    if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key):
        raise BatchError("invalid_input", "Candidate has an invalid source_sha256")
    if key != scope_entry.get("source_sha256") or entry.get("index") != scope_entry.get("index"):
        raise BatchError("invalid_input", f"Candidate identity does not match scope order: {key}")
    prompt_path = project_path(entry.get("prompt_file"), PROMPTS_DIR)
    output = project_path(entry.get("output"), OUTPUTS_DIR)
    if output.suffix.lower() != ".png":
        raise BatchError("invalid_input", f"Output is not a PNG path: {output}")
    base_stem = f"{key}-01"
    transparent_stem = f"{base_stem}-transparent"
    allowed_stems = {base_stem, transparent_stem}
    if prompt_path.stem not in allowed_stems or output.stem not in allowed_stems:
        raise BatchError("invalid_input", f"Prompt/output attempt stem is not frozen external-01 naming: {key}")
    stem = transparent_stem if transparent_stem in (prompt_path.stem, output.stem) else base_stem
    history_stems = tuple(dict.fromkeys((stem, base_stem, transparent_stem)))
    return {
        "entry": entry,
        "scope_entry": scope_entry,
        "index": entry["index"],
        "key": key,
        "stem": stem,
        "prompt_path": prompt_path,
        "output": output,
        "request": output.with_name(f"{output.stem}.request.json"),
        "task": output.with_name(f"{output.stem}.task.json"),
        "result": output.with_name(f"{output.stem}.result.json"),
        "client_prompt": output.with_name(f"{output.stem}.prompt.txt"),
        "dry_run_log": LOGS_DIR / f"{stem}-dryrun.log",
        "actual_log": LOGS_DIR / f"{stem}.log",
        "execution": EXECUTIONS_DIR / f"{stem}.json",
        "history_logs": tuple(LOGS_DIR / f"{item}.log" for item in history_stems),
        "history_executions": tuple(EXECUTIONS_DIR / f"{item}.json" for item in history_stems),
    }


def identity(state):
    return {
        "index": state["index"],
        "source_sha256": state["key"],
        "stem": state["stem"],
    }


def artifact_action(state, include_dry_run):
    custom_action = state.get("artifact_action")
    if custom_action is not None:
        return custom_action(state, include_dry_run)
    for name, reason in (
        ("output", "output_exists"),
        ("task", "task_record_exists"),
        ("result", "result_record_exists"),
    ):
        if state[name].exists():
            return "skip", reason
    if state["request"].exists():
        return "stop", "pending_request_requires_manual_check"
    for path in (*state["history_logs"], *state["history_executions"]):
        if path.exists():
            return "skip", "actual_execution_history_exists"
    if state["client_prompt"].exists():
        return "stop", "client_prompt_sidecar_requires_manual_check"
    if include_dry_run and state["dry_run_log"].exists():
        return "stop", "dry_run_log_exists_requires_manual_check"
    return "dispatch", None


def stop_message(reason):
    messages = {
        "pending_request_requires_manual_check": "Request sidecar exists without output/task/result; reconcile the remote task before any new POST",
        "client_prompt_sidecar_requires_manual_check": "Client prompt sidecar already exists; inspect the incomplete local dispatch record",
        "dry_run_log_exists_requires_manual_check": "Dry-run log already exists and logs are never overwritten; inspect it before dispatch",
    }
    return messages.get(reason, reason)


def acknowledged_execution_hold(scope_entry, entry):
    index = scope_entry.get("index")
    key = scope_entry.get("source_sha256")
    if entry is None or entry.get("status") != "prepared_not_dispatched" or entry.get("index") != index or entry.get("attempt") != "external-01":
        raise BatchError("invalid_execution_hold", f"Hold {index} is not a frozen original prepared source")
    stem = f"{key}-01"
    execution_path = EXECUTIONS_DIR / f"{stem}.json"
    try:
        execution, execution_sha = read_json_with_sha(execution_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BatchError("invalid_execution_hold", f"Unable to verify original execution hold {index}: {exc}") from exc
    if any(execution.get(field) != expected for field, expected in (
        ("index", index), ("source_sha256", key), ("attempt", "external-01"),
        ("result", None), ("output_sha256", None),
    )):
        raise BatchError("invalid_execution_hold", f"Execution identity or result binding differs for hold {index}")
    if execution.get("status") not in {"failed", "resume_existing_task_required"} or not execution.get("finished_at_utc"):
        raise BatchError("invalid_execution_hold", f"Execution {index} is not a finished unresolved dispatch")
    for suffix in (".png", ".result.json"):
        if (OUTPUTS_DIR / f"{stem}{suffix}").exists():
            raise BatchError("invalid_execution_hold", f"Hold {index} now has a returned result; reconcile it instead of holding")
    return {
        "index": index,
        "source_sha256": key,
        "stem": stem,
        "reason": "unresolved_execution_hold_retained",
        "execution": relative_path(execution_path),
        "execution_sha256": execution_sha,
        "execution_status": execution["status"],
        "task_id": execution.get("task_id"),
        "completion_claimed": False,
        "retry_or_resume_attempted": False,
    }


def collect_batch(context, limit, only_indices=None, acknowledged_holds=()):
    selected = []
    skipped = []
    failed = []
    scope_entries = context["scope"].get("entries")
    if not isinstance(scope_entries, list):
        raise BatchError("invalid_input", "scope.json entries must be a list")
    for scope_entry in scope_entries:
        if not isinstance(scope_entry, dict):
            raise BatchError("invalid_input", "scope.json contains an invalid entry")
        key = scope_entry.get("source_sha256")
        entry = context["prepared_entries"].get(key)
        if scope_entry.get("index") in acknowledged_holds:
            skipped.append(acknowledged_execution_hold(scope_entry, entry))
            continue
        if only_indices is not None and scope_entry.get("index") not in only_indices:
            continue
        if entry is None or entry.get("status") != "prepared_not_dispatched":
            continue
        try:
            state = entry_state(entry, scope_entry)
        except BatchError as exc:
            failed.append({
                "index": scope_entry.get("index"),
                "source_sha256": key,
                "status": exc.status,
                "error": str(exc),
            })
            break
        action, reason = artifact_action(state, include_dry_run=True)
        if action == "skip":
            skipped.append({**identity(state), "reason": reason})
            continue
        if action == "stop":
            failed.append({**identity(state), "status": reason, "error": stop_message(reason)})
            break
        selected.append(state)
        if len(selected) == limit:
            break
    return selected, skipped, failed


def require_disk_space():
    try:
        free = shutil.disk_usage("C:/").free
    except OSError as exc:
        raise BatchError("disk_check_failed", f"Unable to check C volume free space: {exc}") from exc
    if free < MINIMUM_FREE_BYTES:
        raise BatchError(
            "insufficient_disk_space",
            f"C volume has {free} free bytes; at least {MINIMUM_FREE_BYTES} are required",
        )
    return free


def client_command(state):
    entry = state["entry"]
    command = [
        sys.executable,
        str(CLIENT_PATH),
        "--prompt-file", str(state["prompt_path"]),
        "--output", str(state["output"]),
        "--model", str(entry.get("model")),
        "--size", str(entry.get("size")),
        "--resolution", str(entry.get("resolution")),
        "--quality", str(entry.get("quality")),
        "--background", str(entry.get("background")),
    ]
    for url in entry.get("image_urls", []):
        command.extend(("--image-url", url))
    if entry.get("mask_url") is not None:
        command.extend(("--mask-url", entry["mask_url"]))
    return command


def validate_frozen_entry(context, state):
    require_context_unchanged(context)
    entry = state["entry"]
    scope_entry = state["scope_entry"]
    key = state["key"]
    try:
        prompt_bytes = state["prompt_path"].read_bytes()
        prompt_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise BatchError("frozen_input_mismatch", f"Prompt is not readable strict UTF-8: {exc}") from exc
    if not prompt_bytes.strip():
        raise BatchError("frozen_input_mismatch", "Prompt file is empty")
    prompt_sha = sha256_bytes(prompt_bytes)
    if entry.get("prompt_sha256") != prompt_sha:
        raise BatchError("frozen_input_mismatch", f"Prompt SHA mismatch for {key}")

    source_path = project_path(entry.get("source_png"))
    scope_source_path = project_path(scope_entry.get("source_png"))
    if source_path != scope_source_path:
        raise BatchError("frozen_input_mismatch", f"Source PNG path differs from scope for {key}")
    try:
        source_sha = file_sha256(source_path)
    except OSError as exc:
        raise BatchError("frozen_input_mismatch", f"Unable to hash local source PNG: {exc}") from exc
    if entry.get("converted_png_sha256") != source_sha:
        raise BatchError("frozen_input_mismatch", f"Local source PNG SHA mismatch for {key}")
    if scope_entry.get("converted_png_sha256") != source_sha:
        raise BatchError("frozen_input_mismatch", f"Scope source PNG SHA mismatch for {key}")

    release_asset = context["release_assets"].get(key)
    if release_asset is None:
        raise BatchError("frozen_input_mismatch", f"Source is absent from input-release.json: {key}")
    if release_asset.get("converted_png_sha256") != source_sha:
        raise BatchError("frozen_input_mismatch", f"Input release source SHA mismatch for {key}")
    if release_asset.get("public_unauthenticated_sha256_verified") is not True:
        raise BatchError("frozen_input_mismatch", f"Input release source lacks public SHA verification: {key}")

    mascot = context["scope"].get("mascot_reference")
    if not isinstance(mascot, dict):
        raise BatchError("frozen_input_mismatch", "Scope mascot reference is invalid")
    mascot_path = project_path(mascot.get("path"))
    try:
        mascot_sha = file_sha256(mascot_path)
    except OSError as exc:
        raise BatchError("frozen_input_mismatch", f"Unable to hash local mascot PNG: {exc}") from exc
    if mascot.get("sha256") != mascot_sha:
        raise BatchError("frozen_input_mismatch", "Local mascot SHA differs from the frozen scope")
    input_validation = state.get("input_validation")
    if input_validation is None:
        expected_inputs = [source_sha, mascot_sha]
        expected_urls = [release_asset.get("url"), mascot.get("url")]
    else:
        expected_inputs, expected_urls = input_validation(context, state)
    if entry.get("ordered_input_sha256") != expected_inputs:
        raise BatchError("frozen_input_mismatch", f"Ordered input SHA binding mismatch for {key}")
    if entry.get("image_urls") != expected_urls:
        raise BatchError("frozen_input_mismatch", f"Ordered input URL binding mismatch for {key}")
    if entry.get("model") != context["scope"].get("model"):
        raise BatchError("frozen_input_mismatch", f"Model differs from frozen scope for {key}")
    if entry.get("n") != 1:
        raise BatchError("frozen_input_mismatch", f"Batch entries must generate exactly one image: {key}")

    parameters = {
        "model": entry.get("model"),
        "size": entry.get("size"),
        "image_urls": entry.get("image_urls"),
        "resolution": entry.get("resolution"),
        "quality": entry.get("quality"),
        "background": entry.get("background"),
        "n": 1,
    }
    if entry.get("mask_url") is not None:
        parameters["mask_url"] = entry["mask_url"]
    custom_validation = state.get("frozen_validator")
    if custom_validation is not None:
        custom_validation(context, state)
    return {
        "prompt_sha256": prompt_sha,
        "command": client_command(state),
        "parameters": parameters,
    }


def run_to_log(command, log_path):
    try:
        with log_path.open("xb") as log:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
    except FileExistsError:
        raise BatchError("log_already_exists", f"Refusing to overwrite log: {log_path}") from None
    except (OSError, subprocess.SubprocessError) as exc:
        raise BatchError("client_process_or_log_failed", f"Client process or log failed: {exc}") from exc
    return completed.returncode


def validate_dry_run(state, validated):
    try:
        body = read_json(state["dry_run_log"])
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError) as exc:
        raise BatchError("dry_run_validation_failed", f"Dry-run stdout/stderr is not one JSON object: {exc}") from exc
    if body.get("status") != "validated_without_network_or_writes":
        raise BatchError("dry_run_validation_failed", "Dry-run status is not the client's no-network/no-write validation status")
    if body.get("endpoint") != GENERATIONS_URL:
        raise BatchError("dry_run_validation_failed", "Dry-run endpoint differs from the pinned generations endpoint")
    if body.get("prompt_sha256") != validated["prompt_sha256"]:
        raise BatchError("dry_run_validation_failed", "Dry-run prompt SHA differs from the frozen prompt")
    if body.get("parameters") != validated["parameters"]:
        raise BatchError("dry_run_validation_failed", "Dry-run parameters or ordered image URLs differ from prepared.json")
    dry_output = body.get("output")
    if not isinstance(dry_output, str):
        raise BatchError("dry_run_validation_failed", "Dry-run output path is missing")
    candidate = Path(dry_output)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    if candidate.resolve() != state["output"]:
        raise BatchError("dry_run_validation_failed", "Dry-run output path differs from prepared.json")


def write_json_new(path, value):
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=True, indent=2)
            stream.write("\n")
    except FileExistsError:
        raise BatchError("execution_record_exists", f"Refusing to overwrite execution record: {path}") from None
    except OSError as exc:
        raise BatchError("execution_record_write_failed", f"Unable to create execution record: {exc}") from exc


def replace_execution_json(path, value):
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=True, indent=2)
            stream.write("\n")
        temporary.replace(path)
    except OSError as exc:
        raise BatchError("execution_record_write_failed", f"Unable to finish execution record: {exc}") from exc


def readable_task_id(path):
    try:
        value = read_json(path).get("task_id")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError):
        return None
    return value if isinstance(value, str) and value else None


def finish_actual_execution(record, state, exit_code):
    errors = []
    task_id = None
    result = None
    task_record_present = state["task"].exists()
    if task_record_present:
        try:
            task_value = read_json(state["task"]).get("task_id")
            if not isinstance(task_value, str) or not task_value:
                raise RuntimeError("task_id is missing or invalid")
            task_id = task_value
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError) as exc:
            errors.append(f"Unreadable task record: {exc}")

    if state["result"].exists():
        try:
            result = read_json(state["result"])
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError) as exc:
            errors.append(f"Unreadable result record: {exc}")
    elif exit_code == 0:
        errors.append("Client exited successfully without a result.json record")

    if isinstance(result, dict):
        result_task_id = result.get("task_id")
        if task_id is None and isinstance(result_task_id, str) and result_task_id:
            task_id = result_task_id
        elif task_id is not None and result_task_id != task_id:
            errors.append("Task ID differs between task.json and result.json")

    output_sha = None
    if exit_code == 0:
        try:
            if not state["output"].is_file():
                raise RuntimeError("Output PNG is missing")
            with state["output"].open("rb") as stream:
                if stream.read(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
                    raise RuntimeError("Output does not have a PNG signature")
            output_sha = file_sha256(state["output"])
            if not isinstance(result, dict) or result.get("sha256") != output_sha:
                raise RuntimeError("Output PNG SHA differs from result.json")
        except (OSError, RuntimeError) as exc:
            errors.append(str(exc))
    if exit_code != 0:
        errors.append(f"Client exited with code {exit_code}; no automatic retry or new POST is allowed")

    record["task_id"] = task_id
    record["result"] = result
    record["output_sha256"] = output_sha
    if errors:
        record["status"] = "resume_existing_task_required" if task_id or task_record_present else "failed"
        record["error"] = "; ".join(errors)
        replace_execution_json(state["execution"], record)
        raise BatchError(record["status"], record["error"])
    record["status"] = "completed"
    record["error"] = None
    replace_execution_json(state["execution"], record)
    return output_sha


def dispatch_one(context, state):
    action, reason = artifact_action(state, include_dry_run=True)
    if action == "skip":
        return "skip", reason
    if action == "stop":
        raise BatchError(reason, stop_message(reason))

    validated = validate_frozen_entry(context, state)
    require_disk_space()
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    dry_returncode = run_to_log(validated["command"] + ["--dry-run"], state["dry_run_log"])
    if dry_returncode != 0:
        raise BatchError("dry_run_failed", f"Dry-run exited with code {dry_returncode}; see {state['dry_run_log']}")
    validate_dry_run(state, validated)

    validated_again = validate_frozen_entry(context, state)
    if validated_again != validated:
        raise BatchError("frozen_input_mismatch", "Validated inputs changed between dry-run and actual dispatch")
    action, reason = artifact_action(state, include_dry_run=False)
    if action == "skip":
        return "skip", reason
    if action == "stop":
        raise BatchError(reason, stop_message(reason))
    free_bytes = require_disk_space()
    current_machine_id = machine_id()
    EXECUTIONS_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "schema": "naiwa-evolink-high131-execution-v1",
        "machine_id": current_machine_id,
        "index": state["index"],
        "source_sha256": state["key"],
        "attempt": state["entry"].get("attempt"),
        "status": "running",
        "started_at_utc": utc_now(),
        "finished_at_utc": None,
        "exit_code": None,
        "executable": sys.executable,
        "arguments": validated["command"][1:],
        "prompt_file": relative_path(state["prompt_path"]),
        "prompt_sha256": validated["prompt_sha256"],
        "ordered_input_sha256": state["entry"].get("ordered_input_sha256"),
        "output": relative_path(state["output"]),
        "output_sha256": None,
        "task_id": None,
        "result": None,
        "log": relative_path(state["actual_log"]),
        "dry_run_log": relative_path(state["dry_run_log"]),
        "prepared_sha256": context["prepared_sha256"],
        "scope_sha256": context["scope_sha256"],
        "input_release_sha256": context["input_release_sha256"],
        "disk_free_bytes_c_before_actual": free_bytes,
        "error": None,
    }
    for name in (
        "repair_preparation", "repair_preparation_sha256", "review",
        "review_sha256", "rejected_output_sha256", "repair_input_mode",
        "edit_target_image", "edit_target_sha256", "remote_commit", "remote_readback", "note_detail",
        "mask", "mask_url",
    ):
        if state.get(name) is not None:
            record[name] = state[name]
    write_json_new(state["execution"], record)
    try:
        actual_returncode = run_to_log(validated["command"], state["actual_log"])
    except BatchError as exc:
        record["finished_at_utc"] = utc_now()
        record["task_id"] = readable_task_id(state["task"])
        record["status"] = "resume_existing_task_required" if record["task_id"] or state["task"].exists() else "failed"
        record["error"] = str(exc)
        replace_execution_json(state["execution"], record)
        raise BatchError(record["status"], str(exc)) from exc
    record["finished_at_utc"] = utc_now()
    record["exit_code"] = actual_returncode
    output_sha = finish_actual_execution(record, state, actual_returncode)
    return "completed", output_sha


def emit_summary(collect_only, completed, skipped, failed, selected=None):
    summary = {
        "collect_only": collect_only,
        "completed": completed,
        "skipped": skipped,
        "failed": failed,
    }
    if collect_only:
        candidates = []
        for state in (selected or []):
            candidate = {
                **identity(state),
                "prompt_sha256": state["entry"].get("prompt_sha256"),
                "output": relative_path(state["output"]),
            }
            if "repair_preparation" in state:
                candidate["attempt"] = state["entry"].get("attempt")
                candidate["parameters"] = {
                    name: state["entry"].get(name)
                    for name in ("model", "size", "background", "resolution", "quality", "n")
                }
                candidate["repair_preparation_sha256"] = state["repair_preparation_sha256"]
            candidates.append(candidate)
        summary["candidates"] = candidates
    if failed:
        summary["stopped"] = True
    print(json.dumps(summary, ensure_ascii=True, separators=(",", ":")))


def limit_argument(value):
    try:
        limit = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer from 1 through 8") from None
    if not 1 <= limit <= 8:
        raise argparse.ArgumentTypeError("must be an integer from 1 through 8")
    return limit


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run a frozen HIGH131 EvoLink batch serially, with no automatic repost or task resume.",
    )
    parser.add_argument("--limit", required=True, type=limit_argument, help="Maximum new actual calls in this batch (1..8)")
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Only list selected candidates; do not invoke the client, read credentials, access the network, or write logs",
    )
    parser.add_argument("--index", action="append", type=int, help="Only process this original scope index; repeat for multiple indices")
    parser.add_argument("--acknowledge-hold", action="append", type=int, default=[], help="Retain a verified unresolved original execution as held, never as completed; requires --index")
    args = parser.parse_args()
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
        context = load_context()
        selected, skipped, failed = collect_batch(
            context,
            args.limit,
            only_indices=set(args.index) if args.index else None,
            acknowledged_holds=set(args.acknowledge_hold),
        )
    except BatchError as exc:
        failed.append({"status": exc.status, "error": str(exc)})
    except (OSError, ValueError, RuntimeError) as exc:
        failed.append({"status": "invalid_input", "error": str(exc)})

    if args.collect_only or failed:
        emit_summary(args.collect_only, completed, skipped, failed, selected)
        return 1 if failed else 0

    for state in selected:
        try:
            outcome, detail = dispatch_one(context, state)
        except BatchError as exc:
            failed.append({**identity(state), "status": exc.status, "error": str(exc)})
            break
        except Exception as exc:
            status = "resume_existing_task_required" if state["task"].exists() else "batch_execution_failed"
            failed.append({**identity(state), "status": status, "error": f"{type(exc).__name__}: {exc}"})
            break
        if outcome == "skip":
            skipped.append({**identity(state), "reason": detail})
            continue
        completed.append({
            **identity(state),
            "output_sha256": detail,
            "execution": relative_path(state["execution"]),
        })

    emit_summary(False, completed, skipped, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
