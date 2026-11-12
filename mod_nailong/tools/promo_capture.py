"""Bounded raw-desktop video capture; observes OS focus, never game internals.

The recorder produces raw media and technical receipts. Clean spans and their
meaning require a subsequent review; this command never declares them approved.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.common import machine_id, write_json
from tools.desktop import desktop_modules, observe

PACKAGE_CAP = 512 * 1024 * 1024
CLIP_CAP = 32 * 1024 * 1024


def file_binding(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
            'sha256': digest.hexdigest()}


def package_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hwnd', type=int, required=True)
    parser.add_argument('--package-root', type=Path, required=True)
    parser.add_argument('--clip-id', required=True)
    parser.add_argument('--seconds', type=int, default=18, choices=range(5, 31))
    args = parser.parse_args()
    package = args.package_root.resolve()
    if package.parent != ROOT / 'runtime' or not package.name.startswith('promo-capture-'):
        parser.error('package-root must be an owned runtime/promo-capture-* directory')
    if not args.clip_id or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in args.clip_id):
        parser.error('clip-id must contain only lowercase ASCII letters, digits, dash or underscore')
    clip = package / 'clips' / args.clip_id
    if clip.exists():
        parser.error('clip already exists; failed attempts must remain separate')
    if package_bytes(package) + 2 * CLIP_CAP >= PACKAGE_CAP:
        parser.error('bounded package lacks room for a clip and later preservation copy')
    if shutil.disk_usage(package).free < 32 * 1024**3:
        parser.error('volume lacks the profile system reserve and safety margin')
    gui, windows = desktop_modules()
    title = windows.GetWindowText(args.hwnd)
    size = tuple(gui.size())
    if windows.GetForegroundWindow() != args.hwnd or title != 'Hearts of Iron IV (DirectX 11)':
        parser.error('fresh observed HOI4 window must already have foreground focus')
    rect = tuple(windows.GetWindowRect(args.hwnd))
    if rect != (0, 0, *size):
        parser.error('requires the inspected full-desktop game window, without an unrelated window border')
    ffmpeg = shutil.which('ffmpeg')
    ffprobe = shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        parser.error('FFmpeg and ffprobe are required')
    clip.mkdir(parents=True)
    before = observe(clip / 'before.png', ocr=True)
    if before['foreground_hwnd'] != args.hwnd:
        raise RuntimeError('focus changed before starting capture')
    raw = clip / 'raw.mkv'
    argv = [ffmpeg, '-hide_banner', '-nostats', '-loglevel', 'warning',
            '-f', 'gdigrab', '-framerate', '30', '-draw_mouse', '0',
            '-video_size', f'{size[0]}x{size[1]}', '-i', 'desktop',
            '-t', str(args.seconds), '-an', '-c:v', 'libx264', '-preset', 'veryfast',
            '-crf', '16', '-maxrate', '8M', '-bufsize', '16M',
            '-pix_fmt', 'yuv420p', '-fps_mode', 'cfr', '-fs', str(CLIP_CAP), str(raw)]
    started = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    failure = None
    samples = 0
    with (clip / 'ffmpeg.stderr.txt').open('wb') as stderr:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                   stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
        while process.poll() is None:
            samples += 1
            if windows.GetForegroundWindow() != args.hwnd:
                failure = 'foreground-focus-changed'
            elif tuple(gui.size()) != size or tuple(windows.GetWindowRect(args.hwnd)) != rect:
                failure = 'desktop-or-window-size-changed'
            elif package_bytes(package) >= PACKAGE_CAP - CLIP_CAP:
                failure = 'bounded-package-limit'
            elif time.monotonic() - start > args.seconds + 20:
                failure = 'capture-watchdog'
            if failure:
                try:
                    process.communicate(b'q\n', timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                break
            time.sleep(0.25)
        process.wait()
    after = observe(clip / 'after.png', ocr=True)
    # An input collision after the last monitor poll is also a failed capture.
    if after['foreground_hwnd'] != args.hwnd or after['image_size'] != list(size):
        failure = failure or 'post-capture-focus-or-size-changed'
    probe = subprocess.run([ffprobe, '-v', 'error', '-count_frames', '-show_streams',
                            '-show_format', '-of', 'json', str(raw)],
                           capture_output=True, check=False)
    (clip / 'ffprobe.stdout.json').write_bytes(probe.stdout)
    (clip / 'ffprobe.stderr.txt').write_bytes(probe.stderr)
    info = json.loads(probe.stdout) if probe.returncode == 0 else None
    streams = info.get('streams', []) if info else []
    videos = [s for s in streams if s.get('codec_type') == 'video']
    if process.returncode != 0 or probe.returncode != 0 or len(videos) != 1:
        failure = failure or 'recorder-or-probe-failed'
    if videos and (int(videos[0]['width']), int(videos[0]['height'])) != size:
        failure = failure or 'encoded-size-mismatch'
    duration = float(info['format']['duration']) if info else None
    count = videos[0].get('nb_read_frames') if videos else None
    frames = int(count) if str(count).isdigit() else None
    if duration is None or abs(duration - args.seconds) > 0.5:
        failure = failure or 'requested-duration-not-captured'
    if frames is None or frames < 30 * (args.seconds - 0.5):
        failure = failure or 'insufficient-decoded-frames'
    receipt = {
        'schema': 'gangnailongxin-bounded-raw-capture-v1', 'machine_id': machine_id(),
        'clip_id': args.clip_id, 'started_at_utc': started,
        'finished_at_utc': datetime.now(timezone.utc).isoformat(),
        'producer': 'FFmpeg gdigrab raw desktop pixels; no game or Steam API',
        'argv': argv, 'expected_hwnd': args.hwnd, 'expected_title': title,
        'desktop_size': list(size), 'focus_monitor_samples': samples,
        'recorder_exit_code': process.returncode, 'probe_exit_code': probe.returncode,
        'raw': file_binding(raw), 'before': file_binding(clip / 'before.png'),
        'after': file_binding(clip / 'after.png'),
        'duration_seconds': duration,
        'frame_count': frames,
        'technical_capture_status': 'failed' if failure else 'recorded-awaiting-content-review',
        'failure': failure, 'clean_spans': None, 'human_signoff': None,
        'audio': 'No audio stream captured; narration/music/SFX are later production work.',
        'budget': {'per_clip_cap_bytes': CLIP_CAP, 'package_cap_bytes': PACKAGE_CAP,
                   'current_package_bytes': package_bytes(package)},
    }
    write_json(clip / 'capture-technical.json', receipt)
    print(json.dumps({k: receipt[k] for k in ('clip_id', 'duration_seconds', 'frame_count',
                      'technical_capture_status', 'failure', 'raw')}, ensure_ascii=False), flush=True)
    return 2 if failure else 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
