"""How many published cards state an EPS change across a split, bonus or consolidation (F153, TODO 43).

Read-only: pages the public feed (`/api/feed?range=all`, which carries each card's JSON), reads each company's memory once
(`/api/companies/<scrip>`, for `dossier.corporate_actions`; `/api/cards/<id>` only when a card's JSON is missing from the
feed), 0.3-0.5 s between calls. A published results card counts when the EPS change it states (its results table's YoY or
QoQ, a key number, the takeaway or a line naming EPS with a per cent) spans the ex-date of a recorded action with a share
factor. It also lists cards whose implied share count (profit / EPS) moved by an exact split or bonus ratio (within 1%) with no
recorded action ("unrecorded": EPS not comparable and nothing says why).

    cd pipeline && PYTHONPATH=src python scripts/eps_bonus_scan.py [--base URL] [--max-cards N] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request

from bse_intel import eps_adjust

BASE = "https://insiders.reply-bd3.workers.dev"
EPS_PCT = re.compile(r"\b(?:eps|earnings per share)\b[^.;]{0,60}?([+-]?\d+(?:\.\d+)?)\s*%", re.I)


def get(url: str):
    time.sleep(random.uniform(0.3, 0.5))
    req = urllib.request.Request(url, headers={"User-Agent": "insiders-eps-scan/1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def feed(base: str, limit_cards: int | None):
    cursor, seen = None, 0
    while True:
        query = {"range": "all", "limit": 50, **({"cursor": cursor} if cursor else {})}
        page = get(f"{base}/api/feed?{urllib.parse.urlencode(query)}")
        for card in page.get("cards", []):
            yield card
            seen += 1
            if limit_cards and seen >= limit_cards:
                return
        cursor = page.get("next_cursor")
        if not cursor or not page.get("cards"):
            return


def stated_changes(card: dict) -> list[str]:
    """Every place the card states an EPS change, as text."""
    out = []
    results = card.get("results") or {}
    eps = results.get("eps") or {}
    for slot in ("yoy_pct", "qoq_pct"):
        if eps.get(slot) is not None:
            out.append(f"table {slot[:3].upper()} {eps[slot]:+.1f}%")
    for key in card.get("key_numbers") or []:
        if re.search(r"\beps\b", str(key.get("label", "")), re.I) and key.get("change"):
            out.append(f"key number {key['change']}")
    texts = [("takeaway", card.get("takeaway") or "")]
    texts += [("line", (f.get("text") if isinstance(f, dict) else str(f)) or "") for f in card.get("what_happened") or []]
    for where, text in texts:
        for m in EPS_PCT.finditer(text):
            out.append(f"{where} {m[1]}%")
    return out


def check(card_row: dict, card: dict, dossier: dict | None) -> dict | None:
    results = card.get("results") or {}
    eps = results.get("eps") or {}
    period = results.get("period")
    if not period or eps.get("value") is None:
        return None
    pat = results.get("pat") or {}
    spans, unrecorded = [], []
    for slot, label, old_period in (("prev_year", "YoY", results.get("prev_year_period")),
                                    ("prev_quarter", "QoQ", results.get("prev_quarter_period"))):
        old = eps.get(slot)
        if old is None or not old_period:
            continue
        compared = eps_adjust.compare(dossier, period, old_period, eps["value"], old, pat.get("value"), pat.get(slot))
        stated = eps.get(f"{label.lower()}_pct")
        if compared.kind == "adjusted":
            spans.append({"label": label, "old_period": old_period, "stated_pct": stated, "note": compared.note,
                          "adjusted_pct": round((eps["value"] / compared.eps_old - 1) * 100, 1) if compared.eps_old > 0 else None})
        elif compared.kind == "blank":
            unrecorded.append({"label": label, "old_period": old_period, "stated_pct": stated})
    if not spans and not unrecorded:
        return None
    return {"news_id": card_row["news_id"], "company": card_row.get("company_name"), "scrip": card_row.get("scrip_code"),
            "period": period, "spans_recorded_action": spans, "unrecorded_share_jump": unrecorded,
            "stated": stated_changes(card)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--max-cards", type=int)
    ap.add_argument("--json")
    args = ap.parse_args()
    dossiers: dict[str, dict | None] = {}
    total = results = published = 0
    hits, jumps = [], []
    for row in feed(args.base, args.max_cards):
        total += 1
        if total % 500 == 0:
            print(f"... {total} cards read, {len(hits)} hits, {len(dossiers)} companies", file=sys.stderr, flush=True)
        if row.get("event_category") != "RESULTS" or row.get("held"):
            continue
        published += 1
        raw = row.get("card_json")
        card = json.loads(raw) if raw else (get(f"{args.base}/api/cards/{row['news_id']}").get("card") or {})
        if not (card.get("results") or {}).get("eps"):
            continue
        results += 1
        scrip = row["scrip_code"]
        if scrip not in dossiers:
            try:
                dossiers[scrip] = get(f"{args.base}/api/companies/{scrip}").get("dossier") or {}
            except Exception as exc:  # a company page that will not load is counted, not fatal
                print(f"company {scrip}: {exc}", file=sys.stderr)
                dossiers[scrip] = None
        found = check(row, card, dossiers[scrip] if dossiers[scrip] is not None else {})
        if found:
            (hits if found["spans_recorded_action"] else jumps).append(found)
    with_actions = sum(1 for d in dossiers.values() if d and any(a.get("factor") for a in d.get("corporate_actions") or []))
    print(f"cards read: {total}; published results cards: {published}; with an EPS line: {results}; "
          f"companies read: {len(dossiers)} ({with_actions} with a recorded split/bonus/consolidation)")
    print(f"EPS change spans a recorded action: {len(hits)}; share count jumps with no record: {len(jumps)}")
    for h in hits:
        for s in h["spans_recorded_action"]:
            print(f"  {h['company']} {h['news_id']} {h['period']} {s['label']} vs {s['old_period']}: stated {s['stated_pct']}"
                  f" -> adjusted {s['adjusted_pct']} ({s['note']}); also stated: {h['stated']}")
    for j in jumps:
        for s in j["unrecorded_share_jump"]:
            print(f"  [unrecorded] {j['company']} {j['news_id']} {j['period']} {s['label']} vs {s['old_period']}: "
                  f"stated {s['stated_pct']}; also stated: {j['stated']}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"hits": hits, "unrecorded": jumps}, fh, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
