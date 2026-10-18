import unittest
from tools.portrait_dispatch_guard import same_service_family, surname

def entry(path,*characters):
    return {'paths':[path],'characters':list(characters)}

class PortraitDispatchGuardTest(unittest.TestCase):
    def test_distinct_joliot_curie_people_are_not_service_variants(self):
        frederic=entry('gfx/leaders/scientists/portrait_FRA_frederic_joliot_curie.dds','FRA_frederic_joliot_curie')
        irene=entry('gfx/leaders/scientists/portrait_FRA_irene_joliot_curie.dds','FRA_irene_joliot_curie')
        self.assertFalse(same_service_family('frederic','irene',frederic,irene))
        self.assertFalse(same_service_family('irene','frederic',irene,frederic))
    def test_same_person_small_and_large_remain_held(self):
        large=entry('gfx/leaders/scientists/portrait_FRA_irene_joliot_curie.dds')
        small=entry('gfx/interface/ideas/idea_FRA_irene_joliot_curie_small.dds')
        self.assertTrue(same_service_family('small','large',small,large))
    def test_source_and_native_character_identity_override_filename_distinction(self):
        first=entry('portrait_FRA_frederic_joliot_curie.dds','same_native_character')
        other=entry('portrait_FRA_irene_joliot_curie.dds','same_native_character')
        self.assertTrue(same_service_family('first','other',first,other))
        self.assertTrue(same_service_family('same_source','same_source',entry('one.dds'),entry('two.dds')))
    def test_generic_and_format_suffix_do_not_group_unrelated_people(self):
        self.assertIsNone(surname('idea_generic_army_europe_4.dds'))
        first=entry('portrait_USA_william_halsey_jr_small.dds')
        self.assertEqual('halsey_jr',surname(first['paths'][0]))
        self.assertFalse(same_service_family('first','other',first,entry('portrait_USA_douglas_mcarthur_small.dds')))
    def test_ordinals_and_titles_are_not_person_names_by_themselves(self):
        wilhelm=entry('portrait_GER_wilhelm_ii.dds')
        self.assertFalse(same_service_family('one','two',wilhelm,entry('portrait_BEL_leopold_ii.dds')))
        self.assertTrue(same_service_family('one','variant',wilhelm,entry('portrait_GER_wilhelm_ii_small.dds')))
        self.assertFalse(same_service_family('one','two',entry('idea_TUR_refe_pasha.dds'),entry('idea_TUR_ahmet_fevzi_pasha.dds')))
    def test_donitz_spelling_variants_remain_held(self):
        self.assertTrue(same_service_family('one','two',entry('portrait_GER_karl_donitz.dds'),entry('idea_GER_karl_doenitz.dds')))

if __name__=='__main__':unittest.main()
