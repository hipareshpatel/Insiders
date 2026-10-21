"""On/off audit of the results-size rule (Gate 1 for RESULTS, 2026-10-21) over the stored published cards.

Reads every published RESULTS card from the live API, re-scores it from its stored score (pillars and gates) with the
rule off (as stored) and on (scoring._results_size), and lists the cards whose signal flag would change. No AI.
Usage: python scripts/signals_onoff/results_size.py [docs/audit/signals-results-size/onoff.json]
"""
import json
import sys
import urllib.parse
import urllib.request

from bse_intel.scoring import HIGH, _band, _results_size

API = "https://insiders.reply-bd3.workers.dev/api/feed"


def cards():
    cursor = None
    while True:
        q = {"from": "2025-01-01", "category": "RESULTS", "limit": "50", **({"cursor": cursor} if cursor else {})}
        req = urllib.request.Request(f"{API}?{urllib.parse.urlencode(q)}", headers={"User-Agent": "insiders-audit/1"})
        with urllib.request.urlopen(req, timeout=60) as r:
            page = json.load(r)
        yield from page["cards"]
        cursor = page.get("next_cursor")
        if not cursor:
            return


def rescore(card: dict) -> dict | None:
    s = card.get("score") or {}
    pillars, gates = s.get("pillars"), s.get("gates")
    if not pillars or not gates or not any(r.startswith("Size: no stated amount") for r in s.get("reasons", [])):
        return None  # sized by a deal amount, or scored before pillars were stored: the rule does not touch it
    sized = _results_size(card)
    mag = max(pillars["magnitude"], _band(sized[0])) if sized else pillars["magnitude"]
    g1 = bool(sized and sized[0] >= 25)
    raw = sum(pillars.values()) - pillars["magnitude"] + mag
    total = max(0, min(100, min(raw, 35) if s.get("vetoes") else raw))
    actionable = total >= HIGH and gates["clean"] and sum((g1, gates["inflection"], gates["price"])) >= 2
    return {"total": total, "gate1": g1, "actionable": actionable, "size": sized[1] if sized else None}


def main(out: str | None) -> None:
    rows, n, touched = [], 0, 0
    for row in cards():
        n += 1
        card = json.loads(row["card_json"]) if isinstance(row["card_json"], str) else row["card_json"]
        new = rescore(card)
        if new is None:
            continue
        touched += 1
        old = bool(row.get("is_actionable_signal"))
        if new["actionable"] != old or new["gate1"]:
            rows.append({"news_id": row["news_id"], "company": row.get("company_name"), "filed_at": row["filed_at"],
                         "headline": card.get("headline"), "pdf_url": row.get("pdf_url"), "old_score": row.get("actionability_score"),
                         "new_score": new["total"], "old_signal": old, "new_signal": new["actionable"], "size": new["size"],
                         "gates": {**card["score"]["gates"], "magnitude": new["gate1"]}})
    gained = [r for r in rows if r["new_signal"] and not r["old_signal"]]
    lost = [r for r in rows if r["old_signal"] and not r["new_signal"]]
    print(f"published results cards {n}; scored without a deal amount {touched}; Gate 1 opens on {len(rows)}; "
          f"signals gained {len(gained)}, lost {len(lost)}")
    for r in gained:
        print(f"  + {r['filed_at'][:10]} {r['company'][:34]:34} {r['old_score']}->{r['new_score']}  {r['size']}")
    if out:
        json.dump({"cards": n, "touched": touched, "gate1_opens": rows, "gained": gained, "lost": lost},
                  open(out, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
