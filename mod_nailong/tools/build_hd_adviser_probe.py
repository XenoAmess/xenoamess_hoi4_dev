"""Build a development-only adviser sprite adapter without resampling its texture."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PIL import Image
from tools.common import ROOT, file_sha256, game_root, machine_id, read_json, utc_now, write_json
from mod_nailong.tools.build_release import build, verify

KEY = '53b8774127c8c87cb52ccdd571dc4c801273aa818f2aaba991943fb16cf4fdaa'
ALIASES = ('GFX_portrait_USA_william_halsey_jr_small', 'GFX_idea_USA_william_halsey_jr')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=['cornered-tile', 'masking-hd-sampler'], default='cornered-tile')
    args = parser.parse_args()
    manifest = build(args.output, preview=True, validation_keys={KEY})
    assert len(manifest['bindings']) == 1
    binding = manifest['bindings'][0]
    width, height = binding['original_game_size']
    assert (width, height) == (65, 67)
    texture = args.output / 'staging' / binding['path']
    master_row = read_json(ROOT / 'mod_nailong/data/generated.json')['portraits'][KEY]
    master = ROOT / master_row['generated_fullsize_image']
    with Image.open(master) as original, Image.open(texture) as encoded:
        assert original.size == encoded.size
        assert original.convert('RGBA').tobytes() == encoded.convert('RGBA').tobytes()
    # Verify both native aliases really address this same virtual texture.
    sources = ['interface/_leader_portraits.gfx', 'interface/ideas_characters.gfx']
    import re
    for alias, rel in zip(ALIASES, sources):
        text = (game_root() / rel).read_text(encoding='utf-8-sig')
        pattern = r'name\s*=\s*"?' + re.escape(alias) + r'"?\s+texturefile\s*=\s*"' + re.escape(binding['path']) + r'"'
        assert re.search(pattern, text, flags=re.IGNORECASE), (alias, rel)
    chunks = ['spriteTypes = {']
    carrier_relative = None
    if args.mode == 'masking-hd-sampler':
        carrier_relative = f'gfx/interface/naiwa_white_layout_{width}_{height}.dds'
        carrier = args.output / 'staging' / carrier_relative
        carrier.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGBA', (width, height), (255, 255, 255, 255)).save(carrier, format='DDS')
        effect_relative = 'gfx/FX/naiwa_hd_masking_sampler.shader'
        effect = args.output / 'staging' / effect_relative
        effect.parent.mkdir(parents=True, exist_ok=True)
        effect.write_bytes((ROOT / 'mod_nailong/assets/runtime/hd_portrait_masking_sampler.shader').read_bytes())
        for rel, item in [(carrier_relative, carrier), (effect_relative, effect)]:
            manifest['files'].append({'path': rel, 'bytes': item.stat().st_size, 'sha256': file_sha256(item)})
    for alias in ALIASES:
        if args.mode == 'masking-hd-sampler':
            chunks.append(f''' spriteType = {{
  name = "{alias}"
  texturefile = "{carrier_relative}"
  masking_texture = "{binding['path']}"
  effectFile = "gfx/FX/naiwa_hd_masking_sampler.lua"
  noOfFrames = 1
  legacy_lazy_load = no
 }}''')
        else:
            chunks.append(f''' corneredTileSpriteType = {{
  name = "{alias}"
  texturefile = "{binding['path']}"
  size = {{ x = {width} y = {height} }}
  borderSize = {{ x = 0 y = 0 }}
  tilingCenter = no
 }}''')
    chunks.append('}')
    relative = 'interface/zz_naiwa_hd_adviser_probe.gfx'
    target = args.output / 'staging' / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('\n'.join(chunks) + '\n', encoding='utf-8', newline='\n')
    manifest['files'].append({'path': relative, 'bytes': target.stat().st_size, 'sha256': file_sha256(target)})
    manifest['files'].sort(key=lambda row: row['path'])
    manifest['development_fixture'] = {
        'kind': f'Unqualified adviser {args.mode} logical size experiment',
        'source_sha256': KEY, 'aliases': list(ALIASES), 'logical_size': [width, height],
        'hd_raster_unchanged': True, 'hd_pixel_readback_identical': True,
        'layout_carrier_contains_no_portrait_pixels': carrier_relative is not None,
        'formal_release_eligible': False, 'gui_or_gameplay_changes': False,
        'native_binding_sources': [{'path': str(game_root() / rel), 'sha256': file_sha256(game_root() / rel)} for rel in sources],
        'acceptance': 'Not run. Must inspect real Chief of Navy picker, binding, layout and usable close button; this does not qualify other portrait classes.'
    }
    write_json(args.output / 'manifest.json', manifest)
    with zipfile.ZipFile(args.output / 'naiwa-world.zip', 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for row in manifest['files']:
            info = zipfile.ZipInfo(row['path'], date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, (args.output / 'staging' / row['path']).read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    verify(args.output)
    write_json(args.output / 'build-receipt.json', {
        'machine_id': machine_id(), 'observed_at_utc': utc_now(),
        'source': 'build_hd_adviser_probe.py + exact master/DDS RGBA readback + manifest/ZIP verification',
        'preview': True, 'live_acceptance': 'not-run', 'hd_raster_resized': False
    })
    print('Built unchanged fullsize adviser texture with an unqualified 65x67 logical display adapter')


if __name__ == '__main__':
    main()
