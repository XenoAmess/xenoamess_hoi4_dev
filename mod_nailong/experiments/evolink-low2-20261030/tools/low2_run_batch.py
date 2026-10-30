from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from runtime import high131_run_batch as batch
from tools.common import file_sha256, read_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-low2-20261030"
AUTHORIZATION = EXPERIMENT / "authorization.json"
EXPECTED_PARAMETERS = {"model": "gpt-image-2.5-flare", "size": "3:4", "resolution": "2K", "quality": "high", "background": "opaque", "n": 1}
BATCH_FIELDS = ("ROOT", "EXPERIMENT", "PREPARED_PATH", "SCOPE_PATH", "RELEASE_PATH", "PROMPTS_DIR", "OUTPUTS_DIR", "LOGS_DIR", "EXECUTIONS_DIR", "CLIENT_PATH", "collect_batch", "write_json_new", "replace_execution_json")
ORIGINAL_BATCH_STATE = {name: getattr(batch, name) for name in BATCH_FIELDS}
for name in BATCH_FIELDS[:9]:
    value = ROOT if name == "ROOT" else EXPERIMENT if name == "EXPERIMENT" else EXPERIMENT / {
        "PREPARED_PATH": "prepared.json", "SCOPE_PATH": "scope.json", "RELEASE_PATH": "input-release.json",
        "PROMPTS_DIR": "prompts", "OUTPUTS_DIR": "outputs", "LOGS_DIR": "logs", "EXECUTIONS_DIR": "executions",
    }[name]
    setattr(batch, name, value)
batch.CLIENT_PATH = ROOT / "skills/evolink-imagegen/scripts/evolink_image.py"
original_collect_batch = batch.collect_batch
original_write_json_new = batch.write_json_new
original_replace_execution_json = batch.replace_execution_json


def require(condition, message):
    if not condition:
        raise batch.BatchError("invalid_low2_scope", message)


def require_scope(context, state):
    scope = context["scope"]
    require(scope.get("schema") == "low2-kimi-evolink-scope-v1" and scope.get("source_count") == 2, "Wrong LOW2 scope")
    require(scope.get("handoff_pinned_commit") == "398db2a4959364c4303f9d912397b58df5fe907a", "Pinned handoff commit differs")
    require(batch.project_path(scope["handoff"]) == ROOT / "docs/handoffs/2026-10-30-low-two-pending.md", "Wrong handoff path")
    require(file_sha256(ROOT / scope["handoff"]) == scope["handoff_sha256"], "Handoff bytes changed")
    require(batch.project_path(scope["authorization"]) == AUTHORIZATION, "Wrong authorization path")
    require(file_sha256(AUTHORIZATION) == scope["authorization_sha256"], "Authorization bytes changed")
    auth = read_json(AUTHORIZATION)
    require(auth.get("authorized_agent") == "Kimi" and auth.get("codex_tool_permission_changed") is False, "Agent permission boundary differs")
    require(auth.get("permission_documents_modified") is False, "Permission documents changed")
    entry = state["entry"]
    for field, expected in EXPECTED_PARAMETERS.items():
        require(entry.get(field) == expected, f"Frozen generation parameter differs: {field}")
    require(entry.get("attempt") == "external-01", "Only one scoped external attempt is allowed")
    queue = read_json(ROOT / "mod_nailong/data/image-retry-queue.json")
    for source in scope["entries"]:
        require(queue["sources"].get(source["source_sha256"], {}).get("retries_used") == 0, f"Builtin counter changed: {source['source_sha256']}")
    for item in entry.get("inputs", []):
        require(file_sha256(batch.project_path(item["path"])) == item["sha256"], f"Ordered local input changed: {item['path']}")


def collect_batch(context, *args, **kwargs):
    selected, skipped, failed = original_collect_batch(context, *args, **kwargs)
    for state in selected:
        state["frozen_validator"] = require_scope
    return selected, skipped, failed


def write_json_new(path, value):
    if value.get("schema") == "naiwa-evolink-high131-execution-v1":
        value = {**value, "schema": "low2-kimi-evolink-execution-v1"}
    return original_write_json_new(path, value)


def replace_execution_json(path, value):
    if value.get("schema") == "naiwa-evolink-high131-execution-v1":
        value = {**value, "schema": "low2-kimi-evolink-execution-v1"}
    return original_replace_execution_json(path, value)


batch.collect_batch = collect_batch
batch.write_json_new = write_json_new
batch.replace_execution_json = replace_execution_json
LOW2_BATCH_STATE = {name: getattr(batch, name) for name in BATCH_FIELDS}


def restore_shared_batch():
    for name, value in ORIGINAL_BATCH_STATE.items():
        setattr(batch, name, value)


restore_shared_batch()


if __name__ == "__main__":
    for name, value in LOW2_BATCH_STATE.items():
        setattr(batch, name, value)
    try:
        raise SystemExit(batch.main())
    finally:
        restore_shared_batch()
