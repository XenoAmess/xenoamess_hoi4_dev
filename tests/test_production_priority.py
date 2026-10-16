import unittest
from mod_nailong.tools.production_priority import classify,gate_lower_priority

class ProductionPriorityTests(unittest.TestCase):
    def test_named_fictional_and_generic_fallback_are_high(self):
        def asset(key,path,character=None):
            return {'source_sha256':key,'path':path,'size':[156,210],
                    'references':[{'character':character,'scope':'characters/'+character+'/portraits/civilian'}] if character else []}
        rows=[asset('named','gfx/leaders/ALT/portrait_ALT_fictional_emperor.dds'),
              asset('fallback','gfx/leaders/Europe/generic_leader.dds','ALT_named_person'),
              asset('pilot','gfx/aces/ALT_named_pilot_ace.dds'),
              asset('generic','gfx/aces/ace_m_0.dds'),
              asset('unknown','gfx/leaders/leader_unknown.dds')]
        entries=classify({'assets':rows},{})
        self.assertEqual({k for k,e in entries.items() if e['high_priority']},{'named','fallback','pilot'})

    def test_blocked_or_rejected_high_does_not_unlock_low(self):
        entries={'high':{'high_priority':True},'low':{'high_priority':False}}
        available=[{'source_sha256':'low'}]
        for records in [{},{'high':{'review':'rejected','art_direction':'hair-features-v1'}},
                        {'high':{'review':'approved','art_direction':'legacy'}},
                        {'high':{'review':'approved','art_direction':'hair-features-v1'}}]:
            selected,incomplete=gate_lower_priority(available,entries,records)
            self.assertEqual(selected,[])
            self.assertEqual(incomplete,{'high'})
        ready={'review':'approved','art_direction':'hair-features-v1','image_sha256':'reviewed-image',
               'collar_fit':{'policy':'collar-fit-v1','status':'approved','image_sha256':'reviewed-image'}}
        selected,incomplete=gate_lower_priority(available,entries,{'high':ready})
        self.assertEqual(selected,available)
        self.assertFalse(incomplete)
        ready['collar_fit']['image_sha256']='different-image'
        self.assertFalse(gate_lower_priority(available,entries,{'high':ready})[0])
