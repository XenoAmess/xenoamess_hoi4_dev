"""Inventory vanilla and installed DLC character portraits without running HOI4.

GENERATED FILE catalog output: modify this tool, never edit catalog rows by hand.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import io
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT, file_sha256, game_root, machine_id, sha256, utc_now, write_json
from PIL import Image, ImageDraw

MOD = ROOT / "mod_nailong"
TEXTURE_EXTENSIONS = {".dds", ".tga", ".png"}
NON_PORTRAIT_TEXTURES = {
    "gfx/aces/ace_kia.dds": "Coffin/cross status icon; no person to transform (visually reviewed 2026-10-16)",
    "gfx/aces/ace_none.dds": "Playing-card placeholder icon; no person to transform (visually reviewed 2026-10-16)",
}
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|#[^\n]*|[{}=]|[^\s{}=#"]+')

def tokens(text):
    for match in TOKEN.finditer(text):
        token = match.group(0)
        if not token.startswith("#"):
            yield token[1:-1] if token.startswith('"') else token

def assignments(text):
    """Yield (scope path, key, scalar) with balanced nested block traversal."""
    ts = list(tokens(text))
    stack = []
    i = 0
    while i < len(ts):
        if ts[i] == "}":
            if stack:
                stack.pop()
            i += 1
        elif i + 2 < len(ts) and ts[i + 1] == "=":
            key, value = ts[i], ts[i + 2]
            if value == "{":
                stack.append(key)
            else:
                yield tuple(stack), key, value
            i += 3
        elif ts[i] == "{":
            stack.append("")
            i += 1
        else:
            i += 1

def sprite_definitions(text):
    """Read each sprite block independently, preserving duplicate definitions."""
    ts = list(tokens(text))
    result = []
    for i in range(len(ts) - 2):
        if ts[i].lower() not in {"spritetype", "cornersizedspritetype"} or ts[i+1:i+3] != ["=", "{"]:
            continue
        depth, j, values = 1, i + 3, {}
        while j < len(ts) and depth:
            token = ts[j]
            if token == "{":
                depth += 1
            elif token == "}":
                depth -= 1
            elif depth == 1 and j + 2 < len(ts) and ts[j+1] == "=":
                values[token.lower()] = ts[j+2]
            j += 1
        if "name" in values and "texturefile" in values:
            result.append((values["name"], values["texturefile"].replace("\\", "/")))
    return result

def sources(install: Path):
    roots = [("base", install)]
    for folder in ["dlc", "integrated_dlc"]:
        parent = install / folder
        if parent.is_dir():
            roots.extend((p.relative_to(install).as_posix(), p) for p in sorted(parent.iterdir()) if p.is_dir())
    for name, folder in roots:
        for subtree in ["gfx", "interface", "common/characters", "common/portraits", "portraits"]:
            path = folder / subtree
            if not path.is_dir():
                continue
            for file in sorted(path.rglob("*")):
                if file.is_file() and file.suffix.lower() in TEXTURE_EXTENSIONS | {".gfx", ".txt"}:
                    yield name, file.relative_to(folder).as_posix(), file, None
        if name != "base":
            for archive_path in sorted(folder.rglob("*.zip")):
                with zipfile.ZipFile(archive_path) as archive:
                    for member in sorted(archive.namelist()):
                        if member.startswith(("gfx/", "interface/", "common/characters/", "portraits/")) and Path(member).suffix.lower() in TEXTURE_EXTENSIONS | {".gfx", ".txt"}:
                            yield name, member, archive_path, member

def read_source(row):
    if row[3] is None:
        return row[2].read_bytes()
    with zipfile.ZipFile(row[2]) as archive:
        return archive.read(row[3])

def inventory(install):
    rows = list(sources(install))
    textures = defaultdict(list)
    sprites = defaultdict(list)
    refs = []
    candidates = set()
    for i, row in enumerate(rows):
        package, path, _, _ = row
        lower = path.lower()
        if Path(path).suffix.lower() in TEXTURE_EXTENSIONS:
            textures[lower].append(i)
            if lower.startswith("gfx/leaders/") or "/portraits/" in lower or lower.startswith("gfx/aces/"):
                candidates.add(lower)
        elif lower.endswith(".gfx"):
            for name, texture in sprite_definitions(read_source(row).decode("utf-8-sig", errors="replace")):
                sprites[name.lower()].append((texture.lower(), f"{package}/{path}"))
                if name.lower().startswith("gfx_portrait_") and texture.lower() in textures:
                    candidates.add(texture.lower())
        elif lower.startswith("common/characters/") or "/portraits/" in lower or lower.startswith("portraits/"):
            for scope, key, value in assignments(read_source(row).decode("utf-8-sig", errors="replace")):
                is_portrait = "portraits" in scope and key.lower() in {"large", "small"}
                is_pool = lower.startswith("portraits/") and (value.lower().endswith(tuple(TEXTURE_EXTENSIONS)) or value.lower().startswith("gfx_"))
                if is_portrait or is_pool:
                    refs.append({"character": scope[1] if len(scope)>1 and scope[0]=="characters" else None, "scope": "/".join(scope), "size": key, "value": value, "definition": f"{package}/{path}"})
    unresolved = []
    reference_map = defaultdict(list)
    for ref in refs:
        value = ref["value"].lower().replace("\\", "/")
        targets = [value] if value in textures else [t for t, _ in sprites.get(value, [])]
        if not targets:
            unresolved.append(ref)
        for target in targets:
            if target not in textures:
                unresolved.append(dict(ref, missing_texture=target))
            else:
                candidates.add(target)
                reference_map[target].append(ref)
    # Sprite scans occur before some later DLC textures; resolve once more after all rows exist.
    for name, bindings in sprites.items():
        if name.startswith("gfx_portrait_"):
            for texture, _ in bindings:
                if texture in textures:
                    candidates.add(texture)
    assets = []
    for texture in sorted(candidates):
        if texture in NON_PORTRAIT_TEXTURES:
            continue
        for source_index in textures.get(texture, []):
            row = rows[source_index]
            raw = read_source(row)
            try:
                with Image.open(io.BytesIO(raw)) as image:
                    size = list(image.size)
                    mode = image.mode
            except Exception as exc:
                raise RuntimeError(f"Cannot decode portrait {row[:2]}") from exc
            digest = sha256(raw)
            asset = {"id": sha256((row[0]+"/"+row[1]).encode())[:20], "package": row[0], "path": row[1], "source_sha256": digest, "bytes": len(raw), "size": size, "mode": mode, "references": reference_map[texture]}
            if row[3]:
                asset["archive_member"] = row[3]
            assets.append(asset)
    launcher = __import__("json").loads((install / "launcher-settings.json").read_text(encoding="utf-8"))
    catalog = {"schema": "naiwa-portrait-catalog-v1", "generated_notice": "GENERATED FILE: run catalog.py", "observed_at_utc": utc_now(), "machine_id": machine_id(), "game_version": launcher["rawVersion"], "exe_sha256": file_sha256(install/"hoi4.exe"), "scope": "Vanilla plus all locally installed DLC assets; other Workshop mods are outside this catalog", "excluded_non_portrait_assets": NON_PORTRAIT_TEXTURES, "assets": assets, "unresolved_references": unresolved, "counts": {"textures": len(assets), "distinct_source_images": len({a["source_sha256"] for a in assets}), "character_references": len(refs), "unresolved_references": len(unresolved)}}
    write_json(MOD / "data/catalog.json", catalog)
    print(catalog["counts"])
    print("PACKAGES", dict(__import__("collections").Counter(a["package"] for a in assets)))
    print("SIZES", dict(__import__("collections").Counter(str(a["size"]) for a in assets)))
    print("UNRESOLVED SAMPLE", unresolved[:8])
    write_json(ROOT / "runtime/source-index.json", {a["id"]: {"path": str(rows[i][2]), "member": rows[i][3]} for a in assets for i in textures[a["path"].lower()] if rows[i][0]==a["package"]})
    return catalog

def prepare(catalog, limit=16, offset=0, match=None):
    from tools.common import read_json
    generated = read_json(MOD / "data/generated.json")["portraits"]
    source_index = read_json(ROOT / "runtime/source-index.json")
    pending, seen = [], set()
    for asset in catalog["assets"]:
        key = asset["source_sha256"]
        if key not in generated and key not in seen:
            pending.append(asset)
            seen.add(key)
    priority_names = ["pierre_laval", "stanley_baldwin", "churchill", "chiang_kai", "franklin_roosevelt", "joseph_stalin", "adolf_hitler", "benito_mussolini", "charles_de_gaulle", "mao_zedong", "hirohito"]
    def priority(asset):
        name = asset["path"].lower()
        rank = next((i for i, word in enumerate(priority_names) if word in name), 100)
        return (0 if rank<100 and "/leaders/" in name else 1 if rank<100 else 2),rank,name,asset["package"]
    pending.sort(key=priority)
    failures_path=MOD/"data/generation-failures.json"
    failures=read_json(failures_path) if failures_path.exists() else {}
    blocked_keys={row["source_sha256"] for row in failures.get("attempts",[]) if row.get("status")=="blocked"}
    held_paths={path.lower() for path in failures.get("held_source_paths",[])}
    eligible=[asset for asset in pending if asset["source_sha256"] not in blocked_keys and asset["path"].lower() not in held_paths]
    held_count=len(pending)-len(eligible)
    if match:eligible=[asset for asset in eligible if match.lower() in asset["path"].lower()]
    selected = eligible[offset:offset+limit]
    jobs = []
    for asset in selected:
        source = source_index[asset["id"]]
        if source["member"]:
            with zipfile.ZipFile(source["path"]) as archive:
                raw = archive.read(source["member"])
        else:
            raw = Path(source["path"]).read_bytes()
        if sha256(raw) != asset["source_sha256"]:
            raise SystemExit("Source changed; rerun inventory before generation")
        target = ROOT / "runtime/references" / (asset["source_sha256"] + ".png")
        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(io.BytesIO(raw)) as image:
            converted = image.convert("RGBA")
            converted.save(target)
            transparent = converted.getchannel("A").getextrema()[0] < 255
        jobs.append({"key": asset["source_sha256"], "path": str(target), "source": asset["path"], "size": asset["size"], "id": asset["id"], "transparent": transparent})
    write_json(ROOT / "runtime/generation-jobs.json", jobs)
    if jobs:
        columns = min(8, len(jobs))
        sheet = Image.new("RGB", (columns*172, ((len(jobs)+columns-1)//columns)*252), "#ece9df")
        draw = ImageDraw.Draw(sheet)
        for index, job in enumerate(jobs):
            with Image.open(job["path"]) as image:
                ratio=min(156/image.width,210/image.height)
                image=image.convert("RGBA").resize((round(image.width*ratio),round(image.height*ratio)),Image.Resampling.NEAREST if ratio>1 else Image.Resampling.LANCZOS)
                x, y = (index%columns)*172+8, (index//columns)*252+4
                sheet.paste(image, (x,y),image.getchannel("A"))
                draw.text((x,y+212), f"{index+1} {job['key'][:8]}", fill="black")
                draw.text((x,y+228), Path(job["source"]).stem[-22:], fill="black")
        sheet.save(ROOT / "runtime/input-contact-sheet.png")
    print({"pending_unique_images": len(pending),"held_after_service_refusal":held_count,"matching_eligible_images":len(eligible), "prepared": len(jobs), "contact_sheet": "runtime/input-contact-sheet.png"})
    return jobs

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["scan", "prepare"])
    parser.add_argument("--game-root")
    parser.add_argument("--limit", type=int, default=16)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--match",help="Filter pending source paths by case-insensitive substring, e.g. /FRA/ or pierre_laval")
    args=parser.parse_args()
    if args.command=="scan":
        inventory(game_root(args.game_root))
    else:
        from tools.common import read_json
        prepare(read_json(MOD/"data/catalog.json"),args.limit,args.offset,args.match)

if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
