"""The Results page's KPI figures from the saved statements only (owner, 30 Oct 2026: "that page should only use saved XBRL
statements, no card"; "redesign the entire page as a KPI report").

The company page's Quarterly results table is ``dossier["statements"]`` in each company's memory file: the exchange's XBRL files by
screener's rules, file-labelled. This job turns that same source into one table per quarter and keeps the KPI figures of each in the
``results_kpi`` table, one row per company and quarter, so the page can filter, sort and summarise them in the database. No card, no
AI, no exchange call. Every statement layout (``family``) gives a row: a corporate filer's revenue, EBITDA (operating profit), margin
and profit; a bank's revenue (interest earned), financing profit (after interest and provisions, as Screener), margin and profit; an NBFC's revenue, financing profit and financing margin (in the EBITDA and
margin columns) and profit; an insurer's profit only. A quarter with no profit line has no row. The basis is consolidated when the
statements have the quarter on it with a profit line, else standalone."""

from __future__ import annotations

import hashlib
import json
import logging

from . import fact_sheet, screener_view as sv, statements
from .metrics import CONSOLIDATED, STANDALONE
from .periods import prior_quarter_period, prior_year_period

log = logging.getLogger(__name__)

STATEMENT = "results_kpi_upsert"
PRUNE_STATEMENT = "results_kpi_prune"
PRUNE_BATCH = 200
SAVE_EVERY = 100   # companies read between two saves
QUARTERS_KEPT = 10   # the latest quarters a company keeps: the page's eight-quarter trend, and last quarter's growth for momentum
# A change across a loss is a named turn, not a per cent; as a sort key it ranks beside the per cents (a loss turned to profit
# first, a profit turned to loss last)
TURN_KEY = {"LOSS_TO_PROFIT": 1e6, "LOSS_NARROWED": 1e5, "LOSS_WIDENED": -1e5, "PROFIT_TO_LOSS": -1e6}
# family -> (revenue row, EBITDA row, margin row) of its saved statements; None: the family has no such line
LAYOUT = {sv.CORPORATE: ("Sales", "Operating Profit", "OPM %"),
          # a bank takes Screener's own rows (screener_view.bank_pl): Financing Profit = Revenue - Interest - Expenses, provisions inside Expenses,
          # and its margin, in the EBITDA and margin slots (owner, 31 Oct 2026: "match Screener; banks get a figure"); the page keeps banks out
          # of the EBITDA tile and medians
          sv.BANK: ("Revenue", "Financing Profit", "Financing Margin %"),
          sv.NBFC: ("Revenue", "Financing Profit", "Financing Margin %"),
          sv.INSURER: (None, None, None),
          # a REIT or InvIT files the corporate lines (reit_results.py); only its kind differs on the page
          "reit": ("Sales", "Operating Profit", "OPM %"),
          "invit": ("Sales", "Operating Profit", "OPM %")}
# a company on the NBFC template whose NSE industry is known and is not financial services is no lender: its page is the corporate one
# (measured 31 Oct 2026, live: WESTLIFE restaurants, KIRLOSIND industrial products, HEALTHX healthcare services, RTNINDIA e-retail and
# IBULLSLTD commercial services file the NBFC template and showed as NBFCs, their EBITDA the financing profit; nbfc_pl also holds Sales / Operating Profit / OPM %)
PAT_ROWS = (fact_sheet.OWNERS, "Net Profit")   # the profit to shareholders when the file has it, else the net profit
EXCEPTIONAL_AT = "Exceptional items AT"   # screener_view._exceptional_rows: the exceptional item after its tax (a gain is positive); corporate, bank and NBFC filers
EXCEPTIONAL = "Exceptional items"


def insurer_industry(industry: str | None) -> bool:
    """True when NSE's industry is an insurance one ("Financial Services > Insurance > Life Insurance")."""
    return "insurance" in (industry or "").lower()


def non_lender(industry: str | None) -> bool:
    """True when the industry is known and is not financial services ("Financial Services > ..." or a bare "Finance"); an unknown one is not."""
    text = (industry or "").strip().lower()
    return bool(text) and not text.startswith("financial services") and text != "finance"


