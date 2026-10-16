"""Actual sprite/character resolution across doubled Windows game separators."""
import tempfile
from pathlib import Path
import unittest
import zipfile
from unittest.mock import patch
from PIL import Image
from tools.common import write_json
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
            with patch.object(catalog,'ROOT',root),patch.object(catalog,'MOD',mod),patch.object(catalog,'machine_id',return_value='test-machine'):
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
            with patch.object(catalog,'ROOT',root),patch.object(catalog,'MOD',mod),patch.object(catalog,'machine_id',return_value='test-machine'):
                result=catalog.inventory(game)
            self.assertEqual(result['counts']['textures'],2)
            self.assertEqual(result['counts']['distinct_source_images'],1)
            self.assertEqual({a['package'] for a in result['assets']},{'base','dlc/dlc999_test'})
            self.assertEqual({a['path'] for a in result['assets']},{relative})
            self.assertTrue(all(not a['references'] for a in result['assets']))
