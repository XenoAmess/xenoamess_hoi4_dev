"""Reassemble a locked film and a separately generated, reference-audio coda.

The supplied videos already contain their intended text. This composer adds no
captions, generates no narration, and applies no implicit audio gain or ducking.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

from xar_promo.audio import AudioMixSpec, AudioStem
from xar_promo.capture import CaptureFile
from xar_promo.pipeline import PipelineDependencies, PipelineDraft, PipelineInvocation, SegmentDraft
from xar_promo.process import CommandSpec, run_command
from xar_promo.render import RenderOptions
from xar_promo.sources import VIDEO, VisualProbeResult, VisualSource
from xar_promo.storyboard import TimelineSpacing, plan_storyboard

from . import _wave_seconds


def compose(config, run, *, config_path, run_path, workdir, adapter_factory,
            preset_factory, validate_only):
    path = Path(os.environ['NAILONG_PROMO_INPUTS']).resolve()
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('assembly inputs exceed 1MiB')
    body = json.loads(path.read_text(encoding='utf-8'))
    if body.get('schema') != 'gangnailongxin-promo-final-assembly-v1':
        raise ValueError('unsupported final assembly inputs')
    root = Path(body['project_root']).resolve()
    if not path.is_relative_to(root):
        raise ValueError('assembly inputs must be within the project')
    style = preset_factory(root=root, binding=body['style'])
    chapters = config.to_dict()['chapters']
    if [chapter['id'] for chapter in chapters] != ['MAIN', 'LAUGH']:
        raise ValueError('expected the locked film followed by the laugh coda')
    rows = body['segments']
    if set(rows) != {'MAIN', 'LAUGH'}:
        raise ValueError('assembly requires exactly two bound segments')
    sources = {}
    durations = {}
    for chapter in chapters:
        key = chapter['id']
        row = rows[key]
        visual = CaptureFile.from_mapping(row['video'], project_root=root).path
        audio = CaptureFile.from_mapping(row['audio'], project_root=root).path
        duration = _wave_seconds(audio)
        expected = 60 if key == 'MAIN' else 5
        if abs(duration - expected) > 1e-6:
            raise ValueError('assembly audio duration differs from the locked edit')
        sources[key] = (visual, audio)
        durations[key] = duration
    timeline = plan_storyboard(config, narration_duration_resolver=None,
        draft_estimator=lambda p, ch, cue: durations[ch.chapter_id],
        spacing=TimelineSpacing(cue_gap_seconds=0, chapter_gap_seconds=0), validate_only=True)
    if float(timeline.duration_seconds) != 65 or style['duration_seconds'] != 65:
        raise ValueError('the final edit must be exactly65 seconds')

    def subtitles(segment, narration, *, workdir):
        return ('[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n'
                '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, '
                'SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, '
                'StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, '
                'Alignment, MarginL, MarginR, MarginV, Encoding\n'
                'Style: Default,Arial,48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,'
                '0,0,0,0,100,100,0,0,1,1,0,2,0,0,0,1\n'
                '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, '
                'MarginV, Effect, Text\n')

    segments = []
    for timing in timeline.chapters:
        key = timing.chapter_id
        video, audio = sources[key]
        duration = float(timing.duration_seconds)
        mix = AudioMixSpec((AudioStem(key + '.prepared', audio),),
                           duration_seconds=duration, normalize=False)
        segments.append(SegmentDraft(key, VisualSource(key, VIDEO, video,
            'hoi4-promo-final-assembly', requires_resolution=False),
            RenderOptions(1920,1080,30,duration,preset='veryfast',crf=19), {},
            prepared_narration=audio, audio_mix=mix))
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise ValueError('FFmpeg not found')

    def probe(path):
        result = run_command(CommandSpec.create([shutil.which('ffprobe'),
            '-v','error','-select_streams','v:0','-show_entries',
            'stream=width,height','-of','json',str(path)],
            label='Probe bound final-assembly visual'),
            audit_directory=workdir/'probe-audit'/path.stem)
        stream = json.loads(result.stdout)['streams'][0]
        return VisualProbeResult('video/mp4', stream['width'], stream['height'])

    return PipelineInvocation(PipelineDraft(config, tuple(segments),
        Path('gangnailongxin-peace-laugh-native-intermediate-v4.mp4'),
        'promo-laugh-native-intermediate-v4', 'video/mp4'),
        PipelineDependencies(ffmpeg, subtitles, run_command, probe), workdir)
