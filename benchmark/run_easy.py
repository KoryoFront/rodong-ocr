import os, sys, time, easyocr
from order import to_lines
reader = easyocr.Reader(['ko'], gpu=os.environ.get('OCR_DEVICE','cpu')!='cpu')
for crop in sys.argv[1:]:
    t = time.time()
    res = reader.readtext(crop + '.png')
    items = [(min(p[0] for p in b), min(p[1] for p in b), max(p[0] for p in b), max(p[1] for p in b), s) for b, s, _ in res]
    open(f'out_easyocr_{crop}.txt', 'w', encoding='utf-8').write(to_lines(items))
    print('easyocr', crop, f'{time.time()-t:.1f}s')
