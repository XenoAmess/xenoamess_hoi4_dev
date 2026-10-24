"""Classify installed-game character roles and prioritize important portraits.

Historical authenticity is not inferred from a named game character. Counts of
role-bound images overlap and use exact original-byte SHA deduplication.
"""
from collections import defaultdict
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT, file_sha256, game_root, machine_id, read_json, sha256, utc_now, write_json
from mod_nailong.tools.catalog import sources, read_source, tokens
from mod_nailong.tools.art_contract import portrait_ready

MOD = ROOT / 'mod_nailong'
REPORT = MOD / 'data/production-priority.json'
MAJORS = ['CHI', 'PRC', 'GER', 'SOV', 'USA', 'ENG', 'JAP', 'ITA', 'FRA']
FEATURED = [
    'chiang_kai', 'mao_zedong', 'joseph_stalin', 'franklin_roosevelt', 'churchill',
    'adolf_hitler', 'benito_mussolini', 'hirohito', 'charles_de_gaulle',
    'philippe_petain', 'leon_blum', 'paul_reynaud',
    'georgy_zhukov', 'zhukov', 'erwin_rommel', 'guderian', 'manstein',
    'eisenhower', 'patton', 'macarthur', 'montgomery', 'rokossovsky', 'konev',
    'vasilevsky', 'zhu_de', 'chu_teh', 'peng_dehuai', 'lin_biao', 'liu_bocheng',
    'bai_chongxi', 'li_zongren', 'chen_cheng', 'xue_yue', 'sun_li',
    'isoroku_yamamoto', 'yamamoto', 'nimitz', 'halsey', 'donitz', 'doenitz',
    'raeder', 'rundstedt', 'kesselring', 'timoshenko', 'mannerheim',
    'alan_brooke', 'harold_alexander', 'bradley', 'yamashita'
]
TIER_NAMES = {
    0: 'P0 常见领袖与著名将领', 1: 'P1 主要国家其他领袖',
    2: 'P2 主要国家其他陆海军将领', 3: 'P3 其他国家领袖',
    4: 'P4 其他国家陆海军将领', 5: 'P5 其他具名角色',
    6: 'P6 其他独立重要人物/路线头像', 7: '非高：通用或未具名人物', 8: '非高：通用飞行员小图'
}
ROLE_GROUPS = {
    'country_leaders': {'country_leader'},
    'land_commanders': {'corps_commander', 'field_marshal'},
    'admirals': {'navy_leader'}, 'advisors': {'advisor'}, 'scientists': {'scientist'}
}

def character_blocks(text):
    ts = list(tokens(text)); stack = []; i = 0
    while i < len(ts):
        if ts[i] == '}':
            if stack: stack.pop()
            i += 1
        elif i+2 < len(ts) and ts[i+1] == '=':
            if ts[i+2] == '{':
                stack.append(ts[i])
                if len(stack) == 3 and stack[0] == 'characters':
                    yield stack[1], stack[2]
            i += 3
        else:
            i += 1

def classify(catalog, roles):
    grouped = defaultdict(list)
    for asset in catalog['assets']:
        grouped[asset['source_sha256']].append(asset)
    entries = {}
    for key, assets in grouped.items():
        paths = sorted({a['path'] for a in assets})
        refs = [r for a in assets for r in a['references'] if r.get('character')]
        characters = sorted({r['character'] for r in refs})
        countries = sorted({c.split('_')[0].upper() for c in characters})
        tags = set()
        for ref in refs:
            identity = roles.get(ref['character'], set())
            portrait_scope = ref['scope'].split('/')[-1]
            if portrait_scope == 'civilian' and 'country_leader' in identity: tags.add('country_leaders')
            if portrait_scope == 'army' and identity & ROLE_GROUPS['land_commanders']: tags.add('land_commanders')
            if portrait_scope in {'navy', 'army'} and 'navy_leader' in identity: tags.add('admirals')
            if 'advisor' in identity: tags.add('advisors')
            if 'scientist' in identity: tags.add('scientists')
        generic = all('generic' in p.lower() or '/leaders/africa/' in p.lower() or '/leaders/europe/' in p.lower() or '/leaders/asia/' in p.lower() or '/leaders/middle_east/' in p.lower() for p in paths)
        ace = any('/aces/' in p.lower() for p in paths)
        if characters: tags.add('character_bound')
        if characters and not generic: tags.add('named_non_generic_portraits')
        if generic: tags.add('generic')
        if ace: tags.add('aces')
        unnamed_ace = ace and all(re.search(r'(?:^|_)ace_[fm]_\d+',Path(p).stem,re.I) for p in paths)
        unknown_placeholder = all(any(marker in p.lower() for marker in ['unknown','placeholder']) for p in paths)
        # User includes fictional/alternate-history and individually presented
        # important figures. A generic picture used by a defined character also
        # stays high so named people are never omitted by their fallback art.
        high = bool(characters) or (not generic and not unnamed_ace and not unknown_placeholder)
        if high: tags.add('high_priority')
        if ace and not unnamed_ace: tags.add('named_aces')
        names = ' '.join(paths).lower()
        featured = next((n for n in FEATURED if n in names), None)
        important_role = bool(tags & {'country_leaders','land_commanders','admirals'})
        major = bool(set(countries) & set(MAJORS))
        if not high: tier = 8 if ace else 7
        elif featured: tier = 0
        elif major and 'country_leaders' in tags: tier = 1
        elif major and important_role: tier = 2
        elif 'country_leaders' in tags: tier = 3
        elif important_role: tier = 4
        elif characters or ace: tier = 5
        else: tier = 6
        featured_rank = FEATURED.index(featured) if featured else len(FEATURED)
        # Main leader/commander screen images precede their advisor-card variants.
        large_first = 0 if any(min(a['size']) >= 100 for a in assets) else 1
        country_rank = min([MAJORS.index(c) for c in countries if c in MAJORS] or [len(MAJORS)])
        entries[key] = {'tier':tier, 'tier_name':TIER_NAMES[tier], 'high_priority':high, 'categories':sorted(tags),
                        'priority_reason':'Defined character (including generic fallback)' if characters else 'Individual/important portrait, including fictional variants' if high else 'Unbound generic/unknown/placeholder portrait',
                        'sort_key':[tier, large_first, featured_rank, country_rank, paths[0].lower()],
                        'paths':paths, 'characters':characters, 'country_tags':countries,
                        'resource_instances':len(assets), 'featured_match':featured}
    return entries

