"""Regression checks for explicit full-canvas classification; no game assets written."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from PIL import Image
from mod_nailong.tools.generation_requests import source_alpha_policy,verified_opaque_canvas_instruction


class SourceAlphaPolicyChecks(unittest.TestCase):
    def image(self,minimum):
        image=Image.new('RGBA',(2,2),(30,20,10,255))
        image.putpixel((0,0),(30,20,10,minimum))
        return image

    def test_frozen_default_classification_stays_compatible(self):
        for minimum in [0,1,240,242,246,248,249,254,255]:
            with self.subTest(minimum=minimum):
                policy=source_alpha_policy(self.image(minimum))
                self.assertEqual(policy['transparent_background'],minimum<249)
                self.assertEqual(policy['original_alpha_extrema'],[minimum,255])
                self.assertNotIn('opaque_canvas_reason',policy)

    def test_explicit_review_recognizes_diagnostic_sources_without_editing_pixels(self):
        for minimum in [240,242,246,249,255]:
            with self.subTest(minimum=minimum):
                image=self.image(minimum);before=image.tobytes()
                policy=source_alpha_policy(image,opaque_canvas_reason='Actually viewed full source rectangle; SHA-bound review evidence')
                self.assertFalse(policy['transparent_background'])
                self.assertEqual(policy['alpha_prompt_policy'],'source-manually-verified-opaque-canvas-v1')
                self.assertEqual(policy['original_alpha_extrema'],[minimum,255])
                self.assertTrue(policy['opaque_canvas_reason'])
                self.assertEqual(image.tobytes(),before)

    def test_missing_evidence_or_genuine_exterior_alpha_cannot_be_overridden(self):
        for reason in ['', '  ']:
            with self.assertRaises(ValueError):source_alpha_policy(self.image(240),opaque_canvas_reason=reason)
        with self.assertRaises(ValueError):source_alpha_policy(self.image(0),opaque_canvas_reason='Claimed painted rectangle')

    def test_manual_instruction_has_no_wrong_numeric_threshold_or_cutout_request(self):
        instruction=verified_opaque_canvas_instruction()
        self.assertIn('alpha 255',instruction)
        self.assertIn('all four canvas edges',instruction)
        self.assertNotIn('at least 249',instruction)


if __name__=='__main__':unittest.main()
