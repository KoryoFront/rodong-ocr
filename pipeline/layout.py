"""Stage 2: layout blocks (PP-DocLayout_plus-L) and article regions (PP-DocBlockLayout) for each page."""
import os, sys, json, time
from paddleocr import LayoutDetection
dev = os.environ.get('OCR_DEVICE', 'gpu:0')
models = {'layout': LayoutDetection(model_name='PP-DocLayout_plus-L', device=dev),
          'region': LayoutDetection(model_name='PP-DocBlockLayout', device=dev)}
# usage: python layout.py <stage_dir> page-1.png page-2.png ...
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
for img in sys.argv[2:]:
    name = os.path.splitext(os.path.basename(img))[0]
    for kind, m in models.items():
        t = time.time()
        r = m.predict(img, layout_nms=True)[0]
        boxes = [dict(label=b['label'], score=float(b['score']), box=[float(v) for v in b['coordinate']]) for b in r['boxes']]
        json.dump(boxes, open(f'{OUT}/{name}_{kind}.json', 'w', encoding='utf-8'), ensure_ascii=False)
        r.save_to_img(f'{OUT}/{name}_{kind}.png')
        print(kind, name, len(boxes), 'boxes', f'{time.time()-t:.1f}s', flush=True)
