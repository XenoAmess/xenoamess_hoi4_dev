"""Shared filesystem and identity utilities. No game/client connection."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def machine_id() -> str:
    """Same hostname + MachineGuid algorithm as ck3_live_run_id.py."""
    explicit = os.environ.get("XAR_CK3_MACHINE_ID")
    if explicit:
        return re.sub(r"[^a-z0-9]+", "-", explicit.lower()).strip("-")[:64]
    if os.name == "nt":
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            token = "windows-machine-guid:" + winreg.QueryValueEx(key, "MachineGuid")[0]
    else:
        source = next((p for p in [Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")] if p.exists()), None)
        token = "machine-id:" + source.read_text().strip() if source else "node:" + platform.node()
    host = re.sub(r"[^a-z0-9]+", "-", platform.node().lower()).strip("-")[:32].rstrip("-")
    return host + "-" + sha256(token.encode())[:10]

def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    # Windows readers/virus scanners can briefly deny replacement of an open
    # destination. Keep the old complete JSON visible and retry only this local
    # atomic replacement, never any image-generation request.
    for delay in (0.02, 0.05, 0.1, 0.25, 0.5, None):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            if delay is None:
                raise
            time.sleep(delay)

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def game_root(value: str | None = None) -> Path:
    candidate = value or os.environ.get("HOI4_GAME_ROOT")
    if not candidate:
        profile = ROOT / "runtime/local-profile.json"
        if profile.exists():
            candidate = read_json(profile)["game_root"]
    if not candidate:
        raise SystemExit("Set HOI4_GAME_ROOT or pass --game-root (see README).")
    path = Path(candidate).resolve()
    if not (path / "hoi4.exe").is_file():
        raise SystemExit(f"Not a HOI4 installation: {path}")
    return path
