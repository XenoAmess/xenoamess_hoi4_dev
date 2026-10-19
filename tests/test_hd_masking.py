import unittest
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


if __name__=='__main__':unittest.main()
