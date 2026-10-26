import json
import subprocess
from pathlib import Path

from PIL import Image

from tools.common import ROOT, file_sha256, machine_id, read_json

TARGET_PROOF_SCHEMA = "high131-hd-target-readback-v1"
TARGET_PROOF_METHOD = "Complete anonymous raw PNG download; SHA256 and byte count"
NOTE_DETAIL_MODE = "raw-hd-edit-note-detail-v1"
HD_INPUT_MODES = frozenset({"raw-hd-edit-v1", NOTE_DETAIL_MODE})
NOTE_DETAIL_DIR = "mod_nailong/experiments/evolink-high131-flare-20261025/review-source-details"
SOURCE_DETAIL_METHOD = "source-crop-resize-nearest-v1"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def load_remote_proof(commit, path, root=ROOT):
    root = Path(root)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    candidate.relative_to((root / "runtime").resolve())
    proof = read_json(candidate)
    require(proof.get("status") == "verified", "Remote original proof is not verified")
    require(proof.get("commit") == commit and proof.get("machine_id") == machine_id(), "Remote original proof does not match this machine and commit")
    if proof.get("schema") == TARGET_PROOF_SCHEMA:
        require(proof.get("complete_archive_verified") is False, "A target-scoped proof must not claim complete archive verification")
        require(isinstance(proof.get("targets"), dict), "Target-scoped proof lacks its target records")
        return proof, None
    result = subprocess.run(
        ["git", "show", f"{commit}:mod_nailong/data/fullsize-files.json"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    require(result.returncode == 0, "Unable to read the pinned fullsize index")
    try:
        index = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Pinned fullsize index is invalid") from exc
    require(proof.get("distinct_outputs") == index.get("count") and proof.get("original_png_bytes") == index.get("original_png_bytes"), "Remote original proof does not match the pinned index")
    return proof, index


def validate_remote_target(proof, commit, master_path, digest, index=None, root=ROOT):
    root = Path(root)
    candidate = Path(master_path).resolve()
    candidate.relative_to((root / "mod_nailong/assets/generated_fullsize").resolve())
    relative = candidate.relative_to(root.resolve()).as_posix()
    require(file_sha256(candidate) == digest, "Raw-HD edit target differs from the rejected output bytes")
    url = f"https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{commit}/{relative}"
    if proof.get("schema") == TARGET_PROOF_SCHEMA:
        record = proof["targets"].get(digest)
        require(isinstance(record, dict), "Target-scoped proof does not cover this raw-HD edit target")
        require(record.get("path") == relative and record.get("sha256") == digest, "Target-scoped proof path or SHA differs")
        require(record.get("bytes") == candidate.stat().st_size, "Target-scoped proof byte count differs")
        require(record.get("url") == url and record.get("readback_commit") == commit, "Target-scoped proof URL or commit differs")
        require(record.get("method") == TARGET_PROOF_METHOD and record.get("verified_at_utc"), "Target-scoped proof lacks complete byte verification")
        require(record.get("remote_tree_blob_match") is True and record.get("local_original_matches") is True and record.get("png_signature_verified") is True, "Target-scoped proof lacks its tree/local/PNG checks")
    else:
        require(index is not None, "Full original proof lacks its pinned index")
        indexed = index.get("outputs", {}).get(digest)
        require(isinstance(indexed, dict) and indexed.get("path") == relative and indexed.get("bytes") == candidate.stat().st_size, "Raw-HD target is not covered by the verified remote index")
    return url


def validate_remote_reference(proof, commit, reference_path, digest, source_path, root=ROOT):
    root = Path(root)
    require(proof.get("schema") == TARGET_PROOF_SCHEMA and proof.get("complete_archive_verified") is False, "Source-detail references require an explicit target-scoped proof")
    candidate = Path(reference_path).resolve()
    candidate.relative_to((root / NOTE_DETAIL_DIR).resolve())
    relative = candidate.relative_to(root.resolve()).as_posix()
    require(file_sha256(candidate) == digest, "Source-detail reference bytes differ from their SHA")
    source = Path(source_path).resolve()
    source.relative_to((root / "runtime/references").resolve())
    record = proof["targets"].get(digest)
    url = f"https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{commit}/{relative}"
    require(isinstance(record, dict), "Target-scoped proof lacks this source-detail reference")
    require(record.get("path") == relative and record.get("sha256") == digest, "Source-detail proof path or SHA differs")
    require(record.get("bytes") == candidate.stat().st_size, "Source-detail proof byte count differs")
    require(record.get("url") == url and record.get("readback_commit") == commit, "Source-detail proof URL or commit differs")
    require(record.get("method") == TARGET_PROOF_METHOD and record.get("verified_at_utc"), "Source-detail proof lacks complete byte verification")
    require(record.get("remote_tree_blob_match") is True and record.get("local_original_matches") is True and record.get("png_signature_verified") is True, "Source-detail proof lacks tree/local/PNG checks")
    require(record.get("role") == "source-note-detail-reference" and record.get("not_generated_or_game_payload") is True, "Source-detail proof has an invalid reference role")
    derivation = record.get("derivation", {})
    require(derivation.get("source_png_sha256") == file_sha256(source), "Source-detail proof does not bind the exact original source")
    rect = derivation.get("crop_rect")
    scale = derivation.get("scale")
    require(derivation.get("method") == SOURCE_DETAIL_METHOD and derivation.get("derivative_reviewed") is True, "Source-detail reference lacks its source derivation or actual visual review")
    with Image.open(source) as source_image, Image.open(candidate) as detail_image:
        require(isinstance(rect, (list, tuple)) and len(rect) == 4 and all(type(value) is int for value in rect), "Source-detail crop is not four integer coordinates")
        left, top, right, bottom = rect
        require(0 <= left < right <= source_image.width and 0 <= top < bottom <= source_image.height, "Source-detail crop lies outside the original image")
        require(type(scale) is int and 1 <= scale <= 32, "Source-detail scale is invalid")
        expected = source_image.convert("RGBA").crop(rect).resize(((right - left) * scale, (bottom - top) * scale), Image.Resampling.NEAREST)
        require(detail_image.convert("RGBA").tobytes() == expected.tobytes(), "Source-detail pixels differ from the exact source crop and nearest-neighbor enlargement")
        require(list(detail_image.size) == record.get("size") and detail_image.mode == record.get("mode"), "Source-detail proof dimensions or mode differs")
    return url
