import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.common import file_sha256, machine_id, read_json, utc_now, write_json


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worktree", type=Path, required=True)
    args = parser.parse_args()
    worktree = args.worktree.resolve()
    require((worktree / ".git").exists(), "Expected an isolated worktree")
    python_relative = "runtime/low2-python-tests.log"
    python_text = (worktree / python_relative).read_text(encoding="utf-8")
    match = re.search(r"Ran (\d+) tests in ([0-9.]+)s", python_text)
    require(match is not None and re.search(r"^OK\s*$", python_text, re.MULTILINE) is not None, "Python test log is not a complete success")
    require("FAILED" not in python_text and "Traceback" not in python_text, "Python test log contains failure evidence")
    python = {"status": "passed", "passed": int(match.group(1)), "elapsed_seconds": float(match.group(2)), "log": python_relative, "log_sha256": file_sha256(worktree / python_relative), "command": "python -X utf8 -m unittest discover -s tests"}
    javascript_logs = []
    total = 0
    for name in ("bounded-builtin-window", "builtin-terminal-transport-flow", "builtin-transport-policy", "rolling-builtin-queue"):
        relative = f"runtime/low2-{name}.log"
        text = (worktree / relative).read_text(encoding="utf-8")
        passed = re.search(r"^# pass (\d+)\s*$", text, re.MULTILINE)
        failed = re.search(r"^# fail (\d+)\s*$", text, re.MULTILINE)
        require(passed is not None and failed is not None and int(failed.group(1)) == 0, f"JavaScript test log is not a complete success: {relative}")
        require("not ok " not in text, f"JavaScript failure marker: {relative}")
        total += int(passed.group(1))
        javascript_logs.append({"path": relative, "sha256": file_sha256(worktree / relative), "passed": int(passed.group(1))})
    require(total == 24, f"Expected 24 JavaScript tests, got {total}")
    preview_relative = "runtime/low2-preview-build.log"
    preview_text = (worktree / preview_relative).read_text(encoding="utf-8")
    require("PASS: deterministic double build, exact staging/manifest/ZIP and HD texture decode; scope=selected preview validation subset" in preview_text, "Preview double build is not a complete success")
    scope = read_json(worktree / "mod_nailong/experiments/evolink-low2-20261030/scope.json")
    keys = [row["source_sha256"] for row in scope["entries"]]
    descriptor = (worktree / "mod_nailong/mod/descriptor.mod").read_text(encoding="utf-8")
    require("钢奶龙心" in descriptor and "remote_file_id" not in descriptor and "replace_path" not in descriptor, "Development descriptor is not clean")
    receipt = {
        "schema": "low2-kimi-test-receipt-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
        "source_commit": __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], cwd=worktree, text=True).strip(),
        "python": python,
        "javascript": {"status": "passed", "passed": total, "logs": javascript_logs},
        "preview_build": {"status": "passed", "preview_only": True, "formal_release": False, "source_sha256": keys, "command": "python -X utf8 -m mod_nailong.tools.build_release --preview --check --source-key <two scoped source SHA256 values>", "log": preview_relative, "log_sha256": file_sha256(worktree / preview_relative)},
        "development_descriptor_clean": True,
        "hoi4_runtime_acceptance_claimed": False,
    }
    write_json(ROOT / "runtime/low2-evolink-20261030/test-receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
