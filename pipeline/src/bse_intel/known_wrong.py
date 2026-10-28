"""Figures proven wrong where the exchange's own file is the wrong one, held in code (F223, 28 Oct 2026).

Memory writers take the exchange's XBRL as the clean source, and for 99% of figures it is. For a few, the company's own file
differs from its own results statement: a tax line with a flipped sign, a prior-year tax left out, a discontinued line added,
a standalone EPS in the consolidated file. Reading the file again writes the same wrong figure again, so such a figure cannot
be put right by a re-read; it has to be named. This list is the one place that names them, each with its evidence.

* every memory writer honours it: ``dossier.merge`` (the seed, the live run, the BSE fill's seed copy), ``dossier.put_standalone``
  and the BSE gap fill's own write skip a listed figure (``listed``);
* ``memory-drop-known-wrong`` (``memory_drop.py``) takes exactly the listed figures out of the stored dossiers, with a backup
  first, so a figure already written is removed and a later fill cannot put the same value back.

An entry matches on the figure's value as well as its key (scrip, metric, period, basis): a later correct figure for the same key
is never held back and never removed. A figure only goes on this list when the filing itself proves it wrong (the PDF text layer
or the printed statement, with a second source agreeing: docs/DATA_QUALITY.md, the two-source rule); the right value is kept
beside it as evidence, never written by code. Everything a re-read of the file does fix (a flipped sign, a filler zero, a unit
slip) is fixed in the reader and does not belong here.

``listed()`` ignores the ``exchange`` field on purpose: it is evidence, not part of the key. The fault is in the company's own
results file, and the company files the same XBRL with both exchanges, so NSE's copy of the same results (what the seed and the
live run read) carries the same wrong figure as BSE's. Matching on the exchange would let that copy write it back; the value
match is what keeps a correct figure safe, whichever exchange it comes from.

A list entry with a stated basis matches a figure of that basis. A figure whose basis is not stated matches only when the
company's dossier holds that one basis and nothing else (``dossier_bases``: the main block's bases, and STANDALONE when a standalone
block is kept); a company holding two bases, or none, gets no match, since the figure could be the other basis's.

Nothing in this module imports the rest of the package, so every writer can use it."""

from __future__ import annotations

import re
from dataclasses import dataclass

MATCH_TOLERANCE = 0.005   # stored figures are rounded to 2 decimals


@dataclass(frozen=True)
class KnownWrong:
    scrip: str            # the company key memory is stored under (the BSE scrip code)
    basis: str            # CONSOLIDATED, STANDALONE, or "" when the evidence does not say (matches either)
    period: str           # the quarter or year as memory labels it (Q4FY25)
    metric: str           # memory's metric name (pat, eps, revenue ...)
    wrong: float          # the figure the file carries, as memory stores it (crore for money, rupees for EPS)
    right: float | None   # the figure the statement prints, when known: evidence only, never written
    evidence: str         # the source and the page or file, and why the file is wrong
    proven: str           # the date it was proven (YYYY-MM-DD)
    exchange: str = ""    # the exchange whose file carries the wrong figure, when it is one exchange's


