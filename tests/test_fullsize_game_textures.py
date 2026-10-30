"""Native game derivatives must come from their own unchanged HD masters."""
import io,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from tools.common import write_json,file_sha256
from mod_nailong.tools import build_release as builder

class FullsizeGameTextures(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.mod=self.root/'mod_nailong';self.key='a'*64
  self.master=self.mod/'assets/generated_fullsize/master.png';self.master.parent.mkdir(parents=True)
  image=Image.new('RGBA',(24,32));image.putdata([(n%256,(n*7)%256,(n*13)%256,(n*17)%256) for n in range(24*32)]);image.save(self.master)
  (self.mod/'mod').mkdir();(self.mod/'mod/descriptor.mod').write_text('name="HD (Development)"\n')
  write_json(self.mod/'data/catalog.json',{'assets':[{'id':'sample','path':'gfx/leaders/TST/sample.dds','package':'base','source_sha256':self.key,'size':[3,4]}],'game_version':'test','unresolved_references':[]})
  self.row={'image':'low-resolution-preview.png','image_sha256':'preview-sha','review':'approved','art_direction':'hair-features-v1','collar_fit':{'policy':'collar-fit-v1','status':'approved','image_sha256':'preview-sha'},'generated_fullsize_image':self.master.relative_to(self.root).as_posix(),'generated_fullsize_sha256':file_sha256(self.master),'generated_fullsize_size':[24,32]}
  write_json(self.mod/'data/generated.json',{'portraits':{self.key:self.row}})
  for item in [patch.object(builder,'ROOT',self.root),patch.object(builder,'MOD',self.mod),patch.object(builder,'nonperson_scope',return_value=({},None))]:item.start();self.addCleanup(item.stop)
 def test_export_uses_native_dimensions_without_changing_master(self):
  before=self.master.read_bytes()
  files,manifest=builder.payload(preview=True)
  with Image.open(io.BytesIO(files['gfx/leaders/TST/sample.dds'])) as actual,Image.open(self.master) as original:
   self.assertEqual(actual.size,(3,4));self.assertEqual(actual.convert('RGBA').tobytes(),original.convert('RGBA').resize((3,4),Image.Resampling.LANCZOS).tobytes())
  self.assertEqual(self.master.read_bytes(),before)
  self.assertTrue(manifest['bindings'][0]['resized'])
  self.assertEqual(manifest['bindings'][0]['original_game_size'],[3,4])
 def test_missing_master_does_not_fall_back_to_preview(self):
  self.master.unlink()
  with self.assertRaises(FileNotFoundError):builder.payload(preview=True)
 def test_changed_master_blocks_export(self):
  self.master.write_bytes(b'changed')
  with self.assertRaisesRegex(SystemExit,'Fullsize master checksum mismatch'):builder.payload(preview=True)
 def test_streamed_build_uses_native_payload_and_reports_subset_scope(self):
  output=self.root/'out';manifest=builder.build(output,preview=True,validation_keys={self.key})
  self.assertEqual(manifest['validation_scope'],'selected development subset only')
  with Image.open(output/'staging/gfx/leaders/TST/sample.dds') as image:self.assertEqual(image.size,(3,4))
  builder.verify(output)
 def test_subset_cannot_bypass_formal_scope(self):
  with self.assertRaisesRegex(SystemExit,'Validation subsets'):builder.payload(validation_keys={self.key})
 def test_complete_art_does_not_unlock_unqualified_gameplay(self):
  with self.assertRaisesRegex(SystemExit,'gameplay acceptance remains unqualified'):builder.payload(preview=False)
 def test_validation_sample_builds_the_enabled_dlc_variant(self):
  catalog={'assets':[{'id':'base','path':'gfx/leaders/TST/sample.dds','package':'base','source_sha256':self.key,'size':[3,4]},
                     {'id':'dlc1','path':'gfx/leaders/TST/sample.dds','package':'dlc/dlc1','source_sha256':'b'*64,'size':[3,4]},
                     {'id':'dlc2','path':'gfx/leaders/TST/sample.dds','package':'dlc/dlc2','source_sha256':'c'*64,'size':[3,4]}],
           'game_version':'test','unresolved_references':[]}
  rows={key:dict(self.row) for key in [self.key,'b'*64,'c'*64]}
  write_json(self.mod/'data/catalog.json',catalog);write_json(self.mod/'data/generated.json',{'portraits':rows})
  for packages,expected in [(None,'c'*64),(['dlc/dlc1'],'b'*64),([],self.key)]:
   with self.subTest(packages=packages):
    keys=builder.validation_sample_keys(catalog,rows,4,packages)
    self.assertEqual(keys,[expected])
    output=self.root/('sample-'+expected[0]);manifest=builder.build(output,preview=True,packages=packages,validation_keys=keys)
    self.assertEqual([b['source_sha256'] for b in manifest['bindings']],[expected]);builder.verify(output)
 def test_validation_sample_does_not_substitute_superseded_ready_art(self):
  catalog={'assets':[{'id':'base','path':'gfx/leaders/TST/sample.dds','package':'base','source_sha256':self.key,'size':[3,4]},
                     {'id':'dlc','path':'gfx/leaders/TST/sample.dds','package':'dlc/dlc1','source_sha256':'b'*64,'size':[3,4]}]}
  self.assertEqual(builder.validation_sample_keys(catalog,{self.key:self.row},4),[])
 def test_repackage_preserves_verified_textures_and_is_deterministic(self):
  cover=self.mod/'assets/branding/workshop-cover.jpg';cover.parent.mkdir(parents=True)
  Image.new('RGB',(8,8),'yellow').save(cover)
  source=self.root/'source';prior=builder.build(source,preview=True)
  (self.mod/'mod/descriptor.mod').write_text('name="Product"\nversion="0.1.0"\n')
  with patch.object(builder,'validate_heavy_write_admission'):
   first=builder.repackage_verified(source,self.root/'first',None)
   builder.repackage_verified(source,self.root/'second',None)
  self.assertEqual(first['bindings'],prior['bindings'])
  self.assertEqual((self.root/'first/staging/gfx/leaders/TST/sample.dds').read_bytes(),(source/'staging/gfx/leaders/TST/sample.dds').read_bytes())
  self.assertEqual((self.root/'first/staging/descriptor.mod').read_text(),'name="Product"\nversion="0.1.0"\n')
  self.assertEqual(file_sha256(self.root/'first/gangnailongxin.zip'),file_sha256(self.root/'second/gangnailongxin.zip'))
 def test_repackage_rejects_tampered_game_texture(self):
  source=self.root/'source';builder.build(source,preview=True)
  (source/'staging/gfx/leaders/TST/sample.dds').write_bytes(b'changed')
  with self.assertRaises((AssertionError,SystemExit,ValueError)):
   builder.repackage_verified(source,self.root/'out',None)
 def test_repackage_rejects_withdrawn_art_approval(self):
  source=self.root/'source';builder.build(source,preview=True)
  self.row['review']='rejected';write_json(self.mod/'data/generated.json',{'portraits':{self.key:self.row}})
  with self.assertRaisesRegex(ValueError,'currently approved'):
   builder.repackage_verified(source,self.root/'out',None)

if __name__=='__main__':unittest.main()
