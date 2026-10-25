import tempfile,unittest
from pathlib import Path
from PIL import Image
from tools.common import write_json,file_sha256,machine_id
from mod_nailong.tools.prepare_ready_art_reviews import reviewed_canvas_reasons


class ReviewedSourceCanvasTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.key='a'*64
        self.source=self.root/f'runtime/references/{self.key}.png'
        self.source.parent.mkdir(parents=True);Image.new('RGBA',(3,3),(4,5,6,243)).save(self.source)
        evidence=self.root/'manual-observation.json';write_json(evidence,{'actually_viewed':True})
        self.entry={'source_sha256':self.key,'original_png_sha256':file_sha256(self.source)}
        self.registry={'machine_id':machine_id(),'sources':{self.key:{'actually_viewed':True,'complete_painted_rectangle':True,'opaque_canvas_reason':'Actually viewed full grey painted rectangle, including all corners.','original_png_sha256':file_sha256(self.source),'original_alpha_extrema':[243,243],'evidence':[{'path':'manual-observation.json','sha256':file_sha256(evidence)}]}}}
        self.path=self.root/'mod_nailong/data/reviewed-source-canvas.json'
    def save(self):write_json(self.path,self.registry)
    def inspect(self):return reviewed_canvas_reasons(self.root,[(Path('report.json'),self.entry)])
    def test_no_registry_does_not_infer_full_canvas(self):self.assertEqual(self.inspect(),{})
    def test_manually_verified_low_nonzero_alpha_retains_reason(self):
        self.save();self.assertEqual(self.inspect()[self.key]['opaque_canvas_reason'],self.registry['sources'][self.key]['opaque_canvas_reason'])
    def test_unrelated_sources_unchanged(self):
        self.save();self.assertEqual(reviewed_canvas_reasons(self.root,[(Path('r'),{'source_sha256':'b'*64})]),{})
    def test_changed_observation_evidence_rejected(self):
        self.save();write_json(self.root/'manual-observation.json',{'changed':True})
        with self.assertRaises(AssertionError):self.inspect()
    def test_changed_original_rejected(self):
        self.save();Image.new('RGBA',(3,3),(9,8,7,243)).save(self.source)
        with self.assertRaises(AssertionError):self.inspect()
    def test_explicit_visual_classification_required(self):
        self.registry['sources'][self.key]['complete_painted_rectangle']=False;self.save()
        with self.assertRaises(AssertionError):self.inspect()
    def test_true_exterior_transparency_rejected(self):
        Image.new('RGBA',(3,3),(4,5,6,0)).save(self.source)
        proof=self.registry['sources'][self.key];proof['original_png_sha256']=file_sha256(self.source);proof['original_alpha_extrema']=[0,0]
        self.entry['original_png_sha256']=file_sha256(self.source);self.save()
        with self.assertRaises(AssertionError):self.inspect()
    def test_review_source_binding_required(self):
        self.entry['original_png_sha256']='0'*64;self.save()
        with self.assertRaises(AssertionError):self.inspect()


if __name__=='__main__':unittest.main()
