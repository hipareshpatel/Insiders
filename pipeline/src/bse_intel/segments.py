"""The business mix of a results quarter, read from the exchange's own file (owner, 30 Oct 2026: "Business mix ... on stock pages are
wrong or blank", TODO 137), by code and without a model.

A results XBRL carries the segment note: each reportable segment is a dimension member (``ReportableSegments1Member`` ... on the
revenue axis ``ReportableSegmentsAxis``, the result axis ``ReportableSegmentsFinanceCostsAxis`` and the asset and liability axes;
the prefix is ``in-bse-fin`` or ``in-capmkt`` by taxonomy) and its name is the text ``DescriptionOfReportableSegment`` filed in the
same member's contexts. ``xbrl_facts.parse_facts`` keeps every dimensional fact with its axis and member, so nothing is
re-parsed here. A single-segment filer files ``IsCompanyReportingMultisegmentOrSingleSegment`` = "Single segment" and
``DescriptionOfSingleSegment`` instead (Dolphin Offshore: "Offshore Support Services"; Bajaj Finance: "NBFC").

``segment_rows`` gives one quarter's rows (name, revenue in crore, segment result before tax and finance cost, share of the rows'
revenue) or the single-segment marker. The revenue is the segment's own (``SegmentRevenue``, before the inter-segment
elimination, as the note prints it; ``SegmentRevenueFromOperations`` when a filer tags the segment's external revenue), so the
shares add up to 100%. Lines that are no business (unallocated, inter-segment elimination, reconciling items) and segments with no
revenue are left out. ``remember`` writes them into the dossier's ``segment_mix``, labelled ``file``: they replace the AI-read rows
of the same period, and a consolidated file replaces a standalone one (a standalone file never overwrites a consolidated filer's
mix). A failure never fails the filing (statements.from_file)."""

from __future__ import annotations

import logging
import re

from . import xbrl_facts
from .memory_gaps import quarter_end
from .periods import quarter_index

log = logging.getLogger(__name__)

KEY = "segment_mix"
MAX_ROWS = 240       # about 12 quarters of up to 20 segments; the oldest quarters go first
CONSOLIDATED = "CONSOLIDATED"
REVENUE = ("SegmentRevenueFromOperations", "SegmentRevenue")      # the tag of one segment's revenue, the external one first
RESULT = "SegmentProfitLossBeforeTaxAndFinanceCosts"
# a line that is no business: by how it begins ("Unallocated", "Less: Inter-segment revenue", "Eliminations", "Reconciling
# items", "Adjustments"), so a real segment with such a word inside ("Power Adjustment Services") is kept (blind review)
NOT_BUSINESS = re.compile(r"^\W*(less\W+)?(un-?allocat|unallocab|eliminat|inter.?segment|reconcil|adjustment|not allocated|others? un)", re.I)


def _member(ctx: dict) -> str | None:
    """The segment member of a context with exactly one segment dimension, else None."""
    dims = ctx.get("d") or {}
    if len(dims) != 1:
        return None
    (axis, member), = dims.items()
    return member if "ReportableSegment" in axis else None


