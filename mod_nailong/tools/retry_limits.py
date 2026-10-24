"""Keep the default budget and one explicitly source-scoped user exception distinct."""
import re


def extra_retry_authorization(settings, key):
    matches=[]
    for grant in settings.get('source_scoped_extra_retry_rounds', []):
        keys=grant['source_keys']
        assert len(keys)==len(set(keys)) and all(re.fullmatch(r'[0-9a-f]{64}', k) for k in keys)
        assert grant['additional_retries_per_selected_source']==1
        assert grant['retries_used_at_authorization']==settings['max_cooldown_retries_per_source']==8
        assert grant['authorization_id'] and grant['authorization_manifest'] and re.fullmatch(r'[0-9a-f]{64}',grant['authorization_manifest_sha256'])
        if key in keys:matches.append(grant)
    assert len(matches)<=1, 'A source may not silently accumulate extra retry rounds'
    return matches[0] if matches else None


def retry_limit(settings, key):
    return settings['max_cooldown_retries_per_source']+(1 if extra_retry_authorization(settings,key) else 0)
