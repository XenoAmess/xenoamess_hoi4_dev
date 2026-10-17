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
    def partial_import_fixture(self, root):
        mod=root/'mod_nailong';key='b'*64
        image=root/'returned.png';Image.new('RGBA',(4,4),'gold').save(image)
        prompt=root/'prompt.txt';prompt.write_text('Exact original prompt\n',encoding='utf-8')
        journal=mod/'data/generation-requests'/(key+'.json')
        write_json(journal,{'attempts':[{'number':1,'status':'prepared','prompt':prompt.read_text(encoding='utf-8'),'prompt_file':'prompt.txt','prompt_sha256':file_sha256(prompt),'inputs':[{'role':'reference'}],'edit_existing':False,'art_direction':'hair-features-v1'}]})
        write_json(mod/'data/catalog.json',{'assets':[{'source_sha256':key,'size':[2,2]}]})
        write_json(mod/'data/generated.json',{'portraits':{}})
        canonical=mod/'assets/portraits'/(key+'.png');canonical.parent.mkdir(parents=True)
        def interrupted_ingest(*args):
            with Image.open(image) as raw:
                raw.convert('RGBA').resize((2,2),Image.Resampling.LANCZOS).save(canonical,optimize=True)
            write_json(mod/'data/generated.json',{'portraits':{key:{'source_sha256':key,'image':canonical.relative_to(root).as_posix(),'image_sha256':file_sha256(canonical),'generated_fullsize_sha256':file_sha256(image),'prompt':prompt.read_text(encoding='utf-8'),'size':[2,2],'review':'pending'}}})
            raise OSError('simulated interruption after canonical write')
        return mod,key,image,journal,canonical,interrupted_ingest

    def test_interrupted_import_resumes_same_output_without_reimport(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            mod,key,image,journal,canonical,interrupted=self.partial_import_fixture(root)
            with patch.object(requests,'ROOT',root),patch.object(requests,'MOD',mod),patch.object(requests,'REQUESTS',journal.parent),patch.object(requests,'ingest',side_effect=interrupted) as importer:
                with self.assertRaises(OSError):requests.finish(key,str(image))
                before=file_sha256(canonical)
                self.assertEqual(read_json(journal)['attempts'][-1]['status'],'prepared')
                requests.finish(key,str(image))
                self.assertEqual(importer.call_count,1)
            row=read_json(mod/'data/generated.json')['portraits'][key]
            self.assertEqual(file_sha256(canonical),before)
            self.assertEqual(row['image_sha256'],before)
            self.assertEqual(row['review'],'pending')
            self.assertNotIn('revision_history',row)
            self.assertFalse(portrait_ready(row))
            self.assertEqual(row['import_recovery']['fullsize_sha256'],file_sha256(image))
            self.assertEqual(read_json(journal)['attempts'][-1]['output_sha256'],before)
            self.assertTrue((root/'runtime/generated-origins'/(key+'.json')).exists())

    def test_changed_partial_image_cannot_be_reconciled(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            mod,key,image,journal,canonical,interrupted=self.partial_import_fixture(root)
            with patch.object(requests,'ROOT',root),patch.object(requests,'MOD',mod),patch.object(requests,'REQUESTS',journal.parent),patch.object(requests,'ingest',side_effect=interrupted) as importer:
                with self.assertRaises(OSError):requests.finish(key,str(image))
                Image.new('RGBA',(2,2),'blue').save(canonical)
                with self.assertRaisesRegex(AssertionError,'Partial import image changed'):
                    requests.finish(key,str(image))
                self.assertEqual(importer.call_count,1)
            self.assertEqual(read_json(journal)['attempts'][-1]['status'],'prepared')

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
