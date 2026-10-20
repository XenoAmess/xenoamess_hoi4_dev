"""Preserve fullsize edit inputs, exact retry direction and interrupted imports."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from tools.common import file_sha256,read_json,write_json
from mod_nailong.tools import generation_requests as requests
from mod_nailong.tools.art_contract import portrait_ready

class RequestImportTests(unittest.TestCase):
    def test_near_opaque_canvas_is_not_an_exterior_cutout(self):
        for minimum in (249, 250, 254):
            with self.subTest(minimum=minimum),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);mod,key,source,game,master,row=self.edit_fixture(root)
                with Image.open(source) as image:
                    image.putpixel((0,0),(190,185,160,minimum));image.save(source)
                before=file_sha256(source)
                with patch.object(requests,'ROOT',root),patch.object(requests,'MOD',mod),patch.object(requests,'REQUESTS',mod/'data/generation-requests'),patch.object(requests,'original',return_value=source),patch('mod_nailong.tools.image_retries.require_editable_service_state'):
                    job=requests.prepare(key,'Restore original cream backdrop',True)
                attempt=read_json(mod/f'data/generation-requests/{key}.json')['attempts'][0]
                self.assertFalse(job['transparent'])
                self.assertIn('opaque full-canvas portrait',job['prompt'])
                self.assertIn('Do not remove or replace the original background',job['prompt'])
                self.assertEqual(attempt['original_alpha_extrema'],[minimum,255])
                self.assertEqual(attempt['alpha_prompt_policy'],'source-near-opaque-backdrop-v1')
                self.assertEqual(file_sha256(source),before)
                self.assertEqual(job['references'][0],str(master))

    def test_alpha_policy_keeps_lower_alpha_and_opaque_boundary_behavior(self):
        for minimum in (0, 128, 248, 249, 254, 255):
            with self.subTest(minimum=minimum):
                image=Image.new('RGBA',(2,2),(100,90,80,255))
                image.putpixel((0,0),(100,90,80,minimum))
                policy=requests.source_alpha_policy(image)
                self.assertEqual(policy['transparent_background'],minimum<249)
                self.assertEqual(policy['original_alpha_extrema'],[minimum,255])
        self.assertEqual(policy['alpha_prompt_policy'],'source-opaque-v1')

    def edit_fixture(self, root):
        mod=root/'mod_nailong';key='c'*64
        source=root/'original.png';Image.new('RGBA',(3,4),'silver').save(source)
        game=mod/'assets/portraits'/(key+'.png');game.parent.mkdir(parents=True)
        Image.new('RGBA',(3,4),'gold').save(game)
        master=mod/'assets/generated_fullsize/original.png';master.parent.mkdir(parents=True)
        Image.new('RGBA',(30,40),'gold').save(master)
        reference=mod/'assets/reference/naiwa.png';reference.parent.mkdir(parents=True)
        Image.new('RGBA',(7,7),'yellow').save(reference)
        row={'image':game.relative_to(root).as_posix(),'image_sha256':file_sha256(game),
             'generated_fullsize_image':master.relative_to(root).as_posix(),'generated_fullsize_sha256':file_sha256(master),'review':'rejected'}
        write_json(mod/'data/generated.json',{'portraits':{key:row}})
        write_json(mod/'data/catalog.json',{'assets':[{'source_sha256':key,'size':[3,4],'path':'gfx/exact.dds'}]})
        return mod,key,source,game,master,row

    def test_new_edit_uses_fullsize_bytes_and_records_exact_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);mod,key,source,game,master,row=self.edit_fixture(root)
            with patch.object(requests,'ROOT',root),patch.object(requests,'MOD',mod),patch.object(requests,'REQUESTS',mod/'data/generation-requests'),patch.object(requests,'original',return_value=source),patch('mod_nailong.tools.image_retries.require_editable_service_state'):
                job=requests.prepare(key,'Edit moustache only',True)
            self.assertEqual(job['references'][0],str(master))
            target=read_json(mod/f'data/generation-requests/{key}.json')['attempts'][0]['inputs'][0]
            self.assertEqual(target['sha256'],file_sha256(master))
            self.assertNotEqual(target['sha256'],file_sha256(game))
            self.assertEqual(target['derived_game_image_sha256'],file_sha256(game))
            self.assertEqual(file_sha256(game),row['image_sha256'])

    def test_transparent_photo_card_keeps_opaque_backing_and_frozen_request(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);mod,key,source,game,master,row=self.edit_fixture(root)
            with Image.open(source) as image:
                image.putpixel((0,0),(0,0,0,0));image.save(source)
            write_json(mod/'data/catalog.json',{'assets':[{'source_sha256':key,'size':[3,4],'path':'gfx/interface/ideas/portrait_card.dds'}]})
            source_sha=file_sha256(source);master_sha=file_sha256(master)
            with patch.object(requests,'ROOT',root),patch.object(requests,'MOD',mod),patch.object(requests,'REQUESTS',mod/'data/generation-requests'),patch.object(requests,'original',return_value=source),patch('mod_nailong.tools.image_retries.require_editable_service_state'):
                job=requests.prepare(key,'Correct cap badge only',True)
                journal=mod/f'data/generation-requests/{key}.json'
                before=file_sha256(journal)
                with self.assertRaisesRegex(SystemExit,'Unresolved prepared request'):
                    requests.prepare(key,'A changed prompt must not replace this request',True)
                self.assertEqual(file_sha256(journal),before)
            attempt=read_json(journal)['attempts'][0]
            self.assertTrue(job['transparent'])
            self.assertIn('required OPAQUE surface',job['prompt'])
            self.assertIn('ONLY OUTSIDE the complete original photograph FRAME AND NOTE silhouette',job['prompt'])
            self.assertNotIn('No painted gray backdrop',job['prompt'])
            self.assertEqual(attempt['prompt'],job['prompt'])
            self.assertEqual(attempt['prompt_sha256'],file_sha256(root/attempt['prompt_file']))
            self.assertEqual(attempt['alpha_prompt_policy'],'source-content-v3-opaque-body')
            self.assertIn('coat lapels, collar, tie',job['prompt'])
            self.assertIn('FULLY OPAQUE (alpha 255)',job['prompt'])
            self.assertEqual(file_sha256(source),source_sha)
            self.assertEqual(file_sha256(master),master_sha)

    def test_small_standalone_alpha_keeps_original_vignette_without_inventing_card(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);mod,key,source,game,master,row=self.edit_fixture(root)
            with Image.open(source) as image:
                image.putpixel((0,0),(0,0,0,0));image.save(source)
            write_json(mod/'data/catalog.json',{'assets':[{'source_sha256':key,'size':[3,4],'path':'gfx/leaders/TST/shadowed.dds'}]})
            with patch.object(requests,'ROOT',root),patch.object(requests,'MOD',mod),patch.object(requests,'REQUESTS',mod/'data/generation-requests'),patch.object(requests,'original',return_value=source),patch('mod_nailong.tools.image_retries.require_editable_service_state'):
                job=requests.prepare(key,'Preserve dark original illumination',True)
            self.assertTrue(job['transparent'])
            self.assertIn('existing background or dark vignette',job['prompt'])
            self.assertIn('Dark cloth is colored material, not transparent background',job['prompt'])
            self.assertIn('actual exterior boundary',job['prompt'])
            self.assertNotIn('photograph FRAME',job['prompt'])
            self.assertEqual(job['references'][0],str(master))

    def test_missing_or_changed_declared_master_cannot_fall_back_to_thumbnail(self):
        for defect in ('missing-file','changed-bytes','missing-path'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);mod,key,source,game,master,row=self.edit_fixture(root)
                if defect=='missing-file':master.unlink()
                elif defect=='changed-bytes':master.write_bytes(b'changed')
                else:
                    row.pop('generated_fullsize_image')
                    write_json(mod/'data/generated.json',{'portraits':{key:row}})
                with patch.object(requests,'ROOT',root),patch.object(requests,'MOD',mod),patch.object(requests,'REQUESTS',mod/'data/generation-requests'),patch.object(requests,'original',return_value=source),patch('mod_nailong.tools.image_retries.require_editable_service_state'):
                    with self.assertRaisesRegex(ValueError,'fullsize edit target is missing or changed'):
                        requests.prepare(key,'Edit moustache only',True)
                self.assertFalse((mod/f'data/generation-requests/{key}.json').exists())
                self.assertEqual(file_sha256(game),row['image_sha256'])

    def test_old_record_without_declared_master_keeps_explicit_legacy_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);mod,key,source,game,master,row=self.edit_fixture(root)
            row.pop('generated_fullsize_image');row.pop('generated_fullsize_sha256')
            write_json(mod/'data/generated.json',{'portraits':{key:row}})
            with patch.object(requests,'ROOT',root),patch.object(requests,'MOD',mod),patch.object(requests,'REQUESTS',mod/'data/generation-requests'),patch.object(requests,'original',return_value=source),patch('mod_nailong.tools.image_retries.require_editable_service_state'):
                job=requests.prepare(key,'Migrate legacy art',True)
            self.assertEqual(file_sha256(Path(job['references'][0])),row['image_sha256'])
            target=read_json(mod/f'data/generation-requests/{key}.json')['attempts'][0]['inputs'][0]
            self.assertIn('no declared master',target['role'])

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
