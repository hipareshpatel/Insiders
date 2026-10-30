"""Memory recall audit, the export step (TODO row 82, owner Yes 26 Oct 2026). Read only: no AI, no memory or card write.

A reviewer reads the full text of about 20 recent call transcripts and investor decks (CONCALL_PRESENTATION cards) and lists
every point worth remembering, without seeing memory. A second step compares that list with what memory saved from the
same filing. This module writes what both steps need, one folder per sampled filing:

  text.txt     the filing's whole stored text (R2 ``text/<news_id>.json.gz``), every page with a marker saying whether the page
               is the PDF's text layer or OCR (and a page that is scanned but was never OCR'd is named)
  memory.json  everything the company's dossier holds that came from this filing (``attribute``)
  card.json    the stored card
  meta.json    symbol, company, sector, size, filed_at, event type, PDF URL, how each page was read

plus ``index.json`` (the sample, and how it was drawn) and ``README.md`` (the reviewer's task).

Sample: published CONCALL_PRESENTATION cards filed in the last ``days`` days that have text in R2, drawn with a fixed seed,
spread across sectors and size bands (a company at most once while others are left), balanced between transcripts and decks
(told apart by the card's headline, and by the text itself when the headline does not say).

Memory sections and their source ids: see ``attribute``. A section whose entries carry no id of a filing cannot be attributed
to one; they are listed in ``memory.json`` under ``sections_without_filing_id``.
"""
from __future__ import annotations

import gzip
import json
import random
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from .extract import Document, figure_page
from .pipeline import text_key
from .timeutil import today_ist

EVENT = "CONCALL_PRESENTATION"
DAYS = 30
PAGE = 100
READ_WORKERS = 8
# the keys under which a dossier entry names the filing it came from (dossier.py: _forget, merge, call_summary)
ID_KEYS = ("source_news_id", "news_id", "value_news_id", "resolved_by", "repeats", "source")
SIZE_BANDS = ((20000.0, "large"), (5000.0, "mid"), (0.0, "small"))   # market cap, crore; the universe floor is 500

_TRANSCRIPT = re.compile(r"transcript|earnings call|conference call|con-?call|audio|recording|call on", re.I)
_DECK = re.compile(r"presentation|investor deck|\bdeck\b|\bslides?\b|investor update|corporate profile", re.I)

README = """# Memory recall audit: reviewer task

Each folder holds one filing from a company's call (a transcript) or investor presentation (a deck).

You read ONLY `text.txt` in each folder. Do not open `memory.json`, `card.json` or `meta.json`, and do not look the company
up elsewhere. Page markers in `text.txt` say whether a page is the PDF's text layer (`text`) or OCR (`ocr`); OCR can misread
figures, so say so when a point rests on an OCR page.

For each filing, list EVERY point a long-term investor in this company would want remembered a year from now. Read the whole
text, the Q&A of a transcript and the last slides of a deck included. Write the file `<news_id>/recall.json`, a list of
objects `{"type": ..., "point": ..., "page": ..., "quote": ...}`, `point` in plain words with the figure and the date or period
as the filing states them, `quote` the words of the filing it rests on (short, exact).

Types (use exactly these names):

- `guidance`: a target or outlook with its figure and the period or date it is for
- `capex_capacity`: capex and capacity plans, with amounts and dates
- `order_book`: order book, order inflow, pipeline or backlog, with figures
- `target`: a margin, debt, return or other financial target
- `management_change`: a person joining, leaving or changing role
- `dependence`: customer, segment, product or geography dependence
- `risk`: a stated risk
- `one_off`: a one-off item (exceptional gain or loss, a charge, a sale, a restatement)

Rules: one point per object. Do not list ordinary quarterly figures that every results filing carries (revenue, profit as
reported). Do not infer: a point must be in the text. If a filing has nothing to remember, write an empty list and say why in a
file `<news_id>/recall.note.txt`.

A second step then compares your lists with what memory saved from each filing (`memory.json`, kept apart from you), point by
point: saved, saved wrongly, or missed.
"""


# ---------------------------------------------------------------- memory attributed to one filing
def _hit(node, news_id: str) -> bool:
    """Does this entry, anywhere inside it, name the filing as a source?"""
    if isinstance(node, dict):
        return any((k in ID_KEYS and v == news_id) or _hit(v, news_id) for k, v in node.items())
    if isinstance(node, list):
        return any(_hit(v, news_id) for v in node)
    return False