KNOWN_WRONG_FIGURES: tuple[KnownWrong, ...] = (
    KnownWrong(
        "530643", "CONSOLIDATED", "Q4FY25", "pat", 3.42, 2.20,
        "Eco Recycling. PDF 0047672d (OCR of the consolidated page 15): profit before tax 627 lakh, tax 288 + (3) + 122 "
        "prior-year, profit after tax 220 lakh. BSE's XBRL Integrated_Finance_Ind_As_530643_1062025234722.xml: TaxExpense "
        "28,500,000 leaves out the 1.22 Cr prior-year tax, ProfitLossForPeriod 34,200,000. Screener 2.20 agrees; its EPS 1.19 "
        "matches the printed EPS. docs/bench/bse-fill-batches-1-2-check.md",
        "2026-10-27", "BSE"),
    KnownWrong(
        "519152", "STANDALONE", "Q3FY25", "pat", -42.94, -18.31,
        "Vadilal Enterprises. PDF 5f92d39f: net profit -18.31 Cr and EPS -212.25, no discontinued operation. BSE's XBRL "
        "Main_Ind_As_519152_3112025174535.xml adds ProfitLossFromDiscontinuedOperationsAfterTax -246,300,000 and gives "
        "ProfitLossForPeriod -429,400,000 while its EPS stays -212.25 (which is -18.31 over 8.63 lakh shares). Tijori -18.31 "
        "agrees (screener -18). docs/bench/bse-fill-batches-1-2-check.md",
        "2026-10-27", "BSE"),
    KnownWrong(
        "513532", "CONSOLIDATED", "Q4FY26", "pat", 15.83, 10.32,
        "Pradeep Metals. PDF e40783f6: profit before tax 1,307.44 lakh, tax (275.52) lakh, profit 1,031.92 lakh, EPS 5.98. BSE's "
        "XBRL Integrated_Finance_Ind_As_513532_165202621228.xml tags TaxExpense -27,552,000 (sign wrong) and "
        "ProfitLossForPeriod 158,296,000 = 130,744,000 + 27,552,000. Screener 10.32 and tijori 10.319 agree. "
        "docs/bench/bse-fill-batches-1-2-check.md",
        "2026-10-27", "BSE"),
    KnownWrong(
        "505232", "CONSOLIDATED", "Q3FY26", "eps", 10.31, 11.24,
        "Veljan Denison. PDF 75b5e969 (own filing, 11 Feb 2026): consolidated EPS 11.24 (profit 505.72 lakh); 10.31 is the "
        "standalone EPS in the same filing, and BSE's XBRL Integrated_Finance_Ind_As_505232_112202614112.xml carries it in the "
        "consolidated filing. Screener 11.24 and tijori 11.2378 agree; profit 5.06 and revenue 36.92 are right. "
        "docs/bench/bse-fill-batches-1-2-check.md",
        "2026-10-27", "BSE"),
    # Sibling lines of the same figures, found in live memory on 28 Oct 2026 (the public site's /api/companies/<symbol>): the same wrong
    # value stored under another name, from the same file.
    KnownWrong(
        "530643", "CONSOLIDATED", "Q4FY25", "pat_continuing", 3.42, 2.20,
        "Eco Recycling, same file as its profit (no discontinued operation: continuing profit is the profit): 3.42 in live memory, "
        "the statement's profit after tax is 220 lakh.",
        "2026-10-28", "BSE"),
    KnownWrong(
        "513532", "CONSOLIDATED", "Q4FY26", "pat_continuing", 15.83, 10.32,
        "Pradeep Metals, same file as its profit: continuing profit 15.83 in live memory, the statement's is 1,031.92 lakh.",
        "2026-10-28", "BSE"),
    KnownWrong(
        "513532", "CONSOLIDATED", "Q4FY26", "current_tax", -2.58, None,
        "Pradeep Metals, same file: the file tags the tax lines with the sign of a credit (TaxExpense -2.76, current -2.58, deferred "
        "-0.17); the statement prints a tax expense of (275.52) lakh. The statement's split between current and deferred was not read.",
        "2026-10-28", "BSE"),
    KnownWrong(
        "513532", "CONSOLIDATED", "Q4FY26", "deferred_tax", -0.17, None,
        "Pradeep Metals, same file: see current_tax; the sign is the fault, the statement's split was not read.",
        "2026-10-28", "BSE"),
    KnownWrong(
        "505232", "CONSOLIDATED", "Q3FY26", "eps_continuing", 10.31, 11.24,
        "Veljan Denison, same file as its EPS: the standalone EPS stored under the continuing-operations variant too; the consolidated "
        "EPS is 11.24.",
        "2026-10-28", "BSE"),
    KnownWrong(
        "505232", "CONSOLIDATED", "Q3FY26", "eps_total", 10.31, 11.24,
        "Veljan Denison, same file as its EPS: the standalone EPS stored under the whole-company variant too; the consolidated EPS "
        "is 11.24.",
        "2026-10-28", "BSE"),
    # The lines of the same files that carry the same fault (the tax of the wrong profit, the discontinued line that was added),
    # proven by the same statements: left in, memory would show a profit that does not equal its own PBT less tax.
    KnownWrong(
        "530643", "CONSOLIDATED", "Q4FY25", "tax_expense", 2.85, 4.07,
        "Eco Recycling, same file and statement as its profit: the statement's tax is 288 + (3) + 122 prior-year = 407 lakh "
        "(4.07 Cr); the file's TaxExpense 28,500,000 leaves out the 1.22 Cr prior-year tax.",
        "2026-10-27", "BSE"),
    KnownWrong(
        "513532", "CONSOLIDATED", "Q4FY26", "tax_expense", -2.76, 2.76,
        "Pradeep Metals, same file and statement as its profit: the statement's tax is (275.52) lakh, an expense of 2.76 Cr; the "
        "file tags TaxExpense -27,552,000, the sign wrong.",
        "2026-10-27", "BSE"),
    KnownWrong(
        "519152", "STANDALONE", "Q3FY25", "pat_discontinued", -24.63, None,
        "Vadilal Enterprises, same file and statement as its profit: the statement has no discontinued operation; the file adds "
        "ProfitLossFromDiscontinuedOperationsAfterTax -246,300,000 (-24.63 Cr).",
        "2026-10-27", "BSE"),
    # Kovai Medical: the BSE fill already skips its Q4FY26 quarter (bse_gap_fill.KNOWN_WRONG, owner 27 Oct 2026: "skip Kovai and
    # start saving"). The figures are listed too, so that a seed or the live run from the same file cannot write them either.
    KnownWrong(
        "523323", "", "Q4FY26", "pat", 59.69, 63.35,
        "Kovai Medical: the company's corrigendum of 25 May 2026 (newspaper extract) corrects Q4 tax, so profit is 6,335.32 lakh "
        "(63.35 Cr); BSE's XBRL of 22 May still has 59.69 Cr. Read from the note in bse_gap_fill.KNOWN_WRONG.",
        "2026-10-27", "BSE"),
    KnownWrong(
        "523323", "", "Q4FY26", "eps", 54.55, 57.90,
        "Kovai Medical: the same corrigendum gives basic EPS 57.90; BSE's XBRL of 22 May still has 54.55.",
        "2026-10-27", "BSE"),
)


