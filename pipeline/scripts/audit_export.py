"""Export cards and their filing text for an independent card-vs-PDF audit (docs/AUDIT_LOOP.md).

Usage:
  npx wrangler d1 execute insiders --local --persist-to ../data/wrangler --json --command \
    "SELECT c.news_id, c.scrip_code, f.headline headline_filing, f.subject, c.card_json FROM cards c JOIN filings f USING(news_id) ..." > cards.json
  python scripts/audit_export.py cards.json OUT_DIR [--per-reviewer 10] [--limit 100] [--skip audited_ids.txt]

The query must select scrip_code and filed_at too: the round is spread across companies (at least MIN_COMPANIES of
them, newest cards first) instead of taking whichever cards come first.

Writes OUT_DIR/reviewer_NN/<news_id>.card.json and <news_id>.pdf.txt (the same cached text the pipeline read, not a
re-download). Reviewers write findings.json beside them; scripts/audit_tally.py summarises. Run with `python -I -X utf8`.
"""
import argparse
import collections
import gzip
import json
import pathlib
import sys

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from bse_intel.extract import Document  # noqa: E402
from bse_intel.settings import get_settings  # noqa: E402

MIN_COMPANIES = 10   # the owner's rule (2026-10-16): a round covers at least ten different companies

KEEP = ("headline", "takeaway", "core_catalyst", "what_happened", "why_it_matters", "key_numbers", "notable_changes",
        "deal_value", "quantified_impact", "track_next", "signals", "timeline_entry", "event_type", "impact_level",
        "missing_disclosures", "grounding", "review", "xbrl", "model")


def spread(rows: list[dict]) -> list[dict]:
    """The cards in company order, one company at a time round and round, so a round covers every company
    instead of the first few (the owner's rule: at least MIN_COMPANIES companies a round). Within a company
    the newest cards come first, because they were written by the newest code."""
    by_company: dict[str, list[dict]] = {}
    for row in sorted(rows, key=lambda r: str(r.get("filed_at") or ""), reverse=True):
        by_company.setdefault(str(row.get("scrip_code")), []).append(row)
    out = []
    while any(by_company.values()):
        for queue in by_company.values():
            if queue:
                out.append(queue.pop(0))
    return out


def _round_robin(rows: list[dict]) -> list[dict]:
    """One card per company in turn, keeping each company's cards in the order given (a seeded shuffle)."""
    by_company: dict[str, list[dict]] = {}
    for row in rows:
        by_company.setdefault(str(row.get("scrip_code")), []).append(row)
    out = []
    while any(by_company.values()):
        for queue in by_company.values():
            if queue:
                out.append(queue.pop(0))
    return out


def _xbrl_table(url: str | None, news_id: str = "") -> str:
    """The XBRL table the pipeline put in front of the card's text, rebuilt from the cached file (the pipeline's own
    `_xbrl_file` cache); empty when the file is not in the cache."""
    if not url and not news_id:
        return ""
    import hashlib

    from bse_intel import xbrl  # noqa: E402

    root = get_settings().text_cache_dir
    if not root:
        return ""
    # a results file is cached beside the filing's text (Pipeline._xbrl), others by URL (Pipeline._xbrl_file)
    path = root / news_id[:2] / f"{news_id}.xbrl.gz"
    if not path.exists() and url:
        path = root / "xbrl" / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".xml.gz")
    if not path.exists():
        return ""
    parsed = xbrl.parse(gzip.decompress(path.read_bytes()))
    return parsed.table() if parsed else ""