def gate_lower_priority(eligible, entries, generated, *, idle_low_authorized=False, immediate_high=False):
    approved={k for k,r in generated.items() if portrait_ready(r)}
    incomplete={k for k,e in entries.items() if e['high_priority'] and k not in approved}
    locked=bool(incomplete) and (not idle_low_authorized or immediate_high)
    return ([a for a in eligible if entries[a['source_sha256']]['high_priority']] if locked else eligible), incomplete

def build(catalog=None, install=None):
    catalog = catalog or read_json(MOD/'data/catalog.json')
    install = install or game_root()
    if catalog['machine_id'] != machine_id() or file_sha256(install/'hoi4.exe') != catalog['exe_sha256']:
        raise SystemExit('Current machine/game differs from catalog; rescan before role analysis')
    roles = defaultdict(set); pins = {}
    for row in sources(install):
        if not row[1].lower().startswith('common/characters/') or not row[1].lower().endswith('.txt'): continue
        raw = read_source(row); pins[row[0]+'/'+row[1]] = sha256(raw)
        for character, role in character_blocks(raw.decode('utf-8-sig',errors='replace')):
            roles[character].add(role)
    entries = classify(catalog, roles)
    approved = {k for k,r in read_json(MOD/'data/generated.json')['portraits'].items() if portrait_ready(r)}
    categories = {}
    for name, group in ROLE_GROUPS.items():
        keys = {k for k,e in entries.items() if name in e['categories']}
        categories[name] = {'unique_images':len(keys), 'resource_instances':sum(entries[k]['resource_instances'] for k in keys),
                            'approved_unique_images':len(keys & approved),
                            'defined_character_ids':len({c for c,r in roles.items() if r & group})}
    for name in ['named_non_generic_portraits','character_bound','generic','aces','named_aces','high_priority']:
        keys = {k for k,e in entries.items() if name in e['categories']}
        categories[name] = {'unique_images':len(keys), 'resource_instances':sum(entries[k]['resource_instances'] for k in keys), 'approved_unique_images':len(keys & approved)}
    tiers = [{'tier':tier,'name':label,'unique_images':sum(e['tier']==tier for e in entries.values()),
              'approved_unique_images':sum(k in approved and e['tier']==tier for k,e in entries.items())} for tier,label in TIER_NAMES.items()]
    leader_military = {k for k,e in entries.items() if set(e['categories']) & {'country_leaders','land_commanders','admirals'}}
    payload = {'schema':'naiwa-production-priority-v1','machine_id':machine_id(),'observed_at_utc':utc_now(),
               'game_version':catalog['game_version'],'catalog_sha256':file_sha256(MOD/'data/catalog.json'),
               'evidence':'Read-only installed common/characters role blocks, resolved catalog portrait references and original source SHA-256',
               'definition_sha256':pins,'character_role_counts':{name:sum(bool(r & group) for r in roles.values()) for name,group in ROLE_GROUPS.items()},
               'categories_overlap':True,'historical_authenticity_verified_for_every_character':False,
               'limitations':'Named game characters include alternate-history or fictional branches; this is game-role classification, not a verified historical-person census. Generic art used by a defined character is also high priority. Unbound individual/important portraits and named aces are high; only unbound generic/unknown/placeholder figures are low. All variants and sizes remain in inventory.',
               'leader_and_military_union':{'unique_images':len(leader_military),'approved_unique_images':len(leader_military & approved)},
               'major_country_tags':MAJORS,'featured_name_patterns':FEATURED,'categories':categories,'tiers':tiers,'sources':entries}
    write_json(REPORT,payload)
    print({'categories':categories,'leader_and_military_union':payload['leader_and_military_union'],'tiers':tiers})
    return payload

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8');build()
