from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from runtime import high131_hd_proof as hd_proof
from runtime import high131_prepare_note_details as prepare_details
from runtime import high131_run_repairs as repairs
from runtime import high131_verify_records as verify
from tools.common import ROOT, file_sha256, machine_id, read_json, write_json


class NoteDetailInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / 'runtime')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'runtime/references/source.png'
        self.source.parent.mkdir(parents=True)
        image = Image.new('RGBA', (65, 67))
        for y in range(67):
            for x in range(65):
                image.putpixel((x, y), ((x * 17) % 256, (y * 19) % 256, ((x + y) * 11) % 256, 255))
        image.save(self.source)
        self.source_sha = file_sha256(self.source)
        self.rect = [32, 22, 65, 67]
        self.scale = 16
        detail = image.crop(self.rect).resize((528, 720), Image.Resampling.NEAREST)
        self.detail = self.root / 'mod_nailong/experiments/evolink-high131-flare-20261025/review-source-details/detail.png'
        self.detail.parent.mkdir(parents=True)
        detail.save(self.detail)
        self.detail_sha = file_sha256(self.detail)
        raw = self.root / 'mod_nailong/assets/generated_fullsize/raw.png'
        raw.parent.mkdir(parents=True)
        raw.write_bytes(b'raw HD target')
        self.raw_sha = file_sha256(raw)
        mascot = self.root / 'mascot.png'
        mascot.write_bytes(b'mascot')
        self.mascot_sha = file_sha256(mascot)
        self.commit = 'c' * 40
        raw_relative = raw.relative_to(self.root).as_posix()
        detail_relative = self.detail.relative_to(self.root).as_posix()
        self.raw_url = f'https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{self.commit}/{raw_relative}'
        self.detail_url = f'https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{self.commit}/{detail_relative}'
        common = {
            'readback_commit': self.commit,
            'method': 'Complete anonymous raw PNG download; SHA256 and byte count',
            'verified_at_utc': '2026-01-01T00:00:00+00:00',
            'remote_tree_blob_match': True,
            'local_original_matches': True,
            'png_signature_verified': True,
        }
        self.proof = {
            'schema': 'high131-hd-target-readback-v1', 'status': 'verified',
            'machine_id': machine_id(), 'commit': self.commit, 'complete_archive_verified': False,
            'targets': {
                self.raw_sha: {
                    **common, 'path': raw_relative, 'bytes': raw.stat().st_size,
                    'sha256': self.raw_sha, 'url': self.raw_url,
                },
                self.detail_sha: {
                    **common, 'path': detail_relative, 'bytes': self.detail.stat().st_size,
                    'sha256': self.detail_sha, 'url': self.detail_url,
                    'role': 'source-note-detail-reference', 'not_generated_or_game_payload': True,
                    'size': [528, 720], 'mode': 'RGBA',
                    'derivation': {
                        'source_png_sha256': self.source_sha, 'crop_rect': self.rect,
                        'scale': self.scale, 'method': 'source-crop-resize-nearest-v1',
                        'derivative_reviewed': True,
                    },
                },
            },
        }
        write_json(self.root / 'runtime/proof.json', self.proof)
        self.repair = {
            'repair_input_mode': hd_proof.NOTE_DETAIL_MODE,
            'remote_commit': self.commit,
            'remote_readback': 'runtime/proof.json',
            'edit_target_image': raw_relative,
            'edit_target_sha256': self.raw_sha,
            'rejected_output_sha256': self.raw_sha,
            'remote_target_url': self.raw_url,
            'image_urls': [self.raw_url, 'source-url', 'mascot-url', self.detail_url],
            'ordered_input_sha256': [self.raw_sha, self.source_sha, self.mascot_sha, self.detail_sha],
            'note_detail': {
                'path': detail_relative, 'sha256': self.detail_sha, 'url': self.detail_url,
                'source_png_sha256': self.source_sha,
            },
        }
        self.state = {
            'key': 'a' * 64,
            'repair_input_mode': hd_proof.NOTE_DETAIL_MODE,
            'original_entry': {'converted_png_sha256': self.source_sha, 'source_png': self.source.relative_to(self.root).as_posix()},
            'repair': self.repair,
        }
        self.context = {
            'release_assets': {'a' * 64: {'url': 'source-url'}},
            'scope': {'mascot_reference': {'sha256': self.mascot_sha, 'url': 'mascot-url'}},
        }

    def test_four_input_contracts_preserve_order_and_source_pixels(self):
        with patch.object(repairs.batch, 'ROOT', self.root), patch.object(verify, 'ROOT', self.root):
            inputs, urls = repairs.repair_input_contract(self.context, self.state)
            verified_urls, binding = verify.expected_input_route(
                self.context['scope'],
                {'url': 'source-url', 'converted_png_sha256': self.source_sha},
                self.repair,
                source_path=self.source,
            )
        self.assertEqual(inputs, self.repair['ordered_input_sha256'])
        self.assertEqual(urls, self.repair['image_urls'])
        self.assertEqual(verified_urls, urls)
        self.assertEqual(binding['ordered_input_sha256'], inputs)
        self.assertEqual(binding['note_detail_sha256'], self.detail_sha)

    def test_substituted_detail_pixels_are_rejected(self):
        with Image.open(self.detail) as image:
            image.putpixel((0, 0), (1, 2, 3, 4))
            image.save(self.detail)
        digest = file_sha256(self.detail)
        record = dict(self.proof['targets'][self.detail_sha])
        record.update(sha256=digest, bytes=self.detail.stat().st_size)
        self.proof['targets'][digest] = record
        with self.assertRaisesRegex(RuntimeError, 'Source-detail pixels'):
            hd_proof.validate_remote_reference(self.proof, self.commit, self.detail, digest, self.source, root=self.root)

    def test_source40_uses_separate_exact_derivative_manifest(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
            experiment = Path(directory)
            shutil.copyfile(prepare_details.EXPERIMENT / 'scope.json', experiment / 'scope.json')
            old_manifest = prepare_details.EXPERIMENT / 'note-detail-sources.json'
            old_sha = file_sha256(old_manifest)
            with patch.object(prepare_details, 'EXPERIMENT', experiment), patch.object(sys, 'argv', ['high131_prepare_note_details.py', '--index', '40']):
                prepare_details.main()
            manifest = read_json(experiment / 'note-detail-sources-40.json')
            self.assertEqual(manifest['status'], 'pending_actual_derivative_review')
            self.assertFalse((experiment / 'note-detail-sources.json').exists())
            self.assertEqual(file_sha256(old_manifest), old_sha)
            self.assertEqual(len(manifest['entries']), 1)
            entry = manifest['entries'][0]
            self.assertEqual(entry['index'], 40)
            self.assertEqual(entry['source_sha256'], '2a6394fc8d1b68a7150b114a47923cac16e60e4931cd49ba82ac2f4982355b79')
            self.assertEqual(entry['source_png_sha256'], 'ee8a5d9d492a7ecaf1c04b63401b2fc893bc5bac9ad2ef91915275619167cf02')
            self.assertFalse(entry['derivative_reviewed'])
            detail_path = ROOT / entry['path']
            self.assertEqual(file_sha256(detail_path), entry['sha256'])
            with Image.open(ROOT / entry['source_png']) as source, Image.open(detail_path) as detail:
                expected = source.convert('RGBA').crop(entry['crop_rect']).resize(detail.size, Image.Resampling.NEAREST)
                self.assertEqual(detail.convert('RGBA').tobytes(), expected.tobytes())
                self.assertEqual(detail.size, (528, 720))
                self.assertEqual(detail.mode, 'RGBA')


if __name__ == '__main__':
    unittest.main()
