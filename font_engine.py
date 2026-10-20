"""Build a static TrueType font from two outline sources. No system changes."""
import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont, TTCollection
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools import subset
from fontTools.merge import Merger
from fontTools.ttLib.scaleUpem import ScalerVisitor


def native_merge(fonts, selected, ratio, progress):
    """Disjoint Unicode subsets prevent merger's automatic locl overrides."""
    upm = fonts[0]['head'].unitsPerEm
    with tempfile.TemporaryDirectory(prefix='bilingual-') as directory:
        paths = []
        for index, font in enumerate(fonts):
            progress('原生合并：处理%s字符与排版表…' % ('中文' if index == 0 else '英文'))
            # System UI is horizontal. A vertical table in only one source
            # cannot be merged with missing metrics from the other source.
            for tag in ('vhea', 'vmtx', 'VORG', 'STAT', 'DSIG'):
                if tag in font:
                    del font[tag]
            options = subset.Options()
            options.hinting = index == 0
            options.notdef_glyph = True
            options.notdef_outline = True
            options.layout_features = ['*']
            options.name_IDs = ['*']
            subsetter = subset.Subsetter(options=options)
            subsetter.populate(unicodes=[cp for cp, item in selected.items() if item[0] == index])
            subsetter.subset(font)
            if index == 1:
                factor = upm / font['head'].unitsPerEm * ratio
                ScalerVisitor(factor).visit(font)
                font['head'].unitsPerEm = upm
            path = str(Path(directory) / ('source%d.ttf' % index))
            font.save(path)
            paths.append(path)
        merged = Merger().merge(paths)
    if len(merged.getGlyphOrder()) > 65535:
        raise ValueError('合成字形数超过 TTF 上限。')
    if set(merged.getBestCmap()) != set(selected):
        raise ValueError('原生合并后的字符映射校验失败。')
    # Conservative Windows line metrics, including layout-only accent glyphs.
    merged['glyf'].compile(merged)
    top = max(getattr(g, 'yMax', 0) for g in merged['glyf'].glyphs.values())
    bottom = min(getattr(g, 'yMin', 0) for g in merged['glyf'].glyphs.values())
    ascender = max(top, merged['hhea'].ascent)
    descender = min(bottom, merged['hhea'].descent)
    merged['hhea'].ascent, merged['hhea'].descent = ascender, descender
    merged['hhea'].lineGap = 0
    for attr, value in [('sTypoAscender', ascender), ('sTypoDescender', descender), ('sTypoLineGap', 0), ('usWinAscent', ascender), ('usWinDescent', -descender)]:
        setattr(merged['OS/2'], attr, value)
    return merged


def faces(path):
    with open(path, 'rb') as stream:
        collection = stream.read(4) == b'ttcf'
    if collection:
        fonts = TTCollection(path, lazy=True)
        try:
            return [font['name'].getDebugName(4) or 'Face %d' % i for i, font in enumerate(fonts.fonts)]
        finally:
            fonts.close()
    with TTFont(path, lazy=True) as font:
        return [font['name'].getDebugName(4) or Path(path).stem]


def latin(cp):
    # ASCII letters, digits and punctuation, Latin accents and extended Latin.
    return (0x20 <= cp <= 0x024F or 0x1E00 <= cp <= 0x1EFF or
            0x2C60 <= cp <= 0x2C7F or 0xA720 <= cp <= 0xA7FF or
            0xAB30 <= cp <= 0xAB6F)


def open_font(path, index):
    font = TTFont(path, fontNumber=int(index), recalcTimestamp=False)
    if 'fvar' in font:
        axes = {axis.axisTag: axis.defaultValue for axis in font['fvar'].axes}
        font = instantiateVariableFont(font, axes, inplace=True)
    if not ('glyf' in font or 'CFF ' in font or 'CFF2' in font):
        font.close()
        raise ValueError('仅支持包含矢量轮廓的 TTF / OTF / TTC 字体。')
    return font