def _carries_id(node) -> bool:
    """Does any entry inside carry an id key of a filing (a non-empty value under one of ID_KEYS)?"""
    if isinstance(node, dict):
        return any((k in ID_KEYS and v) or _carries_id(v) for k, v in node.items())
    if isinstance(node, list):
        return any(_carries_id(v) for v in node)
    return False


def attribute(dossier: dict | None, news_id: str) -> dict:
    """What the dossier holds that came from ``news_id``: ``{"news_id", "entries", "sections": {path: [entry, ...]},
    "sections_without_filing_id": [path, ...]}``.

    An entry is attributed when it, or anything inside it (a metric's ``sources``, a guidance item's ``status_history``, a deal's
    history, a resolved prediction's ``resolved_by``), names the filing under ``source_news_id``, ``news_id``, ``value_news_id``,
    ``resolved_by``, ``repeats`` or ``source``. The whole entry is kept, so the reader sees every source of a figure.
    Sections are walked generically (list sections by entry, dict sections by their children), so a section added to the
    dossier later is covered without a change here. A section with entries none of which carries an id cannot be attributed to
    a filing and is named in ``sections_without_filing_id``."""
    sections: dict[str, list] = {}
    no_id: list[str] = []

    def walk(path: str, node) -> None:
        if isinstance(node, list):
            if not node:
                return
            if not any(isinstance(e, (dict, list)) for e in node):
                no_id.append(path)   # a list of plain strings (identity.former_names)
                return
            for entry in node:
                if _hit(entry, news_id):
                    sections.setdefault(path, []).append(entry)
            if not _carries_id(node):
                no_id.append(path)
        elif isinstance(node, dict):
            if path and any(k in ID_KEYS and v == news_id for k, v in node.items()):
                sections.setdefault(path, []).append(node)
                return
            for k, v in node.items():
                if isinstance(v, (list, dict)):
                    walk(f"{path}.{k}" if path else k, v)

    walk("", dossier or {})
    return {"news_id": news_id, "entries": sum(len(v) for v in sections.values()), "sections": sections,
            "sections_without_filing_id": sorted(no_id)}


# ---------------------------------------------------------------- the text with page markers
def render_text(data: dict) -> tuple[str, list[dict]]:
    """The stored text of a filing as one file, every page under a marker, and how each page was read.

    A page is ``ocr`` when the cache holds an OCR reading of it, ``text`` otherwise; ``text (scanned or garbled, not OCR'd)`` is
    a page the text layer could not carry and nothing read, so the reviewer knows it is thin on purpose."""
    doc = Document.from_cache(data)
    pages, parts = [], []
    total = doc.page_count
    for i in range(total):
        text = doc.page_text(i)
        if i in doc._ocr_cache:
            how = "ocr"
        elif doc.is_scanned(i) or doc.is_unreadable(i):
            how = "text (scanned or garbled, not OCR'd)"
        else:
            how = "text"
        pages.append({"page": i + 1, "source": how, "chars": len(text), "figure_page": figure_page(doc._digital[i])})
        parts.append(f"===== PAGE {i + 1} of {total} [{how}] =====\n{text.strip()}\n")
    return "\n".join(parts), pages


def size_band(market_cap_cr) -> str:
    if not isinstance(market_cap_cr, (int, float)):
        return "unknown"
    return next(name for floor, name in SIZE_BANDS if market_cap_cr >= floor)


def kind_of(headline: str) -> str:
    """transcript, deck or unknown, from the card's headline; the text decides an unknown one later."""
    call, deck = bool(_TRANSCRIPT.search(headline or "")), bool(_DECK.search(headline or ""))
    return "transcript" if call and not deck else "deck" if deck and not call else "unknown"


INVITATION_PAGES = 3          # a notice of an upcoming call is a page or two
INVITATION_CHARS = 6000


def invitation(doc: Document) -> bool:
    """A short document with no call in it: the notice that a call will be held (no moderator, no questions, a few pages).
    Syrma SGS's nse-106828335, headlined "to discuss Q2FY27 results on November 2 earnings call", is two pages of dial-in
    details; sampled as a transcript it sent a reviewer to list points from a page of logistics (26 Oct 2026)."""
    if doc.kind() == "TRANSCRIPT":
        return False
    chars = sum(len(page) for page in doc._digital) + sum(len(t) for t in doc._ocr_cache.values())
    return doc.page_count <= INVITATION_PAGES and chars < INVITATION_CHARS


def kind_from_text(data: dict, headline: str) -> str:
    """The headline first, but a headline that says "earnings call" over an invitation is not a transcript: the text decides
    then (a deck when it is one, else ``invitation``). A headline-less or unclear one is read from the document's own look."""
    k = kind_of(headline)
    doc = Document.from_cache(data)
    if k == "transcript" and invitation(doc):
        return "deck" if doc.kind() == "PRESENTATION" else "invitation"
    if k != "unknown":
        return k
    return "transcript" if doc.kind() == "TRANSCRIPT" else "deck"


