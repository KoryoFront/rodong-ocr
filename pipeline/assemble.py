"""Stage 3: combine OCR lines, layout blocks and article regions into articles (title, subtitles, paragraphs, captions)."""
import json, os, re, sys
import numpy as np

TITLE, SUB, CAPTION, TEXT = 'doc_title', 'paragraph_title', 'figure_title', 'text'
DROP = {'header', 'footer', 'number', 'header_image', 'footer_image', 'image', 'chart', 'seal'}

def area(b):
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])

def inter(a, b):
    return area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])

def center(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)

def contains(b, pt):
    return b[0] <= pt[0] <= b[2] and b[1] <= pt[1] <= b[3]

def gap(a, b):
    dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return np.hypot(dx, dy)

def is_junk(line):
    """Ornamental borders/rules and photo texture that the recognizer reads as runs of symbols, zeros
    or ones (e.g. a ++++ border read as 111114111). Real text without Hangul (dates, page numbers)
    is read with high confidence and no long repeats."""
    t = line['text'].strip()
    if re.search(r'[∞×$]', t) or re.search(r'[0oO8X]{6,}', t) or set(t) <= set('…·.-—_~ |'):
        return True
    no_hangul = not any('가' <= ch <= '힣' for ch in t)
    return no_hangul and (line['score'] < 0.7 or bool(re.search(r'(.)\1{3,}', t)))

def is_vertical(b):
    return (b[3] - b[1]) > 2.5 * (b[2] - b[0])

def split_on_gap(blocks, axis):
    """Split blocks where the projection on `axis` (0 = x, 1 = y) has a gap; None if no gap."""
    lo, hi = axis, axis + 2
    items = sorted(blocks, key=lambda b: b['box'][lo])
    groups, reach = [[items[0]]], items[0]['box'][hi]
    for b in items[1:]:
        if b['box'][lo] > reach - 5:      # small tolerance for touching boxes
            groups.append([b])
        else:
            groups[-1].append(b)
        reach = max(reach, b['box'][hi])
    return groups if len(groups) > 1 else None

def column_order(items, col_w=None):
    """Recursive XY-cut over text lines: split at vertical gaps (columns, left-to-right) first. If a line
    wider than a column (subtitle etc.) blocks that, cut into horizontal bands at the wide lines;
    otherwise split at horizontal gaps. Recurse into each part."""
    if len(items) <= 1:
        return list(items)
    if col_w is None:
        widths = sorted(b['box'][2] - b['box'][0] for b in items)
        col_w = widths[int(len(widths) * 0.75)]
    groups = split_on_gap(items, 0)
    if groups:
        return [b for g in groups for b in column_order(g, col_w)]
    wide = sorted([b for b in items if b['box'][2] - b['box'][0] > 1.6 * col_w], key=lambda b: b['box'][1])
    if wide and len(wide) < len(items):
        out, top, rest = [], float('-inf'), [b for b in items if b not in wide]
        for w in wide + [None]:
            cut = center(w['box'])[1] if w else float('inf')
            out += column_order([b for b in rest if top <= center(b['box'])[1] < cut], col_w)
            if w:
                out.append(w); top = cut
        return out
    groups = split_on_gap(items, 1)
    if groups:
        return [b for g in groups for b in column_order(g, col_w)]
    return sorted(items, key=lambda b: (b['box'][1], b['box'][0]))

def group_rows(lines):
    """Cluster word/line boxes into visual rows (by vertical-center overlap), each row ordered left-to-right."""
    rows = []
    for ln in sorted(lines, key=lambda l: (l['box'][1] + l['box'][3]) / 2):
        b = ln['box']; cy, h = (b[1] + b[3]) / 2, b[3] - b[1]
        if rows and abs(cy - rows[-1]['cy']) < 0.5 * min(h, rows[-1]['h']):
            rows[-1]['items'].append(ln)
        else:
            rows.append(dict(cy=cy, h=h, items=[ln]))
    out = []
    for r in rows:
        items = sorted(r['items'], key=lambda l: l['box'][0])
        out.append(dict(text=' '.join(l['text'].strip() for l in items),
                        box=[min(l['box'][0] for l in items), min(l['box'][1] for l in items),
                             max(l['box'][2] for l in items), max(l['box'][3] for l in items)]))
    return out

