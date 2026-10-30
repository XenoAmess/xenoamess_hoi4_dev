"""Validate existing user-approved non-person exceptions without new art review."""
from pathlib import Path
from tools.common import ROOT,read_json,file_sha256,machine_id


def load_nonperson_exceptions(scope, root=None):
    root=Path(root or ROOT)
    experiment=root/'mod_nailong/experiments/evolink-high131-flare-20261025'
    path=experiment/'nonperson-scope-decision.json'
    if not path.exists():return {},None
    body=read_json(path)
    assert body['schema']=='naiwa-evolink-high131-nonperson-scope-decision-v1'
    assert body['machine_id']==machine_id()
    assert body['decision']=='preserved_original_nonperson_exception'
    assert body['user_selection']['selected_option']=='保留原图并登记例外（推荐）'
    for name in ('no_image_call_created_for_this_decision','original_assets_retained','canonical_generated_row_must_not_be_fabricated'):assert body[name] is True
    assert body['generated_output_required'] is False
    prior=root/body['prior_visual_review'];assert prior.parent==experiment
    prior_entries=read_json(prior)['entries'];scope_by_key={r['source_sha256']:r for r in scope['entries']}
    exceptions={}
    for row in body['entries']:
        key=row['source_sha256'];source=scope_by_key[key]
        for name in ('index','source_assets','source_size','source_png','source_alpha_extrema'):assert source[name]==row[name]
        assert source['converted_png_sha256']==row['source_png_sha256']
        cached=root/row['source_png']
        if cached.exists():assert file_sha256(cached)==row['source_png_sha256']
        else:
            # A fresh checkout intentionally contains no exported base-game
            # art. Revalidate installed original bytes through its local index.
            from mod_nailong.tools.build_release import original_nonperson_bytes
            from tools.common import sha256
            catalog=read_json(root/'mod_nailong/data/catalog.json')
            assets=[a for a in catalog['assets'] if a['source_sha256']==key]
            assert assets,'Missing locally inventoried non-person source'
            assert all(sha256(original_nonperson_bytes(a))==key for a in assets)
        assert row['observed_subject'] and key not in exceptions
        exceptions[key]=row
    assert {r['source_sha256'] for r in prior_entries}==set(exceptions) and len(exceptions)==4
    return exceptions,{'path':path.relative_to(root).as_posix(),'sha256':file_sha256(path)}