# ---------------------------------------------------------------- the sample
def candidates(sink, days: int = DAYS, today=None, held: bool = False) -> list[dict]:
    """Published CONCALL_PRESENTATION cards filed in the last ``days`` days (export_cards, keyset paged from the cutoff);
    with ``held`` the held ones too."""
    cutoff = ((today or today_ist()) - timedelta(days=days)).isoformat()
    after, out = [cutoff, ""], []
    while True:
        rows = sink.query("export_cards", [after[0], after[1], PAGE])
        if not rows:
            break
        after = [rows[-1]["filed_at"], rows[-1]["news_id"]]
        out += [r for r in rows if r.get("event_category") == EVENT and (held or not r.get("held"))]
        if len(rows) < PAGE:
            break
    return out


def _spread(rows: list[dict], seed: int) -> list[dict]:
    """Rows in the order to try them: groups of one sector and size band in a seeded order, one row from each group in turn;
    a company's second and later rows go after every company has had a turn."""
    rng = random.Random(seed)
    firsts, rest, seen = [], [], set()
    for r in rows:
        (rest if r["scrip_code"] in seen else firsts).append(r)
        seen.add(r["scrip_code"])
    ordered = []
    for pool in (firsts, rest):
        groups: dict[tuple, list[dict]] = {}
        for r in pool:
            groups.setdefault((r.get("sector") or "", r.get("_band") or "unknown"), []).append(r)
        keys = sorted(groups)
        rng.shuffle(keys)
        for k in keys:
            rng.shuffle(groups[k])
        while any(groups.values()):
            for k in keys:
                if groups[k]:
                    ordered.append(groups[k].pop())
    return ordered


def choose(rows: list[dict], read_text, limit: int, seed: int) -> list[dict]:
    """The sample: transcripts and decks in turn, each pool spread over sectors and sizes, only cards whose text is stored.
    ``read_text(news_id)`` gives the stored entry (a dict) or None. Rows come back with ``_data`` (the entry) and ``_kind``."""
    rows = sorted(rows, key=lambda r: r["news_id"])
    pools: dict[str, list[dict]] = {"transcript": [], "deck": [], "unknown": []}
    for r in rows:
        pools[kind_of(r.get("headline") or "")].append(r)
    queues = {k: _spread(v, seed) for k, v in pools.items()}
    picked: list[dict] = []
    seen: set[str] = set()   # companies already in the sample: a second filing of one waits until every queue is through
    turn = 0
    for relax in (False, True):
        deferred: dict[str, list[dict]] = {k: [] for k in queues}
        while len(picked) < limit and any(queues.values()):
            mine, other = ("transcript", "deck") if turn % 2 == 0 else ("deck", "transcript")
            turn += 1
            kind = mine if queues[mine] else other if queues[other] else "unknown"
            if not queues[kind]:
                kind = next(k for k, q in queues.items() if q)
            row = queues[kind].pop(0)
            if not relax and row["scrip_code"] in seen:
                deferred[kind].append(row)
                continue
            data = read_text(row["news_id"])
            if data and (data.get("digital") or data.get("ocr")):
                actual = kind_from_text(data, row.get("headline") or "")
                if actual == "invitation":
                    continue   # not a call and not a deck: nothing for a reviewer to read
                picked.append({**row, "_data": data, "_kind": actual})
                seen.add(row["scrip_code"])
        queues = deferred
    return picked


def read_text_from(sink):
    def read(news_id: str) -> dict | None:
        try:
            body = sink.get_object(text_key(news_id))
            return json.loads(gzip.decompress(body)) if body else None
        except Exception:   # noqa: BLE001 - a damaged or missing entry is no text
            return None
    return read


# ---------------------------------------------------------------- the export
def _folder_name(news_id: str) -> str:
    return "".join(ch for ch in news_id if ch.isalnum() or ch in "-_")[:80] or "unnamed"


def _ledger_rows(sink, ids: list[str]) -> list[dict]:
    """Rows for named filings with no published call or deck card (a call read for memory alone, a held or merged card): the
    ledger's own fields, no card."""
    from .call_memory import find_filing

    out = []
    for nid in ids:
        f = find_filing(sink, nid)
        if f is not None:
            out.append({"news_id": nid, "scrip_code": f.scrip_code, "symbol": f.symbol, "company_name": f.company_name,
                        "filed_at": f.filed_at, "headline": f.headline, "pdf_url": f.pdf_url, "event_category": f.event_type,
                        "card_json": None})
    return out