def _entry(dossier: dict, period: str | None, basis: str) -> dict | None:
    """The file-labelled quarters-table entry of a period and basis (any family), or None."""
    if not period:
        return None
    for e in dossier.get(statements.KEY, []) or []:
        if (isinstance(e, dict) and e.get("table") == "quarters" and e.get("period") == period and e.get("basis") == basis
                and e.get("family") in LAYOUT and (e.get("lab") or {}).get("by") == "file"):
            return _without_pat_slip(_owners_that_add_up(_without_filler_owners(e)))
    return None


def _without_filler_owners(e: dict) -> dict:
    """The entry with an owners' profit of exactly 0 beside a net profit that is not replaced by that net profit: a filler (measured
    31 Oct 2026, the live table: 204 quarters at 0, e.g. PNB Housing Q2FY27, CreditAccess, Kaynes Q2FY26, Goldiam; the NBFC template is
    read without the corporate guard of screener_view); a listed parent's shareholders never own none of a profit. The owners' row is
    kept, at the net profit, so a quarter whose owners' row is real still finds its year-ago base on the same row (Kaynes Q1FY27 PAT 56.43
    against Q1FY26 74.61 had no YoY when the filler row was dropped)."""
    rows = e.get("rows") or {}
    if rows.get(fact_sheet.OWNERS) == 0 and rows.get("Net Profit") not in (None, 0):
        return {**e, "rows": {**rows, fact_sheet.OWNERS: rows["Net Profit"]}}
    return e


def _owners_that_add_up(e: dict) -> dict:
    """An owners' profit that does not add up with the minority's share to the whole profit is the whole profit less the minority's (the
    rule reit_results.read applies, within max(0.01 Cr, 0.5%)). Measured 31 Oct 2026, ATUL Q2FY26 consolidated, NSE's own file
    INTEGRATED_FILING_INDAS_1551863: ProfitLossForPeriod 182.37, owners 87.95, minority 3.13 (the owners' tag is a slip; Screener 182,
    Tijori 179.24 = 182.37 - 3.13), so Q2FY27 showed +77.1% where the truth is about -13%. Without a minority row nothing says what the
    owners' share should be, so the owners' row stays (a filler 0 is handled above, a wrong sign by the slip guard)."""
    rows = e.get("rows") or {}
    owners, minority, net = rows.get(fact_sheet.OWNERS), rows.get("Minority share"), rows.get("Net Profit")
    if owners is None or minority is None or net is None or abs(owners + minority - net) <= max(0.01, abs(net) / 200):
        return e
    return {**e, "rows": {**rows, fact_sheet.OWNERS: round(net - minority, 2)}}


SLIP_MIN = 5.0   # Cr: a profit this far from PBT - tax, and on the other side of zero, is a slip
SLIP_SHARE = 0.5


def _without_pat_slip(e: dict) -> dict:
    """A corporate quarter whose profit line is on the other side of zero from Profit before tax - Tax, and further from it than
    max(5 Cr, half of it), has PBT - Tax as its profit (measured 31 Oct 2026, live: APARINDS Q1FY27 PAT -138.56 beside EBITDA 757.57 and
    revenue 6,591; four other sites show 467.45). The corporate PBT already holds the associates' share, the regulatory deferral
    movement and the discontinued operations after tax (screener_view), and Tax is the continuing tax, so PBT - Tax is the whole profit;
    the owners' profit is that less the minority's share (without a minority row it is guarded only when it equals the whole). A genuine
    loss (same side of zero) stays. Other families are not guarded: their PBT is not built the same way."""
    rows = e.get("rows") or {}
    pbt, tax = rows.get("Profit before tax"), rows.get("Tax")
    if e.get("family") != sv.CORPORATE or pbt is None or tax is None:
        return e
    whole = round(pbt - tax, 2)
    fixed = dict(rows)
    net = rows.get("Net Profit")
    for row, expected in (("Net Profit", whole), (fact_sheet.OWNERS, None)):
        value = rows.get(row)
        if value is None:
            continue
        if expected is None:
            minority = rows.get("Minority share")
            if minority is None:
                minority = 0.0 if value == net else None
            if minority is None:
                continue
            expected = round(whole - minority, 2)
        if value * expected < 0 and abs(value - expected) > max(SLIP_MIN, SLIP_SHARE * abs(expected)):
            fixed[row] = expected
    return e if fixed == rows else {**e, "rows": fixed}


