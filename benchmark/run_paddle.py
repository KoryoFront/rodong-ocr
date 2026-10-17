import sys, time, numpy as np
from paddleocr import PaddleOCR
from order import to_lines
import os
DEVICE = os.environ.get('OCR_DEVICE', 'cpu')
variants = {
    'paddle_v5mobile': dict(lang='korean', ocr_version='PP-OCRv5'),
    'paddle_v5server_det': dict(text_detection_model_name='PP-OCRv5_server_det', text_recognition_model_name='korean_PP-OCRv5_mobile_rec'),
    'paddle_v3': dict(lang='korean', ocr_version='PP-OCRv3'),
}
for name, kw in variants.items():
    try:
        ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False, enable_mkldnn=False, device=DEVICE, **kw)
    except Exception as e:
        print(name, 'FAILED', e); continue
    for crop in sys.argv[1:]:
        t = time.time()
        r = ocr.predict(crop + '.png')[0]
        items = [(*np.array(b).tolist(), s) for b, s in zip(r['rec_boxes'], r['rec_texts'])]
        open(f'out_{name}_{crop}.txt', 'w', encoding='utf-8').write(to_lines(items))
        print(name, crop, f'{time.time()-t:.1f}s')