def build(config, destination, progress=lambda text: None):
    name = config['name'].strip()
    if not name or len(name.encode('utf-16-le')) // 2 > 31 or any(ord(c) < 32 for c in name):
        raise ValueError('字体名称需要 1–31 个字符（普通中英文），且不能有换行。')
    sizes = [float(config['cn_size']), float(config['en_size'])]
    if any(not math.isfinite(v) or not 6 <= v <= 72 for v in sizes):
        raise ValueError('中英文字号需在 6–72 pt 之间。')
    ratio = sizes[1] / sizes[0]
    if not 0.5 <= ratio <= 2:
        raise ValueError('英文字号应为中文字号的 0.5–2 倍，以避免系统文字裁切。')
    destination = Path(destination).resolve()
    paths = [Path(config[k]).resolve() for k in ('cn_path', 'en_path')]
    if destination in paths:
        raise ValueError('输出文件不能覆盖源字体。')
    if destination.exists():
        raise ValueError('输出文件已经存在，请更换名称，避免覆盖已安装字体。')
    fonts = []
    try:
        for key, path in zip(('cn', 'en'), paths):
            progress('读取%s字体…' % ('中文' if key == 'cn' else '英文'))
            fonts.append(open_font(path, config.get(key + '_index', 0)))
        maps = [font.getBestCmap() or {} for font in fonts]
        if not any(0x3400 <= cp <= 0x9FFF or 0x20000 <= cp <= 0x323AF for cp in maps[0]):
            raise ValueError('中文字体中没有汉字，请选择包含中文的字体文件。')
        missing = [c for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789' if ord(c) not in maps[1]]
        if missing:
            raise ValueError('英文字体缺少基本英文字母或数字：' + ''.join(missing))
        selected = {}
        for cp in sorted(set(maps[0]) | set(maps[1])):
            if cp < 32 or 0xD800 <= cp <= 0xDFFF or cp > 0x10FFFF:
                continue
            source = 1 if latin(cp) and cp in maps[1] else (0 if cp in maps[0] else 1)
            selected[cp] = (source, maps[source][cp])
        use_native = all('glyf' in font for font in fonts) and config.get('mode') != 'outline'
        if use_native:
            merged = native_merge(fonts, selected, ratio, progress)
            builder = FontBuilder(font=merged)
            ascender, descender = merged['hhea'].ascent, merged['hhea'].descent
        else:
            keys = [(0, '.notdef')] + list(dict.fromkeys(selected.values()))
            if len(keys) > 65535:
                raise ValueError('合成字形数超过 TTF 的 65535 上限，请选择较小的源字体。')
            names = {key: ('.notdef' if i == 0 else 'g%d' % i) for i, key in enumerate(keys)}
            glyphs, metrics = {}, {}
            sets = [font.getGlyphSet() for font in fonts]
            upm = 2048
            scales = [upm / fonts[0]['head'].unitsPerEm, upm / fonts[1]['head'].unitsPerEm * ratio]
            top, bottom = 0, 0
            for i, key in enumerate(keys):
                source, old_name = key
                scale = scales[source]
                pen = TTGlyphPen(None)
                recording = DecomposingRecordingPen(sets[source])
                sets[source][old_name].draw(recording)
                # Expand components before transforming; convert cubic OTF outlines.
                recording.replay(TransformPen(Cu2QuPen(pen, 0.8, reverse_direction='glyf' not in fonts[source]), (scale, 0, 0, scale, 0, 0)))
                glyph = pen.glyph()
                glyph.recalcBounds(None)
                glyph_name = names[key]
                glyphs[glyph_name] = glyph
                advance = round(fonts[source]['hmtx'][old_name][0] * scale)
                lsb = getattr(glyph, 'xMin', 0)
                if not 0 <= advance <= 65535 or any(abs(getattr(glyph, attr, 0)) > 32767 for attr in ('xMin', 'xMax', 'yMin', 'yMax')):
                    raise ValueError('缩放后的字形超出 TTF 坐标范围，请减小字号比例。')
                metrics[glyph_name] = (advance, lsb)
                top = max(top, getattr(glyph, 'yMax', 0))
                bottom = min(bottom, getattr(glyph, 'yMin', 0))
                if i % 1000 == 0:
                    progress('合成字形 %d / %d…' % (i, len(keys)))
            # Accommodate accents and full-height CJK glyphs without clipping.
            ascender = max(top, round(fonts[0]['hhea'].ascent * scales[0]))
            descender = min(bottom, round(fonts[0]['hhea'].descent * scales[0]))
            builder = FontBuilder(upm, isTTF=True)
            builder.setupGlyphOrder(list(names.values()))
            builder.setupCharacterMap({cp: names[key] for cp, key in selected.items()})
            builder.setupGlyf(glyphs)
            builder.setupHorizontalMetrics(metrics)
            builder.setupHorizontalHeader(ascent=ascender, descent=descender, lineGap=0)
        digest = hashlib.sha256((name + json.dumps(config, sort_keys=True)).encode()).hexdigest()[:10]
        ps_name = re.sub('[^A-Za-z0-9-]', '', name)[:35] or 'BilingualFont'
        notices = []
        for source, font in enumerate(fonts):
            for name_id in (0, 13, 14):
                value = font['name'].getDebugName(name_id)
                if value:
                    notices.append('%s: %s' % ('Chinese source' if source == 0 else 'Latin source', value))
        builder.setupNameTable({
            'familyName': name, 'styleName': 'Regular', 'uniqueFontIdentifier': name + '-' + digest,
            'fullName': name, 'psName': ps_name + '-' + digest, 'version': 'Version 1.000',
            'copyright': '\n'.join(notices),
            'description': 'Personal bilingual composite. Chinese baseline %.1f pt; Latin %.1f pt. Original source licenses apply.' % tuple(sizes),
            'licenseDescription': '\n'.join(notices),
        })
        if use_native:
            builder.font['OS/2'].usWeightClass = 400
            builder.font['OS/2'].fsSelection = 0x40
            builder.font['head'].macStyle = 0
        else:
            builder.setupOS2(sTypoAscender=ascender, sTypoDescender=descender, sTypoLineGap=0,
                             usWinAscent=ascender, usWinDescent=-descender,
                             usWeightClass=400, fsSelection=0x40,
                             fsType=fonts[0]['OS/2'].fsType | fonts[1]['OS/2'].fsType)
            builder.setupPost()
            builder.setupMaxp()
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(suffix='.ttf', dir=str(destination.parent))
        os.close(fd)
        try:
            builder.save(temp)
            with TTFont(temp, checkChecksums=2) as check:
                assert len(check.getBestCmap()) == len(selected)
                assert check['maxp'].numGlyphs == len(builder.font.getGlyphOrder())
            os.rename(temp, destination)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        report = dict(config, output=str(destination), characters=len(selected), glyphs=len(builder.font.getGlyphOrder()), method='FontTools native merge' if use_native else 'FontTools outline rebuild',
                      english_ratio=ratio, recommended_noMeiryoUI_pt=sizes[0],
                      limitations=('原生合并：保留中文 hinting 和受支持的布局表，英文缩放后移除 hinting。' if use_native else '轮廓兼容：不保留 hinting、kerning、GSUB/GPOS。') + '静态 Regular；可变字体取默认轴值。')
        try:
            destination.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError:
            pass
        progress('字体已生成')
        return report
    finally:
        for font in fonts:
            font.close()
