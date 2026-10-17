"""Stage 1: text lines (box, text, score) for each page via PP-OCRv5 server det + Korean rec.
Pages are processed in overlapping full-width strips at native resolution to fit in GPU memory;
a line is kept only from the strip whose core band contains its vertical center."""
import os, sys, json, time
import cv2
import numpy as np
from paddleocr import PaddleOCR
STRIP, OVERLAP = int(os.environ.get('STRIP', 1200)), 300
ocr = PaddleOCR(device=os.environ.get('OCR_DEVICE', 'gpu:0'),
                text_detection_model_name='PP-OCRv5_server_det',
                text_recognition_model_name='korean_PP-OCRv5_mobile_rec',
                use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False,
                enable_mkldnn=False,  # oneDNN CPU backend crashes on Windows in Paddle 3.x
                text_det_limit_type='max', text_det_limit_side_len=5000,
                text_recognition_batch_size=1)
# usage: python ocr_lines.py <stage_dir> page-1.png page-2.png ...
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
for img_path in sys.argv[2:]:
    t = time.time()
    img = cv2.imread(img_path)
    H = img.shape[0]
    lines = []
    for y0 in range(0, H, STRIP):
        top, bot = max(0, y0 - OVERLAP), min(H, y0 + STRIP + OVERLAP)
        r = ocr.predict(img[top:bot])[0]
        for b, p, s, c in zip(r['rec_boxes'], r['rec_polys'], r['rec_texts'], r['rec_scores']):
            b = np.array(b, dtype=float); b[[1, 3]] += top
            p = np.array(p, dtype=float); p[:, 1] += top
            if y0 <= (b[1] + b[3]) / 2 < y0 + STRIP:
                lines.append(dict(box=b.tolist(), poly=p.tolist(), text=s, score=float(c)))
    name = os.path.splitext(os.path.basename(img_path))[0]
    json.dump(lines, open(f'{OUT}/{name}_ocr.json', 'w', encoding='utf-8'), ensure_ascii=False)
    print('ocr', name, len(lines), 'lines', f'{time.time()-t:.1f}s', flush=True)
