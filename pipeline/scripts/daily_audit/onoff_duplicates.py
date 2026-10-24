"""F110 on/off: same-company card pairs within 3 days whose PDFs duplicates.match() calls repeats (no AI).
Run: python -I onoff_duplicates.py <workdir>  (from any directory; downloads PDFs into <workdir>/pdf)."""
import json, subprocess, os, sys, hashlib
from concurrent.futures import ThreadPoolExecutor
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'src'))
from bse_intel.extract import Document
from bse_intel import duplicates
WORK = sys.argv[1]  # a scratch directory holding pairs.json: [[first_id, first_pdf_url, second_id, second_pdf_url, symbol], ...]
pairs = json.load(open(os.path.join(WORK, 'pairs.json')))
urls = sorted({p[1] for p in pairs} | {p[3] for p in pairs})
D = os.path.join(WORK, 'pdf'); os.makedirs(D, exist_ok=True)
def path(u): return os.path.join(D, hashlib.md5(u.encode()).hexdigest() + '.pdf')
def get(u):
    p = path(u)
    if os.path.exists(p) and os.path.getsize(p) > 1000: return
    subprocess.run(['curl', '-s', '-L', '--max-time', '90', '--max-filesize', '40000000', '-A', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36',
                    '-H', 'Referer: https://www.nseindia.com/', '-o', p, u])
with ThreadPoolExecutor(8) as ex: list(ex.map(get, urls))
bodies = {}
def body(u):
    if u in bodies: return bodies[u]
    p = path(u); b = None
    try:
        data = open(p, 'rb').read()
        if data[:4] == b'%PDF':
            d = Document(data); b = duplicates.body(d.select_text(duplicates.CHARS, figures=False)); d.close()
    except Exception as e: print('ERR', u, e, flush=True)
    bodies[u] = b; return b
out = []; unread = 0
for a, ua, b, ub, sym in pairs:
    x, y = body(ua), body(ub)
    if x is None or y is None: unread += 1; continue
    k = duplicates.match(y, x)
    if k: out.append({'symbol': sym, 'first': a, 'second': b, 'kind': k, 'first_url': ua, 'second_url': ub})
json.dump({'pairs': len(pairs), 'unread': unread, 'matches': out}, open(os.path.join(WORK, 'result.json'), 'w'), indent=1)
print('pairs', len(pairs), 'unread', unread, 'matches', len(out))
