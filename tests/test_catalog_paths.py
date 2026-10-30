"""Actual sprite/character resolution across doubled Windows game separators."""
import tempfile
from pathlib import Path
import unittest
import zipfile
from unittest.mock import patch
from PIL import Image
from tools.common import file_sha256, write_json
from mod_nailong.tools import catalog

class CatalogPathTests(unittest.TestCase):
    def test_sprite_and_direct_path_resolve_to_existing_texture(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);game=root/'game';mod=root/'mod_nailong'
            image=game/'gfx/leaders/AST/portrait.png';image.parent.mkdir(parents=True)
            Image.new('RGBA',(2,2),'white').save(image)
            interface=game/'interface';interface.mkdir()
            (interface/'portraits.gfx').write_text('spriteTypes = { spriteType = { name = "GFX_AST_test" texturefile = "gfx\\\\leaders\\\\AST\\\\portrait.png" } }',encoding='utf-8')
            chars=game/'common/characters';chars.mkdir(parents=True)
            (chars/'AST.txt').write_text('characters = { AST_test = { portraits = { civilian = { large = "GFX_AST_test" small = "gfx//leaders//AST//portrait.png" } } } }',encoding='utf-8')
            write_json(game/'launcher-settings.json',{'rawVersion':'test-version'})
            (game/'hoi4.exe').write_bytes(b'test-only-executable-identity')
            registry=mod/'data/verified-idea-portraits.json'
            write_json(registry,{'schema':'naiwa-visually-verified-idea-portraits-v1','sources':[]})
            with patch.object(catalog,'ROOT',root),patch.object(catalog,'MOD',mod),patch.object(catalog,'VISUALLY_VERIFIED_IDEA_PORTRAITS',registry),patch.object(catalog,'machine_id',return_value='test-machine'):
                result=catalog.inventory(game)
            self.assertEqual(result['counts']['distinct_source_images'],1)
            self.assertEqual(result['unresolved_references'],[])
            self.assertEqual(len(result['assets'][0]['references']),2)
            self.assertEqual({r['character'] for r in result['assets'][0]['references']},{'AST_test'})

    def test_unbound_portrait_cards_survive_nonportrait_sprite_names_and_dlc(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);game=root/'game';mod=root/'mod_nailong'
            relative='gfx/interface/ideas/portrait_TEST_unbound_small.png'
            portrait=game/relative;portrait.parent.mkdir(parents=True)
            Image.new('RGBA',(2,2),'gold').save(portrait)
            # This is an ordinary interface asset, not a portrait candidate.
            Image.new('RGBA',(2,2),'blue').save(portrait.parent/'idea_supply.png')
            interface=game/'interface';interface.mkdir()
            (interface/'ideas.gfx').write_text('spriteTypes = { spriteType = { name = "GFX_idea_TEST_unbound" texturefile = "'+relative+'" } }',encoding='utf-8')
            dlc=game/'dlc/dlc999_test';dlc.mkdir(parents=True)
            with zipfile.ZipFile(dlc/'portraits.zip','w') as archive:
                archive.writestr(relative,portrait.read_bytes())
            write_json(game/'launcher-settings.json',{'rawVersion':'test-version'})
            (game/'hoi4.exe').write_bytes(b'test-only-executable-identity')
            registry=mod/'data/verified-idea-portraits.json'
            write_json(registry,{'schema':'naiwa-visually-verified-idea-portraits-v1','sources':[]})
            with patch.object(catalog,'ROOT',root),patch.object(catalog,'MOD',mod),patch.object(catalog,'VISUALLY_VERIFIED_IDEA_PORTRAITS',registry),patch.object(catalog,'machine_id',return_value='test-machine'):
                result=catalog.inventory(game)
            self.assertEqual(result['counts']['textures'],2)
            self.assertEqual(result['counts']['distinct_source_images'],1)
            self.assertEqual({a['package'] for a in result['assets']},{'base','dlc/dlc999_test'})
            self.assertEqual({a['path'] for a in result['assets']},{relative})
            self.assertTrue(all(not a['references'] for a in result['assets']))

    def test_reviewed_idea_without_portrait_binding_is_included_but_same_size_icon_is_not(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);game=root/'game';mod=root/'mod_nailong'
            relative='gfx/interface/ideas/idea_reviewed_person.png'
            image=game/relative;image.parent.mkdir(parents=True)
            Image.new('RGBA',(53,65),'gold').save(image)
            Image.new('RGBA',(53,65),'blue').save(image.parent/'idea_supply.png')
            registry=mod/'data/verified-idea-portraits.json'
            write_json(registry,{'schema':'naiwa-visually-verified-idea-portraits-v1','sources':[
                {'path':relative,'source_sha256':file_sha256(image),'size':[53,65],
                 'classification':'person_or_person_silhouette_visually_confirmed'}]})
            write_json(game/'launcher-settings.json',{'rawVersion':'test-version'})
            (game/'hoi4.exe').write_bytes(b'test-only-executable-identity')
            with patch.object(catalog,'ROOT',root),patch.object(catalog,'MOD',mod),patch.object(catalog,'VISUALLY_VERIFIED_IDEA_PORTRAITS',registry),patch.object(catalog,'machine_id',return_value='test-machine'):
                result=catalog.inventory(game)
            self.assertEqual([row['path'] for row in result['assets']],[relative])
            self.assertEqual(result['visually_verified_idea_portrait_registry_sha256'],file_sha256(registry))

    def test_changed_visual_source_requires_new_review(self):
        with tempfile.TemporaryDirectory() as temp:
            image=Path(temp)/'person.png'
            Image.new('RGBA',(53,65),'gold').save(image)
            relative='gfx/interface/ideas/idea_reviewed_person.png'
            registry={'schema':'naiwa-visually-verified-idea-portraits-v1','sources':[
                {'path':relative,'source_sha256':file_sha256(image),'size':[53,65],
                 'classification':'person_or_person_silhouette_visually_confirmed'}]}
            Image.new('RGBA',(53,65),'blue').save(image)
            with self.assertRaisesRegex(RuntimeError,'texture changed'):
                catalog.verified_idea_paths([('base',relative,image,None)],{relative:[0]},registry)

    def test_unreviewed_dlc_override_cannot_inherit_base_visual_decision(self):
        with tempfile.TemporaryDirectory() as temp:
            image=Path(temp)/'person.png'
            Image.new('RGBA',(53,65),'gold').save(image)
            relative='gfx/interface/ideas/idea_reviewed_person.png'
            registry={'schema':'naiwa-visually-verified-idea-portraits-v1','sources':[
                {'path':relative,'package':'base','source_sha256':file_sha256(image),'size':[53,65],
                 'classification':'person_or_person_silhouette_visually_confirmed'}]}
            rows=[('base',relative,image,None),('dlc/dlc999_test',relative,image,None)]
            with self.assertRaisesRegex(RuntimeError,'Unreviewed same-path'):
                catalog.verified_idea_paths(rows,{relative:[0,1]},registry)
