"""On/off audit of the reworded-quote rule (2026-10-21) over the held cards of a live export, no AI.

A key number, notable change or "why it matters" whose quote is not the filing's own words now passes when each of its
figures is on a filing line naming it (or in the company's memory, labelled so). This replays the quoted-number check
with that path off (`_scope_lines` returning nothing) and on, against each card's own PDF read by the pipeline's
extractor (text layer; no OCR, no XBRL block, no memory, so it can only under-count what the rule releases).
Usage: python -I scripts/held_onoff/quote_sources.py docs/audit/live/held-<date>.json OUT.json PDF_DIR
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from bse_intel import pipeline as P  # noqa: E402
from bse_intel.extract import Document  # noqa: E402
from bse_intel.grounding import declared_unit  # noqa: E402
from bse_intel.models import Pass2Output  # noqa: E402

QUOTE = re.compile(r"^Give each fact the filing's own sentence as its quote: (key number|notable change|why it matters) "
                   r"\"(.*)\" quotes a sentence that is not in the filing$")
real = P._scope_lines


def run(out, text, on):
    if not on:
        P._scope_lines = lambda *a, **k: ""
    try:
        return P.check_quoted_numbers(out, text, declared_unit(text))
    finally:
        P._scope_lines = real


def pdf_text(url: str, cache: Path) -> str | None:
    path = cache / (re.sub(r"[^A-Za-z0-9_.-]", "_", url.rsplit("/", 1)[-1])[:120])
    if not path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            path.write_bytes(urllib.request.urlopen(req, timeout=90).read())
        except Exception:
            return None
    try:
        return Document(path.read_bytes()).select_text(10_000_000, [])
    except Exception:
        return None


def main(export: str, out_path: str, pdf_dir: str) -> None:
    cache = Path(pdf_dir)
    cache.mkdir(parents=True, exist_ok=True)
    rows, n = [], 0
    for x in json.load(open(export, encoding="utf-8")):
        card = json.loads(x["card_json"]) if isinstance(x["card_json"], str) else x["card_json"]
        review = card.get("review") or {}
        issues = review.get("issues") or []
        quoted = [i for i in issues if QUOTE.match(i)]
        if not quoted or len(quoted) != len(issues) or review.get("held") or not x.get("pdf_url"):
            continue   # held for something else too: this rule alone cannot release it
        text = pdf_text(x["pdf_url"], cache)
        if not text:
            rows.append({"news_id": x["news_id"], "company": x.get("company_name"), "status": "NO_TEXT"})
            continue
        n += 1
        out = Pass2Output.model_validate({"is_material": True, "event_type": card.get("event_type") or "OTHER", "timeline_entry": "x",
                                          "card": {f: card[f] for f in ("impact_level", "headline", "what_happened", "key_numbers",
                                                                        "notable_changes", "why_it_matters") if card.get(f) is not None}})
        off, _, _ = run(out, text, False)
        on, _, notes = run(out, text, True)
        cleared = sorted(set(off) - set(on))
        rows.append({"news_id": x["news_id"], "company": x.get("company_name"), "event_category": x.get("event_category"),
                     "filed_at": x.get("filed_at"), "pdf_url": x["pdf_url"], "headline": card.get("headline"),
                     "problems_off": off, "problems_on": on, "cleared": cleared,
                     "accepted_as": [m for m in notes if "own words" in m or "from company memory" in m],
                     "released": bool(off) and not on, "still_held_in_replay": bool(on),
                     "replay_clean_both": not off})
    released = [r for r in rows if r.get("released")]
    print(json.dumps({"only_quote_held": len(rows), "replayed": n, "no_text": sum(r.get("status") == "NO_TEXT" for r in rows),
                      "released_by_rule": len(released), "still_held": sum(bool(r.get("still_held_in_replay")) for r in rows),
                      "clean_both_ways": sum(bool(r.get("replay_clean_both")) for r in rows)}))
    json.dump(rows, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:4])
