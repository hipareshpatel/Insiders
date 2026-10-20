"""Regression check of the quote rules (F87-F90): run as  python -I -X utf8 scripts/audit_quote_rules.py OUT.json

Regression check of F87-F89's quote rules on every stored card, no AI: the quoted-number check with the three new
paths on and off, and every claim the new paths accept that the old check refused."""
import glob, gzip, json, random, sqlite3, sys
sys.path.insert(0, r"D:\Insiders\pipeline\src")
from bse_intel import gate, pipeline as P
from bse_intel.extract import Document
from bse_intel.grounding import declared_unit
from bse_intel.models import Pass2Output

db = [p for p in glob.glob(r"D:\Insiders\data\wrangler\v3\d1\miniflare-D1DatabaseObject\*.sqlite") if "metadata" not in p][0]
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
real = (P._table_line_quoted, P._row_quoted, gate.quote_scattered)

def run(out, text, new):
    if not new:
        P._table_line_quoted = lambda *a, **k: None
        P._row_quoted = lambda *a, **k: None
        gate.quote_scattered = lambda *a, **k: None
    try:
        return P.check_quoted_numbers(out, text, declared_unit(text))[0]
    finally:
        P._table_line_quoted, P._row_quoted, gate.quote_scattered = real

accepted, cards_changed, cards = [], 0, 0
for nid, scrip, held, cj in con.execute("select news_id, scrip_code, held, card_json from cards"):
    k = json.loads(cj)
    safe = "".join(ch for ch in nid if ch.isalnum() or ch in "-_")[:80]
    path = rf"D:\Insiders\data\text_cache\{safe[:2]}\{safe}.json.gz"
    try:
        text = Document.from_cache(json.loads(gzip.decompress(open(path, "rb").read()))).select_text(10_000_000, [])
        out = Pass2Output.model_validate({"is_material": True, "event_type": k.get("event_type") or "OTHER", "timeline_entry": "x",
                                          "card": {f: k[f] for f in ("impact_level", "headline", "what_happened", "key_numbers",
                                                                     "notable_changes", "why_it_matters") if k.get(f) is not None}})
    except Exception:
        continue
    cards += 1
    old, new = set(run(out, text, False)), set(run(out, text, True))
    gone = sorted(old - new)
    if gone:
        cards_changed += 1
        for g in gone:
            accepted.append({"news_id": nid, "scrip": scrip, "held": held, "event_type": k.get("event_type"), "problem_cleared": g})
    if new - old:
        print("NEW PROBLEM (should not happen):", nid, sorted(new - old)[:2])
json.dump(accepted, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({"cards_checked": cards, "cards_with_a_problem_cleared": cards_changed, "problems_cleared": len(accepted)}))