def stray_heading_piece(ln, lines):
    """1-3 letters floating mid-column: a fragment of a letter-spaced subtitle, never real body text."""
    b = ln['box']
    if len(re.sub(r'\s', '', ln['text'])) > 3:
        return False
    col = sorted(o['box'][0] for o in lines if xoverlap(o['box'], b) > 0.5)
    return b[0] - col[len(col) // 10] > 0.6 * (b[3] - b[1])

def paragraphs(lines):
    """Lines in reading order -> paragraphs. A line indented relative to its neighbours above/below in
    the same column starts a new paragraph (lines wrapped around a photo or vertical title are all
    shifted together, so they don't count); wrapped lines are joined without a space."""
    paras, cur = [], ''
    for i, ln in enumerate(lines):
        b = ln['box']; h = b[3] - b[1]
        near = [lines[j]['box'] for j in (i - 1, i + 1) if 0 <= j < len(lines)
                and xoverlap(lines[j]['box'], b) > 0.3 and abs(lines[j]['box'][1] - b[1]) < 2.5 * h]
        if near:
            ref = min(o[0] for o in near)
        else:
            col = sorted(o['box'][0] for o in lines if xoverlap(o['box'], b) > 0.5)
            ref = col[len(col) // 10]
        if cur and b[0] - ref > 0.6 * h:
            paras.append(cur); cur = ''
        cur += ln['text'].strip()
    if cur:
        paras.append(cur)
    return paras

def xoverlap(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) / max(1, min(a[2] - a[0], b[2] - b[0]))

def join_lines(lines, block_box):
    """Lines in reading order -> paragraphs; an indented line starts a new paragraph. Wrapped lines join without a space."""
    paras, cur = [], ''
    for ln in lines:
        b = ln['box']; h = b[3] - b[1]
        indented = b[0] - block_box[0] > 0.6 * h
        if cur and indented:
            paras.append(cur); cur = ''
        cur += ln['text'].strip()
    if cur:
        paras.append(cur)
    return paras

def merge_overlapping(blocks):
    """The layout model sometimes emits two boxes for one paragraph; union same-label boxes that mostly overlap."""
    out = []
    for b in sorted(blocks, key=lambda b: -area(b['box'])):
        for o in out:
            if o['label'] == b['label'] and inter(o['box'], b['box']) > 0.5 * min(area(o['box']), area(b['box'])):
                o['box'] = [min(o['box'][0], b['box'][0]), min(o['box'][1], b['box'][1]),
                            max(o['box'][2], b['box'][2]), max(o['box'][3], b['box'][3])]
                break
        else:
            out.append(dict(b))
    return out

def page_articles(stage, name, overrides):
    lines = [l for l in json.load(open(f'{stage}/{name}_ocr.json', encoding='utf-8')) if not is_junk(l)]
    blocks = merge_overlapping(json.load(open(f'{stage}/{name}_layout.json', encoding='utf-8')))
    regions = [r['box'] for r in json.load(open(f'{stage}/{name}_region.json', encoding='utf-8'))]
    regions += overrides.get('add_regions', [])

    # line -> layout block with the largest overlap
    for b in blocks:
        b['lines'] = []
    loose = []
    for ln in lines:
        best = max(blocks, key=lambda b: inter(b['box'], ln['box']), default=None)
        if best is not None and inter(best['box'], ln['box']) > 0.5 * area(ln['box']):
            best['lines'].append(ln)
        else:
            loose.append(ln)
    # stray lines become their own text blocks so nothing is lost
    for ln in loose:
        blocks.append(dict(label=TEXT, box=ln['box'], lines=[ln], loose=True))

    # block -> region containing its center (else nearest region)
    arts = [dict(region=r, blocks=[]) for r in regions]
    for b in blocks:
        if b['label'] in DROP or not b['lines']:
            continue
        c = center(b['box'])
        forced = [m['region'] for m in overrides.get('move', []) if contains(m['box'], c)]
        if forced:
            arts[forced[0]]['blocks'].append(b); continue
        inside = [a for a in arts if contains(a['region'], c)]
        tgt = min(inside, key=lambda a: area(a['region'])) if inside else min(arts, key=lambda a: gap(a['region'], b['box']))
        tgt['blocks'].append(b)

    out = []
    for a in arts:
        bl = a['blocks']
        titles = sorted([b for b in bl if b['label'] == TITLE], key=lambda b: (b['box'][1], b['box'][0]))
        subs = sorted([b for b in bl if b['label'] == SUB], key=lambda b: (b['box'][1], b['box'][0]))
        caps = [b for b in bl if b['label'] == CAPTION]
        cand = [l for b in bl if b['label'] not in (TITLE, SUB, CAPTION) for l in b['lines']]
        hs = sorted(l['box'][3] - l['box'][1] for l in cand) or [0]
        body_h = hs[len(hs) // 2]
        # headline-size or vertical type inside the article area is title material, not body text
        body = [l for l in cand if not is_vertical(l['box']) and l['box'][3] - l['box'][1] < 1.6 * body_h]
        body = column_order([l for l in body if not stray_heading_piece(l, body)])
        def text_of(b):
            if all(is_vertical(l['box']) for l in b['lines']):
                return ' '.join(l['text'].strip() for l in sorted(b['lines'], key=lambda l: (l['box'][0], l['box'][1])))
            return ' / '.join(r['text'] for r in group_rows(b['lines']))
        paras = paragraphs(body)
        out.append(dict(page=int(name.split('-')[1]), region=[int(v) for v in a['region']],
                        title=[text_of(b) for b in titles], subtitles=[text_of(b) for b in subs],
                        captions=[text_of(b) for b in caps], paragraphs=paras,
                        has_image=any(inter(x['box'], a['region']) > 0.5 * area(x['box']) for x in json.load(open(f'{stage}/{name}_layout.json')) if x['label'] == 'image')))
    return out

if __name__ == '__main__':
    # usage: python assemble.py <stage_dir> <curation.json> <articles_raw.json>
    stage, curation, out = sys.argv[1:4]
    overrides = json.load(open(curation, encoding='utf-8'))['page_overrides']
    pages = sorted(int(m.group(1)) for f in os.listdir(stage) if (m := re.match(r'p-(\d+)_ocr\.json$', f)))
    allart = []
    for p in pages:
        allart += page_articles(stage, f'p-{p}', overrides.get(str(p), {}))
    json.dump(allart, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for i, a in enumerate(allart):
        print(f"[{i}] p{a['page']} {a['region']} T={a['title']} paras={len(a['paragraphs'])}")
