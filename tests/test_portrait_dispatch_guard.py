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
    def test_unnamed_ace_gender_and_index_are_not_person_names(self):
        male=entry('gfx/aces/DEN_ace_m_0.dds')
        other=entry('gfx/aces/southamerican_ace_m_0.dds')
        self.assertIsNone(surname(male['paths'][0]))
        self.assertIsNone(surname(other['paths'][0]))
        self.assertFalse(same_service_family('one','two',male,other))
        self.assertFalse(same_service_family('one','two',entry('western_european_ace_f_0.dds'),entry('eastern_european_ace_f_1.dds')))
    def test_actual_identity_of_unnamed_aces_and_named_ace_variants_stays_held(self):
        first=entry('DEN_ace_m_0.dds','real_native_character')
        other=entry('southamerican_ace_m_0.dds','real_native_character')
        self.assertTrue(same_service_family('one','two',first,other))
        self.assertTrue(same_service_family('same','same',entry('ace_m_0.dds'),entry('ace_m_1.dds')))
        self.assertEqual(surname('ace_hans_philipp.dds'),'philipp')
        self.assertTrue(same_service_family('one','two',entry('ace_hans_philipp.dds'),entry('portrait_hans_philipp_small.dds')))
    def test_ordinals_and_titles_are_not_person_names_by_themselves(self):
        wilhelm=entry('portrait_GER_wilhelm_ii.dds')
        self.assertFalse(same_service_family('one','two',wilhelm,entry('portrait_BEL_leopold_ii.dds')))
        self.assertTrue(same_service_family('one','variant',wilhelm,entry('portrait_GER_wilhelm_ii_small.dds')))
        self.assertFalse(same_service_family('one','two',entry('idea_TUR_refe_pasha.dds'),entry('idea_TUR_ahmet_fevzi_pasha.dds')))
    def test_donitz_spelling_variants_remain_held(self):
        self.assertTrue(same_service_family('one','two',entry('portrait_GER_karl_donitz.dds'),entry('idea_GER_karl_doenitz.dds')))

    def test_civil_outfit_suffix_does_not_merge_distinct_native_people(self):
        calles=entry('gfx/leaders/MEX/portrait_mex_calles_civil.dds','MEX_plutarco_calles')
        avila=entry('gfx/leaders/MEX/portrait_mex_avila_civil.dds','MEX_manuel_avila_camacho')
        self.assertEqual(surname(calles['paths'][0]),'calles')
        self.assertEqual(surname(avila['paths'][0]),'avila')
        self.assertFalse(same_service_family('calles','avila',calles,avila))
        self.assertFalse(same_service_family('avila','calles',avila,calles))

    def test_outfit_variants_of_actual_same_person_remain_held(self):
        for suffix in ['civil','civilian','military','army','navy','admiral','scientist','unaligned','leader']:
            with self.subTest(suffix=suffix):
                base=entry('portrait_MEX_manuel_avila_camacho.dds')
                variant=entry('portrait_MEX_manuel_avila_camacho_'+suffix+'_small.dds')
                self.assertTrue(same_service_family('base','variant',base,variant))
                other=entry('portrait_MEX_plutarco_calles_'+suffix+'_small.dds')
                self.assertFalse(same_service_family('base','other',base,other))

if __name__=='__main__':unittest.main()
