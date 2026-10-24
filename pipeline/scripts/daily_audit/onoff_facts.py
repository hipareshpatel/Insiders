"""RESULTS_FACTS on/off over stored results cards (no AI): what code would add to each card, and whether the EBITDA rule
keeps a change the old rule removed.

Each card's XBRL figures are rebuilt from the company's memory (the results files' own figures, `xbrl:res:` rows), its
filing PDF is read with PyMuPDF, and facts.py runs as the pipeline would. The output goes to independent reviewers,
who check every added line against the PDF.

    python -I onoff_facts.py <results.json> <out_dir> [--n 25] [--seed 24]
results.json: a list of feed cards (/api/feed?category=RESULTS pages)."""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from bse_intel import computed  # noqa: E402
from bse_intel.facts import block, capex_revisions, guidance_facts, results_facts  # noqa: E402
from bse_intel.models import BalanceSheet, FinancialMetric  # noqa: E402
from bse_intel.periods import prior_quarter_period, prior_year_period  # noqa: E402
from bse_intel.xbrl import PERCENT, XbrlResult  # noqa: E402

API = "https://insiders.reply-bd3.workers.dev/api"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"


def fetch(url: str, dest: pathlib.Path | None = None) -> bytes:
    cmd = ["curl", "-s", "-L", "-A", UA, "-H", "Referer: https://www.nseindia.com/", url]
    data = subprocess.check_output(cmd, timeout=120)
    if dest:
        dest.write_bytes(data)
    return data


def periods_of(period: str) -> set[str]:
    out = {period, prior_year_period(period) or "", prior_quarter_period(period) or ""}
    q, fy = period[:2], period[2:]
    to_date = {"Q2": "H1", "Q3": "9M", "Q4": ""}.get(q)
    if to_date is not None:
        out |= {f"{to_date}{fy}", f"{to_date}{prior_year_period(fy) or ''}"}
    return out - {""}


def tagged_from_memory(dossier: dict, period: str, basis: str | None) -> XbrlResult:
    wanted = periods_of(period)
    metrics = [FinancialMetric(metric=m["metric"], period=m["period"], value=m["value"],
                               unit="PCT" if m["metric"] in PERCENT else m.get("unit") or "INR_CR")
               for m in dossier.get("financial_metrics", [])
               if m.get("period") in wanted and m.get("value") is not None
               and str(m.get("source_news_id") or "").startswith("xbrl:res")
               and (not basis or not m.get("basis") or m["basis"] == basis)]
    snap = next((b for b in reversed(dossier.get("balance_sheet", [])) if b.get("period") == period), None)
    sheet = BalanceSheet(**{k: v for k, v in snap.items() if k in BalanceSheet.model_fields}) if snap else None
    # the pipeline has the file's template; from memory, a lender is told by its industry
    kind = (dossier.get("industry") or "").lower()
    template = "NBFC" if any(w in kind for w in ("> banks", "> finance", "insurance")) else ""
    return XbrlResult(kind="RESULTS", basis=basis, period=period, metrics=metrics, balance_sheet=sheet, template=template)


def ebitda_kept(tagged: XbrlResult, text: str) -> tuple[bool, bool, float | None]:
    """(old rule keeps the YoY change, new rule keeps it, the change)."""
    val = {(m.metric, m.period): m.value for m in tagged.metrics}
    now, then = val.get(("ebitda", tagged.period)), val.get(("ebitda", prior_year_period(tagged.period) or ""))
    if now is None or not then or then <= 0 or now < 0:
        return False, False, None
    change = round((now - then) / then * 100, 1)
    sign = 1 if change > 0 else -1
    new = computed.build_pool(text, tagged).has("pct", abs(change), 1, sign)
    saved, computed._DERIVED = computed._DERIVED, set()
    try:
        old = computed.build_pool(text, tagged).has("pct", abs(change), 1, sign)
    finally:
        computed._DERIVED = saved
    return old, new, change


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cards")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=25)
    ap.add_argument("--seed", type=int, default=24)
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cards = json.load(open(args.cards, encoding="utf-8"))
    random.Random(args.seed).shuffle(cards)
    ext = pathlib.Path(__file__).with_name("ext.py")
    rows, dossiers = [], {}
    for card in cards:
        if len(rows) >= args.n:
            break
        cj = json.loads(card["card_json"]) if isinstance(card["card_json"], str) else card["card_json"]
        period = (cj.get("results") or {}).get("period")
        if not period or not card.get("pdf_url"):
            continue
        scrip = card["scrip_code"]
        if scrip not in dossiers:
            dossiers[scrip] = json.loads(fetch(f"{API}/companies/{scrip}"))["dossier"]
        dossier = dossiers[scrip]
        tagged = tagged_from_memory(dossier, period, cj.get("basis"))
        if not any(m.period == period for m in tagged.metrics):
            continue
        folder = out / card["news_id"]
        folder.mkdir(exist_ok=True)
        pdf = folder / "filing.pdf"
        if not pdf.exists():
            fetch(card["pdf_url"], pdf)
        text = subprocess.run([sys.executable, "-I", str(ext), str(pdf)], capture_output=True, text=True).stdout
        if len(text) < 200:
            continue
        before = {k: [x for x in dossier.get(k, []) if (x.get("as_of") or x.get("given_on") or "") < card["filed_at"]]
                  for k in ("balance_sheet", "guidance", "deals")}
        facts = (results_facts(tagged, text, [b for b in before["balance_sheet"] if b.get("period") != period])
                 + guidance_facts(tagged, before["guidance"]) + capex_revisions(before["deals"], card["filed_at"]))
        old, new, change = ebitda_kept(tagged, text)
        rows.append({"news_id": card["news_id"], "symbol": card["symbol"], "scrip_code": scrip, "period": period,
                     "basis": cj.get("basis"), "pdf_url": card["pdf_url"], "headline": card["headline"],
                     "added_lines": [f.text for f in facts if f.text], "memory_refs": [f.memory_ref for f in facts if f.memory_ref],
                     "ebitda_yoy": change, "ebitda_old_rule_keeps": old, "ebitda_new_rule_keeps": new})
        (folder / "block.txt").write_text(block(facts), encoding="utf-8")
        print(card["symbol"], period, len([f for f in facts if f.text]), "lines; EBITDA", change, old, "->", new, flush=True)
    (out / "onoff.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
