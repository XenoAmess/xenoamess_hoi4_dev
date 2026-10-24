import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / 'mod_nailong/tools/repair_outer_alpha.py'


class RepairOuterAlphaTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / 'source.png'
        self.base = self.root / 'base.png'
        self.output = self.root / 'output.png'
        source = Image.new('RGBA', (2, 2))
        source.putdata([(255, 0, 0, 255), (0, 255, 0, 254), (0, 0, 255, 128), (255, 255, 0, 0)])
        source.save(self.source)
        Image.new('RGB', (4, 4), (10, 20, 30)).save(self.base)

    def run_tool(self, check=True):
        return subprocess.run([sys.executable, str(SCRIPT), '--source', str(self.source), '--base', str(self.base), '--output', str(self.output)], check=check, capture_output=True, text=True)

    def test_rgb_is_unchanged_and_source_alpha_is_mapped(self):
        result = self.run_tool()
        receipt = json.loads(result.stdout)
        with Image.open(self.source) as source, Image.open(self.base) as base, Image.open(self.output) as output:
            expected_alpha = source.getchannel('A').resize(base.size, Image.Resampling.BILINEAR)
            self.assertEqual(output.mode, 'RGBA')
            self.assertEqual(output.size, base.size)
            self.assertEqual(output.convert('RGB').tobytes(), base.convert('RGB').tobytes())
            self.assertEqual(output.getchannel('A').tobytes(), expected_alpha.tobytes())
            output_coordinates = ((0, 0), (output.width - 1, 0), (0, output.height - 1), (output.width - 1, output.height - 1))
            source_coordinates = ((0, 0), (source.width - 1, 0), (0, source.height - 1), (source.width - 1, source.height - 1))
            self.assertEqual([output.getchannel('A').getpixel(point) for point in output_coordinates], [source.getchannel('A').getpixel(point) for point in source_coordinates])
        self.assertTrue(receipt['rgb_unchanged'])
        self.assertTrue(receipt['alpha_matches_resized_source'])
        self.assertEqual(receipt['output_sha256'], receipt['output_sha256'].lower())

    def test_existing_output_is_not_overwritten(self):
        self.run_tool()
        original = self.output.read_bytes()
        result = self.run_tool(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
