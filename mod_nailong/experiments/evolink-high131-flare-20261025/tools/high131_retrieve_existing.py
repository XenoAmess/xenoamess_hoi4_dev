import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.high131_run_batch import relative_path
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now, write_json

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"


def main():
    parser = argparse.ArgumentParser(description="Retrieve one already-created HIGH131 task without a generation POST.")
    parser.add_argument("--index", required=True, type=int)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--recovery-id", required=True)
    args = parser.parse_args()
    if not args.recovery_id.startswith("retrieve") or not args.recovery_id[8:].isdigit():
        raise RuntimeError("recovery-id must be retrieveN")
    scope = read_json(EXPERIMENT / "scope.json")
    matches = [row for row in scope["entries"] if row["index"] == args.index]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one scope entry for index {args.index}")
    key = matches[0]["source_sha256"]
    number = int(args.attempt.removeprefix("external-"))
    if args.attempt != f"external-{number:02}":
        raise RuntimeError("attempt must be zero-padded external-NN")
    stem = f"{key}-{number:02}"
    output = EXPERIMENT / "outputs" / f"{stem}.png"
    result_path = output.with_name(f"{stem}.result.json")
    task_path = output.with_name(f"{stem}.task.json")
    prompt_path = output.with_name(f"{stem}.prompt.txt")
    request_path = output.with_name(f"{stem}.request.json")
    prior_execution_path = EXPERIMENT / "executions" / f"{stem}.json"
    prior_execution = read_json(prior_execution_path)
    task_id = read_json(task_path)["task_id"]
    if prior_execution["status"] != "resume_existing_task_required":
        raise RuntimeError("The original execution is not an unresolved task recovery boundary")
    for field, expected in (("index", args.index), ("source_sha256", key), ("attempt", args.attempt), ("task_id", task_id), ("output_sha256", None), ("result", None)):
        if prior_execution.get(field) != expected:
            raise RuntimeError(f"Original execution binding mismatch: {field}")
    request = read_json(request_path)
    if request["prompt"] != prompt_path.read_text(encoding="utf-8"):
        raise RuntimeError("Client prompt and request prompt differ")
    if prior_execution["prompt_sha256"] != file_sha256(prompt_path):
        raise RuntimeError("Original prompt binding mismatch")
    original_arguments = prior_execution["arguments"]
    if Path(original_arguments[0]).name != "evolink_image.py":
        raise RuntimeError("Unexpected original client")
    image_urls = [original_arguments[i + 1] for i, value in enumerate(original_arguments[:-1]) if value == "--image-url"]
    if request["image_urls"] != image_urls:
        raise RuntimeError("Original ordered inputs differ from the request")
    if request["n"] != 1:
        raise RuntimeError("Unexpected original request count")
    receipt_path = EXPERIMENT / "executions" / f"{stem}-{args.recovery_id}.json"
    log_path = EXPERIMENT / "logs" / f"{stem}-{args.recovery_id}.log"
    for path in (output, result_path, receipt_path, log_path):
        if path.exists():
            raise RuntimeError(f"Refusing to overwrite or replay an existing recovery artifact: {path}")
    command = [
        sys.executable,
        str(ROOT / "skills/evolink-imagegen/scripts/evolink_image.py"),
        "--task-id", task_id,
        "--output", str(output),
    ]
    started = utc_now()
    with log_path.open("x", encoding="utf-8") as log:
        completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False)
    result = read_json(result_path) if result_path.is_file() else None
    if result is not None:
        if result["task_id"] != task_id or result["sha256"] != file_sha256(output):
            raise RuntimeError("Retrieved output/result/task binding mismatch")
    status = "completed" if completed.returncode == 0 and result is not None else "resume_existing_task_required"
    receipt = {
        "schema": "naiwa-evolink-high131-existing-task-retrieval-v1",
        "machine_id": machine_id(),
        "index": args.index,
        "source_sha256": key,
        "attempt": args.attempt,
        "status": status,
        "started_at_utc": started,
        "prior_execution": relative_path(prior_execution_path),
        "prior_execution_sha256": file_sha256(prior_execution_path),
        "task_id": task_id,
        "request_sha256": file_sha256(request_path),
        "prompt_sha256": file_sha256(prompt_path),
        "new_generation_tasks_created": 0,
        "command": command,
        "log": relative_path(log_path),
        "finished_at_utc": utc_now(),
        "exit_code": completed.returncode,
        "output": relative_path(output),
        "output_sha256": file_sha256(output) if output.is_file() else None,
        "result": result,
    }
    write_json(receipt_path, receipt)
    print(json.dumps({"index": args.index, "status": status, "exit_code": completed.returncode, "receipt": relative_path(receipt_path), "output_sha256": receipt["output_sha256"]}, ensure_ascii=True))
    return 0 if status == "completed" else completed.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())
