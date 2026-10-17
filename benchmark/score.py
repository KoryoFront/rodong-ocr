import sys, unicodedata, re
def norm(s, hangul_only=False):
    s = unicodedata.normalize('NFKC', s)
    s = re.sub(r'\s+', '', s)
    if hangul_only: s = re.sub(r'[^\uac00-\ud7a3]', '', s)
    return s
def lev(a, b):
    prev = list(range(len(b)+1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j]+1, cur[j-1]+1, prev[j-1]+(ca != cb)))
        prev = cur
    return prev[-1]
gt, hyp = open(sys.argv[1], encoding='utf-8').read(), open(sys.argv[2], encoding='utf-8').read()
for h in (False, True):
    g, p = norm(gt, h), norm(hyp, h)
    print(f"{'hangul' if h else 'all   '} CER {lev(g,p)/len(g)*100:5.1f}%  (gt {len(g)} chars, out {len(p)})")
import difflib
g, p = norm(gt, True), norm(hyp, True)
for op, a1, a2, b1, b2 in difflib.SequenceMatcher(None, g, p, autojunk=False).get_opcodes():
    if op != 'equal': print(f"   {op}: key[{g[max(0,a1-3):a2+3]}] -> out[{p[max(0,b1-3):b2+3]}]")
