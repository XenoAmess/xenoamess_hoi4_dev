"""A historical exact retry must retain its old art direction on import."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from tools.common import file_sha256,read_json,write_json
from mod_nailong.tools import generation_requests as requests
from mod_nailong.tools.art_contract import portrait_ready

class RequestImportTests(unittest.TestCase):
    def test_legacy_retry_is_not_silently_promoted_to_current_art(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);mod=root/'mod_nailong';key='a'*64
            original=root/'generated.png';Image.new('RGBA',(2,2),'yellow').save(original)
            journal=mod/'data/generation-requests'/(key+'.json')
            write_json(journal,{'attempts':[{'number':2,'status':'prepared','prompt_file':'prompt.txt','inputs':[{'role':'reference'}],'edit_existing':False,'art_direction':'legacy-no-hair-v0'}]})
            def old_ingest(*args):
                write_json(mod/'data/generated.json',{'portraits':{key:{'image':'generated.png','image_sha256':file_sha256(original),'art_direction':'hair-features-v1','review':'pending'}}})
            with patch.object(requests,'ROOT',root),patch.object(requests,'MOD',mod),patch.object(requests,'REQUESTS',journal.parent),patch.object(requests,'ingest',side_effect=old_ingest):
                requests.finish(key,str(original))
            row=read_json(mod/'data/generated.json')['portraits'][key]
            self.assertEqual(row['art_direction'],'legacy-no-hair-v0')
            self.assertFalse(portrait_ready(row))
            self.assertEqual(read_json(journal)['attempts'][-1]['status'],'generated_pending_visual_review')
