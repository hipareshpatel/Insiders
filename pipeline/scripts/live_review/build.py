"""Live review 2026-10-20: a seeded, stratified sample of published live cards, one blind folder per reviewer."""
import json, random, subprocess, sys, urllib.request
from pathlib import Path
sys.path.insert(0, "/home/user/Insiders/pipeline/src")
from bse_intel.dossier import dossier_as_of

SP = Path(sys.argv[1]); OUT = SP / "folders"; OUT.mkdir(exist_ok=True)
SITE = "https://insiders.reply-bd3.workers.dev"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}
def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))

feed = json.load(open(SP.parent / (sys.argv[3] if len(sys.argv) > 3 else "live") / "feed.json"))
plan = {"RESULTS": 4, "M_AND_A": 3, "LITIGATION_REGULATORY": 3, "ORDER_WIN": 3, "CONCALL_PRESENTATION": 2, "DEBT_RATINGS": 2,
        "GOVERNANCE": 1, "MONTHLY_BUSINESS_UPDATE": 1, "FUNDRAISE": 1, "MANAGEMENT_CHANGE": 1, "CAPEX": 1, "PRODUCT_LAUNCH": 1,
        "OTHER": 1}
rng = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 20261020)
sample = []
import os
if os.environ.get("ALL"):   # every card in the feed file (live review 3: the 27 cards production wrote on 20 Oct)
    plan = {}
    sample = sorted((c for c in feed if c.get("pdf_url")), key=lambda c: c["news_id"])
for kind, n in plan.items():
    pool = sorted((c for c in feed if c.get("event_category") == kind and c.get("pdf_url")), key=lambda c: c["news_id"])
    sample += rng.sample(pool, min(n, len(pool)))
rng.shuffle(sample)
DROP = {"model", "pack", "review", "grounding", "promise_updates"}
manifest = []
for i, row in enumerate(sample):
    folder = OUT / f"reviewer_{i // 4 + 1:02d}"; folder.mkdir(exist_ok=True)
    nid = row["news_id"]
    full = get(f"{SITE}/api/cards/{nid}")
    card = json.loads(full["card_json"]) if isinstance(full.get("card_json"), str) else full.get("card_json") or {}
    card = {k: v for k, v in card.items() if k not in DROP}
    card.update({"company": full.get("company_name"), "symbol": full.get("symbol"), "filed_at": full.get("filed_at")})
    (folder / f"{nid}.card.json").write_text(json.dumps(card, indent=1, ensure_ascii=False))
    import time
    for attempt in range(3):   # an empty memory is retried: the first review's 11 of 24 came back empty mid-load
        company = get(f"{SITE}/api/companies/{full['scrip_code']}")
        if company.get("dossier"):
            break
        time.sleep(70)   # past the 60 s edge cache
    memory = dossier_as_of(company.get("dossier") or {}, full["filed_at"], inclusive=False) or {}
    memory["_input"] = "memory as of the filing" if company.get("dossier") else "NO MEMORY ON THE LIVE SITE: do not judge memory points"
    if card.get("scale"):
        memory["scale_block"] = card["scale"]
    (folder / f"{nid}.memory.json").write_text(json.dumps(memory, indent=1, ensure_ascii=False))   # whole: a cut file is no JSON
    pdf = folder / f"{nid}.pdf"
    subprocess.run(["curl", "-s", "--max-time", "90", "-A", UA["User-Agent"], "-o", str(pdf), full["pdf_url"]], check=False)
    manifest.append({"news_id": nid, "folder": folder.name, "event_type": row.get("event_category"), "company": full.get("company_name"),
                     "filed_at": full["filed_at"], "pdf_url": full["pdf_url"], "pdf_bytes": pdf.stat().st_size if pdf.exists() else 0})
    print(i, folder.name, nid, row.get("event_category"), manifest[-1]["pdf_bytes"])
json.dump(manifest, open(SP / "manifest.json", "w"), indent=1)
