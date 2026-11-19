"""Validate existing user-approved non-person exceptions without new art review."""
from pathlib import Path
from tools.common import ROOT,read_json,file_sha256,machine_id


def _load_legacy_nonperson_exceptions(scope, root=None):
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


def load_nonperson_exceptions(scope, root=None):
    """Keep the legacy approval intact and bind separately approved additions."""
    root=Path(root or ROOT)
    exceptions,legacy_receipt=_load_legacy_nonperson_exceptions(scope,root=root)
    path=root/'mod_nailong/data/nonperson-preservation-decisions.json'
    if not path.exists():return exceptions,legacy_receipt
    body=read_json(path)
    assert body['schema']=='nailong-additional-nonperson-preservation-decisions-v1'
    assert body['decisions'],'Empty supplemental preservation registry'
    catalog=read_json(root/'mod_nailong/data/catalog.json')
    for row in body['decisions']:
        key=row['source_sha256']
        assert key not in exceptions,'A supplemental decision cannot override an existing exception'
        assert row['machine_id']==machine_id()
        assert row['decision']=='preserved_original_nonperson_exception'
        assert row['user_selection']['selected_option']=='沿用非人物例外（推荐）'
        assert row['user_selection']['answer_received_in_current_session'] is True
        for name in ('no_image_call_created_for_this_decision','original_assets_retained','canonical_generated_row_must_not_be_fabricated'):assert row[name] is True
        assert row['generated_output_required'] is False
        prior=(root/row['prior_visual_review']).resolve()
        assert prior.is_relative_to((root/'mod_nailong/data/update-reviews').resolve()),'Observation must be a project review record'
        assert file_sha256(prior)==row['prior_visual_review_sha256'],'Nonperson observation changed'
        observation=read_json(prior)
        assert observation['schema']=='nailong-update-nonperson-observation-v1'
        assert observation['source_sha256']==key and observation['source_index']==row['index']
        assert observation['source_size']==row['source_size'] and observation['source_png_sha256']==row['source_png_sha256']
        assert observation['actual_image_calls']==0 and observation['art_qualification_claimed'] is False
        assert row['observed_subject']==observation['observation'] and row['observed_subject']
        assets=[a for a in catalog['assets'] if a['source_sha256']==key]
        assert assets,'Supplemental nonperson source is absent from current catalog'
        bindings=[{name:a[name] for name in ('id','package','path','size')} for a in assets]
        assert sorted(bindings,key=lambda a:a['id'])==sorted(row['catalog_assets'],key=lambda a:a['id']),'Supplemental catalog identity changed'
        assert all(a['size']==row['source_size'] for a in assets)
        assert sorted({a['path'] for a in assets})==sorted(row['source_assets'])
        assert row['index_basis']=='hoi4-1.19.5-update-plan-1-based'
        exceptions[key]=row
    return exceptions,{'legacy':legacy_receipt,'additional':{'path':path.relative_to(root).as_posix(),'sha256':file_sha256(path)},'validator_sha256':file_sha256(Path(__file__))}


def annotate_update_plan(plan, exceptions):
    """Separate preserved originals from art qualification without hiding sources."""
    for row in plan['sources']:
        key=row['source_sha256'];preserved=key in exceptions
        row['release_art_required']=not row['release_excluded'] and not preserved
        if preserved:
            assert not row['generated'] and not row['portrait_ready'],'Nonperson preservation is not generated art'
            row.update(preserved_original_nonperson_exception=True,production_status='preserved_original_nonperson_exception',art_review='not_applicable_nonperson',generation_calls_this_task=0)
    new=[r for r in plan['sources'] if r['new_unique_source']]
    plan['processing_counts']={
        'new_sources_total':len(new),
        'new_sources_art_approved':sum(r['portrait_ready'] for r in new),
        'new_sources_preserved_nonperson':sum(r['source_sha256'] in exceptions for r in new),
        'new_sources_unprocessed':sum(not r['portrait_ready'] and r['source_sha256'] not in exceptions for r in new),
        'new_release_art_missing':sum(not r['portrait_ready'] and r['release_art_required'] for r in new),
        'new_archive_art_missing':sum(not r['portrait_ready'] and r['release_excluded'] for r in new),
        'historical_preserved_nonperson':sum(not r['new_unique_source'] and r['source_sha256'] in exceptions for r in plan['sources']),
        'art_qualification_denominator_unchanged':True}
    return plan
