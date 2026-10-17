"""Every cached announcement's pages: digital, scanned, OCR'd, scanned past the OCR cap, garbled."""
import sys, glob, gzip, json, re, sqlite3, collections
sys.path.insert(0, "src")
from bse_intel import gate
from bse_intel.extract import SCANNED_PAGE_CHARS
from bse_intel.settings import get_settings

_WORD = re.compile(r"^[A-Za-z][a-z]+[.,;:)]?$|^[A-Z]{2,}[.,;:)]?$")
def word_share(text):
    toks = [t for t in text.split() if len(t) >= 3 and any(c.isalpha() for c in t)]
    return (sum(1 for t in toks if _WORD.match(t)) / len(toks)) if len(toks) >= 25 else None

db = [p for p in glob.glob("../data/wrangler/v3/d1/miniflare-D1DatabaseObject/*.sqlite") if "metadata" not in p][0]
etype = dict(sqlite3.connect(db).execute("select news_id, coalesce(event_type, 'UNTYPED') from filings"))
agg = collections.defaultdict(collections.Counter)
shares = []
for p in glob.glob(str(get_settings().text_cache_dir / "*" / "*.json.gz")):
    nid = p.replace("\\", "/").rsplit("/", 1)[-1][:36]
    try:
        d = json.loads(gzip.decompress(open(p, "rb").read()))
    except Exception:
        continue
    digital, img, ocr = d.get("digital") or [], d.get("has_image") or [], d.get("ocr") or {}
    t = etype.get(nid, "UNKNOWN")
    a = agg[t]
    a["filings"] += 1
    any_bad = False
    for i, text in enumerate(digital):
        a["pages"] += 1
        scanned = len(text.strip()) < SCANNED_PAGE_CHARS and (img[i] if i < len(img) else False)
        if scanned:
            a["scanned"] += 1
            any_bad = True
            a["scanned_ocrd" if str(i) in ocr else "scanned_not_read"] += 1
        elif len(text) >= 200:
            ws = word_share(text)
            if ws is not None:
                shares.append(ws)
            if gate.text_is_garbled(text):
                a["garbled_digits"] += 1; any_bad = True
            elif ws is not None and ws < 0.55:
                a["garbled_words"] += 1; any_bad = True
    a["filings_with_a_bad_page"] += any_bad
cols = ("filings", "pages", "scanned", "scanned_ocrd", "scanned_not_read", "garbled_digits", "garbled_words", "filings_with_a_bad_page")
print(f"{'event type':26}" + "".join(f"{c[:14]:>15}" for c in cols))
tot = collections.Counter()
for t, a in sorted(agg.items(), key=lambda kv: -kv[1]["filings"]):
    tot.update(a)
    print(f"{t[:26]:26}" + "".join(f"{a[c]:>15}" for c in cols))
print(f"{'ALL':26}" + "".join(f"{tot[c]:>15}" for c in cols))
shares.sort()
print("\nclean-word share on text pages: p5 %.2f  p10 %.2f  median %.2f" % (shares[len(shares)//20], shares[len(shares)//10], shares[len(shares)//2]))
