import ctypes
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from runtime import high131_verify_records as verify
from runtime import high131_io
from tools.common import ROOT, write_json


class InputRouteTests(unittest.TestCase):
    def setUp(self):
        self.scope = {
            'model': 'gpt-image-2.5-flare',
            'mascot_reference': {'url': 'mascot-url', 'sha256': '2' * 64},
        }
        self.asset = {'url': 'source-url', 'converted_png_sha256': '3' * 64}

    def test_original_route_has_two_ordered_inputs(self):
        urls, proof = verify.expected_input_route(self.scope, self.asset, None)
        self.assertEqual(urls, ['source-url', 'mascot-url'])
        self.assertEqual(proof['ordered_input_sha256'], ['3' * 64, '2' * 64])
        self.assertIsNone(proof['remote_commit'])

    def test_hd_route_checks_target_proof_and_three_input_order(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
            root = Path(directory)
            payload = b'retained raw HD target'
            digest = hashlib.sha256(payload).hexdigest()
            relative = f'mod_nailong/assets/generated_fullsize/{digest}.png'
            target = root / relative
            target.parent.mkdir(parents=True)
            target.write_bytes(payload)
            commit = 'a' * 40
            url = f'https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{commit}/{relative}'
            repair = {
                'repair_input_mode': 'raw-hd-edit-v1',
                'remote_commit': commit,
                'remote_readback': 'runtime/readback.json',
                'edit_target_image': relative,
                'edit_target_sha256': digest,
                'rejected_output_sha256': digest,
                'remote_target_url': url,
                'image_urls': [url, 'source-url', 'mascot-url'],
                'ordered_input_sha256': [digest, '3' * 64, '2' * 64],
            }
            write_json(root / 'runtime/readback.json', {
                'status': 'verified', 'commit': commit, 'machine_id': 'test-machine',
                'distinct_outputs': 1, 'original_png_bytes': len(payload),
            })
            index = {
                'count': 1, 'original_png_bytes': len(payload),
                'outputs': {digest: {'path': relative, 'bytes': len(payload)}},
            }
            completed = verify.hd_proof.subprocess.CompletedProcess(args=['git'], returncode=0, stdout=json.dumps(index))
            with patch.object(verify, 'ROOT', root), patch.object(verify.hd_proof, 'machine_id', return_value='test-machine'), patch.object(verify.hd_proof.subprocess, 'run', return_value=completed) as git:
                urls, proof = verify.expected_input_route(self.scope, self.asset, repair)
            self.assertEqual(urls, [url, 'source-url', 'mascot-url'])
            self.assertEqual(proof['ordered_input_sha256'], [digest, '3' * 64, '2' * 64])
            self.assertEqual(proof['edit_target_sha256'], digest)
            self.assertIn(f'{commit}:mod_nailong/data/fullsize-files.json', git.call_args.args[0])

    def test_hd_route_accepts_target_scoped_proof_without_full_index(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
            root = Path(directory)
            payload = b'target-scoped HD bytes'
            digest = hashlib.sha256(payload).hexdigest()
            relative = f'mod_nailong/assets/generated_fullsize/{digest}.png'
            target = root / relative
            target.parent.mkdir(parents=True)
            target.write_bytes(payload)
            commit = 'a' * 40
            url = f'https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{commit}/{relative}'
            repair = {
                'repair_input_mode': 'raw-hd-edit-v1', 'remote_commit': commit,
                'remote_readback': 'runtime/readback.json', 'edit_target_image': relative,
                'edit_target_sha256': digest, 'rejected_output_sha256': digest,
                'remote_target_url': url, 'image_urls': [url, 'source-url', 'mascot-url'],
                'ordered_input_sha256': [digest, '3' * 64, '2' * 64],
            }
            write_json(root / 'runtime/readback.json', {
                'schema': 'high131-hd-target-readback-v1', 'status': 'verified',
                'commit': commit, 'machine_id': 'test-machine', 'complete_archive_verified': False,
                'targets': {digest: {
                    'path': relative, 'bytes': len(payload), 'sha256': digest,
                    'url': url, 'readback_commit': commit,
                    'method': 'Complete anonymous raw PNG download; SHA256 and byte count',
                    'verified_at_utc': '2026-01-01T00:00:00+00:00',
                    'remote_tree_blob_match': True, 'local_original_matches': True,
                    'png_signature_verified': True,
                }},
            })
            with patch.object(verify, 'ROOT', root), patch.object(verify.hd_proof, 'machine_id', return_value='test-machine'), patch.object(verify.hd_proof.subprocess, 'run', side_effect=AssertionError('full index must not be required')):
                urls, proof = verify.expected_input_route(self.scope, self.asset, repair)
            self.assertEqual(urls, [url, 'source-url', 'mascot-url'])
            self.assertEqual(proof['edit_target_sha256'], digest)
            self.assertEqual(proof['remote_commit'], commit)

    def test_hd_route_rejects_wrong_machine_proof(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
            root = Path(directory)
            payload = b'target'
            digest = hashlib.sha256(payload).hexdigest()
            relative = f'mod_nailong/assets/generated_fullsize/{digest}.png'
            target = root / relative
            target.parent.mkdir(parents=True)
            target.write_bytes(payload)
            commit = 'a' * 40
            write_json(root / 'runtime/readback.json', {
                'status': 'verified', 'commit': commit, 'machine_id': 'other-machine',
                'distinct_outputs': 1, 'original_png_bytes': len(payload),
            })
            repair = {
                'repair_input_mode': 'raw-hd-edit-v1', 'remote_commit': commit,
                'remote_readback': 'runtime/readback.json', 'edit_target_image': relative,
                'edit_target_sha256': digest, 'rejected_output_sha256': digest,
            }
            with patch.object(verify, 'ROOT', root), patch.object(verify.hd_proof, 'machine_id', return_value='test-machine'):
                with self.assertRaisesRegex(AssertionError, 'machine and commit'):
                    verify.expected_input_route(self.scope, self.asset, repair)


class MaskInputRouteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.scope = {
            'model': 'gpt-image-2.5-flare',
            'mascot_reference': {'url': 'mascot-url', 'sha256': '2' * 64},
        }
        self.asset = {'url': 'source-url', 'converted_png_sha256': '3' * 64}
        self.target_sha = '4' * 64
        self.mask_sha = '5' * 64
        self.detail_sha = '6' * 64
        self.manifest_sha = '7' * 64
        self.commit = 'a' * 40
        self.target_relative = f'mod_nailong/assets/generated_fullsize/{self.target_sha}.png'
        self.mask_relative = 'mod_nailong/experiments/evolink-high131-flare-20261025/review-masks/mask.png'
        self.detail_relative = 'mod_nailong/experiments/evolink-high131-flare-20261025/review-source-details/detail.png'
        self.manifest_relative = 'mod_nailong/experiments/evolink-high131-flare-20261025/review-masks/mask.json'
        prefix = f'https://raw.githubusercontent.com/XenoAmess/xenoamess_hoi4_dev/{self.commit}'
        self.target_url = f'{prefix}/{self.target_relative}'
        self.mask_url = f'{prefix}/{self.mask_relative}'
        self.detail_url = f'{prefix}/{self.detail_relative}'
        self.mask = {
            'path': self.mask_relative, 'sha256': self.mask_sha, 'url': self.mask_url,
            'target_sha256': self.target_sha, 'manifest': self.manifest_relative,
            'manifest_sha256': self.manifest_sha,
        }
        self.repair = {
            'repair_input_mode': verify.hd_proof.MASK_NOTE_MODE,
            'remote_commit': self.commit, 'remote_readback': 'runtime/proof.json',
            'edit_target_image': self.target_relative, 'edit_target_sha256': self.target_sha,
            'rejected_output_sha256': self.target_sha, 'remote_target_url': self.target_url,
            'image_urls': [self.target_url, 'source-url', 'mascot-url', self.detail_url],
            'ordered_input_sha256': [self.target_sha, '3' * 64, '2' * 64, self.detail_sha],
            'note_detail': {
                'path': self.detail_relative, 'sha256': self.detail_sha,
                'url': self.detail_url, 'source_png_sha256': '3' * 64,
            },
            'mask': self.mask, 'mask_url': self.mask_url,
        }
        self.proof = {
            'targets': {
                self.mask_sha: {
                    'mask_manifest': self.manifest_relative,
                    'mask_manifest_sha256': self.manifest_sha,
                },
            },
        }

    def expected_route(self, repair):
        with (
            patch.object(verify, 'ROOT', self.root),
            patch.object(verify.hd_proof, 'load_remote_proof', return_value=(self.proof, None)),
            patch.object(verify.hd_proof, 'validate_remote_target', return_value=self.target_url),
            patch.object(verify.hd_proof, 'validate_remote_reference', return_value=self.detail_url) as detail_check,
            patch.object(verify.hd_proof, 'validate_remote_mask', return_value=self.mask_url) as mask_check,
        ):
            result = verify.expected_input_route(
                self.scope, self.asset, repair,
                source_path=self.root / 'runtime/references/source.png',
            )
        return result, detail_check, mask_check

    def test_mask_route_verifies_note_proof_mask_and_actual_request(self):
        (urls, binding), detail_check, mask_check = self.expected_route(self.repair)
        self.assertEqual(urls, self.repair['image_urls'])
        self.assertNotIn(self.mask_url, urls)
        self.assertEqual(binding['note_detail_sha256'], self.detail_sha)
        self.assertEqual(binding['mask_sha256'], self.mask_sha)
        self.assertEqual(binding['mask_target_sha256'], self.target_sha)
        self.assertEqual(binding['mask_url'], self.mask_url)
        detail_check.assert_called_once()
        mask_check.assert_called_once_with(
            self.proof, self.commit, self.root / self.mask_relative, self.mask_sha,
            self.root / self.target_relative, self.target_sha, root=self.root,
        )
        verify.validate_request_mask({'mask_url': self.mask_url}, self.repair)
        for request in ({}, {'mask_url': 'https://example.invalid/wrong.png'}):
            with self.subTest(request=request), self.assertRaises(AssertionError):
                verify.validate_request_mask(request, self.repair)

    def test_mask_manifest_and_url_must_match_remote_proof(self):
        for field, value in (
            ('url', 'https://example.invalid/other-mask.png'),
            ('manifest', 'mod_nailong/experiments/evolink-high131-flare-20261025/review-masks/other.json'),
            ('manifest_sha256', '0' * 64),
        ):
            with self.subTest(field=field):
                repair = dict(self.repair)
                repair['mask'] = {**self.mask, field: value}
                with self.assertRaises(AssertionError):
                    self.expected_route(repair)

    def test_old_routes_reject_any_actual_mask_url(self):
        for repair in (None, {'repair_input_mode': 'raw-hd-edit-v1'}, {'repair_input_mode': verify.hd_proof.NOTE_DETAIL_MODE}):
            with self.subTest(repair=repair):
                verify.validate_request_mask({}, repair)
                with self.assertRaises(AssertionError):
                    verify.validate_request_mask({'mask_url': self.mask_url}, repair)


class BoundedJsonReplaceTests(unittest.TestCase):
    def test_transient_windows_error_retries_same_payload(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'runtime') as directory:
            path = Path(directory) / 'receipt.json'
            value = {'complete': [1, 2]}
            calls = []

            def flaky(target, payload):
                calls.append((target, payload))
                if len(calls) == 1:
                    raise ctypes.WinError(1175, 'transient replacement sharing conflict')
                target.write_text(json.dumps(payload), encoding='utf-8')

            with patch.object(high131_io, 'common_write_json', side_effect=flaky), patch.object(high131_io.time, 'sleep') as sleep:
                high131_io.write_json(path, value)
            self.assertEqual(len(calls), 2)
            self.assertIs(calls[0][1], value)
            self.assertIs(calls[1][1], value)
            sleep.assert_called_once_with(0.02)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), value)

    def test_other_replace_errors_are_not_retried(self):
        with patch.object(high131_io, 'common_write_json', side_effect=ctypes.WinError(5, 'denied')) as writer, patch.object(high131_io.time, 'sleep') as sleep:
            with self.assertRaises(OSError):
                high131_io.write_json(Path('not-written.json'), {})
        self.assertEqual(writer.call_count, 1)
        sleep.assert_not_called()

    def test_persistent_windows_error_has_a_bounded_retry_count(self):
        with patch.object(high131_io, 'common_write_json', side_effect=ctypes.WinError(1175, 'still occupied')) as writer, patch.object(high131_io.time, 'sleep'):
            with self.assertRaises(OSError):
                high131_io.write_json(Path('not-written.json'), {})
        self.assertEqual(writer.call_count, 11)


if __name__ == '__main__':
    unittest.main()
