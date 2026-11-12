"""Read-only byte and editorial-policy binding for this project's clip index.

Index/type/duration guards partially follow the locally reviewed model candidate.
Owner correction delegates normalized paths and both file bindings to xAR. This
verifies references; it never grants visual acceptance or film signoff.
"""
import json
import math
from pathlib import Path

from xar_promo.capture import CaptureFile, CaptureReceipt, load_capture_receipt


def load_capture_index(project_root: Path, index_path: Path,
                       expected_casting_policy: dict) -> dict[str, CaptureReceipt]:
    root = project_root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError('project_root does not exist')
    path = index_path.expanduser().resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('index must be a file beneath project_root')
    with path.open('rb') as stream:
        data = stream.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError('index exceeds 1MiB')
    payload = json.loads(data.decode('utf-8-sig'))
    if not isinstance(payload, dict) or payload.get('schema') != 'gangnailongxin-capture-index-v1':
        raise ValueError('unsupported capture index')
    if payload.get('casting_policy') != expected_casting_policy:
        raise ValueError('casting_policy mismatch')
    clips = payload.get('clips')
    if not isinstance(clips, list) or not clips:
        raise ValueError('clips must be a nonempty list')
    result = {}
    for row in clips:
        if not isinstance(row, dict):
            raise ValueError('clip row must be an object')
        key = row.get('clip_id')
        if not isinstance(key, str) or not key.strip() or key in result:
            raise ValueError('clip_id is empty or duplicated')
        duration = row.get('duration_seconds')
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise ValueError('duration must be a number')
        try:
            duration = float(duration)
        except OverflowError as exc:
            raise ValueError('duration exceeds finite range') from exc
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError('duration must be finite and positive')
        raw = CaptureFile.from_mapping(row.get('raw'), project_root=root, context='index.raw')
        binding = CaptureFile.from_mapping(row.get('capture_receipt'), project_root=root,
                                           context='index.capture_receipt')
        receipt = load_capture_receipt(binding.path, project_root=root)
        receipt.verify_unchanged()
        if (receipt.raw_capture.relative_path, receipt.raw_capture.bytes, receipt.raw_capture.sha256) != (
                raw.relative_path, raw.bytes, raw.sha256):
            raise ValueError('index raw binding disagrees with capture receipt')
        if not math.isclose(receipt.duration_seconds, duration, rel_tol=0, abs_tol=1e-6):
            raise ValueError('index duration disagrees with capture receipt')
        result[key] = receipt
    return result
