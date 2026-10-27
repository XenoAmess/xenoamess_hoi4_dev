import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from tools.common import ROOT, file_sha256, machine_id, read_json

TARGET_PROOF_SCHEMA = "high131-hd-target-readback-v1"
TARGET_PROOF_METHOD = "Complete anonymous raw PNG download; SHA256 and byte count"
NOTE_DETAIL_MODE = "raw-hd-edit-note-detail-v1"
MASK_NOTE_MODE = "raw-hd-mask-note-v1"
HD_INPUT_MODES = frozenset({"raw-hd-edit-v1", NOTE_DETAIL_MODE, MASK_NOTE_MODE})
NOTE_DETAIL_DIR = "mod_nailong/experiments/evolink-high131-flare-20261025/review-source-details"
NOTE_MASK_DIR = "mod_nailong/experiments/evolink-high131-flare-20261025/review-masks"
SOURCE_DETAIL_METHOD = "source-crop-resize-nearest-v1"


def mask_revision_suffix(revision):
    if type(revision) is not int or revision < 1:
        raise RuntimeError("Mask revision must be a positive integer")
    return "" if revision == 1 else f"-v{revision}"


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


def validate_remote_mask(proof, commit, mask_path, digest, target_path, target_digest, root=ROOT):
    root = Path(root)
    require(proof.get("schema") == TARGET_PROOF_SCHEMA and proof.get("complete_archive_verified") is False, "Inpainting masks require an explicit target-scoped proof")
    validate_remote_target(proof, commit, target_path, target_digest, root=root)
    candidate = Path(mask_path).resolve()
    candidate.relative_to((root / NOTE_MASK_DIR).resolve())
    relative = candidate.relative_to(root.resolve()).as_posix()
    require(file_sha256(candidate) == digest, "Inpainting mask bytes differ from their SHA")
    with candidate.open("rb") as stream:
        require(stream.read(8) == b"\x89PNG\r\n\x1a\n", "Inpainting mask lacks a PNG signature")
    record = proof["targets"].get(digest)
    url = f"https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{commit}/{relative}"
    require(isinstance(record, dict), "Target-scoped proof lacks this inpainting mask")
    require(record.get("path") == relative and record.get("sha256") == digest, "Mask proof path or SHA differs")
    require(record.get("bytes") == candidate.stat().st_size, "Mask proof byte count differs")
    require(record.get("url") == url and record.get("readback_commit") == commit, "Mask proof URL or commit differs")
    require(record.get("method") == TARGET_PROOF_METHOD and record.get("verified_at_utc"), "Mask proof lacks complete byte verification")
    require(record.get("remote_tree_blob_match") is True and record.get("local_original_matches") is True and record.get("png_signature_verified") is True, "Mask proof lacks tree/local/PNG checks")
    require(record.get("role") == "inpainting-mask" and record.get("not_generated_or_game_payload") is True, "Mask proof has an invalid reference role")
    require(record.get("target_sha256") == target_digest and record.get("no_generated_master_pixels_modified") is True, "Mask proof is not bound to the exact rejected target")
    manifest_value = record.get("mask_manifest")
    require(isinstance(manifest_value, str) and not Path(manifest_value).is_absolute(), "Mask proof lacks a repository-relative visual-review manifest")
    manifest_path = (root / manifest_value).resolve()
    manifest_path.relative_to((root / "mod_nailong/experiments/evolink-high131-flare-20261025").resolve())
    require(file_sha256(manifest_path) == record.get("mask_manifest_sha256"), "Mask visual-review manifest bytes differ from the remote proof")
    manifest = read_json(manifest_path)
    require(manifest.get("schema") == "high131-note-inpainting-mask-v1" and manifest.get("machine_id") == machine_id(), "Mask manifest has an invalid schema or machine")
    require(manifest.get("status") == "mask_visually_verified", "Mask requires actual visual review before use")
    require(isinstance(manifest.get("reviewer"), str) and manifest["reviewer"].strip(), "Mask lacks its actual reviewer")
    require(isinstance(manifest.get("reviewed_at_utc"), str) and manifest["reviewed_at_utc"], "Mask lacks its review time")
    require(manifest.get("mask_file") == relative and manifest.get("mask_sha256") == digest, "Mask manifest path or SHA differs")
    require(manifest.get("target_sha256") == target_digest and manifest.get("no_generated_master_pixels_modified") is True, "Mask manifest differs from the rejected target")
    preview_path = (root / manifest.get("preview_file", "")).resolve()
    preview_path.relative_to((root / NOTE_MASK_DIR).resolve())
    require(file_sha256(preview_path) == manifest.get("preview_sha256"), "Mask preview differs from the reviewed overlay")
    rects = manifest.get("rects")
    require(isinstance(rects, list) and rects, "Mask lacks its reviewed edit rectangles")
    with Image.open(target_path) as target_image, Image.open(candidate) as mask_image, Image.open(preview_path) as preview_image:
        require(target_image.size == mask_image.size == preview_image.size, "Mask, preview and rejected target dimensions differ")
        require(mask_image.mode == preview_image.mode == "RGBA", "Mask and preview must be RGBA")
        expected_mask = Image.new("RGBA", target_image.size, (0, 0, 0, 255))
        overlay = Image.new("RGBA", target_image.size, (0, 0, 0, 0))
        mask_draw = ImageDraw.Draw(expected_mask)
        overlay_draw = ImageDraw.Draw(overlay)
        for rect in rects:
            require(isinstance(rect, (list, tuple)) and len(rect) == 4 and all(type(value) is int for value in rect), "Mask rectangle is not four integer coordinates")
            left, top, right, bottom = rect
            require(0 <= left <= right < mask_image.width and 0 <= top <= bottom < mask_image.height, "Mask rectangle lies outside the rejected target")
            mask_draw.rectangle(rect, fill=(0, 0, 0, 0))
            overlay_draw.rectangle(rect, fill=(255, 0, 0, 90))
        require(mask_image.tobytes() == expected_mask.tobytes(), "Mask pixels differ from their declared edit rectangles")
        expected_preview = Image.alpha_composite(target_image.convert("RGBA"), overlay)
        require(preview_image.tobytes() == expected_preview.tobytes(), "Reviewed mask preview differs from the rejected target and edit rectangles")
        alpha = mask_image.getchannel("A")
        extrema = list(alpha.getextrema())
        histogram = alpha.histogram()
        require(extrema == [0, 255] and histogram[0] + histogram[255] == mask_image.width * mask_image.height, "Mask alpha must contain both 0 and 255 with no intermediate values")
        require(histogram[0] > 0, "Mask must contain a nonempty edit region")
        for value in (record, manifest):
            require(value.get("size") == list(mask_image.size) and value.get("mode") == "RGBA", "Mask proof dimensions or mode differs")
            require(value.get("rects") == rects and value.get("alpha_extrema") == extrema, "Mask proof rectangles or alpha extrema differ")
            require(value.get("transparent_pixels") == histogram[0] and value.get("opaque_pixels") == histogram[255], "Mask proof alpha counts differ")
    return url
