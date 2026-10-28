import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

from runtime import high131_model_policy as policy
from runtime import high131_run_source65_nano as runner
from tools.common import ROOT

SCRIPT = ROOT / 'skills/evolink-imagegen/scripts/evolink_image.py'
spec = importlib.util.spec_from_file_location('evolink_skill_client', SCRIPT)
evolink_image = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evolink_image)


class NanoRouteTests(unittest.TestCase):
    def test_only_exact_user_authorized_model_is_allowed(self):
        self.assertTrue(policy.authorized_nano(ROOT, policy.NANO_KEY, policy.NANO_ATTEMPT, policy.NANO_MODEL))
        self.assertEqual(policy.production_method(ROOT, policy.NANO_KEY, policy.NANO_ATTEMPT, policy.NANO_MODEL), f'EvoLink {policy.NANO_MODEL}')
        for key, attempt, model in (
            (policy.NANO_KEY, 'external-06', policy.NANO_MODEL),
            (policy.NANO_KEY, policy.NANO_ATTEMPT, 'gpt-image-2.5-flare'),
            ('0' * 64, policy.NANO_ATTEMPT, policy.NANO_MODEL),
        ):
            self.assertFalse(policy.authorized_nano(ROOT, key, attempt, model))
        refusal = policy.retained_previous_refusal(ROOT, policy.NANO_KEY)
        self.assertEqual(refusal['provider_error'], 'content_policy_violation')
        self.assertIsNone(refusal['output_sha256'])
        self.assertEqual(refusal['new_generation_tasks_created'], 0)

    def test_frozen_runner_uses_external05_and_actual_nano_protocol(self):
        context, state = runner.prepare()
        state['dispatch_gate'] = False
        command, parameters, refusal = runner.validate(context, state)
        self.assertEqual(state['previous_attempt'], 'external-05')
        self.assertEqual(state['previous_number'], 5)
        self.assertEqual(state['repair_input_mode'], 'raw-hd-edit-note-detail-v1')
        self.assertIsNone(state['repair'].get('mask_url'))
        self.assertEqual(parameters['model'], policy.NANO_MODEL)
        self.assertEqual(parameters['quality'], '2K')
        self.assertEqual(len(parameters['image_urls']), 4)
        self.assertNotIn('background', parameters)
        self.assertNotIn('n', parameters)
        self.assertNotIn('resolution', parameters)
        self.assertNotIn('mask_url', parameters)
        self.assertNotIn('--background', command)
        self.assertNotIn('--mask-url', command)
        self.assertEqual(refusal['provider_error'], 'content_policy_violation')

    def test_client_serializes_resolution_as_nano_quality_only(self):
        prompt_path = ROOT / 'mod_nailong/experiments/evolink-high131-flare-20261025/prompts/889edc5a10979a25b5507640325ac122112474d07a0ca1efe99d067d5d4a5f28-07.txt'
        urls = [f'https://example.invalid/{index}.png' for index in range(4)]
        args = SimpleNamespace(
            prompt_file=prompt_path, model=policy.NANO_MODEL, image_url=urls,
            mask_url=None, size='1:1', resolution='2K', quality='high', background='transparent',
        )
        prompt, payload = evolink_image.build_request(args)
        self.assertEqual(prompt, prompt_path.read_text(encoding='utf-8'))
        self.assertEqual(payload, {
            'model': policy.NANO_MODEL, 'prompt': prompt, 'size': '1:1',
            'image_urls': urls, 'quality': '2K',
        })
        for field in ('background', 'n', 'resolution', 'mask_url'):
            self.assertNotIn(field, payload)


if __name__ == '__main__':
    unittest.main()