def _by_scrip(entries) -> dict[str, list[KnownWrong]]:
    out: dict[str, list[KnownWrong]] = {}
    for e in entries:
        out.setdefault(e.scrip, []).append(e)
    return out


BY_SCRIP = _by_scrip(KNOWN_WRONG_FIGURES)


def norm_metric(metric: str | None) -> str:
    """The metric as memory names it (dossier._norm)."""
    return re.sub(r"[^a-z0-9]+", "_", str(metric or "").lower()).strip("_")


def same_value(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) <= MATCH_TOLERANCE
    except (TypeError, ValueError):
        return False


def dossier_bases(dossier: dict | None) -> set[str]:
    """The bases a dossier holds figures on: its main block's, and STANDALONE when it keeps a standalone block."""
    found: set[str] = set()
    for entry in (dossier or {}).get("financial_metrics", []):
        if not isinstance(entry, dict):
            continue
        for row in [entry, *(entry.get("sources") or [])]:
            found.add(str(row.get("basis") or (row.get("lab") or {}).get("basis") or "").upper())
    if ((dossier or {}).get("standalone") or {}).get("metrics"):
        found.add("STANDALONE")
    return found - {""}


def basis_fits(entry: KnownWrong, basis: str | None, held_bases=None) -> bool:
    """A figure of the other basis is another figure. A figure with no stated basis fits an entry with one only when the
    company's dossier holds that single basis (``held_bases``: a set, or a function returning it, read only when needed);
    with no dossier to say, it does not fit. An entry with no basis fits every figure."""
    if not entry.basis:
        return True
    if basis:
        return str(basis).upper() == entry.basis
    held = held_bases() if callable(held_bases) else held_bases
    return held is not None and set(held) == {entry.basis}


def listed(scrip: str | None, metric: str | None, period: str | None, value, basis: str | None = None,
           entries: dict[str, list[KnownWrong]] | None = None, held_bases=None) -> KnownWrong | None:
    """The list entry a figure matches (same company, metric, period, a basis that fits, and the same value), else None.
    ``exchange`` is not matched (module docstring)."""
    table = BY_SCRIP if entries is None else entries
    for e in table.get(str(scrip or ""), ()):
        if norm_metric(metric) == e.metric and period == e.period and same_value(value, e.wrong) \
                and basis_fits(e, basis, held_bases):
            return e
    return None


def for_scrip(scrip: str, entries: dict[str, list[KnownWrong]] | None = None) -> list[KnownWrong]:
    return list((BY_SCRIP if entries is None else entries).get(scrip, ()))


def scrips(entries: dict[str, list[KnownWrong]] | None = None) -> list[str]:
    return sorted(BY_SCRIP if entries is None else entries)
