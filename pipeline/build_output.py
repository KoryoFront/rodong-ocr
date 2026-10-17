"""Stage 4: apply the issue's manual curation, restore word spacing (Kiwi) and write the articles
as a plain UTF-8 text file (one block per article), plus optionally a PDF.

usage: python build_output.py <articles_raw.json> <curation.json> <out.txt> [--pdf out.pdf] [--json out.json]
"""
import argparse, json, os, re, difflib
from kiwipiepy import Kiwi

ap = argparse.ArgumentParser()
ap.add_argument('articles_raw')
ap.add_argument('curation')
ap.add_argument('txt')
ap.add_argument('--pdf')
ap.add_argument('--json', help='also dump the final article list as JSON')
args = ap.parse_args()

arts = json.load(open(args.articles_raw, encoding='utf-8'))
cur = json.load(open(args.curation, encoding='utf-8'))
issue = cur['issue']
kiwi = Kiwi()
DPRK_INITIAL = set('련로력리량녀령론래례류륙락란람랑렬렴뢰룡루륜률륭름릉린림립료롱록뇨뉴닉')


def squash(s):
    return re.sub(r'[\s/]', '', s)


def hangul_count(s):
    return sum('\uac00' <= ch <= '\ud7a3' for ch in s)


def respace(s):
    s = re.sub(r'\s*/\s*', ' ', s).strip()
    s = s.replace('«', '《').replace('»', '》')
    s = re.sub(r'(\d)\s*(뚫|됐|몫|돐)', lambda m: m.group(1) + '돐', s)   # recurring misread of 돐 (anniversary)
    if not s:
        return s
    spaced = kiwi.space(s, reset_whitespace=False)
    # Kiwi is trained on South Korean text and splits DPRK initial-ㄹ/ㄴ spellings (련 합, 로 동, 력 사):
    # undo a space Kiwi inserted right after a lone syllable from that set.
    out, i = [], 0
    for ch in spaced:
        if i < len(s) and ch == s[i]:
            out.append(ch); i += 1
        elif ch == ' ' and len(out) >= 1 and out[-1] in DPRK_INITIAL and (len(out) == 1 or out[-2] == ' '):
            continue
        else:
            out.append(ch)
    spaced = ''.join(out)
    # bylines: "본사 기자 정경 철" -> "본사기자 정경철"
    return re.sub(r'(본사\s?기자|특파\s?기자|로[동농]\s?통신원|작업\s?반장)\s*((?:[가-힣]\s?){2,3})(\s*)$',
                  lambda m: re.sub(r'\s', '', m.group(1)) + ' ' + re.sub(r'\s', '', m.group(2)), spaced)


# merges: photo regions folded into their article
for src, dst in cur['merge'].items():
    a, b = arts[int(src)], arts[dst]
    extra = ' '.join(a['paragraphs'])
    b['captions'] += a['captions'] + ([extra] if hangul_count(extra) > 8 else [])

items = []
for idx in cur['order']:
    a, fix = arts[idx], cur['articles'].get(str(idx), {})
    title = fix.get('title') or ' '.join(a['title']) or '(제목 없음)'
    subs = fix.get('subtitle', [])
    section = fix.get('section', '')
    captions = fix.get('captions') or a['captions']
    paras = a['paragraphs']
    if idx in cur.get('photo_only', []):
        captions = captions or [' '.join(paras)]
        paras = []
    heads = [squash(h) for h in [title, section] + subs + a['title'] + a['subtitles'] if h]

    def is_heading_dup(k, p):
        """Stray heading text the OCR put into the body: tiny fragments anywhere, heading copies only
        near the top (a quote in the body may legitimately repeat the headline)."""
        q = squash(p)
        if hangul_count(q) <= 2:
            return True
        return k < 3 and any(q in h or difflib.SequenceMatcher(None, q, h).ratio() > 0.9 for h in heads)

    paras = [p for k, p in enumerate(paras) if not is_heading_dup(k, p)]
    items.append(dict(idx=idx, page=a['page'], section=section, title=title, subs=subs,
                      captions=[respace(c) for c in captions if hangul_count(c) > 3],
                      paras=[respace(p) for p in paras]))

