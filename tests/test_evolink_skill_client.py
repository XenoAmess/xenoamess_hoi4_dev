"""Offline behavior checks; never read credentials or contact EvoLink."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/evolink-imagegen/scripts/evolink_image.py'
spec = importlib.util.spec_from_file_location('evolink_skill_client', SCRIPT)
client = importlib.util.module_from_spec(spec); spec.loader.exec_module(client)


class Response(io.BytesIO):
    status = 200
    headers = {'Content-Type': 'image/png'}


class EvoLinkSkillTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name); self.prompt = self.root / 'input.txt'; self.output = self.root / 'attempt/output.png'
        self.prompt_bytes = '  原始完整请求\r\n保留末尾空行。\n\n'.encode('utf-8')
        self.prompt.write_bytes(self.prompt_bytes)
        self.raw = client.PNG_SIGNATURE + b'fixture returned bytes, not a real art-validation PNG'
        self.key = 'fixture-key-never-real'
        self.stdout = io.StringIO()

    def run_client(self, extra=(), http=None, download=None):
        argv = ['evolink_image.py', '--output', str(self.output), *extra]
        with patch('sys.argv', argv), patch.object(client, 'require_api_key', return_value=self.key) as key, patch.object(client, 'http_json', side_effect=http) as api, patch.object(client, 'urlopen', side_effect=download) as fetch, patch.object(client.time, 'sleep'), contextlib.redirect_stdout(self.stdout):
            result = client.main()
            return result, key, api, fetch

    def test_dry_run_needs_no_credentials_network_or_archive_writes(self):
        result, key, api, fetch = self.run_client(['--dry-run', '--prompt-file', str(self.prompt)])
        self.assertEqual(result, 0); key.assert_not_called(); api.assert_not_called(); fetch.assert_not_called()
        self.assertFalse(self.output.parent.exists())
        body = json.loads(self.stdout.getvalue())
        self.assertEqual(body['prompt_sha256'], hashlib.sha256(self.prompt_bytes).hexdigest())

    def test_creation_archives_exact_prompt_and_raw_return_without_secrets(self):
        requests = []
        def http(request, operation):
            requests.append(request)
            if request.method == 'POST':
                payload = json.loads(request.data.decode('utf-8'))
                self.assertEqual(payload['prompt'].encode('utf-8'), self.prompt_bytes)
                return {'id': 'fixture-task', 'status': 'pending'}
            return {'status': 'completed', 'results': ['https://cdn.example/image.png?temporary=fixture']}
        def download(request, timeout):
            self.assertFalse(request.has_header('Authorization'))
            return Response(self.raw)
        result, _, _, _ = self.run_client(['--prompt-file', str(self.prompt)], http, download)
        self.assertEqual(result, 0); self.assertEqual([r.method for r in requests], ['POST', 'GET'])
        self.assertEqual(self.output.read_bytes(), self.raw)
        self.assertEqual(self.output.with_suffix('.prompt.txt').read_bytes(), self.prompt_bytes)
        record = json.loads(self.output.with_suffix('.result.json').read_text(encoding='utf-8'))
        self.assertEqual(record['sha256'], hashlib.sha256(self.raw).hexdigest())
        archived = '\n'.join(p.read_text(encoding='utf-8') for p in self.output.parent.iterdir() if p.suffix != '.png')
        self.assertNotIn(self.key, archived); self.assertNotIn('temporary=fixture', archived)

    def test_existing_task_resume_never_creates_another_paid_task(self):
        args = type('Args', (), {'prompt_file': self.prompt, 'model': 'gpt-image-2', 'size': '2:3', 'resolution': '2K', 'quality': 'high', 'background': 'transparent', 'image_url': []})()
        prompt, payload = client.build_request(args)
        client.write_generation_record(self.output, prompt, payload)
        client.write_or_validate_task_record(self.output, 'fixture-task')
        def http(request, operation):
            self.assertEqual(request.method, 'GET')
            return {'status': 'completed', 'results': ['https://cdn.example/image.png']}
        result, _, api, _ = self.run_client(['--task-id', 'fixture-task'], http, lambda request, timeout: Response(self.raw))
        self.assertEqual(result, 0); self.assertEqual(api.call_count, 1)

    def test_gpt_image_25_models_use_native_transparent_fields(self):
        for model in ('gpt-image-2.5-sunburst', 'gpt-image-2.5-flare'):
            with self.subTest(model=model):
                args = type('Args', (), {'prompt_file': self.prompt, 'model': model, 'size': '3:4', 'resolution': '2K', 'quality': 'high', 'background': 'transparent', 'image_url': ['https://example.org/source.png']})()
                prompt, payload = client.build_request(args)
                self.assertEqual(payload, {'model': model, 'prompt': prompt, 'size': '3:4', 'image_urls': ['https://example.org/source.png'], 'resolution': '2K', 'quality': 'high', 'background': 'transparent', 'n': 1})

    def test_gpt_opaque_background_is_forwarded(self):
        args = type('Args', (), {'prompt_file': self.prompt, 'model': 'gpt-image-2.5-flare', 'size': '3:4', 'resolution': '2K', 'quality': 'high', 'background': 'opaque', 'image_url': []})()
        _, payload = client.build_request(args)
        self.assertEqual(payload['background'], 'opaque')

    def test_nano_banana_uses_documented_request_fields(self):
        args = type('Args', (), {'prompt_file': self.prompt, 'model': 'gemini-nano-banana-2.1', 'size': '3:4', 'resolution': '2K', 'quality': 'high', 'background': 'transparent', 'image_url': ['https://example.org/source.png']})()
        prompt, payload = client.build_request(args)
        self.assertEqual(prompt.encode('utf-8'), self.prompt_bytes)
        self.assertEqual(payload, {'model': 'gemini-nano-banana-2.1', 'prompt': prompt, 'size': '3:4', 'image_urls': ['https://example.org/source.png'], 'quality': '2K'})

    def test_failed_task_is_retained_without_resubmission(self):
        count = [0]
        def http(request, operation):
            count[0] += 1
            if request.method == 'POST': return {'id': 'fixture-task', 'status': 'failed', 'error': 'fixture service failure'}
            self.fail('A failed task must not be re-created or polled indefinitely')
        with self.assertRaisesRegex(RuntimeError, 'no resubmission'):
            self.run_client(['--prompt-file', str(self.prompt)], http)
        self.assertEqual(count[0], 1)
        self.assertTrue(self.output.with_suffix('.task.json').exists()); self.assertFalse(self.output.exists())

    def test_partial_archive_or_existing_output_cannot_be_overwritten(self):
        self.output.parent.mkdir(); sidecar = self.output.with_suffix('.request.json'); sidecar.write_bytes(b'prior request')
        with self.assertRaisesRegex(RuntimeError, 'overwrite'):
            self.run_client(['--prompt-file', str(self.prompt)])
        self.assertEqual(sidecar.read_bytes(), b'prior request')

    def test_resume_without_original_record_stops_before_api_call(self):
        with self.assertRaisesRegex(RuntimeError, 'without its archived'):
            self.run_client(['--task-id', 'fixture-task'], lambda *args: self.fail('Missing record must not contact API'))

    def test_local_or_credential_bearing_reference_is_not_sent(self):
        for url in ['C:/local/input.png', 'https://user:secret@example.org/input.png', 'https://example.org/input.png?signature=fixture']:
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                self.run_client(['--dry-run', '--prompt-file', str(self.prompt), '--image-url', url])


if __name__ == '__main__': unittest.main()
