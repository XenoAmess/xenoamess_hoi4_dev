"""HOI4-owned capture interpretation, film layout and XAR composition.

No entry point controls the game. Production requires a byte-bound input
manifest with all planned footage present. Planning performs file reads only.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import wave

from PIL import Image, ImageDraw, ImageFont
from xar_promo.audio import AudioMixSpec, AudioStem, DuckWindow
from xar_promo.capture import CaptureFile
from xar_promo.pipeline import PipelineDependencies, PipelineDraft, PipelineInvocation, SegmentDraft
from xar_promo.process import CommandSpec, run_command
from xar_promo.render import RenderOptions, execute_render_plan, plan_concat
from xar_promo.sources import VIDEO, VisualProbeResult, VisualSource
from xar_promo.storyboard import TimelineSpacing, plan_storyboard
from xar_promo.subtitles import AssCue, AssDocumentConfig, AssStyleConfig, SubtitleTrackConfig, render_ass_document

from .capture_index import load_capture_index


def adapter(*, project_root, index_path, casting_policy):
    return load_capture_index(Path(project_root), Path(index_path), casting_policy)


def preset(*, root, binding):
    file = CaptureFile.from_mapping(binding, project_root=root, context='style')
    result = json.loads(file.path.read_text(encoding='utf-8'))
    if result.get('schema') != 'gangnailongxin-promo-style-v1':
        raise ValueError('Unsupported film style')
    if tuple(result[k] for k in ('width','height','fps','duration_seconds')) != (1920,1080,30,75):
        raise ValueError('This preset implements the approved1080p30/75-second film')
    return result


def _read_inputs():
    path = Path(os.environ['NAILONG_PROMO_INPUTS']).expanduser().resolve()
    with path.open('rb') as stream:
        data = stream.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError('production inputs exceed 1MiB')
    body = json.loads(data.decode('utf-8'))
    if body.get('schema') != 'gangnailongxin-promo-production-inputs-v1':
        raise ValueError('Unsupported production inputs')
    if body.get('capture_complete') is not True:
        raise ValueError('Filming incomplete: '+', '.join(body.get('remaining_capture', [])))
    root = Path(body['project_root']).resolve()
    if not path.is_relative_to(root):
        raise ValueError('production inputs must stay inside project root')
    return root, body


def _wave_seconds(path):
    with wave.open(str(path), 'rb') as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (48000, 2, 2):
            raise ValueError('prepared narration must be48kHz stereo16-bit WAV')
        return wav.getnframes()/wav.getframerate()


def _font(style, size):
    return ImageFont.truetype(str(Path(os.environ['WINDIR'])/'Fonts'/style['font_file']), size)


def _card(style, arts, phase, target):
    image = Image.new('RGB', (style['width'], style['height']), style['background'])
    draw = ImageDraw.Draw(image)
    accent, text, muted = style['accent'], style['text'], style['muted']
    draw.line((80, 36, 1840, 36), fill=accent, width=3)
    draw.text((80, 45), '钢奶龙心', font=_font(style, 54), fill=text)
    draw.text((1590, 75), '1.0', font=_font(style, 38), fill=accent)
    layout = phase['layout']
    def portrait(key, box):
        if key not in style['allowed_art_ids']:
            raise ValueError('Unplanned focal figure: '+key)
        with Image.open(arts[key]) as original:
            framed = original.convert('RGBA')
            framed.thumbnail((box[2], box[3]), Image.Resampling.LANCZOS)
            image.paste(framed, (box[0]+(box[2]-framed.width)//2, box[1]), framed)
    if layout in {'title', 'end'}:
        portrait('ENG', (150, 178, 560, 754))
        draw.text((165, 940), style['art_label'], font=_font(style, 24), fill=muted)
        draw.text((850, 245), '钢奶龙心', font=_font(style, 112), fill=text)
        draw.text((858, 400), '1.0', font=_font(style, 78), fill=accent)
        if layout == 'title':
            draw.text((860, 565), '奶龙，登场。', font=_font(style, 62), fill=text)
            draw.text((863, 682), 'HOI4 人物头像模组', font=_font(style, 38), fill=muted)
        else:
            draw.text((860, 560), 'Steam 创意工坊', font=_font(style, 48), fill=text)
            draw.text((860, 642), '搜索「钢奶龙心」', font=_font(style, 54), fill=accent)
            draw.text((863, 760), '条目 ID：3830400579', font=_font(style, 30), fill=muted)
    else:
        draw.rectangle((79, 155, 1105, 925), outline=style['panel'], width=2)
        label = '实机画面（裁切）' if phase.get('crop') else '实机画面'
        draw.text((82, 122), label, font=_font(style, 22), fill=muted)
        headings = {'map':'1936\n世界局势\n很严肃', 'reveal':'出席会议的\n是——',
                    'countries':'熟悉的角色\n奶龙登场', 'detail':'认角色\n也看细节',
                    'advisors':'领袖之外\n还有顾问', 'meeting':'下一次\n开会……',
                    'joke':'请先忍住\n别笑'}
        draw.multiline_text((1185, 190), headings[layout], font=_font(style, 62), fill=text, spacing=20)
        keys = phase.get('art', [])
        if keys:
            if len(keys) == 1:
                portrait(keys[0], (1295, 440, 360, 480))
            elif len(keys) == 4:
                for key, box in zip(keys, [(1210,415,180,240),(1530,415,180,240),(1210,690,150,200),(1530,690,150,200)]):
                    portrait(key, box)
            else:
                for i, key in enumerate(keys):
                    portrait(key, (1180+i*205, 490, 190, 255))
            draw.text((1188, 927), style['art_label'], font=_font(style, 23), fill=muted)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)


def _probe(path):
    base = path.parent/'probe-audit'/path.stem
    for number in range(100):
        audit = base/f'probe-{number:03}'
        if not audit.exists():
            break
    else:
        raise ValueError('visual probe attempt limit reached')
    result = run_command(CommandSpec.create([shutil.which('ffprobe'), '-v', 'error',
        '-select_streams','v:0','-show_entries','stream=width,height','-of','json',str(path)],
        label='probe project visual'), audit_directory=audit)
    stream = json.loads(result.stdout)['streams'][0]
    return VisualProbeResult('video/mp4', int(stream['width']), int(stream['height']))


def _crop_for(phase, clip):
    size = clip.metadata['capture_size']
    crop = phase.get('crop', [0,0,*size])
    if len(crop)!=4 or any(type(x) is not int for x in crop) or crop[0]<0 or crop[1]<0 or crop[2]<=0 or crop[3]<=0 or crop[0]+crop[2]>size[0] or crop[1]+crop[3]>size[1]:
        raise ValueError('invalid native capture crop')
    return crop


def compose(config, run, *, config_path, run_path, workdir, adapter_factory, preset_factory,
            validate_only):
    root, body = _read_inputs()
    style = preset_factory(root=root, binding=body['style'])
    clips = adapter_factory(project_root=root, index_path=root/body['capture_index'],
                            casting_policy=body['casting_policy'])
    policy = json.loads(CaptureFile.from_mapping(body['shot_plan'], project_root=root).path.read_text(encoding='utf-8'))
    if policy['casting_policy'] != body['casting_policy']:
        raise ValueError('production casting does not match the director shot plan')
    assets = {key:CaptureFile.from_mapping(value, project_root=root).path for key,value in body['arts'].items()}
    audio = {key:CaptureFile.from_mapping(value, project_root=root).path for key,value in body['narration'].items()}
    score = CaptureFile.from_mapping(body['score'], project_root=root).path
    durations = {key:_wave_seconds(path) for key,path in audio.items()}
    timeline = plan_storyboard(config, narration_duration_resolver=None,
        draft_estimator=lambda p,ch,cue:durations[ch.chapter_id],
        spacing=TimelineSpacing(cue_gap_seconds=0, chapter_gap_seconds=0), validate_only=True)
    if abs(float(timeline.duration_seconds)-style['duration_seconds']) > 1e-6:
        raise ValueError('prepared audio timeline differs from75-second editorial target')
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise ValueError('FFmpeg not found')
    phases = body['shots']
    for chapter in timeline.chapters:
        text = ''.join(cue['narration']['zh-CN'] for cue in next(
            row for row in config.to_dict()['chapters'] if row['id']==chapter.chapter_id)['cues'])
        if body['narration_texts'].get(chapter.chapter_id) != text:
            raise ValueError('prepared narration text differs from current project config')
        recipe = phases[chapter.chapter_id]
        if not recipe or abs(sum(p['seconds'] for p in recipe)-float(chapter.duration_seconds)) > 1e-6:
            raise ValueError('phase durations differ from narration timeline')
        for phase in recipe:
            if phase.get('missing_capture_role') or (chapter.chapter_id not in {'S03','S08'} and 'clip_id' not in phase):
                raise ValueError('Missing recorded phase for '+chapter.chapter_id)
            if not isinstance(phase['seconds'], (int,float)) or not math.isfinite(phase['seconds']) or phase['seconds'] <= 0:
                raise ValueError('invalid phase duration')
            if 'clip_id' in phase:
                clip = clips[phase['clip_id']]
                _crop_for(phase, clip)
                span = next(s for s in clip.clean_spans if s.span_id == phase['span_id'])
                if not span.begin_seconds <= phase['start_seconds'] < phase['start_seconds']+phase['seconds'] <= span.end_seconds+1e-6:
                    raise ValueError('film phase escapes selected capture span')

    def resolve(source, *, workdir):
        key = source.source_id
        target = source.path
        parts = []
        for number, phase in enumerate(phases[key], 1):
            card = workdir/'cards'/f'{key}-{number}.png'
            _card(style, assets, phase, card)
            part = workdir/'visual-parts'/f'{key}-{number}.mp4'
            part.parent.mkdir(parents=True, exist_ok=True)
            args = [ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-n','-loop','1','-framerate','30','-i',str(card)]
            if 'clip_id' in phase:
                clip = clips[phase['clip_id']]
                args += ['-ss',str(phase['start_seconds']),'-i',str(clip.raw_capture.path)]
                crop = _crop_for(phase, clip)
                scale = min(1,1024/crop[2],768/crop[3])
                width,height=(max(2,round(crop[2]*scale/2)*2),max(2,round(crop[3]*scale/2)*2))
                x,y=80+(1024-width)//2,156+(768-height)//2
                graph=f'[1:v]crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]},scale={width}:{height},fps=30[game];[0:v][game]overlay={x}:{y}:shortest=1,format=yuv420p[v]'
                args += ['-filter_complex',graph,'-map','[v]']
            else:
                fade = f",fade=t=out:st={phase['seconds']-.5}:d=.5" if phase['layout']=='end' else ''
                args += ['-vf','format=yuv420p'+fade]
            args += ['-t',str(phase['seconds']),'-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p',str(part)]
            run_command(CommandSpec.create(args,label='compose project visual',partial_artifacts=(part,)),audit_directory=workdir/'layout-audit'/f'{key}-{number}')
            parts.append(part)
        target.parent.mkdir(parents=True, exist_ok=True)
        execute_render_plan(plan_concat(ffmpeg=ffmpeg, segment_paths=parts,
            concat_path=workdir/'visual-parts'/f'{key}.ffconcat',
            partial_output=target.with_name(target.stem+'.partial.mp4'), final_output=target,
            audit_directory=workdir/'layout-concat-audit'/key))
        return target

    def subtitles(segment, narration, *, workdir):
        timing = next(c for c in timeline.chapters if c.chapter_id == segment.segment_id)
        cues = [AssCue(row['id'],'zh-CN',row['start_seconds']-float(timing.start_seconds),
                       row['end_seconds']-float(timing.start_seconds),row['text'].replace('\n',''))
                for row in body['subtitle_cues']
                if float(timing.start_seconds) <= row['start_seconds'] < float(timing.end_seconds)]
        return render_ass_document(AssDocumentConfig(segment.segment_id,1920,1080,float(timing.duration_seconds)),
            [SubtitleTrackConfig('zh-CN','zh-CN',1,AssStyleConfig('Narration',style['font_family'],48,
                 margin_left=80,margin_right=80,margin_vertical=70))], cues,
            available_font_names=[style['font_family']])

    segments=[]
    for timing in timeline.chapters:
        key=timing.chapter_id;duration=float(timing.duration_seconds);start=float(timing.start_seconds)
        ducks=tuple(DuckWindow(row['start_seconds']-start,row['end_seconds']-start,-8)
                    for row in body['subtitle_cues'] if start<=row['start_seconds']<float(timing.end_seconds))
        mix=AudioMixSpec((AudioStem(key+'.voice',audio[key],gain_db=3),
             AudioStem(key+'.bgm',score,trim_start_seconds=start,trim_duration_seconds=duration,
                       gain_db=-3,duck_windows=ducks)),duration_seconds=duration,normalize=False)
        segments.append(SegmentDraft(key,VisualSource(key,VIDEO,workdir/'visuals'/f'{key}.mp4',
            'hoi4-promo-composite',requires_resolution=True),RenderOptions(1920,1080,30,duration,
            preset='veryfast',crf=19),{'zh-CN':key},prepared_narration=audio[key],audio_mix=mix))
    return PipelineInvocation(PipelineDraft(config,tuple(segments),Path('gangnailongxin-promo-review-v1.mp4'),
        'promo-review-v1','video/mp4'),PipelineDependencies(ffmpeg,subtitles,run_command,_probe,
        visual_resolver=resolve),workdir)
