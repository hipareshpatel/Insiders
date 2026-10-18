"""Memory stores only trusted figures (audit round 2, 2026-10-18).

Memory carried slips forward onto every later card: Magellanic's ₹12.76 Cr GAIL order stored as ₹127.62 Cr (the
LOA said 127.62 million) and then counted in ORDER_FLOW on three cards; Bandhan's net worth stored 100x too small
("contingent liabilities 110x net worth"); SBI Life's expense ratio 100x. Memory points were wrong on 37 of 90
round-2 cards. So a figure the model read goes into memory only when the checks confirm it: printed in this filing
at its declared unit, and within ten times of what the company is known to be (revenue, net worth, market cap).
Anything else stays on the card it came from and is never reused. XBRL figures are added after this, unfiltered.
"""

from __future__ import annotations

import logging

from .grounding import SourceIndex, declared_unit
from .models import Pass2Output

log = logging.getLogger(__name__)

SCALE_LIMIT = 10                      # times the company's known scale, either way
TWO_WAY = {"revenue", "revenue_from_operations", "total_income", "net_worth", "net_sales", "sales"}


def _decimals(value: float) -> int:
    text = f"{value:.4f}".rstrip("0")
    return len(text.partition(".")[2])


class Checker:
    def __init__(self, filed_text: str, company: dict | None, dossier: dict | None):
        self.index = SourceIndex(filed_text or "")
        unit = declared_unit(filed_text or "")
        # at the unit the filing declares; with none declared, as crore or as rupees written in full
        self.scales = (unit,) if unit else (1, 1e7)
        from .scoring import ttm_revenue
        from .signals import _latest_net_worth

        dossier = dossier or {}
        refs = {"market cap": (company or {}).get("market_cap_cr"), "net worth": _latest_net_worth(dossier)}
        ttm = ttm_revenue(dossier)
        refs["revenue"] = ttm[0] if ttm else None
        self.refs = {k: float(v) for k, v in refs.items() if v}
        self.history = {}   # what XBRL says the company is, metric by metric: the two-way test uses only these
        for m in dossier.get("financial_metrics", []):
            if str(m.get("value_news_id") or m.get("source_news_id") or "").startswith("xbrl:") and m.get("value"):
                self.history.setdefault(m["metric"], []).append(abs(m["value"]))
        for snap in dossier.get("balance_sheet", []):
            if str(snap.get("source_news_id") or "").startswith("xbrl:") and snap.get("net_worth_cr"):
                self.history.setdefault("net_worth", []).append(abs(snap["net_worth_cr"]))

    def printed_crore(self, value: float) -> bool:
        return self.index.stated_crore(abs(value), _decimals(value), plain_scales=self.scales)

    def printed(self, value: float) -> bool:
        return self.index.stated(abs(value), _decimals(value), (1,))

    def in_scale(self, value: float, metric: str = "") -> bool:
        v = abs(value)
        if not self.refs:
            return True
        if v > SCALE_LIMIT * max(self.refs.values()):
            return False
        same = self.history.get(metric) or []
        if metric in TWO_WAY and same and v > 0 and v * SCALE_LIMIT < min(same):
            return False
        return True

    def amount_ok(self, value: float | None, metric: str = "") -> bool:
        return value is not None and self.printed_crore(value) and self.in_scale(value, metric)


def for_memory(out: Pass2Output, filed_text: str, company: dict | None, dossier: dict | None) -> tuple[Pass2Output, list[str]]:
    """A copy of the output carrying only the figures memory may keep; the card keeps its own."""
    copy = out.model_copy(deep=True)
    delta, check, notes = copy.dossier_delta, Checker(filed_text, company, dossier), []
    kept = []
    for m in delta.financial_metrics:
        ok = (check.amount_ok(m.value, m.metric) if (m.unit or "INR_CR") == "INR_CR"
              else m.value is not None and check.printed(m.value))
        if not ok:
            notes.append(f"{m.metric} {m.period} {m.value} {m.unit or ''}".strip())
            continue
        for field in ("yoy_pct", "qoq_pct"):   # a change the model worked out is not a fact to reuse
            value = getattr(m, field, None)
            if value is not None and not check.printed(value):
                setattr(m, field, None)
        kept.append(m)
    delta.financial_metrics = kept
    sheet = delta.balance_sheet
    if sheet is not None:
        derived = sheet.net_debt_cr
        for field, value in sheet.model_dump().items():
            if isinstance(value, float) and field.endswith("_cr") and field != "net_debt_cr" \
                    and not check.amount_ok(value, field[:-3]):
                setattr(sheet, field, None)
                notes.append(f"balance sheet {field} {value}")
        # net debt is gross debt less cash: kept when both are confirmed and it adds up, or when printed itself
        if derived is not None and not check.amount_ok(derived, "net_debt") and not (
                sheet.gross_debt_cr is not None and sheet.cash_cr is not None
                and abs(sheet.gross_debt_cr - sheet.cash_cr - derived) <= max(0.06, abs(derived) * 0.002)):
            sheet.net_debt_cr = None
            notes.append(f"balance sheet net_debt_cr {derived}")
    segments = []
    for s in delta.segment_mix:
        values = [v for k, v in s.model_dump().items() if isinstance(v, float) and k not in ("yoy_pct", "qoq_pct")]
        if all(check.printed(v) or check.printed_crore(v) for v in values):
            segments.append(s)
        else:
            notes.append(f"segment {s.segment} {values}")
    delta.segment_mix = segments
    deal = copy.card.deal_value if copy.card is not None else None
    if deal is not None and deal.amount_cr and not check.amount_ok(deal.amount_cr):
        notes.append(f"deal amount {deal.amount_cr}")
        deal.amount_cr = None
    if notes:
        log.info("memory: kept on the card only, not confirmed at the filing's unit and the company's scale: %s", notes[:12])
    return copy, notes