def export(sink, out: Path, limit: int = 20, seed: int = 26, days: int = DAYS, today=None, ids: list[str] | None = None) -> dict:
    """Write the sample to ``out``; returns the index. Reads only. With ``ids`` the sample is those filings alone."""
    rows = candidates(sink, days, today, held=bool(ids))
    if ids:
        rows = [r for r in rows if r["news_id"] in set(ids)]
        rows += _ledger_rows(sink, [i for i in ids if i not in {r["news_id"] for r in rows}])
        limit = len(rows)
    scrips = sorted({r["scrip_code"] for r in rows})

    def cap(scrip):
        try:
            return (sink.company(scrip) or {}).get("market_cap_cr")
        except Exception:   # noqa: BLE001 - a missing company only loses its size band
            return None

    with ThreadPoolExecutor(max_workers=READ_WORKERS) as pool:
        caps = dict(zip(scrips, pool.map(cap, scrips)))
    for r in rows:
        r["_cap"], r["_band"] = caps.get(r["scrip_code"]), size_band(caps.get(r["scrip_code"]))
    picked = choose(rows, read_text_from(sink), limit, seed)

    out.mkdir(parents=True, exist_ok=True)
    dossiers: dict[str, dict | None] = {}
    sample = []
    for r in picked:
        nid = r["news_id"]
        folder = out / _folder_name(nid)
        folder.mkdir(parents=True, exist_ok=True)
        text, pages = render_text(r["_data"])
        if r["scrip_code"] not in dossiers:
            dossiers[r["scrip_code"]] = sink.get_dossier(r["scrip_code"])
        memory = attribute(dossiers[r["scrip_code"]], nid)
        card = json.loads(r["card_json"]) if isinstance(r.get("card_json"), str) else (r.get("card_json") or {})
        meta = {"news_id": nid, "symbol": r.get("symbol"), "company": r.get("company_name"), "scrip_code": r["scrip_code"],
                "sector": r.get("sector"), "market_cap_cr": r["_cap"], "size_band": r["_band"], "filed_at": r.get("filed_at"),
                "event_type": r.get("event_category"), "kind": r["_kind"], "headline": r.get("headline"),
                "pdf_url": r.get("pdf_url"), "pages": pages,
                "pages_text": sum(p["source"] == "text" for p in pages), "pages_ocr": sum(p["source"] == "ocr" for p in pages),
                "pages_unread": sum(p["source"].startswith("text (") for p in pages), "chars": len(text)}
        (folder / "text.txt").write_text(text, encoding="utf-8")
        (folder / "memory.json").write_text(json.dumps(memory, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
        (folder / "card.json").write_text(json.dumps(card, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        sample.append({k: meta[k] for k in ("news_id", "symbol", "company", "sector", "size_band", "kind", "filed_at", "headline",
                                            "pages_text", "pages_ocr", "pages_unread", "chars")}
                      | {"folder": folder.name, "memory_entries": memory["entries"]})
    kinds = ("transcript", "deck", "unknown")
    index = {"seed": seed, "limit": limit, "days": days, "candidates": len(rows),
             "candidates_by_headline_kind": {k: sum(kind_of(r.get("headline") or "") == k for r in rows) for k in kinds},
             "sampled": len(sample), "by_kind": {k: sum(s["kind"] == k for s in sample) for k in kinds[:2]},
             "companies": len({s["symbol"] for s in sample}), "sectors": len({s["sector"] for s in sample}),
             "sample": sample}
    if ids:   # a requested filing not exported: older than `days`, not a call or deck, no stored text, or an invitation
        index |= {"requested": len(ids), "missing": sorted(set(ids) - {s["news_id"] for s in sample})}
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / "README.md").write_text(README, encoding="utf-8")
    return index


def render(index: dict) -> str:
    lines = [f"memory recall export: {index['sampled']} of {index['candidates']} candidate cards "
             f"(last {index['days']} days, seed {index['seed']}); transcripts {index['by_kind']['transcript']}, "
             f"decks {index['by_kind']['deck']}; {index['companies']} companies, {index['sectors']} sectors"]
    for s in index["sample"]:
        lines.append(f"  {s['news_id']}  {s['symbol'] or '-':12} {s['kind']:10} {s['size_band']:7} pages {s['pages_text']} text, "
                     f"{s['pages_ocr']} ocr, {s['pages_unread']} unread; memory entries {s['memory_entries']}")
    return "\n".join(lines)