if args.json:
    json.dump(items, open(args.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

NOTE = ('본문은 PaddleOCR PP-OCRv5 (한국어 인식 모델 + PP-OCRv5 서버 검출 모델)로 인식하였고, PP-DocLayout_plus-L / '
        'PP-DocBlockLayout으로 기사 영역을 나눈 뒤 단 순서대로 재구성하였다. 띄여쓰기는 인식 모델이 자주 빠뜨려 Kiwi 형태소 '
        '분석기로 자동 복원하였다 (일부 오류 가능). 제목·부제목·사진설명은 원본 지면을 직접 확인하여 교정하였고, 본문은 교정하지 '
        '않은 OCR 결과이다.')

# ---------- plain text ----------
RULE = '=' * 72
with open(args.txt, 'w', encoding='utf-8', newline='\n') as f:
    f.write(f"{issue['paper']} {issue['date']} {issue['number']}\n")
    f.write(f"원본: {issue['source']} · {issue['pages']}면 · 기사 {len(items)}건\n")
    f.write(NOTE + '\n')
    for n, it in enumerate(items, 1):
        f.write(f'\n{RULE}\n')
        f.write(f"기사 {n:02d} · 제{it['page']}면\n")
        if it['section']:
            f.write(f"[{it['section']}]\n")
        f.write(it['title'] + '\n')
        for s in it['subs']:
            f.write(s + '\n')
        for c in it['captions']:
            f.write(f'(사진) {c}\n')
        f.write(f'{RULE}\n\n')
        f.write('\n\n'.join(it['paras']) + ('\n' if it['paras'] else ''))
print('wrote', args.txt, len(items), 'articles', sum(len(it['paras']) for it in items), 'paragraphs')

# ---------- PDF (optional) ----------
if args.pdf:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepTogether, HRFlowable
    from xml.sax.saxutils import escape

    # any Korean TTF works; defaults to Windows' Malgun Gothic
    font_dir = os.environ.get('KOREAN_FONT_DIR', 'C:/Windows/Fonts')
    pdfmetrics.registerFont(TTFont('Kor', os.path.join(font_dir, os.environ.get('KOREAN_FONT', 'malgun.ttf'))))
    pdfmetrics.registerFont(TTFont('KorBd', os.path.join(font_dir, os.environ.get('KOREAN_FONT_BOLD', 'malgunbd.ttf'))))
    INK, MUTED, ACCENT = '#1a1a1a', '#6b6b6b', '#a3201c'
    st = {
        'cover_t': ParagraphStyle('ct', fontName='KorBd', fontSize=34, leading=44, alignment=TA_CENTER, textColor=ACCENT),
        'cover_s': ParagraphStyle('cs', fontName='Kor', fontSize=13, leading=20, alignment=TA_CENTER, textColor=INK),
        'note': ParagraphStyle('n', fontName='Kor', fontSize=8.5, leading=13, textColor=MUTED),
        'toc_h': ParagraphStyle('th', fontName='KorBd', fontSize=11, leading=16, textColor=ACCENT, spaceBefore=8, spaceAfter=2),
        'toc': ParagraphStyle('t', fontName='Kor', fontSize=9.5, leading=14, leftIndent=8, textColor=INK),
        'meta': ParagraphStyle('m', fontName='Kor', fontSize=8.5, leading=12, textColor=MUTED, spaceAfter=2),
        'section': ParagraphStyle('s', fontName='KorBd', fontSize=9.5, leading=13, textColor=ACCENT, spaceAfter=2),
        'title': ParagraphStyle('ti', fontName='KorBd', fontSize=17, leading=24, textColor=INK, spaceAfter=3),
        'sub': ParagraphStyle('su', fontName='KorBd', fontSize=11, leading=16, textColor='#3a3a3a', spaceAfter=3),
        'cap': ParagraphStyle('ca', fontName='Kor', fontSize=9, leading=13, textColor=MUTED, leftIndent=8, spaceAfter=3),
        'body': ParagraphStyle('b', fontName='Kor', fontSize=10.5, leading=17, firstLineIndent=10.5, spaceAfter=4, textColor=INK),
    }

    def P(text, style, anchor=None):
        t = escape(text)
        if anchor:
            t = f'<a name="{anchor}"/>' + t
        return Paragraph(t, st[style])

    def on_page(c, doc):
        c.saveState()
        c.setFont('Kor', 8)
        c.setFillColor(MUTED)
        c.drawString(18 * mm, 12 * mm, f"{issue['paper']} {issue['date']} — OCR 기사 모음")
        c.drawRightString(A4[0] - 18 * mm, 12 * mm, str(doc.page))
        c.restoreState()

    story = [Spacer(1, 50 * mm), P(issue['paper'], 'cover_t'), Spacer(1, 4 * mm),
             P(f"{issue['date']} · {issue['number']}", 'cover_s'),
             P(f"기사 {len(items)}건 · {issue['pages']}면", 'cover_s'), Spacer(1, 30 * mm),
             P(f"원본: {issue['source']}. " + NOTE, 'note'),
             PageBreak(), P('차례', 'title')]
    for pg in sorted({it['page'] for it in items}):
        story.append(P(f'제{pg}면', 'toc_h'))
        for i, it in enumerate(items):
            if it['page'] == pg:
                label = (it['section'] + ' — ' if it['section'] else '') + it['title']
                if it['title'].startswith('경애하는 김정은동지께') and it['subs']:
                    label += ' ' + it['subs'][0]
                story.append(Paragraph(f'<a href="#a{i}" color="{INK}">{escape(label)}</a>', st['toc']))
    story.append(PageBreak())

    for i, it in enumerate(items):
        head = [P(f'제{it["page"]}면', 'meta', anchor=f'a{i}')]
        if it['section']:
            head.append(P(it['section'], 'section'))
        head.append(P(it['title'], 'title'))
        head += [P(s, 'sub') for s in it['subs']]
        head += [P('사진 — ' + c, 'cap') for c in it['captions']]
        head.append(HRFlowable(width='100%', thickness=0.6, color='#cccccc', spaceBefore=3, spaceAfter=6))
        body = [P(p, 'body') for p in it['paras']]
        story.append(KeepTogether(head + body[:1]))
        story += body[1:]
        story.append(Spacer(1, 10 * mm))

    doc = SimpleDocTemplate(args.pdf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                            bottomMargin=20 * mm, title=f"{issue['paper']} {issue['date']} 기사 (OCR)",
                            author='OCR: PaddleOCR PP-OCRv5')
    doc.build(story, onFirstPage=lambda c, d: None, onLaterPages=on_page)
    print('wrote', args.pdf)
