#!/usr/bin/env python3
"""Render a reusable, caption-complete storyboard from a JSON manifest (Pillow)."""
import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps

MODES = {'reference': '多图参考', 'first_last': '首尾帧',
         'audio_reference': '音频参考', 'text': '文生视频'}
ORANGE = '#FF9C36'
GRAY = '#697586'


def wrap(draw, text, font, width):
    result = []
    for paragraph in text.split('\n'):
        line = ''
        for char in paragraph:
            if line and draw.textlength(line + char, font=font) > width:
                result.append(line)
                line = ''
            line += char
        result.append(line)
    return result


def resolve(base, value):
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def choose_font(requested):
    candidates = [requested] if requested else [
        '/System/Library/Fonts/STHeiti Medium.ttc',
        '/System/Library/Fonts/PingFang.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']
    for name in candidates:
        if name and Path(name).is_file():
            return name
    raise ValueError('Provide --font with a font supporting the caption language')


def render_scene_info(image, spec, base, fallback_font, preview_time=None):
    """Composite deterministic scene text for a storyboard or animation sample.

    Sizes are relative to design_height; times are local to the scene shot.
    Original reference pixels remain separate from this preview.
    """
    if not isinstance(spec, dict) or not isinstance(spec.get('lines'), list) or not spec['lines']:
        raise ValueError('scene_info requires a nonempty lines list')
    lines = spec['lines']
    if any(not isinstance(row, dict) or not isinstance(row.get('text'), str) or not row['text'].strip()
           for row in lines):
        raise ValueError('scene_info lines require nonempty text')
    style = spec.get('style', 'plain')
    if style not in ('plain', 'tech', 'cinematic'):
        raise ValueError('scene_info style must be plain, tech or cinematic')
    anchor = spec.get('anchor', [0.065, 0.77])
    if len(anchor) != 2 or any(not 0 <= float(v) <= 1 for v in anchor):
        raise ValueError('scene_info anchor must be normalized x/y')
    source_font = resolve(base, spec['font']) if spec.get('font') else fallback_font
    face_path = choose_font(str(source_font))
    scale = image.height / float(spec.get('design_height', 480))
    spacing = float(spec.get('tracking', 1.0)) * scale
    gap = float(spec.get('line_gap', 10)) * scale
    x, y = round(image.width * float(anchor[0])), round(image.height * float(anchor[1]))
    measure = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    layouts = []
    for index, row in enumerate(lines):
        size = round(float(row.get('size', 28 if index == 0 else 22)) * scale)
        if size < 1:
            raise ValueError('scene_info font size must be positive')
        face = ImageFont.truetype(face_path, size)
        width = sum(measure.textlength(c, font=face) for c in row['text']) + spacing * (len(row['text']) - 1)
        layouts.append((row, face, width, size, y))
        y += size + gap
    right = x + max(row[2] for row in layouts)
    bottom = layouts[-1][4] + layouts[-1][3]
    pad = round(float(spec.get('padding', 14)) * scale)
    if x - pad < 0 or layouts[0][4] - pad < 0 or right + pad > image.width or bottom + pad > image.height:
        raise ValueError('scene_info does not fit; shorten text or adjust placement/size')
    layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    time = spec.get('preview_time') if preview_time is None else preview_time
    if time is None:
        time = max(float(r.get('enter', 0)) + float(r.get('reveal', 0.2)) for r in lines)
    time = float(time)
    visible = any(time > float(r.get('enter', 0)) for r in lines)
    if not visible:
        return image.copy()
    exit_time = spec.get('exit')
    fade = float(spec.get('exit_fade', .2))
    block_alpha = 1 if exit_time is None or time <= float(exit_time) else max(0, 1 - (time-float(exit_time))/max(fade, .001))
    rect = (x-pad, layouts[0][4]-pad, math.ceil(right+pad), math.ceil(bottom+pad))
    if style == 'cinematic':
        # A feathered local shade keeps letters readable without a visible HUD box.
        shade = Image.new('L', image.size, 0)
        sd = ImageDraw.Draw(shade)
        sd.rectangle(rect, fill=round(110*block_alpha))
        from PIL import ImageFilter
        shade = shade.filter(ImageFilter.GaussianBlur(max(1, 24*scale)))
        layer.paste(Image.new('RGBA', image.size, (0, 0, 0, 255)), (0, 0), shade)
        draw = ImageDraw.Draw(layer)
    else:
        draw.rounded_rectangle(rect, radius=max(1, round(3*scale)), fill=(7, 16, 25, round(165*block_alpha)))
    if style == 'tech':
        accent = ImageColor.getrgb(spec.get('accent', '#78DAF5')) + (round(225*block_alpha),)
        stroke = max(1, round(2*scale)); leg = round(12*scale)
        left, top, rx, by = rect
        draw.line([(left, top+leg), (left, top), (left+round(70*scale), top)], fill=accent, width=stroke)
        draw.line([(rx-leg, by), (rx, by), (rx, by-leg)], fill=accent, width=stroke)
    for row, face, width, size, ty in layouts:
        reveal = float(row.get('reveal', .2))
        if reveal <= 0:
            raise ValueError('scene_info reveal must be positive')
        progress = max(0, min(1, (time-float(row.get('enter', 0)))/reveal))
        if progress == 0 or block_alpha == 0:
            continue
        color = ImageColor.getrgb(row.get('color', '#EFF8FF')) + (round(255*progress*block_alpha),)
        tx = float(x)
        for char in row['text']:
            if style == 'cinematic':
                draw.text((round(tx)+1, ty+1), char, font=face, anchor='lt',
                          fill=(0, 0, 0, round(160*progress*block_alpha)))
            draw.text((round(tx), ty), char, font=face, anchor='lt', fill=color)
            tx += measure.textlength(char, font=face) + spacing
    return Image.alpha_composite(image.convert('RGBA'), layer).convert('RGB')


