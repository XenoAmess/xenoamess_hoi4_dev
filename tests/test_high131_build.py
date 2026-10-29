import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from mod_nailong.tools import build_release as builder
from tools.common import ROOT, file_sha256, machine_id, utc_now, write_json


class High131BuildAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT/'runtime')
        self.root = Path(self.temporary.name)
        self.output = self.root/'dist/high131-validation'
        self.lock = self.root/'runtime/coordination.lock'
        write_json(self.lock, {'machine_id':machine_id(), 'batch':'unit-test', 'process_id':os.getpid()})
        self.estimate = 300*1024*1024
        peak = 2*self.estimate+64*1024*1024
        total = 1023892852736
        safety = max(2*1024**3,min(20*1024**3,int(total*0.05)))
        self.body = {
            'schema':'naiwa-high131-heavy-write-admission-v1', 'machine_id':machine_id(),
            'status':'admitted', 'policy_version':'1.0.0', 'scope':'high131-original-rgba-validation-v1',
            'batch':'unit-test', 'output_root':str(self.output.resolve()),
            'decoded_payload_bytes':self.estimate, 'this_write_peak_estimate_bytes':peak,
            'volume_total_bytes':total, 'available_bytes':peak+16*1024**3+10*1024**3+safety,
            'other_unspent_reservations_bytes':16*1024**3, 'system_growth_reserve_bytes':10*1024**3,
            'project_usage_upper_bound_bytes':1024, 'effective_project_quota_bytes':min(100*1024**3,int(total*0.10)),
            'safety_margin_bytes':safety, 'admitted_at_utc':utc_now(),
            'retention_review_by_utc':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
            'coordination_lock':'runtime/coordination.lock', 'coordination_lock_sha256':file_sha256(self.lock),
        }
        self.root_patch = patch.object(builder,'ROOT',self.root)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temporary.cleanup()

    def receipt(self, body=None):
        path = self.root/'runtime/admission.json'
        write_json(path, self.body if body is None else body)
        return path

    def test_admission_binds_real_payload_output_budget_and_lock(self):
        self.assertEqual(builder.validate_heavy_write_admission(self.receipt(),self.estimate,self.output),self.body)
        with self.assertRaisesRegex(SystemExit,'explicit scoped'):
            builder.validate_heavy_write_admission(None,self.estimate,self.output)

    def test_wrong_payload_or_budget_is_rejected(self):
        for field,value in [('decoded_payload_bytes',1),('available_bytes',1),('output_root','other'),('retention_review_by_utc','2000-01-01T00:00:00+00:00')]:
            with self.subTest(field=field):
                body = dict(self.body)
                body[field] = value
                with self.assertRaises(SystemExit):
                    builder.validate_heavy_write_admission(self.receipt(body),self.estimate,self.output)

    def test_live_lock_identity_is_required(self):
        write_json(self.lock, {'machine_id':machine_id(), 'batch':'unit-test', 'process_id':os.getpid()+1})
        with self.assertRaisesRegex(SystemExit,'live coordination lock'):
            builder.validate_heavy_write_admission(self.receipt(),self.estimate,self.output)

    def test_profiles_do_not_claim_suppressed_variants_are_active(self):
        from mod_nailong.tools.high131_validation import profile_scope

        experiment = self.root/'mod_nailong/experiments/evolink-high131-flare-20261025'
        entries = [{'index':index,'source_sha256':f'{index:064x}','source_assets':[f'gfx/{index}.dds']} for index in range(1,132)]
        write_json(experiment/'scope.json', {'entries':entries})
        write_json(experiment/'approved-masters.json', {'entries':[row for row in entries if row['index'] not in {78,125,129,131}]})
        assets = [{'id':str(index),'path':row['source_assets'][0],'source_sha256':row['source_sha256'],'package':'base'} for index,row in enumerate(entries,1)]
        assets.append({'id':'dlc-override','path':'gfx/1.dds','source_sha256':'f'*64,'package':'dlc001'})
        write_json(self.root/'mod_nailong/data/catalog.json', {'assets':assets})
        current = profile_scope(self.root)
        base = profile_scope(self.root,[])
        self.assertEqual(current['active_source_count'],130)
        self.assertEqual(current['active_person_count'],126)
        self.assertEqual(current['active_nonperson_count'],4)
        self.assertEqual([row['index'] for row in current['inactive']],[1])
        self.assertEqual(base['active_source_count'],131)
        self.assertEqual(base['active_person_count'],127)

    def test_original_rgba_and_nonperson_bytes_are_verified(self):
        from PIL import Image
        from mod_nailong.tools.build_high131_validation import verify_payload_pixels
        import hashlib

        original = self.root/'original.png'
        Image.new('RGBA',(2,3),(10,20,30,40)).save(original)
        digest = file_sha256(original)
        master = self.root/'mod_nailong/assets/generated_fullsize'/f'{digest}.png'
        master.parent.mkdir(parents=True)
        master.write_bytes(original.read_bytes())
        staging = self.root/'dist/validation/staging'
        staging.mkdir(parents=True)
        with Image.open(original) as image:
            image.save(staging/'person.dds',format='DDS')
        original_bytes = (staging/'person.dds').read_bytes()
        (staging/'object.dds').write_bytes(original_bytes)
        manifest = {'preview':True,'art_complete':False,'bindings':[
            {'path':'person.dds','source_sha256':'person','fullsize_master_sha256':digest},
            {'path':'object.dds','source_sha256':'object','fullsize_master_sha256':None,'preserved_original_nonperson_exception':True,'sha256':hashlib.sha256(original_bytes).hexdigest()},
        ]}
        proof = verify_payload_pixels(self.root,staging.parent,manifest)
        self.assertEqual(proof['person_textures'],1)
        self.assertEqual(proof['preserved_original_nonperson_textures'],1)
        self.assertEqual(proof['runtime_display_acceptance'],'not-run')
        with self.assertRaisesRegex(ValueError,'incomplete development'):
            verify_payload_pixels(self.root,staging.parent,dict(manifest,art_complete=True))

    def test_actual_package_override_and_unbound_inventory_are_distinct(self):
        from mod_nailong.tools.high131_validation import classify_bindings
        definitions = [
            {'kind':'spritetype','name':'GFX_person','texture':'gfx/base.dds','frames':'1','existing_mask':None,'source_id':0},
            {'kind':'spritetype','name':'GFX_person','texture':'gfx/dlc.dds','frames':'1','existing_mask':None,'source_id':1},
        ]
        conflict = {'source_sha256':'person','references':[],'conflicting_definitions':definitions}
        audit = {
            'selected_paths':['gfx/base.dds','gfx/dlc.dds','gfx/unused.dds'],
            'selected_asset_packages':{'gfx/base.dds':'base','gfx/dlc.dds':'dlc/dlc038_arms_against_tyranny','gfx/unused.dds':'base'},
            'unresolved':[dict(conflict,path='gfx/base.dds'),dict(conflict,path='gfx/dlc.dds'),{'path':'gfx/unused.dds','source_sha256':'unused','references':[],'conflicting_definitions':[]}],
            'native_source_proofs':[{'id':0,'package':'base'},{'id':1,'package':'dlc/dlc038_arms_against_tyranny'}],
            'native_text_references':[], 'gui_references':[],
        }
        result = classify_bindings(audit)
        self.assertEqual([(row['name'],row['texture']) for row in result['resolved_profile_aliases']],[('GFX_person','gfx/dlc.dds')])
        self.assertEqual([row['path'] for row in result['inventory_without_current_consumer']],['gfx/unused.dds'])
        self.assertEqual(result['unresolved'],[])
        self.assertEqual(len(result['initial_unresolved']),3)

    def test_only_bounded_owner_quota_override_is_accepted(self):
        body = dict(self.body)
        body['effective_project_quota_bytes'] = 128*1024**3
        with self.assertRaisesRegex(SystemExit,'quota override'):
            builder.validate_heavy_write_admission(self.receipt(body),self.estimate,self.output)
        body['quota_override'] = {
            'owner':'HIGH131 validation owner', 'reason':'Bounded original-RGBA validation',
            'max_project_bytes':body['effective_project_quota_bytes'],
            'review_at_utc':body['retention_review_by_utc'],
        }
        self.assertEqual(builder.validate_heavy_write_admission(self.receipt(body),self.estimate,self.output),body)
        body['quota_override']['review_at_utc'] = '2000-01-01T00:00:00+00:00'
        with self.assertRaisesRegex(SystemExit,'quota override'):
            builder.validate_heavy_write_admission(self.receipt(body),self.estimate,self.output)

    def test_masking_adapter_end_to_end_preserves_pixels_and_exceptions(self):
        from PIL import Image
        from mod_nailong.tools.hd_masking import augment
        from mod_nailong.tools.build_high131_validation import verify_payload_pixels
        import hashlib
        import shutil

        mod = self.root/'mod_nailong'
        original = self.root/'original.png'
        Image.new('RGBA',(2,3),(10,20,30,40)).save(original)
        digest = file_sha256(original)
        master = mod/'assets/generated_fullsize'/f'{digest}.png'
        master.parent.mkdir(parents=True)
        master.write_bytes(original.read_bytes())
        object_file = self.root/'object.dds'
        Image.new('RGBA',(2,3),(50,60,70,255)).save(object_file,format='DDS')
        object_bytes = object_file.read_bytes()
        object_key = hashlib.sha256(object_bytes).hexdigest()
        write_json(self.root/'runtime/source-index.json', {'object':{'path':str(object_file),'member':None}})
        shader = mod/'assets/runtime/hd_portrait_masking_sampler.shader'
        shader.parent.mkdir(parents=True)
        shutil.copyfile(ROOT/'mod_nailong/assets/runtime/hd_portrait_masking_sampler.shader',shader)
        (mod/'mod').mkdir(parents=True)
        (mod/'mod/descriptor.mod').write_text('name="钢奶龙心 (Development)"\n',encoding='utf-8')
        generated = {}
        for key in ('person','unused'):
            generated[key] = {'generated_fullsize_image':f'mod_nailong/assets/generated_fullsize/{digest}.png','generated_fullsize_sha256':digest,'generated_fullsize_size':[2,3]}
        assets = [
            {'id':'person','path':'gfx/person.dds','source_sha256':'person','size':[2,3],'package':'base'},
            {'id':'unused','path':'gfx/unused.dds','source_sha256':'unused','size':[2,3],'package':'base'},
            {'id':'object','path':'gfx/object.dds','source_sha256':object_key,'size':[2,3],'package':'base'},
            {'id':'low','path':'gfx/low.dds','source_sha256':'low','size':[2,3],'package':'base'},
        ]
        write_json(mod/'data/catalog.json', {'assets':assets,'game_version':'synthetic','unresolved_references':[]})
        write_json(mod/'data/generated.json', {'portraits':generated})
        output = self.root/'dist/adapter'
        with patch('mod_nailong.tools.hd_masking.ROOT',self.root), patch.object(builder,'MOD',mod), patch.object(builder,'ready',lambda row:True), patch.object(builder,'nonperson_scope',return_value=({object_key:{'index':131,'source_sha256':object_key}},None)):
            manifest = builder.build(output,preview=True,validation_keys={'person','unused',object_key})
            manifest = augment(output,manifest,[{'name':'GFX_person','texture':'gfx/person.dds','source_ids':[0]}],[{'id':0,'path':'interface/test.gfx','sha256':'proof'}],inventory_only=[{'path':'gfx/unused.dds','source_sha256':'unused','classification':'no_current_native_consumer_in_bounded_inventory','runtime_display_not_applicable_unless_a_consumer_is_found':True}])
        fixture = manifest['development_fixture']
        self.assertEqual([row['path'] for row in fixture['inventory_without_current_consumer']],['gfx/unused.dds'])
        self.assertEqual([row['path'] for row in fixture['preserved_original_nonperson_paths']],['gfx/object.dds'])
        self.assertEqual(len(fixture['fullsize_pixel_proofs']),2)
        self.assertEqual((output/'staging/gfx/object.dds').read_bytes(),object_bytes)
        self.assertFalse(fixture['formal_release_eligible'])
        proof = verify_payload_pixels(self.root,output,manifest)
        self.assertEqual(proof['person_textures'],2)
        self.assertEqual(proof['preserved_original_nonperson_textures'],1)


if __name__ == '__main__':
    unittest.main()
