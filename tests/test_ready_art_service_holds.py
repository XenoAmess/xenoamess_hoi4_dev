import unittest
from pathlib import Path
from mod_nailong.tools.prepare_ready_art_reviews import eligible_entries, service_held_keys


class ReadyArtServiceHoldTests(unittest.TestCase):
    def test_cancelled_same_person_hold_cannot_block_unrelated_ready_art(self):
        priority={'a':{'characters':['same'],'paths':['gfx/portrait_alfa_small.dds']},
                  'b':{'characters':['same'],'paths':['gfx/portrait_alfa.dds']},
                  'c':{'characters':['other'],'paths':['gfx/portrait_other.dds']}}
        failures=[{'source_sha256':'b','status':'blocked'}]
        held=service_held_keys(['a','c'],priority,failures)
        self.assertEqual(held,{'a'})
        reports=[(Path('report.json'),{'decisions':[
            {'source_sha256':key,'decision':'rejected','generated_fullsize_sha256':key*64}
            for key in ['a','c']]})]
        rows={key:{'review':'rejected','generated_fullsize_sha256':key*64} for key in ['a','c']}
        latest={'a':{'status':'cancelled_before_generation'},'c':{'status':'generated_rejected_visual_review'}}
        selected=eligible_entries(reports,rows,latest,held)
        self.assertEqual([entry['source_sha256'] for _,entry in selected],['c'])

    def test_successful_service_resolution_releases_family_without_resetting_failure(self):
        priority={'a':{'characters':['same'],'paths':['gfx/portrait_alfa_small.dds']},
                  'b':{'characters':['same'],'paths':['gfx/portrait_alfa.dds']}}
        failure={'source_sha256':'b','status':'blocked','resolved_by_retry':True}
        self.assertEqual(service_held_keys(['a'],priority,[failure]),set())
        self.assertTrue(failure['resolved_by_retry'])


if __name__=='__main__':unittest.main()
