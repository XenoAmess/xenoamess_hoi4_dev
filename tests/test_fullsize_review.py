import tempfile
import unittest
from pathlib import Path
from PIL import Image
from tools.common import file_sha256
from mod_nailong.tools.review_pairs import generated_master,review_thumbnail


class FullsizeReviewTests(unittest.TestCase):
    def test_review_uses_raw_master_and_preserves_its_aspect(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);native=root/'native.png';master=root/'master.png'
            Image.new('RGBA',(65,67),'red').save(native)
            Image.new('RGBA',(400,200),'gold').save(master)
            before=file_sha256(master);native_before=file_sha256(native)
            selected=generated_master({'image':'native.png','generated_fullsize_image':'master.png','generated_fullsize_sha256':before},root)
            self.assertEqual(selected,master)
            with Image.open(selected) as image:self.assertEqual(review_thumbnail(image).size,(156,78))
            self.assertEqual(file_sha256(master),before)
            self.assertEqual(file_sha256(native),native_before)

    def test_missing_or_changed_master_never_falls_back_to_native(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);Image.new('RGBA',(65,67),'red').save(root/'native.png')
            row={'image':'native.png','generated_fullsize_image':'missing.png','generated_fullsize_sha256':'0'*64}
            with self.assertRaisesRegex(ValueError,'unavailable'):generated_master(row,root)
            row['generated_fullsize_image']='native.png'
            with self.assertRaisesRegex(ValueError,'changed'):generated_master(row,root)


if __name__=='__main__':unittest.main()
