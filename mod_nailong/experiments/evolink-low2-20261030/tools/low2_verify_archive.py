import json
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from mod_nailong.tools import master_archive, master_files
from tools.common import file_sha256, machine_id, read_json, utc_now, write_json


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    index = read_json(ROOT / "mod_nailong/data/fullsize-files.json")
    expected, _current, _provenance = master_archive.recorded_outputs(ROOT / "mod_nailong")
    expected.update(read_json(ROOT / "mod_nailong/data/fullsize-files.json")["outputs"])
    expected.update(row["output_sha256"] for row in read_json(ROOT / "mod_nailong/experiments/evolink-low2-20261030/outputs-index.json")["entries"])
    require(set(index["outputs"]) == expected, "Complete original index differs from the retained original set")
    require(index["schema"] == "naiwa-fullsize-git-files-v1" and index["storage"] == "ordinary Git blobs containing original PNG bytes", "Original storage differs")
    require(index["count"] == len(index["outputs"]) and index["original_png_bytes"] == sum(row["bytes"] for row in index["outputs"].values()), "Original index totals differ")
    for digest, entry in sorted(index["outputs"].items()):
        path = ROOT / entry["path"]
        require(entry["path"] == master_files.master_path(digest), f"Unexpected original path: {digest}")
        require(path.is_file() and file_sha256(path) == digest, f"Local original bytes differ: {digest}")
        require(path.stat().st_size == entry["bytes"], f"Local original size differs: {digest}")
        with Image.open(path) as image:
            require(list(image.size) == entry["size"] and image.mode == entry["mode"], f"Original PNG metadata differs: {digest}")
            image.verify()
    commit, blobs = master_files.verify_tree("HEAD", root=ROOT, index=index)
    result = {"commit": commit, "verified_original_png_blobs": len(blobs), "original_png_bytes": index["original_png_bytes"]}
    require(result["verified_original_png_blobs"] == index["count"] and result["original_png_bytes"] == index["original_png_bytes"], "Git blob verification totals differ")
    write_json(ROOT / "runtime/low2-evolink-20261030/local-original-verification.json", {
        "schema": "low2-local-original-verification-v1", "machine_id": machine_id(), "observed_at_utc": utc_now(),
        **result, "local_original_files_sha256_and_size_verified": len(index["outputs"]),
        "retained_rejected_originals_not_dropped": True,
        "verification": "Every indexed local PNG file SHA256/size and every committed Git blob SHA256/size, including all retained rejected originals",
        "remote_verification_claimed": False, "runtime_acceptance_claimed": False,
    })
    print(result)


if __name__ == "__main__":
    main()
