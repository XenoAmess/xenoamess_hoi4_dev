from pathlib import Path
import tempfile
import unittest

from mod_nailong.tools.catalog import assignments, sprite_definitions
from mod_nailong.tools.build_release import payload, build, verify
from tools.common import ROOT,read_json


class PortraitPipelineTests(unittest.TestCase):
    def test_character_instance_scope_and_comments(self):
        text='''# large=GFX_wrong
        characters={ TAG_example={ instance={ portraits={
          civilian={large="GFX_portrait_example"} army={small="gfx/leaders/a#b.dds"}
        } } } }'''
        rows=list(assignments(text))
        self.assertEqual(rows,[
            (("characters","TAG_example","instance","portraits","civilian"),"large","GFX_portrait_example"),
            (("characters","TAG_example","instance","portraits","army"),"small","gfx/leaders/a#b.dds")])

    def test_sprite_nested_blocks_do_not_leak_names(self):
        text='''spriteTypes={
        spriteType={name="GFX_one" texturefile="gfx/leaders/one.dds" effect={name="nested"}}
        spriteType={texturefile="gfx/leaders/two.dds" name=GFX_two}
        }'''
        self.assertEqual(sprite_definitions(text),[("GFX_one","gfx/leaders/one.dds"),("GFX_two","gfx/leaders/two.dds")])

    def test_formal_build_rejects_current_incomplete_art(self):
        with self.assertRaisesRegex(SystemExit,"RELEASE BLOCKED"):
            payload(preview=False)

    def test_published_texture_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/"release"
            rows=read_json(ROOT/'mod_nailong/data/generated.json')['portraits']
            from mod_nailong.tools.build_release import ready
            key=next(k for k,r in rows.items() if ready(r))
            manifest=build(output,preview=True,validation_keys={key})
            texture=next(r for r in manifest["files"] if r["path"].endswith(".dds"))
            (output/"staging"/texture["path"]).write_bytes(b"wrong image")
            with self.assertRaisesRegex(SystemExit,"Manifest/ZIP mismatch"):
                verify(output)


if __name__=="__main__":unittest.main()
