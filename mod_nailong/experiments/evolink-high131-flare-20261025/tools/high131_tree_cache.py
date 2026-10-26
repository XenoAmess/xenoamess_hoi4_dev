import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from mod_nailong.tools import master_git_remote
from runtime.high131_io import write_json
from tools.common import ROOT, machine_id, read_json, utc_now


def install_local_tree_cache():
    if os.environ.get("XAR_HIGH131_TREE_CACHE") != "1":
        return None
    original = master_git_remote.verify_tree
    state = {"reused": False, "method": "master_files.verify_tree streaming SHA256 and byte-count checks"}

    def cached_verify_tree(commit="HEAD", root=ROOT, index=None):
        if index is None:
            return original(commit, root=root, index=index)
        full_commit = subprocess.check_output(["git", "rev-parse", commit + "^{commit}"], cwd=root, text=True).strip()
        index_sha = hashlib.sha256(json.dumps(index, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        path = ROOT / "runtime/high131-local-tree-proofs" / f"{full_commit}.json"
        state["path"] = path.relative_to(ROOT).as_posix()
        state["index_sha256"] = index_sha
        if path.exists():
            proof = read_json(path)
            valid = (
                proof.get("schema") == "high131-local-tree-proof-v1"
                and proof.get("status") == "verified"
                and proof.get("machine_id") == machine_id()
                and proof.get("commit") == full_commit
                and proof.get("index_sha256") == index_sha
                and proof.get("distinct_outputs") == index["count"]
                and proof.get("original_png_bytes") == index["original_png_bytes"]
                and set(proof.get("blobs", {})) == set(index["outputs"])
                and all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) for value in proof.get("blobs", {}).values())
            )
            if not valid:
                raise ValueError(f"Local tree proof is invalid for this machine, commit and index: {path}")
            state.update(reused=True, verified_at_utc=proof["verified_at_utc"])
            return full_commit, proof["blobs"]
        actual_commit, blobs = original(commit, root=root, index=index)
        if actual_commit != full_commit or len(blobs) != index["count"]:
            raise RuntimeError("Local tree verification did not return the expected complete commit and blob set")
        verified_at = utc_now()
        write_json(path, {
            "schema": "high131-local-tree-proof-v1",
            "status": "verified",
            "machine_id": machine_id(),
            "commit": full_commit,
            "index_sha256": index_sha,
            "distinct_outputs": index["count"],
            "original_png_bytes": index["original_png_bytes"],
            "blobs": blobs,
            "verified_at_utc": verified_at,
            "method": state["method"],
            "scope": "Reuse only for the same machine, immutable commit and normalized committed index. Remote tree metadata and every original PNG byte are still verified independently.",
        })
        state["verified_at_utc"] = verified_at
        return actual_commit, blobs

    master_git_remote.verify_tree = cached_verify_tree
    return state
