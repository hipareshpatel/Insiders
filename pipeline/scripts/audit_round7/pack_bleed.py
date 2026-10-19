"""Audit round 7: did a fact from one filing in a Gemini pack end up on another filing's card? (PLAN §3, owner 2026-10-19)

  python -I -X utf8 scripts/audit_round7/pack_bleed.py [--out ../docs/audit/round-7-pack-bleed.json]

For every card written in a pack (card_json["pack"] = {"id", "members"}), each figure, name and date on the card that is
not in its own filing's text but is in the text of another filing of the same pack is listed. Figures are matched as
the grounding code matches them (any unit); names are runs of two or more capitalised words; dates are as filings write
them. A listed fact is a candidate, not a verdict: the blind reviewers decide (label "fact from another filing").
Pass mark (set before the run): 0 bled facts on published cards.
"""
from __future__ import annotations

import argparse
import collections
import glob
import gzip
import json
import pathlib
import re
import sqlite3
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from bse_intel.extract import Document  # noqa: E402
from bse_intel.grounding import SourceIndex, _tokens  # noqa: E402

SPEC = json.loads((HERE / "companies.json").read_text())
SCRIPS = [c["scrip_code"] for c in SPEC["companies"]]
ROOT = HERE.parents[2]
NAME = re.compile(r"\b(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:of|and|&|for)?\s*(?:[A-Z][a-z]+|[A-Z]{2,}))+")
DATE = re.compile(r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*,?\s+\d{4}\b", re.I)
SKIP_NAMES = {"Limited", "Ltd", "India", "Board", "Company", "Exchange", "National Stock Exchange", "BSE Limited"}


def text_of(news_id: str) -> str:
    safe = "".join(ch for ch in news_id if ch.isalnum() or ch in "-_")[:80]
    path = ROOT / "data" / "text_cache" / safe[:2] / f"{safe}.json.gz"
    if not path.exists():
        return ""
    return Document.from_cache(json.loads(gzip.decompress(path.read_bytes()))).select_text(10_000_000, [])


def card_text(card: dict) -> str:
    parts = [card.get("headline") or "", card.get("takeaway") or "", card.get("timeline_entry") or ""]
    parts += [f.get("text", "") if isinstance(f, dict) else str(f) for f in card.get("what_happened") or []]
    parts += [w.get("text", "") for w in card.get("why_it_matters") or []]
    parts += [f"{k.get('label', '')} {k.get('value', '')} {k.get('change') or ''}" for k in card.get("key_numbers") or []]
    deal = card.get("deal_value") or {}
    parts += [str(deal.get("counterparty") or "")]
    return " ".join(parts)


def facts(text: str) -> dict[str, list]:
    figures = sorted({(v, d) for v, d, _, _, _ in _tokens(text) if v >= 100})
    names = sorted({n.strip() for n in NAME.findall(text) if n.strip() not in SKIP_NAMES and len(n) > 5})
    dates = sorted({d for d in DATE.findall(text)})
    return {"figures": figures, "names": names, "dates": dates}


def present(kind: str, fact, text: str, index: SourceIndex) -> bool:
    if kind == "figures":
        value, decimals = fact
        return index.stated(value, decimals)
    return fact.lower() in text.lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "audit" / "round-7-pack-bleed.json"))
    args = ap.parse_args()
    db = [p for p in glob.glob(str(ROOT / "data/wrangler/v3/d1/miniflare-D1DatabaseObject/*.sqlite")) if "metadata" not in p][0]
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    marks = ",".join("?" * len(SCRIPS))
    rows = list(conn.execute(f"select news_id, held, card_json from cards where scrip_code in ({marks})", SCRIPS))
    texts: dict[str, str] = {}
    packs = collections.defaultdict(list)
    report = []
    for news_id, held, raw in rows:
        body = json.loads(raw)
        pack = body.get("pack") or {}
        if not pack.get("members"):
            continue
        packs[pack["id"]].append(news_id)
        own = texts.setdefault(news_id, text_of(news_id))
        own_index = SourceIndex(own)
        others = {m: texts.setdefault(m, text_of(m)) for m in pack["members"] if m != news_id}
        bled = []
        for kind, items in facts(card_text(body)).items():
            for fact in items:
                if present(kind, fact, own, own_index):
                    continue
                hits = [m for m, t in others.items() if t and present(kind, fact, t, SourceIndex(t))]
                if hits:
                    bled.append({"kind": kind, "fact": fact if kind != "figures" else fact[0], "in": hits})
        report.append({"news_id": news_id, "pack": pack["id"], "members": len(pack["members"]), "published": not held,
                       "candidates": bled})
    published = [r for r in report if r["published"] and r["candidates"]]
    summary = {"packed_cards": len(report), "packs": len(packs),
               "cards_with_candidates": sum(1 for r in report if r["candidates"]),
               "published_cards_with_candidates": len(published),
               "candidate_facts": sum(len(r["candidates"]) for r in report)}
    pathlib.Path(args.out).write_text(json.dumps({"summary": summary, "cards": report}, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    print(json.dumps(summary))
    for r in published:
        print(r["news_id"], r["pack"], [c["fact"] for c in r["candidates"]][:8])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
