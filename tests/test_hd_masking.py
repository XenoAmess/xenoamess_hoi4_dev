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


if __name__=='__main__':unittest.main()