def _line(key: str, row: str, now: dict, before: dict) -> dict | None:
    """One line of a table: its value, the same line a year and a quarter earlier, and the changes worked out here."""
    value = (now.get("rows") or {}).get(row)
    if value is None:
        return None
    line: dict = {"value": round(value, 2)}
    for slot, tag in (("prev_year", "yoy"), ("prev_quarter", "qoq")):
        base = ((before[slot] or {}).get("rows") or {}).get(row)
        if base is None:
            continue
        line[slot] = round(base, 2)
        change = fact_sheet._change(value, base, key)
        if base == 0 and value < 0 and change.get("turn") == "PROFIT_TO_LOSS":
            change = {"turn": "LOSS_WIDENED"}   # from nothing to a loss is a loss that appeared, not a profit that turned (a zero is no profit)
        if "pct" in change:
            line[f"{tag}_pct"] = change["pct"]
        elif "turn" in change:
            line[f"{tag}_turn"] = change["turn"]
    return line


def _before_exceptional(now: dict, before: dict, pat_row: str, pat: dict) -> dict | None:
    """The profit before exceptional items: the PAT line's own row less the exceptional item after tax (Ind AS 1 shows it apart; brokers
    quote adjusted PAT beside the reported), and its change on the same rule as the PAT's. Only when the quarter has a non-zero exceptional
    item after tax (else it is the PAT). The year-ago base is the same row less that quarter's exceptional item after tax; a quarter
    that filed no exceptional line at all had none. None when the quarter has no such item or the base cannot be worked out."""
    rows = now.get("rows") or {}
    at = rows.get(EXCEPTIONAL_AT)
    if at is None or round(at, 2) == 0 or rows.get(pat_row) is None:
        return None
    line: dict = {"value": round(rows[pat_row] - at, 2)}
    for slot, tag in (("prev_year", "yoy"), ("prev_quarter", "qoq")):
        base_rows = (before[slot] or {}).get("rows") or {}
        if base_rows.get(pat_row) is None:
            continue
        base_at = base_rows.get(EXCEPTIONAL_AT)
        if base_at is None and base_rows.get(EXCEPTIONAL) is not None:
            continue   # a line was filed but its tax could not be worked out: the base is not known
        base = round(base_rows[pat_row] - (base_at or 0.0), 2)
        if slot == "prev_year":
            line["prev_year"] = base
        change = fact_sheet._change(line["value"], base, "pat")
        if base == 0 and line["value"] < 0 and change.get("turn") == "PROFIT_TO_LOSS":
            change = {"turn": "LOSS_WIDENED"}
        if "pct" in change:
            line[f"{tag}_pct"] = change["pct"]
        elif "turn" in change:
            line[f"{tag}_turn"] = change["turn"]
    return line