def render(manifest_path, output, columns=3, card_width=1080, font_path=None):
    if not 1 <= columns <= 6 or card_width < 600:
        raise ValueError('columns must be 1–6; card-width must be at least 600')
    manifest_path = Path(manifest_path).resolve()
    data = json.loads(manifest_path.read_text())
    base = manifest_path.parent
    font_path = choose_font(font_path or data.get('font'))
    font = lambda size: ImageFont.truetype(font_path, size)
    body = font(32)
    heading = font(40)
    small = font(28)
    margin, gap, pad = 50, 36, 24
    inner = card_width - 2 * pad
    measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    shots = data['shots']
    if not shots:
        raise ValueError('shots must not be empty')
    seen, cards = set(), []
    for shot in shots:
        for key in ('id', 'title', 'time', 'mode', 'action', 'sound'):
            if not isinstance(shot.get(key), str) or not shot[key].strip():
                raise ValueError(f'Shot requires nonempty string: {key}')
        if shot['id'] in seen:
            raise ValueError(f'Duplicate shot ID: {shot["id"]}')
        seen.add(shot['id'])
        mode = shot['mode']
        if mode not in MODES:
            raise ValueError(f'Unknown mode: {mode}')
        # Complete dialogue OR complete lyrics/passage is required, never truncate.
        caption_key = 'lyrics' if 'lyrics' in shot else 'dialogue'
        if not isinstance(shot.get(caption_key), str) or not shot[caption_key].strip():
            raise ValueError(f'{shot["id"]}: requires dialogue or lyrics/passage')
        pictures = []
        dependencies = []

        def picture(key, label, dependency_key):
            dependency = shot.get(dependency_key)
            if dependency:
                if not isinstance(dependency, dict) or dependency.get('status') not in ('pending', 'resolved'):
                    raise ValueError(f'{shot["id"]}: invalid {dependency_key}')
                if dependency.get('shot') not in seen or dependency['shot'] == shot['id']:
                    raise ValueError(f'{shot["id"]}: dependency must name a preceding shot')
                pending = dependency['status'] == 'pending'
                if pending and shot.get(key):
                    raise ValueError(f'{shot["id"]}: pending dependency cannot also supply {key}')
                if not pending and any(not dependency.get(k) and dependency.get(k) != 0 for k in ('source_video', 'source_frame', 'source_time')):
                    raise ValueError(f'{shot["id"]}: resolved dependency requires actual source provenance')
                status = '待上一分镜视频实际采用结尾帧生成／不可提交' if pending else '已取实际采用结尾帧'
                dependencies.append(f'{label}依赖：{dependency["shot"]} · {status}；{dependency.get("selection", "")}')
                if pending:
                    placeholder = Image.new('RGB', (752, 423), '#343840')
                    pd = ImageDraw.Draw(placeholder)
                    placeholder_font = font(52)
                    words = wrap(pd, f'{label}待生成\n取自上一分镜 {dependency["shot"]}\n视频实际采用结尾帧\n依赖未就绪 · 不可提交', placeholder_font, 704)
                    for i, line in enumerate(words):
                        pd.text((24, 45 + i * 70), line, font=placeholder_font, fill='#FF9C36')
                    pictures.append((label + '（待生成）', dependency['shot'] + ' 实片末帧依赖', placeholder))
                    return
            if not shot.get(key):
                raise ValueError(f'{shot["id"]}: missing {key}; supply an actual image or explicit pending dependency')
            path = resolve(base, shot[key])
            with Image.open(path) as im:
                preview = im.convert('RGB')
            scene_info = shot.get('scene_info')
            if scene_info and key in scene_info.get('frames', ['image']):
                preview = render_scene_info(preview, scene_info, base, font_path)
                label += '＋场景文字预览'
            pictures.append((label, path.name, preview))

        if mode == 'first_last':
            if not shot.get('pair') or not shot.get('join'):
                raise ValueError(f'{shot["id"]}: first_last requires pair and join rationale')
            for key, label in [('first_frame', '首帧'), ('last_frame', '尾帧')]:
                if key == 'first_frame':
                    picture(key, label, 'first_frame_dependency')
                else:
                    if shot.get('last_frame_dependency'):
                        raise ValueError(f'{shot["id"]}: planning requires an actual designed last frame')
                    picture(key, label, 'last_frame_dependency')
        elif mode != 'text':
            picture('image', '参考图', 'image_dependency')
        headers = wrap(measure, f'{shot["id"]}  {shot["title"]}', heading, inner)
        info = [f'时间：{shot["time"]}  ·  模式：{MODES[mode]}']
        if shot.get('workflow'):
            info.append(f'工作流：{shot["workflow"]}')
        if mode == 'first_last':
            info += [f'配对：{shot["pair"]}', f'衔接：{shot["join"]}']
        info += dependencies
        info += [f'动作：{shot["action"]}',
                 f'{"歌词／段落" if caption_key == "lyrics" else "台词"}：{shot[caption_key]}',
                 f'声音：{shot["sound"]}']
        if shot.get('scene_info'):
            si = shot['scene_info']
            info.append('场景文字：' + ' → '.join(row['text'] for row in si['lines']))
            info.append('逐行入场（镜内时间）：' + '；'.join(
                f'{float(row.get("enter", 0)):.2f}秒 {row["text"]}' for row in si['lines']))
            info.append(f'文字预览：{si.get("preview_label", "全部显示状态；后期叠字计划，未写入原片")}')
        if shot.get('camera'):
            info.append(f'镜头：{shot["camera"]}')
        if shot.get('note'):
            info.append(f'备注：{shot["note"]}')
        lines = [line for item in info for line in wrap(measure, item, body, inner)]
        picture_height = round(inner * 9 / 16) if pictures else 100
        if pictures:
            image_width = (inner - gap) // 2 if len(pictures) == 2 else inner
            picture_height = max(ImageOps.contain(im, (image_width, picture_height)).height for _, _, im in pictures)
        # Endpoint labels/filenames also wrap; preserve both images without crop.
        pw = (inner - gap) // 2 if len(pictures) == 2 else inner
        picture_labels = [wrap(measure, f'{label}：{name}', small, pw)
                          for label, name, _ in pictures]
        label_height = max((len(x) for x in picture_labels), default=0) * 38
        height = pad * 3 + len(headers) * 52 + picture_height + label_height + len(lines) * 44
        cards.append((shot, headers, lines, pictures, picture_labels, picture_height, height))
    columns = min(columns, len(cards))
    width = margin * 2 + columns * card_width + (columns - 1) * gap
    title_lines = wrap(measure, data['title'], font(64), width - 2 * margin)
    subtitle_lines = wrap(measure, data.get('subtitle', ''), body, width - 2 * margin)
    notes = data.get('notes', [])
    if not isinstance(notes, list) or any(not isinstance(x, str) for x in notes):
        raise ValueError('notes must be a list of strings')
    note_lines = [line for note in notes for line in wrap(measure, note, body, width - 2 * margin)]
    legend_lines = wrap(measure, '橙框＝必须首尾帧；灰框＝参考／音频／文生。以模式文字和配对编号共同识别。', small, width - 2 * margin - 50)
    legend_height = max(54, len(legend_lines) * 38 + 20)
    top = margin + len(title_lines) * 80 + len(subtitle_lines) * 44 + legend_height + len(note_lines) * 44 + gap
    rows = math.ceil(len(cards) / columns)
    row_heights = [max(c[6] for c in cards[row * columns:(row + 1) * columns]) for row in range(rows)]
    height = top + sum(row_heights) + (rows - 1) * gap + margin
    canvas = Image.new('RGB', (width, height), '#101115')
    draw = ImageDraw.Draw(canvas)

    def write(lines, x, y, face, advance, fill='#F1F0EC'):
        for line in lines:
            draw.text((x, y), line, font=face, fill=fill)
            y += advance
        return y

    y = write(title_lines, margin, margin, font(64), 80)
    y = write(subtitle_lines, margin, y, body, 44, '#ADB5C0')
    draw.rectangle((margin, y + 10, margin + 34, y + 44), outline=ORANGE, width=6)
    write(legend_lines, margin + 50, y + 8, small, 38, '#DDDDDD')
    y += legend_height
    write(note_lines, margin, y, body, 44, '#ADB5C0')
    y = top
    for row in range(rows):
        for col, card in enumerate(cards[row * columns:(row + 1) * columns]):
            shot, headers, lines, pictures, labels, ph, _ = card
            x = margin + col * (card_width + gap)
            color = ORANGE if shot['mode'] == 'first_last' else GRAY
            draw.rounded_rectangle((x, y, x + card_width, y + row_heights[row]), radius=18,
                                   fill='#202126', outline=color, width=8 if shot['mode'] == 'first_last' else 3)
            cy = write(headers, x + pad, y + pad, heading, 52, ORANGE if shot['mode'] == 'first_last' else '#F1F0EC')
            if pictures:
                pw = (inner - gap) // 2 if len(pictures) == 2 else inner
                for i, (_, _, im) in enumerate(pictures):
                    px = x + pad + i * (pw + gap)
                    fitted = ImageOps.contain(im, (pw, ph), method=Image.Resampling.LANCZOS)
                    canvas.paste(fitted, (px + (pw - fitted.width) // 2, cy + (ph - fitted.height) // 2))
                    write(labels[i], px, cy + ph, small, 38, '#B5BAC3')
                cy += ph + max(len(a) for a in labels) * 38
            else:
                draw.text((x + pad, cy + 25), '无参考图输入', font=body, fill='#ADB5C0')
                cy += ph
            cy += pad
            end = write(lines, x + pad, cy, body, 44)
            assert end <= y + row_heights[row] - pad, shot['id']
        y += row_heights[row] + gap
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', help='JSON; image paths are relative to this manifest')
    parser.add_argument('--output', required=True)
    parser.add_argument('--columns', type=int, default=3)
    parser.add_argument('--card-width', type=int, default=1080)
    parser.add_argument('--font', help='Font file supporting the caption language')
    args = parser.parse_args()
    print(render(args.manifest, args.output, args.columns, args.card_width, args.font))
