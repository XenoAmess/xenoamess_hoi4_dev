import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime import high131_hd_proof as hd_proof
from runtime.high131_io import write_json
from tools.common import ROOT, file_sha256, machine_id, read_json, utc_now

EXPERIMENT = ROOT / "mod_nailong/experiments/evolink-high131-flare-20261025"


def expected_input_route(scope, asset, repair):
    mascot = scope["mascot_reference"]
    mode = repair.get("repair_input_mode") if repair else None
    if mode is None:
        return [asset["url"], mascot["url"]], {
            "input_route": "original-source-and-mascot-v1",
            "ordered_input_sha256": [asset["converted_png_sha256"], mascot["sha256"]],
            "remote_commit": None,
            "remote_readback": None,
        }
    assert mode == "raw-hd-edit-v1", f"Unsupported repair input route: {mode}"
    commit = repair.get("remote_commit")
    assert isinstance(commit, str) and len(commit) == 40 and all(value in "0123456789abcdef" for value in commit), "Invalid pinned remote commit"
    digest = repair["edit_target_sha256"]
    assert digest == repair["rejected_output_sha256"], "Raw-HD edit target must be the exact rejected output"
    target_path = (ROOT / repair["edit_target_image"]).resolve()
    try:
        proof, index = hd_proof.load_remote_proof(commit, repair["remote_readback"], root=ROOT)
        target_url = hd_proof.validate_remote_target(proof, commit, target_path, digest, index=index, root=ROOT)
    except RuntimeError as exc:
        raise AssertionError(str(exc)) from exc
    urls = [target_url, asset["url"], mascot["url"]]
    ordered_sha = [digest, asset["converted_png_sha256"], mascot["sha256"]]
    assert repair["remote_target_url"] == target_url and repair["image_urls"] == urls, "Raw-HD target, original and mascot URL order differs"
    assert repair["ordered_input_sha256"] == ordered_sha, "Raw-HD target, original and mascot SHA order differs"
    return urls, {
        "input_route": mode,
        "ordered_input_sha256": ordered_sha,
        "edit_target_sha256": digest,
        "remote_commit": commit,
        "remote_readback": repair["remote_readback"],
    }


def main():
    scope = read_json(EXPERIMENT / "scope.json")
    release = read_json(EXPERIMENT / "input-release.json")
    assets = {row["source_sha256"]: row for row in release["assets"]}
    scope_sources = {row["source_sha256"]: row for row in scope["entries"]}
    repair_path = EXPERIMENT / "card-repair-preparation.json"
    repairs = read_json(repair_path)["entries"] if repair_path.exists() else []
    repairs_by_attempt = {(row["source_sha256"], row["attempt"]): row for row in repairs}
    mascot = scope["mascot_reference"]
    assert file_sha256(ROOT / mascot["path"]) == mascot["sha256"]
    entries = []
    task_ids = collections.Counter()
    output_hashes = {}
    for result_path in sorted((EXPERIMENT / "outputs").glob("*.result.json")):
        stem = result_path.name[:-len(".result.json")]
        key = stem[:64]
        number = stem[65:].split("-", 1)[0]
        if len(key) != 64 or len(number) != 2 or not number.isdigit():
            raise RuntimeError(f"Unexpected result identity: {result_path}")
        int(key, 16)
        attempt = f"external-{number}"
        output = result_path.with_name(stem + ".png")
        prompt_path = result_path.with_name(stem + ".prompt.txt")
        request_path = result_path.with_name(stem + ".request.json")
        task_path = result_path.with_name(stem + ".task.json")
        result = read_json(result_path)
        request = read_json(request_path)
        task = read_json(task_path)
        prompt = prompt_path.read_bytes().decode("utf-8")
        prompt_sha = file_sha256(prompt_path)
        assert request["prompt"] == prompt
        assert task["task_id"] == result["task_id"]
        assert file_sha256(output) == result["sha256"]
        assert result["png_signature_verified"] is True
        assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        source = ROOT / scope_sources[key]["source_png"]
        source_sha = file_sha256(source)
        assert source_sha == assets[key]["converted_png_sha256"] == scope_sources[key]["converted_png_sha256"]
        repair = repairs_by_attempt.get((key, attempt))
        expected_urls, input_binding = expected_input_route(scope, assets[key], repair)
        assert request["image_urls"] == expected_urls
        assert request["model"] == scope["model"]
        assert request["n"] == 1
        assert request["background"] in {"opaque", "transparent"}
        assert request["size"] in {"1:1", "3:4", "2:3"}
        assert request["resolution"] == "2K" and request["quality"] == "high"
        if repair is not None:
            assert repair["attempt"] == attempt and repair["output"] == output.relative_to(ROOT).as_posix()
            for field in ("size", "background", "resolution", "quality"):
                assert request[field] == repair[field], f"Actual repair parameter differs: {field}"
            if repair.get("repair_input_mode") == "raw-hd-edit-v1":
                repair_prompt = (ROOT / repair["prompt_file"]).resolve()
                repair_prompt.relative_to((EXPERIMENT / "prompts").resolve())
                assert repair_prompt.stem == prompt_path.name.removesuffix(".prompt.txt")
                assert file_sha256(repair_prompt) == repair["prompt_sha256"] == prompt_sha
        task_ids[result["task_id"]] += 1
        output_hashes.setdefault(result["sha256"], []).append(key)
        entries.append({
            "source_sha256": key,
            "attempt": attempt,
            "output": output.relative_to(ROOT).as_posix(),
            "output_sha256": result["sha256"],
            "task_id": result["task_id"],
            "prompt_sha256": prompt_sha,
            "request_sha256": file_sha256(request_path),
            "result_sha256": file_sha256(result_path),
            "source_png_sha256": source_sha,
            "background": request["background"],
            "size": request["size"],
            **input_binding,
        })
    assert all(count == 1 for count in task_ids.values())
    assert all(len(keys) == 1 for keys in output_hashes.values())
    unresolved = []
    for task_path in sorted((EXPERIMENT / "outputs").glob("*.task.json")):
        result_path = task_path.with_name(task_path.name[:-len(".task.json")] + ".result.json")
        if not result_path.exists():
            unresolved.append(task_path.relative_to(ROOT).as_posix())
    target = EXPERIMENT / "record-verification.json"
    write_json(target, {
        "schema": "naiwa-evolink-high131-record-verification-v1",
        "machine_id": machine_id(),
        "observed_at_utc": utc_now(),
        "verified_result_count": len(entries),
        "unique_task_ids": len(task_ids),
        "unique_output_sha256": len(output_hashes),
        "unresolved_task_records": unresolved,
        "scope": "Every returned result's actual prompt, request/task/output SHA and declared ordered input route is verified. Raw-HD edits additionally bind the exact rejected target and fixed remote original-byte proof. This is not art approval, proof of an unknown remote task outcome or game acceptance. Failed calls without task IDs retain separate execution holds and are not made complete by an empty unresolved_task_records list.",
        "entries": entries,
    })
    print(json.dumps({
        "verified_results": len(entries),
        "unique_task_ids": len(task_ids),
        "unique_output_sha256": len(output_hashes),
        "raw_hd_results": sum(row["input_route"] == "raw-hd-edit-v1" for row in entries),
        "unresolved_task_records": unresolved,
    }, ensure_ascii=True))


if __name__ == "__main__":
    main()