def table_of(dossier: dict, period: str, industry: str | None = None) -> dict | None:
    """A quarter's table: ``lens`` (the kind: company, bank, nbfc, insurer), period, basis, source filing and one entry per line (revenue, ebitda, pat,
    ebitda_margin), or None when the statements hold no profit line for it. ``industry`` (NSE's, from the companies table): an NBFC-template
    filer in a known industry that is not financial services is built with the corporate layout and kind "company"."""
    prior = {"prev_year": prior_year_period(period), "prev_quarter": prior_quarter_period(period)}
    for basis in (CONSOLIDATED, STANDALONE):
        now = _entry(dossier, period, basis)
        if now is None:
            continue
        before = {slot: _entry(dossier, p, basis) for slot, p in prior.items()}
        layout = now["family"]
        if layout == sv.NBFC:
            # an insurer on the NBFC template has no financing profit (measured 31 Oct 2026, live: MFSL, "Financial Services > Insurance >
            # Life Insurance", showed "financing profit" and kind nbfc; 7 such rows): the insurer's page, profit only
            layout = sv.CORPORATE if non_lender(industry) else sv.INSURER if insurer_industry(industry) else layout
        revenue_row, ebitda_row, margin_row = LAYOUT[layout]
        # the profit's comparatives are the same row as its value (a total with minority interest is no base for the owners' profit)
        pat_row = next((r for r in PAT_ROWS if (now.get("rows") or {}).get(r) is not None), None)
        pat = _line("pat", pat_row, now, before) if pat_row else None
        if pat is None:
            continue
        table: dict = {"lens": "company" if layout == sv.CORPORATE else layout, "period": period, "basis": basis, "source_news_id": now.get("source_news_id"), "pat": pat}
        pre = _before_exceptional(now, before, pat_row, pat)
        if pre is not None:
            table["pat_pre"] = pre
        for key, row in (("revenue", revenue_row), ("ebitda", ebitda_row)):
            line = _line(key, row, now, before) if row else None
            if line is not None:
                table[key] = line
        margin = (now.get("rows") or {}).get(margin_row) if margin_row else None
        if margin is not None:
            line = {"value": round(margin, 2)}
            for slot, tag in (("prev_year", "yoy"), ("prev_quarter", "qoq")):
                base = ((before[slot] or {}).get("rows") or {}).get(margin_row)
                if base is not None:
                    line[slot] = round(base, 2)
                    base_ebitda = ((before[slot] or {}).get("rows") or {}).get(ebitda_row)
                    # a change in margin means nothing when either margin is past +-100% or the base EBITDA is negative (measured 31 Oct
                    # 2026, live: SADHNANIQ Q2FY27 17.92% against -628.89% gave +64,681 bp, MAHLIFE +12,909): no bps, so no filter or sort reads it
                    if abs(margin) <= 100 and abs(base) <= 100 and not (base_ebitda is not None and base_ebitda < 0):
                        line[f"{tag}_bps"] = round((margin - base) * 100)
            table["ebitda_margin"] = line
        return table
    return None


def company_tables(dossier: dict, kept: int = QUARTERS_KEPT, industry: str | None = None) -> dict[str, dict]:
    """Quarter -> table for one company, from its statements only."""
    periods = sorted({e["period"] for e in dossier.get(statements.KEY, []) or []
                      if isinstance(e, dict) and e.get("table") == "quarters" and str(e.get("period", "")).startswith("Q")},
                     key=lambda p: sv.quarter_index(p) or 0, reverse=True)[:kept]
    out: dict[str, dict] = {}
    for period in periods:
        table = table_of(dossier, period, industry)
        if table is not None:
            out[period] = table
    return out


def _growth_key(line: dict, tag: str) -> float | None:
    """The sort key of a line's year-on-year change: its per cent, else its named turn's number, else None."""
    if line.get(f"{tag}_pct") is not None:
        return line[f"{tag}_pct"]
    return TURN_KEY.get(line.get(f"{tag}_turn"))


def kpi_row(scrip: str, table: dict, at: str) -> dict:
    """One ``results_kpi`` row from a quarter's table: the figures, their changes, and a digest of them (an unchanged row is not
    rewritten in the database). The keys are the table's column names."""
    revenue, ebitda, pat, opm = table.get("revenue") or {}, table.get("ebitda") or {}, table.get("pat") or {}, table.get("ebitda_margin") or {}
    pre = table.get("pat_pre") or {}
    kind = table["lens"]
    news_id = table.get("source_news_id")
    row = {"scrip_code": scrip, "period": table["period"], "basis": table["basis"], "kind": kind,
           "source_news_id": news_id if isinstance(news_id, str) and news_id.startswith("nse-") else None,
           "revenue": revenue.get("value"), "revenue_prev": revenue.get("prev_year"),
           "revenue_yoy": revenue.get("yoy_pct"), "revenue_qoq": revenue.get("qoq_pct"),
           "ebitda": ebitda.get("value"), "ebitda_prev": ebitda.get("prev_year"), "ebitda_yoy": ebitda.get("yoy_pct"),
           "ebitda_qoq": ebitda.get("qoq_pct"), "ebitda_turn": ebitda.get("yoy_turn"), "ebitda_key": _growth_key(ebitda, "yoy"),
           "pat": pat.get("value"), "pat_prev": pat.get("prev_year"), "pat_yoy": pat.get("yoy_pct"), "pat_qoq": pat.get("qoq_pct"),
           "pat_turn": pat.get("yoy_turn"), "pat_qoq_turn": pat.get("qoq_turn"), "pat_key": _growth_key(pat, "yoy"),
           "opm": opm.get("value"), "opm_yoy_bps": opm.get("yoy_bps"), "opm_qoq_bps": opm.get("qoq_bps")}
    # profit not from operations: an ordinary company's profit up (or a loss turned to profit) while its EBITDA fell
    row["nfo"] = int(kind == "company"
                     and ((row["pat_yoy"] or 0) > 0 or row["pat_turn"] == "LOSS_TO_PROFIT")
                     and ((row["ebitda_yoy"] or 0) < 0 or row["ebitda_turn"] in ("PROFIT_TO_LOSS", "LOSS_WIDENED")))
    # the profit before exceptional items, only where there is one: a row without it keeps the digest it had before the columns existed,
    # so the rebuild rewrites no row (D1 writes) that has nothing to add
    if pre:
        row.update({"pat_pre": pre.get("value"), "pat_pre_prev": pre.get("prev_year"), "pat_pre_yoy": pre.get("yoy_pct"),
                    "pat_pre_turn": pre.get("yoy_turn")})
    row["digest"] = hashlib.sha1(json.dumps(row, sort_keys=True).encode()).hexdigest()[:16]
    row["updated_at"] = at
    return row


