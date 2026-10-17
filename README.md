# rodong-ocr

OCR pipeline that turns a scanned issue of 로동신문 (Rodong Sinmun) into a plain UTF-8 text file with
one block per article (title, subtitle, photo captions, body), plus an optional PDF.

The first processed issue is **2026-10-08 (제281호)**:
[`issues/2026-10-08/Rodong261008_articles.txt`](issues/2026-10-08/Rodong261008_articles.txt): 50 articles from 6 pages.

## Output format

```
로동신문 2026년 10월 8일 (목요일) 제281호 [루계 제29077호]
원본: Rodong261008.pdf · 6면 · 기사 50건

========================================================================
기사 01 · 제1면
[section banner, if any]
Title
Subtitle (zero or more lines)
(사진) photo caption (zero or more lines)
========================================================================

Body paragraph 1

Body paragraph 2
...
```

Every article starts with a line of 72 `=`. Paragraphs are separated by a blank line.

## Accuracy

- **Titles, subtitles, section banners and photo captions** were checked against the page images and
  corrected by hand (they are set in decorative fonts the OCR misreads).
- **Body text is uncorrected OCR output.** On clean body type, about 1 character in 200–300 is
  wrong, usually a near-miss stroke (숭→승, 련→런).
- The Korean recognizer often drops spaces between words. Spaces are restored automatically with
  [Kiwi](https://github.com/bab2min/kiwipiepy), which sometimes over-splits words (중 중 첩첩), so
  the output does not preserve the paper's original spacing exactly.
- There are a few extra paragraph breaks where text wraps around a photo or a vertical title.

## Engine comparison

Five crops (two from page 1, three from page 4, the hardest page) were scored against hand-made
transcriptions. The figures are the share of Korean characters read wrong
([`benchmark/`](benchmark/)):

| Engine | P1 body | P1 headline | P4 body | P4 brush-script headline | P4 vertical headline |
|---|---|---|---|---|---|
| **PaddleOCR PP-OCRv5, Korean** | **0.3%** | **0%** | **0%** | **20%** | **6.7%** |
| PaddleOCR PP-OCRv3, Korean | 0.5% | 0% | 0% | 40% | 93% |
| Tesseract 5 `kor` (best) | 1.1% | 3.6% | 1.3% | 80% | 100% |
| Tesseract 5 `kor` (fast) | 1.9% | 5.4% | 2.1% | 53% | 100% |
| EasyOCR `ko` | 7.1% | 3.6% | 6.8% | 33% | 93% |

No public OCR model trained specifically on North Korean print was found. Standard Hangul OCR
works, because DPRK spelling differences (로동, 력사) are spelling rather than different characters.

## Pipeline

| Stage | Script | What it does |
|---|---|---|
| 0 | `pdftoppm -r 300` | Render the PDF pages to PNG at 300 dpi |
| 1 | `pipeline/ocr_lines.py` | Text lines with PP-OCRv5 server detection + `korean_PP-OCRv5_mobile_rec`. Each page is processed in overlapping full-width strips so it fits in an 8 GB GPU at full resolution |
| 2 | `pipeline/layout.py` | Layout blocks (`PP-DocLayout_plus-L`) and article regions (`PP-DocBlockLayout`) |
| 3 | `pipeline/assemble.py` | Lines → blocks → article regions; reading order by recursive XY-cut over text lines; paragraphs from indentation; ornament and stray-heading filtering |
| 4 | `pipeline/build_output.py` | Applies `curation.json`, restores spacing, writes `.txt` (and `--pdf`) |

`issues/<date>/curation.json` holds the manual, per-issue part of the work:
- corrected titles, subtitles, section banners and captions
- photo regions merged into their articles
- regions to drop (masthead, footer)
- block moves for articles that continue elsewhere on the page
- the article order

Article ids are indexes into `articles_raw.json`, which stage 3 writes.

### Run it

Requirements: Python 3.13, an NVIDIA GPU (CPU also works but is slower), and Poppler (`pdftoppm`).

```bash
# OCR environment (GPU build of PaddlePaddle, CUDA 12.6)
python -m venv .venv-ocr
.venv-ocr/Scripts/pip install paddlepaddle-gpu -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
.venv-ocr/Scripts/pip install -r requirements-ocr.txt

# build environment
python -m venv .venv-build
.venv-build/Scripts/pip install -r requirements-build.txt

I=issues/2026-10-08
pdftoppm -r 300 -png $I/Rodong261008.pdf pages/p
.venv-ocr/Scripts/python pipeline/ocr_lines.py $I/stage pages/p-*.png
.venv-ocr/Scripts/python pipeline/layout.py    $I/stage pages/p-*.png
.venv-build/Scripts/python pipeline/assemble.py $I/stage $I/curation.json $I/articles_raw.json
.venv-build/Scripts/python pipeline/build_output.py $I/articles_raw.json $I/curation.json \
    $I/Rodong261008_articles.txt --pdf $I/Rodong261008_articles.pdf
```

The scripts use the GPU by default; set `OCR_DEVICE=cpu` to run without one. `ocr_lines.py` turns off
PaddlePaddle's oneDNN CPU backend, which crashes on Windows in this version.

Stage 1 and 2 outputs for 2026-10-08 are committed in `issues/2026-10-08/stage/`, so stages 3–4 can
be rerun without a GPU. A new issue needs its own `curation.json`: run stage 3, check the regions
it prints against the page images, then fill in the corrections.

The PDF uses Malgun Gothic by default. On other systems, set `KOREAN_FONT_DIR`, `KOREAN_FONT` and
`KOREAN_FONT_BOLD` to any Korean TTF.
