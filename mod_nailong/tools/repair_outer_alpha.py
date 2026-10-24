import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f'Refusing to overwrite existing output: {args.output}')
    with Image.open(args.source) as source, Image.open(args.base) as base:
        source_alpha = source.convert('RGBA').getchannel('A')
        base_rgb = base.convert('RGB')
        source_size = list(source.size)
        base_size = list(base_rgb.size)
        source_mode = source.mode
        base_mode = base.mode
        source_corners = [source_alpha.getpixel((x, y)) for x, y in ((0, 0), (source_alpha.width - 1, 0), (0, source_alpha.height - 1), (source_alpha.width - 1, source_alpha.height - 1))]
        resized_alpha = source_alpha.resize(base_rgb.size, Image.Resampling.BILINEAR)
        repaired = base_rgb.convert('RGBA')
        repaired.putalpha(resized_alpha)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        repaired.save(args.output, format='PNG')
        resized_corners = [resized_alpha.getpixel((x, y)) for x, y in ((0, 0), (resized_alpha.width - 1, 0), (0, resized_alpha.height - 1), (resized_alpha.width - 1, resized_alpha.height - 1))]
        alpha_bytes = resized_alpha.tobytes()
        rgb_bytes = base_rgb.tobytes()
    with Image.open(args.output) as check:
        rgb_unchanged = check.convert('RGB').tobytes() == rgb_bytes
        alpha_matches = check.getchannel('A').tobytes() == alpha_bytes
        output_corners = [check.getchannel('A').getpixel((x, y)) for x, y in ((0, 0), (check.width - 1, 0), (0, check.height - 1), (check.width - 1, check.height - 1))]
        output_mode = check.mode
    if not rgb_unchanged or not alpha_matches:
        raise SystemExit('Repair verification failed')
    print(json.dumps({
        'method': 'source-alpha-resize-bilinear-rgb-unchanged-v1',
        'source': str(args.source),
        'base': str(args.base),
        'output': str(args.output),
        'source_sha256': sha256(args.source),
        'base_sha256': sha256(args.base),
        'output_sha256': sha256(args.output),
        'source_size': source_size,
        'base_size': base_size,
        'source_mode': source_mode,
        'base_mode': base_mode,
        'output_mode': output_mode,
        'source_corner_alpha_tl_tr_bl_br': source_corners,
        'resized_corner_alpha_tl_tr_bl_br': resized_corners,
        'output_corner_alpha_tl_tr_bl_br': output_corners,
        'resized_alpha_sha256': hashlib.sha256(alpha_bytes).hexdigest(),
        'rgb_unchanged': rgb_unchanged,
        'alpha_matches_resized_source': alpha_matches,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
