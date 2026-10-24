import tempfile,unittest,hashlib,base64,io
from pathlib import Path
from PIL import Image
from tools.production_transport_preview import preview,MAX_PREVIEW_BYTES

class PreviewTransportTests(unittest.TestCase):
 def test_original_remains_byte_identical_and_display_is_bounded(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'master.png';Image.effect_noise((1400,1800),80).convert('RGBA').save(path)
   original=path.read_bytes();result=preview(path)
   self.assertEqual(path.read_bytes(),original)
   self.assertEqual(result['original_sha256'],hashlib.sha256(original).hexdigest())
   self.assertLessEqual(result['preview_bytes'],MAX_PREVIEW_BYTES)
   raw=base64.b64decode(result['image_url'].split(',')[1]);self.assertEqual(len(raw),result['preview_bytes'])
   with Image.open(io.BytesIO(raw)) as image:self.assertLessEqual(max(image.size),320)
   self.assertIn('Display-only',result['output_hint'])

if __name__=='__main__':unittest.main()
