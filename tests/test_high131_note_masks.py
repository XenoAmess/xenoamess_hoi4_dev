from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from runtime import high131_hd_proof as hd_proof
from runtime import high131_prepare_hd_repairs as hd_repairs
from runtime import high131_prepare_note_masks as prepare
from runtime import high131_run_repairs as repairs
from runtime import high131_verify_records as verify
from tools.common import ROOT, file_sha256, machine_id, read_json, write_json


class NoteMaskInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / 'runtime')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.experiment = self.root / 'mod_nailong/experiments/evolink-high131-flare-20261025'
        self.source = self.root / 'runtime/references/source.png'
        self.source.parent.mkdir(parents=True)
        source_image = Image.new('RGBA', (65, 67))
        for y in range(67):
            for x in range(65):
                source_image.putpixel((x, y), ((x * 17) % 256, (y * 19) % 256, ((x + y) * 11) % 256, 255))
        source_image.save(self.source)
        self.source_sha = file_sha256(self.source)
        self.rect = [32, 22, 65, 67]
        self.detail = self.experiment / 'review-source-details/detail.png'
        self.detail.parent.mkdir(parents=True)
        source_image.crop(self.rect).resize((528, 720), Image.Resampling.NEAREST).save(self.detail)
        self.detail_sha = file_sha256(self.detail)
        self.raw = self.root / 'mod_nailong/assets/generated_fullsize/raw.png'
        self.raw.parent.mkdir(parents=True)
        Image.new('RGBA', (16, 16), (12, 34, 56, 255)).save(self.raw)
        self.raw_sha = file_sha256(self.raw)
        mascot = self.root / 'mascot.png'
        mascot.write_bytes(b'mascot fixture')
        self.mascot_sha = file_sha256(mascot)
        self.commit = 'c' * 40
        raw_relative = self.raw.relative_to(self.root).as_posix()
        detail_relative = self.detail.relative_to(self.root).as_posix()
        self.raw_url = self.remote_url(raw_relative)
        self.detail_url = self.remote_url(detail_relative)
        self.mask = self.experiment / 'review-masks/mask.png'
        self.mask.parent.mkdir(parents=True)
        self.preview = self.experiment / 'review-masks/mask-preview.png'
        self.rects = [[3, 4, 10, 8], [2, 10, 12, 12]]
        mask_image = Image.new('RGBA', (16, 16), (0, 0, 0, 255))
        overlay = Image.new('RGBA', (16, 16), (0, 0, 0, 0))
        mask_draw = ImageDraw.Draw(mask_image)
        overlay_draw = ImageDraw.Draw(overlay)
        for rect in self.rects:
            mask_draw.rectangle(rect, fill=(0, 0, 0, 0))
            overlay_draw.rectangle(rect, fill=(255, 0, 0, 90))
        mask_image.save(self.mask)
        with Image.open(self.raw) as raw_image:
            Image.alpha_composite(raw_image.convert('RGBA'), overlay).save(self.preview)
        self.mask_sha = file_sha256(self.mask)
        self.mask_url = self.remote_url(self.mask.relative_to(self.root).as_posix())
        self.manifest_path = self.experiment / 'note-mask-65.json'
        alpha = mask_image.getchannel('A')
        histogram = alpha.histogram()
        self.manifest = {
            'schema': 'high131-note-inpainting-mask-v1',
            'machine_id': machine_id(), 'status': 'mask_visually_verified',
            'reviewer': 'Actual visual review fixture', 'reviewed_at_utc': '2026-01-01T00:00:00Z',
            'index': 65, 'source_sha256': 'a' * 64, 'source_png_sha256': self.source_sha,
            'target_sha256': self.raw_sha, 'target_size': [16, 16],
            'mask_file': self.mask.relative_to(self.root).as_posix(), 'mask_sha256': self.mask_sha,
            'preview_file': self.preview.relative_to(self.root).as_posix(), 'preview_sha256': file_sha256(self.preview),
            'size': [16, 16], 'mode': 'RGBA', 'rects': self.rects,
            'alpha_extrema': [0, 255], 'transparent_pixels': histogram[0], 'opaque_pixels': histogram[255],
            'role': 'inpainting-mask', 'not_generated_or_game_payload': True,
            'no_generated_master_pixels_modified': True,
        }
        write_json(self.manifest_path, self.manifest)
        common = {
            'readback_commit': self.commit,
            'method': 'Complete anonymous raw PNG download; SHA256 and byte count',
            'verified_at_utc': '2026-01-01T00:00:00Z',
            'remote_tree_blob_match': True, 'local_original_matches': True, 'png_signature_verified': True,
        }
        self.proof = {
            'schema': 'high131-hd-target-readback-v1', 'status': 'verified',
            'machine_id': machine_id(), 'commit': self.commit, 'complete_archive_verified': False,
            'targets': {
                self.raw_sha: {
                    **common, 'path': raw_relative, 'bytes': self.raw.stat().st_size,
                    'sha256': self.raw_sha, 'url': self.raw_url,
                },
                self.detail_sha: {
                    **common, 'path': detail_relative, 'bytes': self.detail.stat().st_size,
                    'sha256': self.detail_sha, 'url': self.detail_url,
                    'role': 'source-note-detail-reference', 'not_generated_or_game_payload': True,
                    'size': [528, 720], 'mode': 'RGBA',
                    'derivation': {
                        'source_png_sha256': self.source_sha, 'crop_rect': self.rect,
                        'scale': 16, 'method': 'source-crop-resize-nearest-v1',
                        'derivative_reviewed': True,
                    },
                },
                self.mask_sha: {
                    **common, 'path': self.mask.relative_to(self.root).as_posix(),
                    'bytes': self.mask.stat().st_size, 'sha256': self.mask_sha, 'url': self.mask_url,
                    'role': 'inpainting-mask', 'not_generated_or_game_payload': True,
                    'target_sha256': self.raw_sha, 'no_generated_master_pixels_modified': True,
                    'mask_manifest': self.manifest_path.relative_to(self.root).as_posix(),
                    'mask_manifest_sha256': file_sha256(self.manifest_path),
                    'size': [16, 16], 'mode': 'RGBA', 'rects': self.rects,
                    'alpha_extrema': [0, 255], 'transparent_pixels': histogram[0], 'opaque_pixels': histogram[255],
                },
            },
        }
        write_json(self.root / 'runtime/proof.json', self.proof)
        self.repair = {
            'repair_input_mode': hd_proof.MASK_NOTE_MODE,
            'remote_commit': self.commit, 'remote_readback': 'runtime/proof.json',
            'edit_target_image': raw_relative, 'edit_target_sha256': self.raw_sha,
            'rejected_output_sha256': self.raw_sha, 'remote_target_url': self.raw_url,
            'image_urls': [self.raw_url, 'source-url', 'mascot-url', self.detail_url],
            'ordered_input_sha256': [self.raw_sha, self.source_sha, self.mascot_sha, self.detail_sha],
            'note_detail': {
                'path': detail_relative, 'sha256': self.detail_sha, 'url': self.detail_url,
                'source_png_sha256': self.source_sha,
            },
            'mask_url': self.mask_url,
            'mask': {
                'path': self.mask.relative_to(self.root).as_posix(), 'sha256': self.mask_sha,
                'url': self.mask_url, 'target_sha256': self.raw_sha,
                'manifest': self.manifest_path.relative_to(self.root).as_posix(),
                'manifest_sha256': file_sha256(self.manifest_path),
            },
        }
        self.state = {
            'key': 'a' * 64, 'repair_input_mode': hd_proof.MASK_NOTE_MODE,
            'original_entry': {'converted_png_sha256': self.source_sha, 'source_png': self.source.relative_to(self.root).as_posix()},
            'repair': self.repair,
        }
        self.context = {
            'release_assets': {'a' * 64: {'url': 'source-url'}},
            'scope': {'mascot_reference': {'sha256': self.mascot_sha, 'url': 'mascot-url'}},
        }

    def remote_url(self, relative):
        return f'https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{self.commit}/{relative}'

    def validate_mask(self):
        return hd_proof.validate_remote_mask(
            self.proof, self.commit, self.mask, self.mask_sha, self.raw, self.raw_sha, root=self.root,
        )

    def refresh_manifest_proof(self):
        write_json(self.manifest_path, self.manifest)
        self.proof['targets'][self.mask_sha]['mask_manifest_sha256'] = file_sha256(self.manifest_path)

    def test_mask_geometry_and_repair_contract(self):
        self.assertEqual(self.validate_mask(), self.mask_url)
        with patch.object(repairs.batch, 'ROOT', self.root), patch.object(verify, 'ROOT', self.root):
            inputs, urls = repairs.repair_input_contract(self.context, self.state)
            verified_urls, binding = verify.expected_input_route(
                self.context['scope'],
                {'url': 'source-url', 'converted_png_sha256': self.source_sha},
                self.repair, source_path=self.source,
            )
        self.assertEqual(inputs, self.repair['ordered_input_sha256'])
        self.assertEqual(urls, self.repair['image_urls'])
        self.assertEqual(verified_urls, urls)
        self.assertEqual(binding['mask_sha256'], self.mask_sha)
        self.assertEqual(binding['mask_target_sha256'], self.raw_sha)
        self.assertEqual(binding['mask_url'], self.mask_url)
        self.assertNotIn(self.mask_url, urls)

    def test_pending_visual_review_cannot_authorize_mask(self):
        self.manifest['status'] = 'pending_actual_mask_review'
        self.refresh_manifest_proof()
        with self.assertRaisesRegex(RuntimeError, 'actual visual review'):
            self.validate_mask()

    def test_changed_mask_pixels_are_rejected(self):
        with Image.open(self.mask) as image:
            image.putpixel((0, 0), (0, 0, 0, 127))
            image.save(self.mask)
        old_sha = self.mask_sha
        self.mask_sha = file_sha256(self.mask)
        record = dict(self.proof['targets'][old_sha])
        record.update(sha256=self.mask_sha, bytes=self.mask.stat().st_size)
        self.proof['targets'][self.mask_sha] = record
        self.manifest['mask_sha256'] = self.mask_sha
        self.refresh_manifest_proof()
        with self.assertRaisesRegex(RuntimeError, 'Mask pixels differ'):
            self.validate_mask()

    def test_another_rejected_target_cannot_be_substituted(self):
        self.manifest['target_sha256'] = '0' * 64
        self.refresh_manifest_proof()
        with self.assertRaisesRegex(RuntimeError, 'rejected target'):
            self.validate_mask()

    def test_mask_cannot_expand_into_complete_archive_claim(self):
        self.proof['complete_archive_verified'] = True
        with self.assertRaisesRegex(RuntimeError, 'target-scoped proof'):
            self.validate_mask()

    def test_revision_suffix_rejects_invalid_values(self):
        self.assertEqual(hd_proof.mask_revision_suffix(1), '')
        self.assertEqual(hd_proof.mask_revision_suffix(2), '-v2')
        for revision in (0, -1, True, 1.5, '2', None):
            with self.subTest(revision=revision), self.assertRaisesRegex(RuntimeError, 'positive integer'):
                hd_proof.mask_revision_suffix(revision)

    def test_source67_revision2_binds_current_target_without_overwriting_v1(self):
        key = '322c66462794b3abc2eadf075a7cfed79a583a9b5c3457d17e70359edafeb469'
        targets = {
            1: 'b8aca87eb31dbd9ad81f6324697b096006c07b52a882f3a6c40b438b7a78c284',
            2: 'edcd862ece4a33b8af56b5a8afcd27af88244fdaff9850e79c3a8f2aa462fc77',
            3: '7da660fb19276eb4686ed9a2bfb02542fc40738cfa0ec9a527889cefd6b236a7',
        }
        with tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
            experiment = Path(directory)
            shutil.copyfile(prepare.EXPERIMENT / 'scope.json', experiment / 'scope.json')
            progress = read_json(prepare.EXPERIMENT / 'progress.json')
            progress['entries'] = [row for row in progress['entries'] if row['source_sha256'] == key]
            self.assertEqual(len(progress['entries']), 1)
            for revision in (1, 2, 3):
                progress['entries'][0].update(
                    status='rejected_latest_attempt',
                    current_decision='rejected_for_production',
                    current_review={'review_output_sha256': targets[revision]},
                )
                write_json(experiment / 'progress.json', progress)
                argv = ['high131_prepare_note_masks.py', '--index', '67', '--revision', str(revision)]
                with patch.object(prepare, 'EXPERIMENT', experiment), patch.object(sys, 'argv', argv):
                    prepare.main()
                suffix = hd_proof.mask_revision_suffix(revision)
                manifest = read_json(experiment / f'note-mask-67{suffix}.json')
                target = prepare.MASTER_DIR / f'{targets[revision]}.png'
                self.assertEqual(manifest['index'], 67)
                self.assertEqual(manifest['revision'], revision)
                self.assertEqual(manifest['source_sha256'], key)
                self.assertEqual(manifest['target_sha256'], targets[revision])
                self.assertEqual(manifest['status'], 'pending_actual_mask_review')
                self.assertEqual(manifest['rects'], prepare.MASK_RECTANGLES[(67, revision)])
                self.assertEqual(len(manifest['rects']), 3 if revision == 1 else 2)
                self.assertEqual(manifest['size'], [2048, 2048])
                self.assertEqual(manifest['mode'], 'RGBA')
                self.assertEqual(manifest['alpha_extrema'], [0, 255])
                self.assertEqual(file_sha256(target), manifest['target_sha256'])
                self.assertTrue(manifest['mask_file'].endswith(f'-note-mask{suffix}.png'))
                self.assertTrue(manifest['preview_file'].endswith(f'-note-mask-preview{suffix}.png'))
                mask_path = ROOT / manifest['mask_file']
                preview_path = ROOT / manifest['preview_file']
                self.assertEqual(file_sha256(mask_path), manifest['mask_sha256'])
                self.assertEqual(file_sha256(preview_path), manifest['preview_sha256'])
                with Image.open(mask_path) as image:
                    histogram = image.getchannel('A').histogram()
                self.assertEqual(histogram[0], manifest['transparent_pixels'])
                self.assertEqual(histogram[255], manifest['opaque_pixels'])
                self.assertEqual(sum(histogram[1:255]), 0)
                self.assertEqual(histogram[0] + histogram[255], 2048 * 2048)
                if revision == 1:
                    original_v1 = {
                        'note-mask-67.json': file_sha256(experiment / 'note-mask-67.json'),
                        f'{key}-note-mask.png': file_sha256(mask_path),
                        f'{key}-note-mask-preview.png': file_sha256(preview_path),
                    }
                elif revision == 2:
                    self.assertEqual(manifest['rects'], [[1370, 990, 1510, 1090], [1810, 1120, 1950, 1430]])
                    self.assertEqual(manifest['transparent_pixels'], 141 * 101 + 141 * 311)
                    self.assertEqual(manifest['opaque_pixels'], 2048 * 2048 - 141 * 101 - 141 * 311)
                    self.assertIn('extra independent upper-middle gray bar', manifest['official_contract'])
                    for name, digest in original_v1.items():
                        path = experiment / name if name.endswith('.json') else experiment / 'review-masks' / name
                        self.assertEqual(file_sha256(path), digest)
                if revision == 3:
                    self.assertEqual(manifest['rects'], [[1370, 980, 1730, 1110], [1790, 1100, 1960, 1490]])
                    self.assertEqual(manifest['transparent_pixels'], 361 * 131 + 171 * 391)
                    self.assertEqual(manifest['opaque_pixels'], 2048 * 2048 - 361 * 131 - 171 * 391)
                    self.assertIn('horizontal tab', manifest['official_contract'])
                    for name, digest in original_v1.items():
                        path = experiment / name if name.endswith('.json') else experiment / 'review-masks' / name
                        self.assertEqual(file_sha256(path), digest)
                    v2 = read_json(experiment / 'note-mask-67-v2.json')
                    self.assertEqual(v2['target_sha256'], targets[2])
                    self.assertEqual(file_sha256(experiment / 'review-masks' / f'{key}-note-mask-v2.png'), 'dfe99bbc5f93b62101fa075786d6b4202efd02871072c31f97b931ca54551159')
            with patch.object(prepare, 'EXPERIMENT', experiment), patch.object(sys, 'argv', ['high131_prepare_note_masks.py', '--index', '67', '--revision', '4']):
                with self.assertRaisesRegex(RuntimeError, 'candidates and revisions'):
                    prepare.main()

    def test_source40_mask_binds_rgb_target_and_preserves_tab(self):
        key = '2a6394fc8d1b68a7150b114a47923cac16e60e4931cd49ba82ac2f4982355b79'
        digest = '493566c0afaf43189ac8bf81aada993296c9be38cbe5b19530979e71878303da'
        with tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
            experiment = Path(directory)
            shutil.copyfile(prepare.EXPERIMENT / 'scope.json', experiment / 'scope.json')
            progress = read_json(prepare.EXPERIMENT / 'progress.json')
            progress['entries'] = [row for row in progress['entries'] if row['source_sha256'] == key]
            self.assertEqual(len(progress['entries']), 1)
            progress['entries'][0].update(status='rejected_latest_attempt', current_decision='rejected_for_production', current_review={'review_output_sha256': digest})
            write_json(experiment / 'progress.json', progress)
            with patch.object(prepare, 'EXPERIMENT', experiment), patch.object(sys, 'argv', ['high131_prepare_note_masks.py', '--index', '40']):
                prepare.main()
            manifest = read_json(experiment / 'note-mask-40.json')
            self.assertEqual(manifest['target_sha256'], digest)
            self.assertEqual(manifest['rects'], [[1080, 1025, 1410, 1095], [1080, 1105, 1410, 1170]])
            self.assertEqual(manifest['transparent_pixels'], 331 * 71 + 331 * 66)
            self.assertEqual(manifest['opaque_pixels'], 2048 * 2048 - 331 * 71 - 331 * 66)
            self.assertEqual(manifest['status'], 'pending_actual_mask_review')
            self.assertTrue(all(rect[2] < 1500 for rect in manifest['rects']))
            for field, sha_field in (('mask_file', 'mask_sha256'), ('preview_file', 'preview_sha256')):
                self.assertEqual(file_sha256(ROOT / manifest[field]), manifest[sha_field])
            with Image.open(ROOT / manifest['mask_file']) as image:
                histogram = image.getchannel('A').histogram()
            self.assertEqual(sum(histogram[1:255]), 0)
            self.assertEqual(histogram[0] + histogram[255], 2048 * 2048)

    def test_native_alpha_reconciles_exact_reviewed_legacy_sentences(self):
        source40 = 'Use a neutral working matte only outside the full card silhouette for the opaque RGB pass, add no interior backdrop, halo or smoke, and restore source alpha afterward.'
        converted = hd_repairs.native_background_prompt(source40, 40)
        self.assertIn('genuine native transparency directly', converted)
        self.assertIn('do not use a working matte', converted)
        self.assertNotIn('working matte only outside', converted)
        self.assertNotIn('opaque RGB pass', converted)
        self.assertNotIn('restore source alpha afterward', converted)
        legacy67 = 'use a neutral working matte only outside that silhouette for the opaque RGB pass; invent no interior backdrop, halo or smoke, and restore the source alpha afterward.'
        self.assertEqual(hd_repairs.native_background_prompt(legacy67, 67), converted)
        with self.assertRaisesRegex(RuntimeError, 'index 52'):
            hd_repairs.native_background_prompt('For the opaque RGB pass use a neutral working matte only outside the whole card silhouette; restore source alpha afterward.', 52)

    def test_source40_revision2_binds_new_target_and_preserves_v1(self):
        key = '2a6394fc8d1b68a7150b114a47923cac16e60e4931cd49ba82ac2f4982355b79'
        targets = {1: '493566c0afaf43189ac8bf81aada993296c9be38cbe5b19530979e71878303da', 2: '67702ef31da9485a80946f230d4e40a754249e93ce707a015f48ec689a620f67'}
        with tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
            experiment = Path(directory)
            shutil.copyfile(prepare.EXPERIMENT / 'scope.json', experiment / 'scope.json')
            progress = read_json(prepare.EXPERIMENT / 'progress.json')
            progress['entries'] = [row for row in progress['entries'] if row['source_sha256'] == key]
            self.assertEqual(len(progress['entries']), 1)
            for revision in (1, 2):
                progress['entries'][0].update(status='rejected_latest_attempt', current_decision='rejected_for_production', current_review={'review_output_sha256': targets[revision]})
                write_json(experiment / 'progress.json', progress)
                with patch.object(prepare, 'EXPERIMENT', experiment), patch.object(sys, 'argv', ['high131_prepare_note_masks.py', '--index', '40', '--revision', str(revision)]):
                    prepare.main()
                suffix = hd_proof.mask_revision_suffix(revision)
                manifest = read_json(experiment / f'note-mask-40{suffix}.json')
                self.assertEqual(manifest['index'], 40)
                self.assertEqual(manifest['revision'], revision)
                self.assertEqual(manifest['target_sha256'], targets[revision])
                self.assertEqual(manifest['rects'], prepare.MASK_RECTANGLES[(40, revision)])
                self.assertEqual(manifest['status'], 'pending_actual_mask_review')
                self.assertEqual(file_sha256(prepare.MASTER_DIR / f'{targets[revision]}.png'), targets[revision])
                for field, sha_field in (('mask_file', 'mask_sha256'), ('preview_file', 'preview_sha256')):
                    self.assertEqual(file_sha256(ROOT / manifest[field]), manifest[sha_field])
                with Image.open(ROOT / manifest['mask_file']) as image:
                    histogram = image.getchannel('A').histogram()
                self.assertEqual(histogram[0], manifest['transparent_pixels'])
                self.assertEqual(histogram[255], manifest['opaque_pixels'])
                self.assertEqual(sum(histogram[1:255]), 0)
                if revision == 2:
                    self.assertEqual(manifest['rects'], [[1080, 1100, 1410, 1190]])
                    self.assertEqual(manifest['transparent_pixels'], 331 * 91)
                    self.assertIn('short lower-left group and a longer lower-right', manifest['official_contract'])
                    self.assertEqual(file_sha256(experiment / 'review-masks' / f'{key}-note-mask.png'), '848aee352d5a4c3abeb58e83071af3444f4d2ce4e3d6b73faca27bc4dc85bfa8')

    def test_source52_mask_binds_reviewed_target_and_preserves_tab(self):
        key = '581dd8fc38811eeca36e65fcfb5093d743744adbcb44be6f160e63af7e450b90'
        digest = 'bbc6cb1af07dfa23d425cce276376bce095c29c13b2eeab43701c1e78468aa52'
        with tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
            experiment = Path(directory)
            shutil.copyfile(prepare.EXPERIMENT / 'scope.json', experiment / 'scope.json')
            progress = read_json(prepare.EXPERIMENT / 'progress.json')
            progress['entries'] = [row for row in progress['entries'] if row['source_sha256'] == key]
            self.assertEqual(len(progress['entries']), 1)
            progress['entries'][0].update(status='rejected_latest_attempt', current_decision='rejected_for_production', current_review={'review_output_sha256': digest})
            write_json(experiment / 'progress.json', progress)
            with patch.object(prepare, 'EXPERIMENT', experiment), patch.object(sys, 'argv', ['high131_prepare_note_masks.py', '--index', '52']):
                prepare.main()
            manifest = read_json(experiment / 'note-mask-52.json')
            self.assertEqual(manifest['index'], 52)
            self.assertEqual(manifest['target_sha256'], digest)
            self.assertEqual(manifest['rects'], [[1140, 1070, 1470, 1145], [1140, 1150, 1470, 1225]])
            self.assertEqual(manifest['transparent_pixels'], 2 * 331 * 76)
            self.assertEqual(manifest['opaque_pixels'], 2048 * 2048 - 2 * 331 * 76)
            self.assertEqual(manifest['status'], 'pending_actual_mask_review')
            self.assertTrue(all(rect[2] < 1600 for rect in manifest['rects']))
            for field, sha_field in (('mask_file', 'mask_sha256'), ('preview_file', 'preview_sha256')):
                self.assertEqual(file_sha256(ROOT / manifest[field]), manifest[sha_field])
            with Image.open(ROOT / manifest['mask_file']) as image:
                histogram = image.getchannel('A').histogram()
            self.assertEqual(sum(histogram[1:255]), 0)
            self.assertEqual(histogram[0] + histogram[255], 2048 * 2048)

    def test_source52_revision2_binds_new_target_and_preserves_v1(self):
        key = '581dd8fc38811eeca36e65fcfb5093d743744adbcb44be6f160e63af7e450b90'
        digest = 'a26812c70272cfdb0582a7d6f403b3ef30333583976b117ac39e943ea297d59f'
        with tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
            experiment = Path(directory)
            shutil.copyfile(prepare.EXPERIMENT / 'scope.json', experiment / 'scope.json')
            progress = read_json(prepare.EXPERIMENT / 'progress.json')
            progress['entries'] = [row for row in progress['entries'] if row['source_sha256'] == key]
            self.assertEqual(len(progress['entries']), 1)
            progress['entries'][0].update(status='rejected_latest_attempt', current_decision='rejected_for_production', current_review={'review_output_sha256': digest})
            write_json(experiment / 'progress.json', progress)
            with patch.object(prepare, 'EXPERIMENT', experiment), patch.object(sys, 'argv', ['high131_prepare_note_masks.py', '--index', '52', '--revision', '2']):
                prepare.main()
            manifest = read_json(experiment / 'note-mask-52-v2.json')
            self.assertEqual(manifest['index'], 52)
            self.assertEqual(manifest['revision'], 2)
            self.assertEqual(manifest['target_sha256'], digest)
            self.assertEqual(manifest['rects'], [[1140, 1070, 1470, 1145]])
            self.assertEqual(manifest['transparent_pixels'], 331 * 76)
            self.assertEqual(manifest['opaque_pixels'], 2048 * 2048 - 331 * 76)
            self.assertEqual(manifest['status'], 'pending_actual_mask_review')
            self.assertEqual(file_sha256(prepare.MASTER_DIR / f'{digest}.png'), digest)
            for field, sha_field in (('mask_file', 'mask_sha256'), ('preview_file', 'preview_sha256')):
                self.assertEqual(file_sha256(ROOT / manifest[field]), manifest[sha_field])
            with Image.open(ROOT / manifest['mask_file']) as image:
                histogram = image.getchannel('A').histogram()
            self.assertEqual(sum(histogram[1:255]), 0)
            self.assertEqual(histogram[0] + histogram[255], 2048 * 2048)
            self.assertEqual(file_sha256(prepare.EXPERIMENT / 'review-masks' / f'{key}-note-mask.png'), '0751e88214cacccad47f37f24300559f0eaa9c3e6d9e45320efa3ba8d1e91227')
            with patch.object(prepare, 'EXPERIMENT', experiment), patch.object(sys, 'argv', ['high131_prepare_note_masks.py', '--index', '52', '--revision', '3']):
                prepare.main()
            v3 = read_json(experiment / 'note-mask-52-v3.json')
            self.assertEqual(v3['target_sha256'], digest)
            self.assertEqual(v3['rects'], [[1140, 1070, 1560, 1145]])
            self.assertEqual(v3['transparent_pixels'], 421 * 76)
            self.assertEqual(v3['opaque_pixels'], 2048 * 2048 - 421 * 76)
            self.assertEqual(v3['status'], 'pending_actual_mask_review')
            self.assertEqual(file_sha256(ROOT / v3['mask_file']), v3['mask_sha256'])
            self.assertEqual(file_sha256(experiment / 'review-masks' / f'{key}-note-mask-v2.png'), '897c76013023ef5fe48e9cd2431a5d83f8c62425f7511491c08529849ddc7d02')
            with Image.open(ROOT / v3['mask_file']) as image:
                histogram = image.getchannel('A').histogram()
            self.assertEqual(sum(histogram[1:255]), 0)

    def test_source53_mask_binds_current_target_and_preserves_corrected_pose(self):
        key = '54b4ec4ae9b53cd9fdb29065ddafcd8fea67e1d360023c1d6ae55dc6e2e4162b'
        digest = 'b3b747faf2d5a64c442d034a697a5b955247a822c1544b7a7ce4452bab6945a9'
        with tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
            experiment = Path(directory)
            shutil.copyfile(prepare.EXPERIMENT / 'scope.json', experiment / 'scope.json')
            progress = read_json(prepare.EXPERIMENT / 'progress.json')
            progress['entries'] = [row for row in progress['entries'] if row['source_sha256'] == key]
            self.assertEqual(len(progress['entries']), 1)
            progress['entries'][0].update(status='rejected_latest_attempt', current_decision='rejected_for_production', current_review={'review_output_sha256': digest})
            write_json(experiment / 'progress.json', progress)
            with patch.object(prepare, 'EXPERIMENT', experiment), patch.object(sys, 'argv', ['high131_prepare_note_masks.py', '--index', '53']):
                prepare.main()
            manifest = read_json(experiment / 'note-mask-53.json')
            self.assertEqual(manifest['index'], 53)
            self.assertEqual(manifest['target_sha256'], digest)
            self.assertEqual(manifest['rects'], [[1200, 1050, 1620, 1180]])
            self.assertEqual(manifest['transparent_pixels'], 421 * 131)
            self.assertEqual(manifest['opaque_pixels'], 2048 * 2048 - 421 * 131)
            self.assertEqual(manifest['status'], 'pending_actual_mask_review')
            self.assertIn('corrected viewer-right person', manifest['official_contract'])
            self.assertEqual(file_sha256(prepare.MASTER_DIR / f'{digest}.png'), digest)
            for field, sha_field in (('mask_file', 'mask_sha256'), ('preview_file', 'preview_sha256')):
                self.assertEqual(file_sha256(ROOT / manifest[field]), manifest[sha_field])
            with Image.open(ROOT / manifest['mask_file']) as image:
                histogram = image.getchannel('A').histogram()
            self.assertEqual(sum(histogram[1:255]), 0)
            self.assertEqual(histogram[0] + histogram[255], 2048 * 2048)

    def test_source57_mask_preserves_person_clothing_and_tab(self):
        key = '8f53dc26bec02a7f1a6a617afb171d49e221fad8227b265d94e7384ce17f4bd0'
        digest = '940c480f4d37ff159b0dfaf13bd1f34d0dd776f14031691fc0e8de8bc9451981'
        with tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
            experiment = Path(directory)
            shutil.copyfile(prepare.EXPERIMENT / 'scope.json', experiment / 'scope.json')
            progress = read_json(prepare.EXPERIMENT / 'progress.json')
            progress['entries'] = [row for row in progress['entries'] if row['source_sha256'] == key]
            self.assertEqual(len(progress['entries']), 1)
            progress['entries'][0].update(status='rejected_latest_attempt', current_decision='rejected_for_production', current_review={'review_output_sha256': digest})
            write_json(experiment / 'progress.json', progress)
            with patch.object(prepare, 'EXPERIMENT', experiment), patch.object(sys, 'argv', ['high131_prepare_note_masks.py', '--index', '57']):
                prepare.main()
            manifest = read_json(experiment / 'note-mask-57.json')
            self.assertEqual(manifest['index'], 57)
            self.assertEqual(manifest['target_sha256'], digest)
            self.assertEqual(manifest['rects'], [[1150, 1030, 1490, 1150]])
            self.assertEqual(manifest['transparent_pixels'], 341 * 121)
            self.assertEqual(manifest['opaque_pixels'], 2048 * 2048 - 341 * 121)
            self.assertEqual(manifest['status'], 'pending_actual_mask_review')
            self.assertIn('bald-crowned person', manifest['official_contract'])
            self.assertEqual(file_sha256(prepare.MASTER_DIR / f'{digest}.png'), digest)
            for field, sha_field in (('mask_file', 'mask_sha256'), ('preview_file', 'preview_sha256')):
                self.assertEqual(file_sha256(ROOT / manifest[field]), manifest[sha_field])
            with Image.open(ROOT / manifest['mask_file']) as image:
                histogram = image.getchannel('A').histogram()
            self.assertEqual(sum(histogram[1:255]), 0)
            self.assertEqual(histogram[0] + histogram[255], 2048 * 2048)

    def test_source54_mask_binds_reviewed_target_and_preserves_tab(self):
        key = '5770c09b8367c798fe5be23ae82ac30a4f162f41fa0e58da70b29bb757e3e59f'
        digest = '302c9818e330433a713be5b32af6969b7e4de53a5d26db78330d1f4220d468dd'
        with tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
            experiment = Path(directory)
            shutil.copyfile(prepare.EXPERIMENT / 'scope.json', experiment / 'scope.json')
            progress = read_json(prepare.EXPERIMENT / 'progress.json')
            progress['entries'] = [row for row in progress['entries'] if row['source_sha256'] == key]
            self.assertEqual(len(progress['entries']), 1)
            progress['entries'][0].update(status='rejected_latest_attempt', current_decision='rejected_for_production', current_review={'review_output_sha256': digest})
            write_json(experiment / 'progress.json', progress)
            with patch.object(prepare, 'EXPERIMENT', experiment), patch.object(sys, 'argv', ['high131_prepare_note_masks.py', '--index', '54']):
                prepare.main()
            manifest = read_json(experiment / 'note-mask-54.json')
            self.assertEqual(manifest['index'], 54)
            self.assertEqual(manifest['target_sha256'], digest)
            self.assertEqual(manifest['rects'], [[1100, 1040, 1600, 1125], [1100, 1135, 1600, 1210]])
            self.assertEqual(manifest['transparent_pixels'], 501 * 86 + 501 * 76)
            self.assertEqual(manifest['opaque_pixels'], 2048 * 2048 - 501 * 86 - 501 * 76)
            self.assertEqual(manifest['status'], 'pending_actual_mask_review')
            self.assertTrue(all(rect[2] <= 1600 for rect in manifest['rects']))
            for field, sha_field in (('mask_file', 'mask_sha256'), ('preview_file', 'preview_sha256')):
                self.assertEqual(file_sha256(ROOT / manifest[field]), manifest[sha_field])
            with Image.open(ROOT / manifest['mask_file']) as image:
                histogram = image.getchannel('A').histogram()
            self.assertEqual(sum(histogram[1:255]), 0)
            self.assertEqual(histogram[0] + histogram[255], 2048 * 2048)

    def test_source61_through64_masks_preserve_people_clothing_and_tabs(self):
        cases = {
            61: ('5a160dd1e47d2a76dbf153ecf70fed66d73f3dfe21958a284cec3f4971fbfc74', '1ff5de15726d10a09cb0404523453aa80487759544fe1e709b117f7e42aa75e7', [1050, 930, 1490, 1120], 'white-capped person'),
            62: ('55e631c3aaedeef562ccccf0e31ebd55de03e25b719c3ac197e677f30ecb3675', '7eb8e7834b65669b5e466ccee2fcc1b6978de8e4255771fb408816d0a3169633', [1120, 920, 1590, 1110], 'headscarf'),
            63: ('bccaf19c78294b83dc4ab613b8e019a23e77702e342deb376e787b16b0c12336', 'd79cd8b41665140b578dbcfaf6a0bdde6597fb2a4e0bdc5b326e640ba2d35880', [1050, 920, 1340, 1090], 'gray-haired person'),
            64: ('f54980009f57be78a2a931afeb1aad7251b370a8c6ca677164a7198c584cbf7d', '1228384bb2f0c7fecb1170f828a197300fe3f9f3cffa719cd5d1e4494583c7b5', [1130, 1030, 1590, 1260], 'viewer-right person'),
        }
        for index, (key, digest, rect, contract) in cases.items():
            with self.subTest(index=index), tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
                experiment = Path(directory)
                shutil.copyfile(prepare.EXPERIMENT / 'scope.json', experiment / 'scope.json')
                progress = read_json(prepare.EXPERIMENT / 'progress.json')
                progress['entries'] = [row for row in progress['entries'] if row['source_sha256'] == key]
                progress['entries'][0].update(status='rejected_latest_attempt', current_decision='rejected_for_production', current_review={'review_output_sha256': digest})
                write_json(experiment / 'progress.json', progress)
                with patch.object(prepare, 'EXPERIMENT', experiment), patch.object(sys, 'argv', ['high131_prepare_note_masks.py', '--index', str(index)]):
                    prepare.main()
                manifest = read_json(experiment / f'note-mask-{index}.json')
                self.assertEqual(manifest['index'], index)
                self.assertEqual(manifest['target_sha256'], digest)
                self.assertEqual(manifest['rects'], [rect])
                pixels = (rect[2] - rect[0] + 1) * (rect[3] - rect[1] + 1)
                self.assertEqual(manifest['transparent_pixels'], pixels)
                self.assertEqual(manifest['opaque_pixels'], 2048 * 2048 - pixels)
                self.assertEqual(manifest['status'], 'pending_actual_mask_review')
                self.assertIn(contract, manifest['official_contract'])
                self.assertEqual(file_sha256(prepare.MASTER_DIR / f'{digest}.png'), digest)
                for field, sha_field in (('mask_file', 'mask_sha256'), ('preview_file', 'preview_sha256')):
                    self.assertEqual(file_sha256(ROOT / manifest[field]), manifest[sha_field])
                with Image.open(ROOT / manifest['mask_file']) as image:
                    histogram = image.getchannel('A').histogram()
                self.assertEqual(sum(histogram[1:255]), 0)
                self.assertEqual(histogram[0] + histogram[255], 2048 * 2048)


if __name__ == '__main__':
    unittest.main()
