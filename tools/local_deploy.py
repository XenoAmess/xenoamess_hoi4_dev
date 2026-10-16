"""Register a verified local build with the HOI4 launcher; no client control."""
from __future__ import annotations
import argparse
import ctypes
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,file_sha256,machine_id,read_json,utc_now,write_json
from mod_nailong.tools.build_release import verify

def documents():
    buffer=ctypes.create_unicode_buffer(32768)
    result=ctypes.windll.shell32.SHGetFolderPathW(None,5,None,0,buffer)
    if result:raise SystemExit(f"Cannot resolve Windows Documents: {result}")
    return Path(buffer.value)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build",type=Path,required=True)
    parser.add_argument("--enable",action="store_true")
    args=parser.parse_args()
    build=args.build.resolve()
    verify(build)
    profile=documents()/"Paradox Interactive/Hearts of Iron IV"
    target=profile/"mod/naiwa_world.mod"
    target.parent.mkdir(parents=True,exist_ok=True)
    descriptor=(build/"staging/descriptor.mod").read_text(encoding="utf-8")
    content=descriptor+f'path="{(build/"staging").as_posix()}"\n'
    previous=target.read_text(encoding="utf-8-sig") if target.exists() else None
    target.write_text(content,encoding="utf-8",newline="\n")
    dlc_file=profile/"dlc_load.json"
    previous_dlc=dlc_file.read_text(encoding="utf-8-sig") if dlc_file.exists() else None
    if args.enable:
        state=json.loads(previous_dlc) if previous_dlc else {"disabled_dlcs":[],"enabled_mods":[]}
        mods=state.setdefault("enabled_mods",[])
        if "mod/naiwa_world.mod" not in mods:mods.append("mod/naiwa_world.mod")
        write_json(dlc_file,state)
        if "mod/naiwa_world.mod" not in read_json(dlc_file)["enabled_mods"]:raise SystemExit("Local mod enable readback failed")
    write_json(ROOT/"runtime/deployment.json",{"machine_id":machine_id(),"observed_at_utc":utc_now(),"source":"local_deploy.py file write and actual readback; no launcher/game load claim","build":str(build),"user_profile":str(profile),"outer_descriptor":str(target),"outer_sha256":file_sha256(target),"previous_outer_descriptor":previous,"previous_dlc_load":previous_dlc,"enabled_in_dlc_load":args.enable,"game_load":"not-yet-verified"})
    print(f"Registered {target}; game load remains unverified")

if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
