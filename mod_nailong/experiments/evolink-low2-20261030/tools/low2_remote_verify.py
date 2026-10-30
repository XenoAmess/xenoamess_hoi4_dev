import copy
import importlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.common import file_sha256, machine_id, read_json, utc_now, write_json

prepare = importlib.import_module("mod_nailong.experiments.evolink-low7-20261030.tools.low7_prepare")
BASE_PROOF = ROOT / "runtime/low7-delivery-20261030/runtime/low7-evolink-20261030/remote-readback.json"
RECEIPT = ROOT / "runtime/low2-evolink-20261030/remote-readback.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def download_png(reference):
    reference = dict(reference)
    require(reference["url"].startswith("https://") and "?" not in reference["url"] and "#" not in reference["url"], "URL must be fixed public HTTPS")
    import subprocess
    from tools.common import sha256
    errors = []
    for route, proxy in (("proxy", "http://127.0.0.1:10808"), ("noproxy", "*")):
        result = subprocess.run([
            "curl.exe", f"--{route}", proxy, "--fail", "--silent", "--show-error", "--location", "--proto", "=https",
            "--connect-timeout", "20", "--max-time", "90", "--max-filesize", str(16 * 1024 * 1024), reference["url"],
        ], capture_output=True, timeout=105)
        if result.returncode == 0:
            data = result.stdout
            break
        errors.append(result.stderr.decode("utf-8", errors="replace")[:300])
    else:
        raise RuntimeError(f"Remote PNG readback failed: {'; '.join(errors)}")
    require(data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) <= 16 * 1024 * 1024, "Remote response is not an expected PNG")
    require(sha256(data) == reference["sha256"], "Remote PNG SHA differs")
    target = ROOT / "runtime/low2-evolink-20261030/public-inputs" / reference["cache_name"]
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        require(target.read_bytes() == data, "Existing readback cache differs")
    else:
        with target.open("xb") as stream:
            stream.write(data)
    return {"bytes": len(data), "readback_at_utc": utc_now()}


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: low2_remote_verify.py WORKTREE COMMIT")
    worktree = Path(sys.argv[1]).resolve()
    commit = sys.argv[2]
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "Expected a full fixed commit")
    importer = importlib.import_module("mod_nailong.experiments.evolink-low2-20261030.tools.low2_import")
    importer.git(worktree, "fetch", "origin")
    remote = importer.git(worktree, "rev-parse", "origin/master")
    require(commit == remote or importer.git(worktree, "merge-base", "--is-ancestor", commit, remote) == "", "Fixed commit is not public on origin/master")
    index = read_json(worktree / "mod_nailong/data/fullsize-files.json")
    base = read_json(BASE_PROOF)
    require(base.get("schema") == "low7-fullsize-remote-readback-v1", "Base proof schema missing")
    require(base["machine_id"] == machine_id() and base["commit"] == "88f26a181a0227f16fc34f91f8d417a21820b3e6", "Base proof identity differs")
    require(base["distinct_outputs"] == len(base["outputs"]) == 7420 and base["status"] == "verified", "Base proof is incomplete")
    require(base["verification"] == "Fixed-commit Git blob SHA/size checks for all outputs; new originals downloaded completely with SHA256/byte verification; unchanged blobs reuse prior actual complete downloads only after exact blob/path/size match", "Base proof is not original-byte readback")
    require(base["new_originals_actually_downloaded"] == 9 and base["unchanged_original_proofs_reused"] == 7411, "Base proof reuse boundaries differ")
    require(importer.git(worktree, "merge-base", "--is-ancestor", base["commit"], commit) == "", "Base commit is not an ancestor of the fixed commit")
    tree = {}
    for line in importer.git(worktree, "ls-tree", "-r", "-l", commit, "--", "mod_nailong/assets/generated_fullsize").splitlines():
        header, relative = line.split("\t", 1)
        mode, kind, blob, size = header.split()
        require(mode == "100644" and kind == "blob", f"Unexpected original file object: {relative}")
        tree[relative] = {"git_blob_sha1": blob, "bytes": int(size)}
    require(set(tree) == {row["path"] for row in index["outputs"].values()}, "Fixed commit original files differ from the index")
    outputs, new_downloads, reused = {}, [], []
    for digest, entry in sorted(index["outputs"].items()):
        relative = entry["path"]
        current = tree[relative]
        require(current["bytes"] == entry["bytes"], f"Git blob size differs: {relative}")
        if digest in base["outputs"]:
            previous = base["outputs"][digest]
            require(previous["path"] == relative and previous["sha256"] == digest and previous["bytes"] == entry["bytes"], f"Previous proof identity differs: {digest}")
            require(previous["git_blob_sha1"] == current["git_blob_sha1"], f"Blob changed; previous download cannot be reused: {digest}")
            require(previous["method"] == "Complete anonymous raw PNG download; SHA256 and byte count", f"Previous proof is not a complete raw download: {digest}")
            require(previous.get("readback_commit") or previous.get("verified_at_utc"), f"Previous proof has no verified time or commit: {digest}")
            row = {**copy.deepcopy(previous), "unchanged_blob_confirmed_at_commit": commit, "verification_reused_after_exact_blob_match": True}
            reused.append(digest)
        else:
            url = f"https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{commit}/{relative}"
            proof = download_png({"url": url, "sha256": digest, "cache_name": f"final-{commit}-{digest}.png"})
            require(proof["bytes"] == entry["bytes"], f"Remote PNG byte count differs: {digest}")
            row = {
                "path": relative, "bytes": entry["bytes"], "sha256": digest, **current,
                "url": url, "readback_commit": commit, "verified_at_utc": proof["readback_at_utc"],
                "method": "Complete anonymous raw PNG download; SHA256 and byte count",
            }
            new_downloads.append(digest)
        outputs[digest] = row
    expected_new = {row["output_sha256"] for row in read_json(worktree / "mod_nailong/experiments/evolink-low2-20261030/outputs-index.json")["entries"]}
    require(set(new_downloads) == expected_new, f"Actual new downloads do not equal the {len(expected_new)} scoped new original files")
    receipt = {
        "schema": "low2-fullsize-remote-readback-v1", "machine_id": machine_id(),
        "observed_at_utc": utc_now(), "status": "verified", "commit": commit, "remote_master_observed": remote,
        "verification": "Fixed-commit Git blob SHA/size checks for all outputs; new originals downloaded completely with SHA256/byte verification; unchanged blobs reuse prior actual complete downloads only after exact blob/path/size match",
        "base_proof": BASE_PROOF.relative_to(ROOT).as_posix(), "base_proof_sha256": file_sha256(BASE_PROOF),
        "base_commit": base["commit"], "base_distinct_outputs": base["distinct_outputs"],
        "distinct_outputs": len(outputs), "original_png_bytes": sum(row["bytes"] for row in outputs.values()),
        "new_originals_actually_downloaded": len(new_downloads), "new_download_sha256": new_downloads,
        "unchanged_original_proofs_reused": len(reused), "all_current_originals_redownloaded": False,
        "outputs": outputs,
    }
    require(receipt["distinct_outputs"] == index["count"] and receipt["original_png_bytes"] == index["original_png_bytes"], "Readback totals differ from index")
    write_json(RECEIPT, receipt)
    print(json.dumps({key: value for key, value in receipt.items() if key != "outputs"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
