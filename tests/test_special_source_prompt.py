import unittest
from tools.special_source_prompt import special_source_prompt
class SpecialSourcePromptTests(unittest.TestCase):
    def setUp(self):
        self.source={"key":"key","original_png_sha256":"png","description":"source cap facing left"}
        self.auth={"explicit_user_answers":True,"sources":{"key":{"original_png_sha256":"png","mode":"grayscale_mascot_silhouette"}}}
    def test_silhouette_keeps_anonymity_and_source_description(self):
        p=special_source_prompt(self.source,self.auth)
        self.assertIn("No visible eyes",p);self.assertIn(self.source["description"],p)
        self.assertIn("GREY-BLACK",p)
    def test_placeholder_preserves_original_words(self):
        self.auth["sources"]["key"]["mode"]="mascot_placeholder_preserve_text"
        p=special_source_prompt(self.source,self.auth)
        self.assertIn("PLACE and HOLD",p);self.assertIn("Do not remove, translate",p)
    def test_different_source_or_absent_explicit_answer_cannot_inherit_direction(self):
        for s,a in [({**self.source,"original_png_sha256":"different"},self.auth),(self.source,{**self.auth,"explicit_user_answers":False})]:
            with self.assertRaises(AssertionError):special_source_prompt(s,a)
        with self.assertRaises(KeyError):special_source_prompt({**self.source,"key":"other"},self.auth)
    def test_unknown_mode_stops_before_preparation(self):
        self.auth["sources"]["key"]["mode"]="other"
        with self.assertRaises(AssertionError):special_source_prompt(self.source,self.auth)