def company_rows(scrip: str, dossier: dict, at: str, industry: str | None = None) -> list[dict]:
    """The KPI rows of one company, newest quarter first."""
    return [kpi_row(scrip, table, at) for table in company_tables(dossier, industry=industry).values()]


def industries(sink) -> dict[str, str]:
    """Scrip -> NSE's industry for every stored company that has one (the companies table, paged: export_companies)."""
    from .company_master import stored_companies

    return {c["scrip_code"]: c["industry"] for c in stored_companies(sink) if c.get("industry")}


def recent_scrips(sink) -> list[str]:
    """The companies with a results card in the live window: the query the results catch-up already uses (event_catchup)."""
    import datetime

    from .event_catchup import MAX_CARDS, RESULTS_DAYS
    from .timeutil import today_ist

    since = (today_ist() - datetime.timedelta(days=RESULTS_DAYS)).isoformat()
    return sorted({r["scrip_code"] for r in sink.query("results_cards_recent", [since, MAX_CARDS]) if r.get("scrip_code")})


def write(sink, at: str, scrips: list[str] | None = None) -> int:
    """Read each company's statements and put its quarters' KPI rows into the database; ``scrips`` None: every stored company (the full
    rebuild); a list: only those (each pipeline run does the live window's companies, so a run reads a few hundred memory files, not
    all of them). The rows are saved every ``SAVE_EVERY`` companies, so a run that is stopped keeps what it did (and the page fills as it
    goes). A company whose read fails is logged and keeps its old rows. Returns the number of rows sent."""
    names = sink.list_dossiers() if scrips is None else scrips
    try:
        industry = industries(sink)
    except Exception as exc:  # noqa: BLE001 - the 15-minute run builds this table too: without industries it builds as before, it does not stop
        log.warning("results-table: industries not read (%s); NBFC-template filers keep the NBFC layout this run", exc)
        industry = {}
    rows: list[dict] = []
    kept: list[dict] = []
    sent = 0

    def save() -> None:
        nonlocal sent
        if rows:
            sink.execute(STATEMENT, rows)
            for at_ in range(0, len(kept), PRUNE_BATCH):
                sink.execute(PRUNE_STATEMENT, kept[at_:at_ + PRUNE_BATCH])
            sent += len(rows)
        rows.clear()
        kept.clear()

    for i, scrip in enumerate(names, 1):
        try:
            found = company_rows(scrip, sink.get_dossier(scrip) or {}, at, industry.get(scrip))
        except Exception as exc:  # noqa: BLE001 - one company's bad file must not stop the rest
            log.warning("results-table: %s not read: %s", scrip, exc)
            continue
        rows += found
        if found:   # a company with no rows now is left alone: an empty read is not proof its old rows are wrong
            kept.append({"scrip_code": scrip, "periods": [r["period"] for r in found]})
        if i % SAVE_EVERY == 0:
            save()
            log.info("results-table: %d of %d companies read, %d rows sent", i, len(names), sent)
    save()
    return sent
