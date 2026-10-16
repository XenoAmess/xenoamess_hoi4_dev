"""Analyze unresolved original-game portrait references, without changing them."""
from __future__ import annotations
from collections import Counter,defaultdict
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT,game_root,machine_id,read_json,sha256,utc_now,write_json
from mod_nailong.tools.catalog import sources,read_source,sprite_definitions

def main():
    install=game_root()
    catalog=read_json(ROOT/'mod_nailong/data/catalog.json')
    definitions={}
    gfx_pins={}
    all_sprite_names=set()
    all_texture_paths=set()
    for row in sources(install):
        package,path,_,_=row
        if path.lower().endswith('.gfx'):
            raw=read_source(row)
            gfx_pins[package+'/'+path]=sha256(raw)
            all_sprite_names.update(name.lower() for name,_ in sprite_definitions(raw.decode('utf-8-sig',errors='replace')))
        elif path.lower().startswith('common/characters/'):
            definitions[package+'/'+path]=sha256(read_source(row))
        elif path.lower().endswith(('.dds','.png','.tga')):
            all_texture_paths.add(path.lower())
    groups=defaultdict(list)
    for ref in catalog['unresolved_references']:
        groups[ref['value'].lower()].append(ref)
    entries=[]
    for value,refs in sorted(groups.items()):
        missing_texture=sorted({ref['missing_texture'] for ref in refs if 'missing_texture' in ref})
        if missing_texture:
            reason='sprite-defined-but-target-texture-missing'
        elif value not in all_sprite_names and value not in all_texture_paths:
            reason='name-absent-from-all-scanned-installed-sprites-and-textures'
        else:
            reason='scanner-needs-further-analysis'
        entries.append({'value':refs[0]['value'],'reference_count':len(refs),'kind':reason,'source_definitions':sorted({ref['definition'] for ref in refs}),'missing_textures':missing_texture})
    payload={'schema':'naiwa-baseline-reference-analysis-v1','machine_id':machine_id(),'observed_at_utc':utc_now(),'game_version':catalog['game_version'],'exe_sha256':catalog['exe_sha256'],'scope':'Same vanilla plus installed DLC source set as catalog; original files were read only','unresolved_reference_occurrences':len(catalog['unresolved_references']),'distinct_unresolved_values':len(entries),'class_counts':dict(Counter(row['kind'] for row in entries)),'gameplay_change_applied':False,'conclusion':'These are pre-existing source-reference gaps in the installed source set, not references introduced by the texture-only mod. This static analysis does not prove which engine fallback is visible at runtime. Keep them visible in coverage and verify relevant fallbacks during actual game acceptance.','character_definition_sha256':definitions,'sprite_definition_sha256':gfx_pins,'entries':entries}
    write_json(ROOT/'mod_nailong/data/baseline-reference-analysis.json',payload)
    print({key:payload[key] for key in ['unresolved_reference_occurrences','distinct_unresolved_values','class_counts','conclusion']})

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
