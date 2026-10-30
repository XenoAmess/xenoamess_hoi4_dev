import tempfile,unittest
from pathlib import Path
from PIL import Image
from tools.common import file_sha256,write_json
from unittest.mock import patch
from mod_nailong.tools import texture_resolution as resolution


class NativeGameTextureSafety(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name);self.output=self.root/'build'
        self.master_dir=self.root/'mod_nailong/assets/generated_fullsize';self.master_dir.mkdir(parents=True)
        self.payload=self.output/'staging/gfx/person.dds';self.payload.parent.mkdir(parents=True)
        png=self.master_dir/'source.png';image=Image.new('RGBA',(6,8));image.putdata([(i*5%256,i*7%256,i*11%256,i*13%256) for i in range(48)]);image.save(png)
        self.sha=file_sha256(png);self.master=png.with_name(self.sha+'.png');png.rename(self.master)
        with Image.open(self.master) as image:resolution.game_image(image,(3,4)).save(self.payload,format='DDS')
        self.row={'generated_fullsize_image':str(self.master.relative_to(self.root)),'generated_fullsize_sha256':self.sha,'generated_fullsize_size':[6,8],
            'review':'approved','art_direction':'hair-features-v1','image_sha256':'reviewed','collar_fit':{'status':'approved','policy':'collar-fit-v1','image_sha256':'reviewed'}}
        self.catalog={'assets':[{'path':'gfx/person.dds','source_sha256':'source','size':[3,4],'package':'base'}]}
        self.binding={'path':'gfx/person.dds','package':'base','source_sha256':'source','fullsize_master_sha256':self.sha,'fullsize_master_size':[6,8],
            'original_game_size':[3,4],'size':[3,4],'resized':True,'resolution_policy':resolution.POLICY_ID,'sha256':file_sha256(self.payload)}
        self.manifest={'texture_resolution_policy_id':resolution.POLICY_ID,'bindings':[self.binding],'files':[{'path':'gfx/person.dds'}]}

    def verify(self):return resolution.verify_game_textures(self.output,self.manifest,self.catalog,{'source':self.row},root=self.root)

    def test_native_derivative_keeps_fullsize_bytes_and_partial_alpha(self):
        self.assertEqual(self.verify()['native_size_derivatives'],1)
        self.assertEqual(file_sha256(self.master),self.sha)
        with Image.open(self.master) as source:
            expected=resolution.game_image(source,(3,4))
            self.assertEqual(resolution.read_generated_texture(self.payload).tobytes(),expected.tobytes())

    def test_oversized_legacy_payload_and_experimental_adapter_are_blocked(self):
        self.manifest['texture_resolution_policy_id']='original-fullsize-master'
        with self.assertRaisesRegex(ValueError,'Obsolete'):self.verify()
        self.manifest['texture_resolution_policy_id']=resolution.POLICY_ID
        self.manifest['development_fixture']={'aliases':[]}
        with self.assertRaisesRegex(ValueError,'Retired'):self.verify()

    def test_wrong_person_pixels_are_blocked_even_at_correct_dimensions(self):
        Image.new('RGBA',(3,4),'blue').save(self.payload,format='DDS')
        self.binding['sha256']=file_sha256(self.payload)
        with self.assertRaisesRegex(ValueError,'do not match their own approved master'):self.verify()

    def test_wrong_source_package_size_and_stale_review_are_blocked(self):
        self.binding['source_sha256']='other'
        with self.assertRaisesRegex(ValueError,'source/package binding'):self.verify()
        self.binding['source_sha256']='source';self.binding['size']=[4,3]
        with self.assertRaisesRegex(ValueError,'Declared game dimensions'):self.verify()
        self.binding['size']=[3,4];self.row['review']='pending'
        with self.assertRaisesRegex(ValueError,'currently approved master'):self.verify()

    def test_actual_dimensions_undeclared_resize_and_carrier_are_blocked(self):
        Image.new('RGBA',(6,8),'red').save(self.payload,format='DDS')
        self.binding['sha256']=file_sha256(self.payload)
        with self.assertRaisesRegex(ValueError,'Actual game texture dimensions'):self.verify()
        with Image.open(self.master) as source:resolution.game_image(source,(3,4)).save(self.payload,format='DDS')
        self.binding['sha256']=file_sha256(self.payload)
        self.binding['resized']=False
        with self.assertRaisesRegex(ValueError,'Undeclared'):self.verify()
        self.manifest['files'].append({'path':'gfx/white_layout.dds'})
        with self.assertRaisesRegex(ValueError,'Unbound texture'):self.verify()

    def test_decoder_preserves_channel_order_and_rejects_corrupt_header(self):
        image=Image.new('RGBA',(2,2));image.putdata([(1,2,3,4),(250,12,42,0),(18,211,94,254),(55,44,33,255)]);image.save(self.payload,format='DDS')
        self.assertEqual(resolution.read_generated_texture(self.payload).tobytes(),image.tobytes())
        raw=bytearray(self.payload.read_bytes());raw[92:96]=b'\xff\x00\x00\x00';self.payload.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'Unsupported or corrupt'):resolution.read_generated_texture(self.payload)

    def test_verified_bytes_can_reuse_pixel_proof_but_changed_bytes_cannot(self):
        write_json(self.output/'manifest.json',self.manifest)
        resolution.write_pixel_proof(self.output,self.manifest,self.verify())
        with patch.object(resolution,'game_image',side_effect=AssertionError('Unnecessary second resize')):
            result=resolution.verify_game_textures(self.output,self.manifest,self.catalog,{'source':self.row},root=self.root,reuse_pixel_proof=True)
        self.assertTrue(result['pixel_proof_reused'])
        Image.new('RGBA',(3,4),'blue').save(self.payload,format='DDS')
        with self.assertRaisesRegex(ValueError,'bytes changed'):
            resolution.verify_game_textures(self.output,self.manifest,self.catalog,{'source':self.row},root=self.root,reuse_pixel_proof=True)


if __name__=='__main__':unittest.main()
