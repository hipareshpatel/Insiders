"""On/off audit of CARD_EBITDA_PROFIT_V2 (F151) over stored results cards. No AI calls, nothing written to the site.

For each stored RESULTS card the card's code blocks are rendered twice with the same inputs, the switch off and on:
  * the results table (`dossier.results_snapshot`, the block `refresh-card-blocks` rebuilds), from the company's memory
    and the filing's text; and
  * the card's face (headline, takeaway, facts, key numbers) as `results_card.build` writes it, from the company's
    memory rebuilt as the XBRL file's figures (as daily_audit/onoff_facts.py does) and the filing's text.
It writes what changed (cards, lines added, lines removed, where a printed EBITDA was found, which profit line is
chosen) and a blind-review sample in the format of the existing blind reviews (a seeded shuffle, the two renderings
as X and Y, the key kept in a separate file).

    python -I -X utf8 scripts/audit_card_v2.py OUT_DIR --cards feed_cards.json [--texts TEXT_DIR] [--download]
    python -I -X utf8 scripts/audit_card_v2.py OUT_DIR --api [--limit 200] [--texts TEXT_DIR] [--download]
    options: --seed 151  --sample 20  --site https://insiders.reply-bd3.workers.dev

--cards: a JSON list of feed cards (each with news_id, scrip_code, symbol, filed_at, pdf_url, card_json), or an object
with a "cards" list: an export of /api/feed?category=RESULTS pages. --api reads those pages and each company's memory
(/api/companies/<scrip>) through the platform API. --texts: a folder of <news_id>.txt, the filing's text (what
`pipeline.filed_text` gives); with --download a missing one is fetched from the card's PDF and read with PyMuPDF
(daily_audit/ext.py). A card with no text is rendered without a printed EBITDA or headline (ours alone, labelled
calculated; the shareholders' profit), which is what the switch gives a refresh with no text.

Output: diff.json (every card), diff.md (the summary the release check reads), blind_sample.json and blind_key.json.
The reviewers' prompt is docs/audit/REVIEWER_PROMPT_CARD_V2.md."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import subprocess
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "src"))
sys.path.insert(0, str(HERE / "daily_audit"))
from bse_intel import results_card  # noqa: E402
from bse_intel.dossier import dossier_as_of, results_snapshot  # noqa: E402
from bse_intel.models import Card, Pass2Output  # noqa: E402
from onoff_facts import fetch, tagged_from_memory  # noqa: E402  (daily_audit/onoff_facts.py)

SITE = "https://insiders.reply-bd3.workers.dev"
SWITCH = "CARD_EBITDA_PROFIT_V2"


def get(url: str):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60))


def feed_cards(site: str, limit: int) -> list[dict]:
    out, page = [], 1
    while len(out) < limit:
        d = get(f"{site}/api/feed?range=all&category=RESULTS&limit=50&page={page}")
        out += d["cards"]
        if page >= (d.get("pages") or 1):
            break
        page += 1
    return out[:limit]


def table_lines(snap: dict | None) -> list[str]:
    """The results table as the reader sees it: one line per row, with its label, note and figures."""
    if not snap:
        return []
    out = []
    for spec in snap.get("lines") or []:
        row = snap.get(spec["key"])
        if not isinstance(row, dict):
            continue
        parts = [f"{k} {row[k]}" for k in ("value", "prev_year", "yoy_pct", "yoy_bps", "yoy_turn", "prev_quarter", "qoq_pct",
                                           "qoq_bps", "qoq_turn") if k in row]
        out.append(f"TABLE {spec['label']}" + (f" [{spec['note']}]" if spec.get("note") else "") + ": " + ", ".join(parts))
    return out


def face_lines(out: Pass2Output) -> list[str]:
    card = out.card
    lines = [f"HEADLINE {card.headline}", f"TAKEAWAY {card.takeaway}"]
    lines += [f"FACT {f.text}" for f in card.what_happened]
    lines += [f"KEY {k.label}: {k.value}" + (f" ({k.change})" if k.change else "") for k in card.key_numbers]
    return lines


def render(card: dict, dossier: dict, row: dict, text: str | None, period: str | None, on: bool) -> list[str]:
    before = os.environ.get(SWITCH)
    os.environ[SWITCH] = "1" if on else "0"
    try:
        return _render(card, dossier, row, text, period, on)
    finally:
        if before is None:
            os.environ.pop(SWITCH, None)
        else:
            os.environ[SWITCH] = before


def _render(card: dict, dossier: dict, row: dict, text: str | None, period: str | None, on: bool) -> list[str]:
    current = dossier_as_of(dossier, row["filed_at"])
    snap = results_snapshot(current, row["news_id"], (), printed=text, like=None if text else card.get("results"))
    lines = table_lines(snap)
    tagged = tagged_from_memory(dossier, period, card.get("basis")) if period else None
    if tagged is not None and any(m.period == period for m in tagged.metrics):
        out = Pass2Output.model_validate({"is_material": True, "event_type": card.get("event_type") or "RESULTS",
                                          "timeline_entry": card.get("timeline_entry") or "",
                                          "card": {k: card[k] for k in Card.model_fields if k in card}})
        built = results_card.build(out, tagged, row.get("company_name") or row.get("symbol"), text=text or "", v2=on)
        if built:
            lines += face_lines(out)
    return lines


def filing_text(row: dict, texts: pathlib.Path | None, download: bool) -> str | None:
    if texts is not None:
        path = texts / f"{row['news_id']}.txt"
        if path.exists():
            return path.read_text(encoding="utf-8")
    if download and row.get("pdf_url"):
        folder = (texts or pathlib.Path(".")) / "pdf"
        folder.mkdir(parents=True, exist_ok=True)
        pdf = folder / f"{row['news_id']}.pdf"
        if not pdf.exists():
            fetch(row["pdf_url"], pdf)
        text = subprocess.run([sys.executable, "-I", str(HERE / "daily_audit" / "ext.py"), str(pdf)],
                              capture_output=True, text=True).stdout
        if len(text) > 200:
            if texts is not None:
                (texts / f"{row['news_id']}.txt").write_text(text, encoding="utf-8")
            return text
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--cards")
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--texts")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--seed", type=int, default=151)
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--site", default=SITE)
    args = ap.parse_args()
    if bool(args.cards) == bool(args.api):
        ap.error("give --cards FILE or --api")
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    texts = pathlib.Path(args.texts) if args.texts else None
    if texts:
        texts.mkdir(parents=True, exist_ok=True)
    if args.api:
        rows = feed_cards(args.site, args.limit)
    else:
        loaded = json.load(open(args.cards, encoding="utf-8"))
        rows = loaded["cards"] if isinstance(loaded, dict) else loaded
    dossiers: dict[str, dict] = {}
    report, skipped = [], {"not a results card": 0, "no results block": 0, "no memory": 0}
    for row in rows:
        raw = row.get("card_json")
        card = json.loads(raw) if isinstance(raw, str) else raw or row
        if (card.get("event_type") or row.get("event_type")) != "RESULTS":
            skipped["not a results card"] += 1
            continue
        period = (card.get("results") or {}).get("period")
        if not period:
            skipped["no results block"] += 1
            continue
        scrip = str(row["scrip_code"])
        if scrip not in dossiers:
            dossiers[scrip] = (get(f"{args.site}/api/companies/{scrip}") or {}).get("dossier") or {}
        if not dossiers[scrip]:
            skipped["no memory"] += 1
            continue
        text = filing_text(row, texts, args.download)
        try:
            off = render(card, dossiers[scrip], row, text, period, False)
            on = render(card, dossiers[scrip], row, text, period, True)
        except Exception as exc:  # a card the render cannot read is reported, not hidden
            report.append({"news_id": row["news_id"], "symbol": row.get("symbol"), "error": f"{type(exc).__name__}: {exc}"})
            continue
        added = [x for x in on if x not in off]
        removed = [x for x in off if x not in on]
        report.append({"news_id": row["news_id"], "symbol": row.get("symbol"), "scrip_code": scrip, "period": period,
                       "pdf_url": row.get("pdf_url"), "has_text": text is not None, "changed": bool(added or removed),
                       "printed_ebitda": any("(Filing)" in x for x in on),
                       "calculated_only": any("(calculated)" in x for x in on) and not any("(Filing)" in x for x in on),
                       "profit_label": next((x.split(":")[0].replace("TABLE ", "") for x in on if x.startswith("TABLE ")
                                             and ("PAT" in x or "profit" in x.lower()) and "EBITDA" not in x), None),
                       "added": added, "removed": removed, "off": off, "on": on})
    done = [r for r in report if "error" not in r]
    changed = [r for r in done if r["changed"]]
    (out / "diff.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    summary = [
        f"# CARD_EBITDA_PROFIT_V2 on/off, {len(done)} results cards rendered",
        "",
        f"- cards changed: {len(changed)} of {len(done)}",
        f"- lines added: {sum(len(r['added']) for r in changed)}; lines removed: {sum(len(r['removed']) for r in changed)}",
        f"- cards where the company's printed EBITDA was found (shown first, labelled Filing): "
        f"{sum(r['printed_ebitda'] for r in done)}",
        f"- cards with ours alone, labelled calculated: {sum(r['calculated_only'] for r in done)}",
        f"- cards with the filing's text: {sum(r['has_text'] for r in done)}; without (no printed EBITDA or headline "
        f"profit can be found): {sum(not r['has_text'] for r in done)}",
        f"- render errors: {len(report) - len(done)}; skipped: {json.dumps(skipped)}",
        "",
        "## Changed cards",
    ]
    for r in changed:
        summary += [f"### {r['symbol']} {r['period']} ({r['news_id']})", *(f"- removed: {x}" for x in r["removed"]),
                    *(f"- added: {x}" for x in r["added"]), ""]
    (out / "diff.md").write_text("\n".join(summary), encoding="utf-8")
    # the blind sample: changed cards with their text, in a seeded shuffle; X and Y are the two renderings in a seeded
    # order, the key (which is on) kept in its own file until the verdicts are in
    pool = sorted((r for r in changed if r["has_text"]), key=lambda r: r["news_id"])
    rng = random.Random(args.seed)
    rng.shuffle(pool)
    sample, key = [], {}
    for i, r in enumerate(pool[:args.sample], 1):
        on_is_x = rng.random() < 0.5
        sample.append({"id": f"c{i:02d}", "news_id": r["news_id"], "symbol": r["symbol"], "scrip_code": r["scrip_code"],
                       "period": r["period"], "pdf_url": r["pdf_url"],
                       "X": r["on"] if on_is_x else r["off"], "Y": r["off"] if on_is_x else r["on"]})
        key[f"c{i:02d}"] = {"news_id": r["news_id"], "on_is": "X" if on_is_x else "Y"}
    (out / "blind_sample.json").write_text(json.dumps(sample, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "blind_key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    print(json.dumps({"rendered": len(done), "changed": len(changed), "sample": len(sample),
                      "printed_ebitda": sum(r["printed_ebitda"] for r in done), "errors": len(report) - len(done)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
