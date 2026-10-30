import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from tools.common import file_sha256
from mod_nailong.tools.hd_masking import sprite_records,unique_aliases


class NativeBindingSafety(unittest.TestCase):
    def records(self,text):
        return [dict(r,source_id=3) for r in sprite_records(text)]

    def test_comments_nested_animation_and_doubled_slashes_do_not_mix_people(self):
        text='''spriteTypes = {
          spriteType = { name = "GFX_first" texturefile = "gfx\\\\leaders\\\\one.dds"
             animation = { texturefile = "gfx/unrelated.dds" name = "other" } }
          # name = "GFX_bogus" texturefile = "gfx/bogus.dds"
          spriteType = { name = GFX_second texturefile = "gfx/leaders/two.dds" noOfFrames = 1 }
        }'''
        found=unique_aliases(self.records(text),{'gfx/leaders/one.dds','gfx/leaders/two.dds'})
        self.assertEqual([(r['name'],r['texture']) for r in found],
                         [('GFX_first','gfx/leaders/one.dds'),('GFX_second','gfx/leaders/two.dds')])

    def test_cross_package_alias_conflict_cannot_silently_change_identity(self):
        records=self.records('spriteType={name=GFX_person texturefile="gfx/a.dds"}')
        records+=self.records('spriteType={name=gfx_person texturefile="gfx/b.dds"}')
        with self.assertRaisesRegex(ValueError,'Ambiguous'):unique_aliases(records,{'gfx/a.dds'})

    def test_frame_strip_and_existing_mask_require_separate_runtime_work(self):
        for extra,message in [('noOfFrames=2','frame count'),('masking_texture="gfx/mask.dds"','mask already')]:
            with self.subTest(extra=extra):
                records=self.records('spriteType={name=GFX_person texturefile="gfx/a.dds" '+extra+'}')
                with self.assertRaisesRegex(ValueError,message):unique_aliases(records,{'gfx/a.dds'})

    def test_missing_alias_cannot_be_claimed_as_adapted(self):
        with self.assertRaisesRegex(ValueError,'No verified'):unique_aliases([],{'gfx/a.dds'})

    def test_only_registered_original_nonperson_bytes_skip_adaptation(self):
        from mod_nailong.tools.hd_masking import partition_bindings
        person={'path':'gfx/person.dds','source_sha256':'person','fullsize_master_sha256':'master'}
        exception={'path':'gfx/object.dds','source_sha256':'object','fullsize_master_sha256':None,'preserved_original_nonperson_exception':True}
        people,preserved=partition_bindings([person,exception],{'object'})
        self.assertEqual(people,{'gfx/person.dds':person})
        self.assertEqual(preserved,{'gfx/object.dds':exception})
        with self.assertRaisesRegex(ValueError,'Non-person exception'):
            partition_bindings([dict(exception,fullsize_master_sha256='generated')],{'object'})
        with self.assertRaisesRegex(ValueError,'Person binding'):
            partition_bindings([dict(person,preserved_original_nonperson_exception=True)],{'object'})

    def test_inventory_only_requires_actual_no_consumer_evidence(self):
        from mod_nailong.tools.hd_masking import take_inventory_only
        person={'path':'gfx/person.dds','source_sha256':'person','fullsize_master_sha256':'master'}
        record={'path':'gfx/person.dds','source_sha256':'person','classification':'no_current_native_consumer_in_bounded_inventory','runtime_display_not_applicable_unless_a_consumer_is_found':True}
        self.assertEqual(take_inventory_only({'gfx/person.dds':person},[record]),{'gfx/person.dds':person})
        with self.assertRaisesRegex(ValueError,'Unproven'):
            take_inventory_only({'gfx/person.dds':person},[dict(record,classification='guessed_unused')])
        self.assertEqual(take_inventory_only({'gfx/person.dds':person},[]),{})

    def test_shared_layout_keeps_distinct_portrait_masks_and_pixels(self):
        from mod_nailong.tools import hd_masking
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);output=root/'build';staging=output/'staging'
            masters=root/'mod_nailong/assets/generated_fullsize';masters.mkdir(parents=True)
            bindings=[];files=[];aliases=[]
            for name,color in [('first','red'),('second','blue')]:
                png=masters/(name+'.png');Image.new('RGBA',(4,6),color).save(png)
                digest=file_sha256(png);png.rename(masters/(digest+'.png'))
                target=staging/f'gfx/{name}.dds';target.parent.mkdir(parents=True,exist_ok=True)
                Image.new('RGBA',(4,6),color).save(target,format='DDS')
                bindings.append({'path':f'gfx/{name}.dds','source_sha256':name,
                    'fullsize_master_sha256':digest,'original_game_size':[2,3]})
                files.append({'path':f'gfx/{name}.dds','bytes':target.stat().st_size,'sha256':file_sha256(target)})
                aliases.append({'name':'GFX_'+name,'texture':f'gfx/{name}.dds','source_ids':[]})
            shader=root/'mod_nailong/assets/runtime/hd_portrait_masking_sampler.shader'
            shader.parent.mkdir(parents=True);shader.write_text('// test shader\n')
            manifest={'archive_filename':'gangnailongxin.zip','bindings':bindings,'files':files}
            with patch.object(hd_masking,'ROOT',root),patch('mod_nailong.tools.build_release.nonperson_scope',return_value=({},None)):
                hd_masking.augment(output,manifest,aliases,[])
            self.assertEqual(hd_masking.verify_layout_bindings(output)['primary_layout_textures'],1)
            records=sprite_records((staging/'interface/zz_naiwa_hd_masking_samples.gfx').read_text())
            self.assertEqual(len({r['texture'] for r in records}),1)
            self.assertEqual({r['existing_mask'] for r in records},{'gfx/first.dds','gfx/second.dds'})
            for record in records:
                with Image.open(staging/record['texture']) as carrier:
                    self.assertEqual(carrier.size,(2,3))
                    self.assertEqual(carrier.getpixel((0,0)),(255,255,255,255))

            gfx=staging/'interface/zz_naiwa_hd_masking_samples.gfx'
            gfx.write_text(gfx.read_text().replace('masking_texture = "gfx/first.dds"','masking_texture = "gfx/second.dds"'))
            with self.assertRaisesRegex(ValueError,'differ from their exact manifest'):
                hd_masking.verify_layout_bindings(output)


if __name__=='__main__':unittest.main()