def _xbrl_note(card: dict, news_id: str = "") -> str:
    """The pipeline prepends the machine-tagged XBRL table to the filing text it sends the model, but the
    table is built in memory and never cached, so it cannot be exported. Without this note a reviewer reads
    only the PDF and calls an XBRL figure invented, or misses that a wrong figure came from the table rather
    than from the model (audit round 1: three results cards took a wrong year-ago figure from it). Say so."""
    tagged = card.get("xbrl") or {}
    if not tagged.get("period"):
        return ""
    table = _xbrl_table(tagged.get("url"), news_id)
    if table:
        # since 2026-10-19 the card records its file's URL and the pipeline caches the file: show the table itself
        # (round 4's re-run reviewers could not check figures that came from it)
        return ("NOTE FOR THE REVIEWER: the model was given this machine-tagged XBRL table, built from the company's own "
                "XBRL file, and told to prefer it over figures read from the PDF. Its comparatives (YoY, QoQ) are "
                "computed from earlier files and have sometimes been wrong: check them against the statement's own "
                "columns.\n\n" + table + "\n\n--- filing text ---\n")
    return ("NOTE FOR THE REVIEWER: besides the text below, the model was given a machine-tagged XBRL table for "
            f"{tagged.get('basis') or 'an unstated basis'}, {tagged['period']}, holding {tagged.get('figures', '?')} "
            "figures in \u20b9 crore, and was told to prefer it over figures read from the PDF. That table is not "
            "reproducible here. So: a figure that is not in the text below may still have come from the XBRL file "
            "rather than been invented - say it is not in the filing text rather than that the model made it up, and "
            "check any year-on-year or quarter-on-quarter change against the statement's own comparative column, "
            "which is the figure the table itself has sometimes got wrong.\n\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cards_json")
    ap.add_argument("out_dir")
    ap.add_argument("--per-reviewer", type=int, default=10)
    ap.add_argument("--limit", type=int, default=100, help="cards in this round (0 for all)")
    ap.add_argument("--min-companies", type=int, default=MIN_COMPANIES)
    ap.add_argument("--skip", help="file with news_ids already audited, one per line")
    # Audit round 2 (2026-10-18): a reviewer who sees the checks' own verdict on a card is steered by it, and one
    # who cannot see memory cannot judge a point resting on it - two of ten released cards had a wrong memory point.
    ap.add_argument("--blind", action="store_true", help="leave out the pipeline's own grounding, review and model")
    ap.add_argument("--memory", metavar="URL", help="also write <news_id>.memory.json, memory as the card saw it, "
                                                    "read from the local site at URL (e.g. http://localhost:5173)")
    ap.add_argument("--random", type=int, metavar="SEED", help="a seeded random order within each company, not newest first")
    args = ap.parse_args()
    rows = json.load(open(args.cards_json, encoding="utf-8"))[0]["results"]
    skip = set(pathlib.Path(args.skip).read_text().split()) if args.skip else set()
    rows = [r for r in rows if r["news_id"] not in skip]
    if args.random is not None:
        import random
        rows = sorted(rows, key=lambda r: r["news_id"])
        random.Random(args.random).shuffle(rows)
    rows = (spread(rows) if args.random is None else _round_robin(rows))[:args.limit or None]
    keep_fields = tuple(k for k in KEEP if not (args.blind and k in ("grounding", "review", "model")))
    sink = None
    if args.memory:
        from bse_intel.dossier import view_as_of  # noqa: E402
        from bse_intel.sinks.platform import PlatformSink  # noqa: E402
        sink, dossiers = PlatformSink(args.memory, "dev-local-token"), {}
    companies = {str(r.get("scrip_code")) for r in rows}
    if len(companies) < args.min_companies:
        print(f"refusing: {len(rows)} cards cover {len(companies)} companies, fewer than {args.min_companies}. "
              "Let the run write more cards, or lower --min-companies deliberately.")
        return 1
    cache = get_settings().text_cache_dir
    out = pathlib.Path(args.out_dir)
    written, manifest = 0, {}
    for i, row in enumerate(rows):
        folder = out / f"reviewer_{i // args.per_reviewer + 1:02d}"
        folder.mkdir(parents=True, exist_ok=True)
        card = json.loads(row["card_json"])
        keep = {k: card.get(k) for k in keep_fields}
        if row.get("impact_level"):
            # the impact the site shows is the card's score, not the writer's call: round 5's reviewers judged the
            # writer's and 55 of 140 shown impacts went unchecked against what a reader sees (2026-10-19)
            keep["impact_level"] = row["impact_level"]
        if sink is not None:
            scrip = str(row.get("scrip_code"))
            if scrip not in dossiers:
                dossiers[scrip] = sink.get_dossier(scrip) or {}
            view = view_as_of(dossiers[scrip], str(row.get("filed_at"))) if dossiers[scrip] else {}
        keep["_filing"] = {"news_id": row["news_id"], "headline": row.get("headline_filing"), "subject": row.get("subject")}
        (folder / f"{row['news_id']}.card.json").write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
        path = cache / row["news_id"][:2] / f"{row['news_id']}.json.gz"
        text = (Document.from_cache(json.loads(gzip.decompress(path.read_bytes()))).select_text(10_000_000, [])
                if path.exists() else "(no cached text)")
        if sink is not None:
            # The proportions code computed for the card's writer (shares of revenue, net worth, market cap), rebuilt
            # from memory as it stood before the filing. Round 3's reviewers could not see them and counted the ratios
            # as unsupported memory points (36 cards).
            from bse_intel.dossier import dossier_as_of  # noqa: E402
            from bse_intel.grounding import declared_unit  # noqa: E402
            from bse_intel.signals import scale_block  # noqa: E402
            before = dossier_as_of(dossiers[scrip], str(row.get("filed_at")), inclusive=False) if dossiers[scrip] else None
            scale = scale_block(before, sink.company(scrip) or {}, text, declared_unit(text)) if before else ""
            if scale:
                view = {**(view or {}), "scale_block (computed by code from memory, shown to the card's writer)": scale}
            (folder / f"{row['news_id']}.memory.json").write_text(json.dumps(view, ensure_ascii=False, indent=1),
                                                                  encoding="utf-8")
        (folder / f"{row['news_id']}.pdf.txt").write_text(_xbrl_note(card, row["news_id"]) + text, encoding="utf-8")
        manifest[row["news_id"]] = {"model": card.get("model"), "scrip_code": str(row.get("scrip_code")),
                                    "event_type": card.get("event_type"), "folder": folder.name,
                                    "held": bool(row.get("held"))}   # held cards are mixed in blind (round 2)
        written += 1
    # outside the reviewers' folders: which model wrote each card, for the tally, without showing the reviewer
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    folders = len({i // args.per_reviewer for i in range(written)})
    per_company = collections.Counter(str(r.get("scrip_code")) for r in rows)
    print(f"{written} cards in {folders} reviewer folders under {out}")
    print(f"{len(per_company)} companies: " + ", ".join(f"{k} {v}" for k, v in sorted(per_company.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
