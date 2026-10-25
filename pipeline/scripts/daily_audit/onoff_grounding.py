"""On/off over stored cards (no AI): the figures the narrowed memory-grounding rule (grounding.MEMORY_GROUNDED) newly
leaves ungrounded. Each card is re-checked with its filing's PyMuPDF text (plus its results file's figures where the card
names one) and its memory view as of the filing date: memory as a plain source (off), memory for memory lines only (on).
The scale block is left out of both, so only memory's part differs. Cards whose PDF gives no text are counted, not checked.

    python -I onoff_grounding.py <cards.json> <pdf_dir> <out.json> [--workers 8]"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from bse_intel import xbrl  # noqa: E402
from bse_intel.dossier import view_as_of  # noqa: E402
from bse_intel.grounding import check_card  # noqa: E402
from bse_intel.models import Card  # noqa: E402

API = "https://insiders.reply-bd3.workers.dev/api"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
EXT = pathlib.Path(__file__).with_name("ext.py")


def fetch(url: str, dest: pathlib.Path) -> None:
    if not dest.exists() or dest.stat().st_size < 500:
        subprocess.run(["curl", "-s", "-L", "-A", UA, "-H", "Referer: https://www.nseindia.com/", "-o", str(dest), url],
                       timeout=180)


def filing_text(card: dict, cj: dict, pdf_dir: pathlib.Path) -> str:
    folder = pdf_dir / card["news_id"]
    folder.mkdir(parents=True, exist_ok=True)
    pdf = folder / "filing.pdf"
    fetch(card["pdf_url"], pdf)
    text = subprocess.run([sys.executable, "-I", str(EXT), str(pdf)], capture_output=True, text=True).stdout or ""
    url = (cj.get("xbrl") or {}).get("url")
    if url:   # production puts the results file's figures ahead of the PDF text
        fetch(url, folder / "file.xml")
        try:
            parsed = xbrl.parse((folder / "file.xml").read_bytes())
            if parsed:
                text = " ".join(f"{m.metric} {m.period} {m.value}" for m in parsed.metrics) + "\n" + text
        except Exception:  # noqa: BLE001 - a file that does not parse adds nothing
            pass
    return text


def one(card: dict, memories: dict, pdf_dir: pathlib.Path) -> dict | None:
    cj = card["card_json"]
    cj = json.loads(cj) if isinstance(cj, str) else cj
    if not cj or not card.get("pdf_url"):
        return None
    try:
        model = Card.model_validate({k: cj[k] for k in Card.model_fields if k in cj})
    except Exception:  # noqa: BLE001
        return {"news_id": card["news_id"], "skipped": "card does not validate"}
    text = filing_text(card, cj, pdf_dir)
    if len(text) < 200:
        return {"news_id": card["news_id"], "skipped": "no text layer"}
    view = view_as_of(memories.get(card["scrip_code"]), card["filed_at"])
    memory = json.dumps(view or {}, ensure_ascii=False)
    off = check_card(model, text, card.get("headline") or "", memory)
    on = check_card(model, text, card.get("headline") or "", memory=memory)
    new = [f for f in on.ungrounded if f not in off.ungrounded or on.ungrounded.count(f) > off.ungrounded.count(f)]
    return {"news_id": card["news_id"], "symbol": card["symbol"], "event": card["event_category"], "pdf_url": card["pdf_url"],
            "scrip_code": card["scrip_code"], "filed_at": card["filed_at"], "newly_ungrounded": sorted(set(new)),
            "headline_newly": sorted(set(on.headline_ungrounded) - set(off.headline_ungrounded)),
            "texts": {"headline": cj.get("headline"), "takeaway": cj.get("takeaway"),
                      "what_happened": [f.get("text") if isinstance(f, dict) else f for f in cj.get("what_happened") or []],
                      "key_numbers": cj.get("key_numbers")} if new else None}


def main() -> None:
    args = sys.argv[1:]
    workers = int(args[args.index("--workers") + 1]) if "--workers" in args else 8
    every = json.load(open(args[0], encoding="utf-8"))
    cards = [c for c in every if c.get("scrip_code") and c.get("pdf_url")]   # a feed row with neither cannot be checked
    pdf_dir = pathlib.Path(args[1])
    memories: dict = {}
    for scrip in sorted({c["scrip_code"] for c in cards}):
        try:
            memories[scrip] = json.loads(subprocess.check_output(["curl", "-s", f"{API}/companies/{scrip}"], timeout=120))["dossier"]
        except Exception:  # noqa: BLE001
            memories[scrip] = None
    with ThreadPoolExecutor(workers) as pool:
        rows = [r for r in pool.map(lambda c: one(c, memories, pdf_dir), cards) if r]
    checked = [r for r in rows if "skipped" not in r]
    hit = [r for r in checked if r["newly_ungrounded"]]
    json.dump({"cards": len(every), "without_company_or_pdf": len(every) - len(cards), "checked": len(checked), "skipped": len(rows) - len(checked),
               "cards_with_new": len(hit), "rows": hit}, open(args[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("cards", len(cards), "checked", len(checked), "skipped", len(rows) - len(checked), "cards with newly ungrounded", len(hit),
          "figures", sum(len(r["newly_ungrounded"]) for r in hit))


if __name__ == "__main__":
    main()
