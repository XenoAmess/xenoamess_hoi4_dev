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

def _replace_json(temporary: Path, path: Path) -> None:
    if os.name != 'nt':
        temporary.replace(path)
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    replace = kernel.ReplaceFileW
    replace.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                        wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
    replace.restype = wintypes.BOOL
    # MoveFileExW (os.replace) can still deny replacement of an open target
    # even when its reader shares deletion. ReplaceFileW preserves the old
    # reader's complete file and atomically publishes the replacement.
    if replace(str(path), str(temporary), None, 0, None, None):
        return
    error = ctypes.get_last_error()
    if error in (2, 3):  # First write: there is no existing destination.
        temporary.replace(path)
        return
    raise ctypes.WinError(error)

def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    # Windows readers/virus scanners can briefly deny replacement of an open
    # destination. Keep the old complete JSON visible and retry only this local
    # atomic replacement, never any image-generation request.
    # Large live journals can remain share-denied beyond the former ~8s
    # budget. Bound replacement waits to ~32s and preserve the candidate on
    # exhaustion; this never repeats the caller's image request or review.
    for delay in (0.02, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16, None):
        try:
            _replace_json(temporary, path)
            break
        except OSError as error:
            # ReplaceFileW error1175 leaves both original names intact, so
            # retrying this same candidate is safe (unlike1176/1177).
            # https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew
            retryable = isinstance(error, PermissionError) or getattr(error, 'winerror', None) == 1175
            if not retryable or delay is None:
                raise
            time.sleep(delay)

def _open_json_reader(path: Path):
    """Keep a consistent old file readable during an atomic Windows replace.

    The Windows CRT reader does not share deletion, so overlapping readers of
    the large inventory can deny the producer's rename. Share deletion as well
    as ordinary read/write access; the open handle still reads its original
    complete file. Every later open resolves the current path, without cache.
    """
    if os.name != 'nt':
        return path.open('rb')
    import ctypes
    from ctypes import wintypes
    import msvcrt
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    handle = create(str(path), 0x80000000, 0x1 | 0x2 | 0x4, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        close(handle)
        raise
    try:
        return os.fdopen(fd, 'rb')
    except BaseException:
        os.close(fd)
        raise

def read_json(path: Path):
    # An atomic replacement can briefly leave the old Windows file in a
    # delete-pending/share-denied state. Retry only opening this same file;
    # never substitute cached data or retry malformed/missing JSON.
    for delay in (0.02, 0.05, 0.1, 0.25, 0.5, None):
        try:
            with _open_json_reader(path) as stream:
                body = stream.read().decode('utf-8')
        except PermissionError:
            if delay is None:
                raise
            time.sleep(delay)
        else:
            return json.loads(body)

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