def segment_rows(doc: dict) -> dict | None:
    """The quarter's segment note of one stored facts document: ``{"single": False, "rows": [{segment, revenue_cr, pbit_cr,
    share_pct}]}``, or ``{"single": True, "description": text or None}`` for a single-segment filer; None when the file says
    neither (or the period is no quarter)."""
    period = doc.get("period") or ""
    end = quarter_end(period) if period.startswith("Q") else None
    if end is None:
        return None
    facts = xbrl_facts.Facts(doc)
    names: dict[str, str] = {}
    revenue: dict[str, dict[str, float]] = {}
    result: dict[str, float] = {}
    marker = description = None
    for el, ctx_id, unit, value, _ in facts.rows:
        if not facts._at(ctx_id, end, 3, None):
            continue
        ctx = facts.contexts.get(ctx_id) or {}
        if not ctx.get("d"):
            if isinstance(value, str):
                if el == "IsCompanyReportingMultisegmentOrSingleSegment":
                    marker = value
                elif el == "DescriptionOfSingleSegment":
                    description = value.strip() or None
            continue
        member = _member(ctx)
        if member is None:
            continue
        if isinstance(value, str):
            if el == "DescriptionOfReportableSegment" and value.strip():
                names.setdefault(member, value.strip())
        elif facts._is_money(unit):
            if el in REVENUE:
                revenue.setdefault(member, {}).setdefault(el, value / xbrl_facts.CRORE)
            elif el == RESULT:
                result.setdefault(member, value / xbrl_facts.CRORE)
    rows = []
    # one revenue tag for every segment of the quarter when they all carry it, so the shares are on one basis (blind review)
    common = next((t for t in REVENUE if revenue and all(t in by_tag for by_tag in revenue.values())), None)
    for member, by_tag in revenue.items():
        # a segment whose name is not filed in the quarter's contexts is kept under its member's number, so the shares
        # of the others do not add up to 100% without it (blind review)
        name = names.get(member) or ("Segment " + ("".join(ch for ch in member if ch.isdigit()) or "?"))
        rev = by_tag[common] if common else next((by_tag[t] for t in REVENUE if t in by_tag), None)
        if NOT_BUSINESS.search(name) or rev is None or rev <= 0:
            continue
        rows.append({"segment": name, "revenue_cr": round(rev, 2),
                     "pbit_cr": round(result[member], 2) if member in result else None})
    if rows:
        total = sum(r["revenue_cr"] for r in rows)
        for r in rows:
            r["share_pct"] = round(r["revenue_cr"] / total * 100, 1)
        return {"single": False, "rows": sorted(rows, key=lambda r: -r["revenue_cr"])}
    if marker and re.search(r"single", marker, re.I):
        return {"single": True, "description": description}
    return None


def _entries(doc: dict, found: dict, news_id: str, as_of: str, at: str, source: str = "") -> list[dict]:
    period, basis = doc["period"], doc.get("basis")
    lab = {"by": "file", "doc": "results", "basis": basis, "at": at, "rules": "segment_note"}
    if source:
        lab["from"] = source
    common = {"period": period, "basis": basis, "as_of": as_of, "source_news_id": news_id, "lab": lab}
    if found["single"]:
        return [{"segment": found["description"] or "", "single": True, **common}]
    return [{**r, **common} for r in found["rows"]]


def _by_file(entry: dict) -> bool:
    return (entry.get("lab") or {}).get("by") == "file"


def remember(dossier: dict, doc: dict, news_id: str, as_of: str, at: str, replace: bool = True, source: str = "") -> int:
    """Put the file's segment rows into ``dossier["segment_mix"]`` (in place); the number of rows written. They take the place of
    every row of the same period (AI-read ones, the other basis's); a standalone file is left out when the company's figures are
    consolidated or a consolidated file's rows are there already. ``replace`` False (the backfill) adds only a period no file
    row of this basis holds."""
    period, basis = doc.get("period"), doc.get("basis")
    if not period or not quarter_index(period):
        return 0
    held_slip = {str(h.get("period") if isinstance(h, dict) else h) for h in dossier.get("scale_held", [])}
    if period in held_slip:
        return 0      # memory holds this quarter's file as unit-slipped (Jubilant's tenth): its amounts would be wrong too
    found = segment_rows(doc)
    if found is None:
        return 0
    held = [e for e in dossier.get(KEY, []) if isinstance(e, dict)]
    there = {e.get("basis") for e in held if e.get("period") == period and _by_file(e)}
    if basis != CONSOLIDATED:
        main = {m.get("basis") for m in dossier.get("financial_metrics", [])}
        if CONSOLIDATED in there or CONSOLIDATED in main:
            return 0
    if not replace and basis in there:
        return 0
    entries = _entries(doc, found, news_id, as_of, at, source)
    rest = [e for e in held if e.get("period") != period]
    dossier[KEY] = sorted(rest + entries, key=lambda e: quarter_index(str(e.get("period") or "")) or 0)[-MAX_ROWS:]
    return len(entries)
