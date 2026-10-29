from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from runtime import high131_run_batch as batch
from tools.common import file_sha256, read_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-low7-20261030"
AUTHORIZATION = EXPERIMENT / "authorization.json"
EXPECTED_PARAMETERS = {
    "model": "gpt-image-2.5-flare",
    "size": "3:4",
    "resolution": "2K",
    "quality": "high",
    "background": "opaque",
    "n": 1,
}
BATCH_FIELDS = (
    "ROOT", "EXPERIMENT", "PREPARED_PATH", "SCOPE_PATH", "RELEASE_PATH", "PROMPTS_DIR",
    "OUTPUTS_DIR", "LOGS_DIR", "EXECUTIONS_DIR", "CLIENT_PATH", "collect_batch", "write_json_new",
)
ORIGINAL_BATCH_STATE = {name: getattr(batch, name) for name in BATCH_FIELDS}
LOW7_BATCH_STATE = {}
for name in BATCH_FIELDS[:9]:
    value = ROOT if name == "ROOT" else EXPERIMENT if name == "EXPERIMENT" else EXPERIMENT / {
        "PREPARED_PATH": "prepared.json", "SCOPE_PATH": "scope.json", "RELEASE_PATH": "input-release.json",
        "PROMPTS_DIR": "prompts", "OUTPUTS_DIR": "outputs", "LOGS_DIR": "logs", "EXECUTIONS_DIR": "executions",
    }[name]
    setattr(batch, name, value)
    LOW7_BATCH_STATE[name] = value
batch.CLIENT_PATH = ROOT / "skills/evolink-imagegen/scripts/evolink_image.py"
LOW7_BATCH_STATE["CLIENT_PATH"] = batch.CLIENT_PATH
original_collect_batch = batch.collect_batch


def require(condition, message):
    if not condition:
        raise batch.BatchError("invalid_low7_scope", message)


def require_scope(context, state):
    scope = context["scope"]
    require(scope.get("schema") == "low7-kimi-evolink-scope-v1" and scope.get("source_count") == 7, "Wrong LOW7 scope")
    require(scope.get("handoff_sha256") == "36d28fbf52106df2949007e6658514c026030f122a16f8d9adbe5f5bf9228eb5", "Handoff binding changed")
    require(batch.project_path(scope["handoff"]) == ROOT / "docs/handoffs/2026-10-30-low7-exhausted.json", "Wrong handoff path")
    require(file_sha256(ROOT / scope["handoff"]) == scope["handoff_sha256"], "Handoff bytes changed")
    require(batch.project_path(scope["authorization"]) == AUTHORIZATION, "Wrong authorization path")
    require(file_sha256(AUTHORIZATION) == scope["authorization_sha256"], "Authorization bytes changed")
    auth = read_json(AUTHORIZATION)
    require(auth.get("authorized_agent") == "Kimi" and auth.get("codex_tool_permission_changed") is False, "Agent permission boundary differs")
    require(auth.get("permission_documents_modified") is False, "Permission documents must not be changed by this task")
    require(scope.get("builtin_retry_counters_preserved") is True, "Builtin history must be preserved")
    entry = state["entry"]
    for field, expected in EXPECTED_PARAMETERS.items():
        require(entry.get(field) == expected, f"Frozen generation parameter differs: {field}")
    require(entry.get("attempt") == "external-01", "Only one scoped external attempt is authorized")
    queue = read_json(ROOT / "mod_nailong/data/image-retry-queue.json")
    for source in scope["entries"]:
        require(queue["sources"].get(source["source_sha256"], {}).get("retries_used") == 9, f"Builtin counter changed: {source['source_sha256']}")
    for item in entry.get("inputs", []):
        path = batch.project_path(item["path"])
        require(file_sha256(path) == item["sha256"], f"Ordered local input changed: {item['path']}")


def ordered_inputs(context, state):
    key = state["key"]
    matches = [row for row in context["release"]["reference_sets"] if row["source_sha256"] == key]
    require(len(matches) == 1, f"Missing public reference set: {key}")
    rows = matches[0]["ordered_inputs"]
    require(all(row.get("public_unauthenticated_sha256_verified") is True for row in rows), f"Public reference proof missing: {key}")
    return [row["sha256"] for row in rows], [row["url"] for row in rows]


def collect_batch(context, *args, **kwargs):
    selected, skipped, failed = original_collect_batch(context, *args, **kwargs)
    for state in selected:
        state["input_validation"] = ordered_inputs
        state["frozen_validator"] = require_scope
    return selected, skipped, failed


def write_json_new(path, value):
    if value.get("schema") == "naiwa-evolink-high131-execution-v1":
        value = {**value, "schema": "low7-kimi-evolink-execution-v1"}
    return original_write_json_new(path, value)


original_write_json_new = batch.write_json_new
batch.write_json_new = write_json_new
batch.collect_batch = collect_batch
LOW7_BATCH_STATE["write_json_new"] = write_json_new
LOW7_BATCH_STATE["collect_batch"] = collect_batch


def restore_shared_batch():
    for name, value in ORIGINAL_BATCH_STATE.items():
        setattr(batch, name, value)


restore_shared_batch()


if __name__ == "__main__":
    for name, value in LOW7_BATCH_STATE.items():
        setattr(batch, name, value)
    try:
        raise SystemExit(batch.main())
    finally:
        restore_shared_batch()
