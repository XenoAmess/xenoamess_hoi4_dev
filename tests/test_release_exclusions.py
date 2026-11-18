import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from tools.common import file_sha256, read_json, sha256, write_json
from mod_nailong.tools import build_release as builder
from mod_nailong.tools import release_scope as scope
from mod_nailong.tools.release_exclusion_audit import audit, write_audit


class ReleaseExclusions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mod = self.root/'mod_nailong'
        self.policy, _ = scope.load_policy()
        self.prc = self.asset('a', 'gfx/leaders/PRC/portrait_PRC_example.dds', 'PRC_example')
        self.mon = self.asset('b', 'gfx/leaders/PRC/portrait_MON_khorloogiin_choibalsan.dds', 'MON_khorloogiin_choibalsan')
        self.catalog = {'assets': [self.prc, self.mon], 'game_version': 'fixture', 'unresolved_references': []}
        self.generated = {self.prc['source_sha256']: self.art('a', 'yellow'), self.mon['source_sha256']: self.art('b', 'green')}
        (self.mod/'mod').mkdir(parents=True)
        (self.mod/'mod/descriptor.mod').write_text('name="钢奶龙心"\nversion="1.0"\n', encoding='utf-8')
        write_json(self.mod/'data/game-display-qualification.json', {'status': 'qualified_for_release'})
        self.policy_file = self.mod/'data/policy.json'
        for item in [patch.object(builder, 'ROOT', self.root), patch.object(builder, 'MOD', self.mod),
                     patch.object(builder, 'nonperson_scope', return_value=({}, None)),
                     patch.object(scope, 'POLICY_PATH', self.policy_file)]:
            item.start()
            self.addCleanup(item.stop)
        self.save()

    def asset(self, char, path, identity, package='base'):
        return {'id': char + package, 'package': package, 'path': path, 'source_sha256': char*64,
                'size': [3, 4], 'references': [{'character': identity, 'value': 'GFX_' + identity}]}

    def art(self, key, color):
        path = self.mod/f'assets/generated_fullsize/{key}.png'
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGBA', (9, 12), color).save(path)
        return {'review': 'approved', 'art_direction': 'hair-features-v1', 'image_sha256': key,
                'collar_fit': {'status': 'approved', 'policy': 'collar-fit-v1', 'image_sha256': key},
                'generated_fullsize_image': path.relative_to(self.root).as_posix(),
                'generated_fullsize_sha256': file_sha256(path), 'generated_fullsize_size': [9, 12]}

    def save(self):
        self.policy['reviewed_inventory_fingerprint'] = scope.inventory_fingerprint(self.catalog)
        write_json(self.policy_file, self.policy)
        write_json(self.mod/'data/catalog.json', self.catalog)
        write_json(self.mod/'data/generated.json', {'portraits': self.generated})

    def test_excluded_missing_pending_rejected_and_approved_never_block_or_ship(self):
        original = (self.root/self.generated['a'*64]['generated_fullsize_image']).read_bytes()
        for status in [None, 'pending', 'rejected', 'approved']:
            with self.subTest(status=status):
                if status is None:
                    self.generated.pop('a'*64, None)
                else:
                    self.generated['a'*64] = self.art('a', 'yellow')
                    self.generated['a'*64]['review'] = status
                self.save()
                output = self.root/str(status)
                result = builder.build(output)
                self.assertEqual([b['source_sha256'] for b in result['bindings']], ['b'*64])
                self.assertTrue(result['art_complete'])
                self.assertEqual(result['archive_art_complete'], status == 'approved')
                self.assertEqual(audit(output, root=self.root)['excluded_payload_matches'], 0)
                self.assertEqual((self.mod/'assets/generated_fullsize/a.png').read_bytes(), original)

    def test_foreign_communist_identity_and_noncommunist_chinese_identity_remain(self):
        sov = self.asset('c', 'gfx/leaders/SOV/stalin.dds', 'SOV_stalin')
        chi = self.asset('d', 'gfx/leaders/CHI/portrait_CHI_mao_renfeng.dds', 'CHI_mao_renfeng')
        self.catalog['assets'] += [sov, chi]
        self.generated.update({'c'*64: self.art('c', 'blue'), 'd'*64: self.art('d', 'red')})
        self.save()
        result = builder.build(self.root/'foreign')
        self.assertEqual({b['source_sha256'] for b in result['bindings']}, {'b'*64, 'c'*64, 'd'*64})

    def test_only_excluded_assets_can_ship_no_portrait_overrides_without_fabricating_art(self):
        self.catalog['assets'] = [self.prc]
        self.generated = {}
        self.save()
        output = self.root/'empty'
        manifest = builder.build(output)
        self.assertEqual(manifest['bindings'], [])
        self.assertTrue(manifest['art_complete'])
        self.assertFalse(manifest['archive_art_complete'])
        self.assertEqual(audit(output, root=self.root)['checked_actual_portrait_bindings'], 0)

    def test_alias_and_old_dlc_path_closure_blocks_transitive_leaks(self):
        variant = self.asset('c', self.prc['path'].upper(), 'CHI_other', 'dlc/dlc1')
        alias = self.asset('c', 'gfx/leaders/shared.dds', 'MON_other')
        old_alias = self.asset('d', 'gfx/leaders/shared.dds', 'CHI_other', 'dlc/dlc2')
        self.catalog['assets'] += [variant, alias, old_alias]
        self.save()
        result = scope.load_scope(self.catalog, require_review=True)
        self.assertEqual(set(result['excluded_source_sha256']), {'a'*64, 'c'*64, 'd'*64})
        for packages in [None, [], ['dlc/dlc1'], ['dlc/dlc2']]:
            _, manifest = builder.payload(packages=packages)
            self.assertEqual([b['source_sha256'] for b in manifest['bindings']], ['b'*64])

    def test_excluded_unresolved_reference_is_nonblocking_but_other_gaps_block(self):
        self.catalog['unresolved_references'] = [{'character': 'PRC_missing', 'value': 'GFX_portrait_PRC_missing'}]
        self.save()
        builder.build(self.root/'excluded-ref')
        self.catalog['unresolved_references'].append({'character': 'MON_missing', 'value': 'GFX_MON_missing'})
        self.save()
        with self.assertRaisesRegex(SystemExit, 'unresolved'):
            builder.payload()
        self.catalog['unresolved_references'] = []
        self.generated['b'*64]['review'] = 'pending'
        self.save()
        with self.assertRaisesRegex(SystemExit, 'not generated/reviewed'):
            builder.payload()

    def test_changed_inventory_or_unknown_prc_folder_needs_new_affiliation_review(self):
        self.catalog['assets'].append(self.asset('c', 'gfx/leaders/other.dds', 'MON_other'))
        with self.assertRaisesRegex(ValueError, 'inventory changed'):
            scope.load_scope(self.catalog, require_review=True)
        self.catalog['assets'][-1]['path'] = 'gfx/leaders/PRC/new_unknown.dds'
        with self.assertRaisesRegex(ValueError, 'affiliations'):
            scope.load_scope(self.catalog)

    def rewrite_zip(self, output, manifest):
        write_json(output/'manifest.json', manifest)
        with zipfile.ZipFile(output/'gangnailongxin.zip', 'w') as z:
            for row in manifest['files']:
                z.writestr(row['path'], (output/'staging'/row['path']).read_bytes())

    def test_independent_audit_rejects_excluded_file_even_with_consistent_manifest_and_zip(self):
        output = self.root/'tamper'
        manifest = builder.build(output)
        raw = io.BytesIO()
        Image.new('RGBA', (3, 4), 'yellow').save(raw, format='DDS')
        target = output/'staging'/self.prc['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw.getvalue())
        manifest['files'].append({'path': self.prc['path'], 'bytes': len(raw.getvalue()), 'sha256': sha256(raw.getvalue())})
        self.rewrite_zip(output, manifest)
        builder.verify(output)  # Ordinary byte consistency alone cannot catch this leak.
        receipt = output/'failed-exclusion.json'
        with self.assertRaisesRegex(ValueError, 'Excluded portrait path'):
            write_audit(output, root=self.root, receipt=receipt)
        self.assertEqual(read_json(receipt)['status'], 'failed')

    def test_audit_reads_actual_zip_and_rejects_legacy_manifest(self):
        output = self.root/'zip'
        manifest = builder.build(output)
        with zipfile.ZipFile(output/'gangnailongxin.zip', 'a') as z:
            z.writestr('gfx/unlisted.dds', b'leak')
        with self.assertRaisesRegex(ValueError, 'Actual ZIP'):
            audit(output, root=self.root)
        self.rewrite_zip(output, manifest)
        manifest.pop('release_exclusions')
        write_json(output/'manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'policy or source inventory'):
            audit(output, root=self.root)

    def test_renamed_texture_cannot_pass_stale_pixel_proof(self):
        output = self.root/'renamed'
        manifest = builder.build(output)
        old = manifest['bindings'][0]['path']
        new = 'gfx/leaders/renamed.dds'
        (output/'staging'/new).parent.mkdir(parents=True, exist_ok=True)
        (output/'staging'/old).rename(output/'staging'/new)
        manifest['bindings'][0]['path'] = new
        next(f for f in manifest['files'] if f['path'] == old)['path'] = new
        self.rewrite_zip(output, manifest)
        with self.assertRaisesRegex(ValueError, 'native pixel proof'):
            audit(output, root=self.root)

    def test_validation_selection_reports_excluded_and_emitted_sources_separately(self):
        _, manifest = builder.payload(preview=True, validation_keys={'a'*64, 'b'*64})
        self.assertEqual(manifest['validation_source_keys'], ['a'*64, 'b'*64])
        self.assertEqual(manifest['validation_excluded_source_keys'], ['a'*64])
        self.assertEqual(manifest['validation_emitted_source_keys'], ['b'*64])


if __name__ == '__main__':
    unittest.main()
