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

BASE_PROOF = ROOT / "runtime/high131-final-delivery-readback-checkpoint.json"
RECEIPT = ROOT / "runtime/low7-evolink-20261030/remote-readback.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: low7_remote_verify.py WORKTREE COMMIT")
    worktree = Path(sys.argv[1]).resolve()
    commit = sys.argv[2]
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "Expected a full fixed commit")
    importer = importlib.import_module("mod_nailong.experiments.evolink-low7-20261030.tools.low7_import")
    importer.git(worktree, "fetch", "origin")
    remote = importer.git(worktree, "rev-parse", "origin/master")
    require(commit == remote or importer.git(worktree, "merge-base", "--is-ancestor", commit, remote) == "", "Fixed commit is not public on origin/master")
    index = read_json(worktree / "mod_nailong/data/fullsize-files.json")
    base = read_json(BASE_PROOF)
    require(base.get("schema") == "naiwa-fullsize-git-checkpoint-v1", "Base proof schema missing")
    require(base["machine_id"] == machine_id() and base["commit"] == "c050f3a8dcfad66adeb9ccae1ed4ff89a1da721f", "Base proof identity differs")
    require(base["distinct_outputs"] == len(base["outputs"]) == 7411, "Base proof is incomplete")
    require(base["verification"] == "Remote Git tree blob SHA/size match plus complete anonymous raw PNG download SHA256/size for every output; unchanged blobs may retain their earlier pinned readback commit/time", "Base proof is not original-byte readback")
    tree = {}
    for line in importer.git(worktree, "ls-tree", "-r", "-l", commit, "--", "mod_nailong/assets/generated_fullsize").splitlines():
        header, relative = line.split("\t", 1)
        mode, kind, blob, size = header.split()
        require(mode == "100644" and kind == "blob", f"Unexpected original file object: {relative}")
        tree[relative] = {"git_blob_sha1": blob, "bytes": int(size)}
    require(set(tree) == {row["path"] for row in index["outputs"].values()}, "Fixed commit original files differ from the index")
    outputs = {}
    new_downloads = []
    reused = []
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
            proof = prepare.download_public({"url": url, "sha256": digest, "cache_name": f"final-{commit}-{digest}.png"})
            require(proof["bytes"] == entry["bytes"], f"Remote PNG byte count differs: {digest}")
            row = {
                "path": relative, "bytes": entry["bytes"], "sha256": digest, **current,
                "url": url, "readback_commit": commit, "verified_at_utc": proof["readback_at_utc"],
                "method": "Complete anonymous raw PNG download; SHA256 and byte count",
            }
            new_downloads.append(digest)
        outputs[digest] = row
    expected_new = {row["output_sha256"] for row in read_json(worktree / "mod_nailong/experiments/evolink-low7-20261030/outputs-index.json")["entries"]}
    expected_new.add("fca9eca6c6b5bfc340b9b931f88abc0b1af0a23cb870fadd823eb6663d1b6614")
    require(set(new_downloads) == expected_new, "Actual new downloads do not equal the ten scoped new original files")
    receipt = {
        "schema": "low7-fullsize-remote-readback-v1", "machine_id": machine_id(),
        "observed_at_utc": utc_now(), "status": "verified", "commit": commit, "remote_master_observed": remote,
        "verification": "Fixed-commit Git blob SHA/size checks for all outputs; new originals downloaded completely with SHA256/byte verification; unchanged blobs reuse prior actual complete downloads only after exact blob/path/size match",
        "base_proof": str(BASE_PROOF.relative_to(ROOT)), "base_proof_sha256": file_sha256(BASE_PROOF),
        "distinct_outputs": len(outputs), "original_png_bytes": sum(row["bytes"] for row in outputs.values()),
        "new_originals_actually_downloaded": len(new_downloads), "new_download_sha256": new_downloads,
        "unchanged_original_proofs_reused": len(reused),
        "all_current_originals_redownloaded": False,
        "outputs": outputs,
    }
    require(receipt["distinct_outputs"] == index["count"] and receipt["original_png_bytes"] == index["original_png_bytes"], "Readback totals differ from index")
    write_json(RECEIPT, receipt)
    print(json.dumps({key: value for key, value in receipt.items() if key != "outputs"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
