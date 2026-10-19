"""Stage 0 XBRL fast path (blueprint §5.1): machine-tagged figures from the filing's XBRL file.

Listed companies file results (Reg 33) and shareholding patterns (Reg 31) in XBRL beside the PDF.
The tagged figures are exact, so they take precedence over figures the model reads from the PDF:

* Results: revenue, other income, cost lines, finance cost, depreciation, PBT, taxes, PAT, EPS
  and paid-up capital per period (quarter, half year, nine months, year), with EBITDA and its
  margin derived, YoY/QoQ from the comparative columns, and net worth, debt and cash when a
  balance sheet is tagged. Results still go to Pass 2 for the narrative; the XBRL table is put at
  the top of the prompt and its figures overwrite the model's in memory.
* Shareholding patterns: promoter, pledge, FII and DII percentages and the number of small
  shareholders go straight to memory with no AI call.

Parsing is namespace-agnostic (BSE's in-bse-fin / in-bse-shp taxonomies have changed names
between versions); figures are matched by element name, periods come from the context dates, and
facts with dimensions (segments, categories) are kept apart from the totals. Monetary values are
in rupees and are converted to ₹ crore. A results file whose revenue or profit cannot be found in
the PDF text in any common unit is treated as unconfirmed and not used (a wrongly scaled filing).
"""

from __future__ import annotations

import logging
import math
import re
import statistics
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date

from .models import BalanceSheet, FinancialMetric, Ownership
from .periods import canonical_period, prior_quarter_period, prior_year_period

log = logging.getLogger(__name__)

# element name -> dossier metric (first match wins for each metric)
RESULT_TAGS = {
    "RevenueFromOperations": "revenue",
    "OtherIncome": "other_income",
    "Income": "total_income",
    "CostOfMaterialsConsumed": "raw_material_cost",
    "PurchasesOfStockInTrade": "purchases_stock_in_trade",
    "ChangesInInventoriesOfFinishedGoodsWorkInProgressAndStockInTrade": "inventory_change",
    "EmployeeBenefitExpense": "employee_cost",
    "FinanceCosts": "finance_cost",
    "DepreciationDepletionAndAmortisationExpense": "depreciation",
    "DepreciationAndAmortisationExpense": "depreciation",
    "OtherExpenses": "other_expenses",
    "Expenses": "total_expenses",
    "ExceptionalItemsBeforeTax": "exceptional_items",
    "ExceptionalItems": "exceptional_items",
    "ProfitBeforeTax": "pbt",
    "ProfitLossBeforeTax": "pbt",
    "CurrentTax": "current_tax",
    "DeferredTax": "deferred_tax",
    "TaxExpense": "tax_expense",
    "ProfitLossForPeriod": "pat",
    "ProfitLossForThePeriod": "pat",
    "ProfitLossForPeriodFromContinuingOperations": "pat_continuing",
    # the shareholders' share, apart from minority interests: Bajaj Finserv's ₹6,296.67 Cr consolidated profit is
    # ₹3,132 Cr to its owners, and the card gave the first as the company's (round 6, 2026-10-19)
    "ProfitOrLossAttributableToOwnersOfParent": "pat_owners",
    # excise collected for the government sits inside revenue: ITC's Q1FY27 revenue "+27.6%" was -11% net of it (round 6)
    "ExciseDuty": "excise_duty",
    "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations": "eps",
    "BasicEarningsLossPerShareFromContinuingOperations": "eps",
    "BasicEarningsPerShare": "eps",
    "PaidUpValueOfEquityShareCapital": "paid_up_capital",
    # Banks file the banking template, not the commercial one, so none of the names above appear on a
    # bank's results and its memory held almost nothing: no top line, no PBT, no interest cost (found on
    # CSB Bank, audit round 1 - 6 of 12 metrics). Interest earned is the top line of a bank's statement,
    # interest expended its cost of funds, and operating profit before provisions its pre-provision
    # operating profit, which is the figure a bank is read on rather than EBITDA.
    # EPS too: the banking template reports it before and after extraordinary items (the RBI Form B
    # names), not under the commercial tag, so SBI and CSB Bank had no EPS at all. Where a bank
    # reports both and they differ, the first in the document wins, as for every other metric.
    "BasicEarningsPerShareAfterExtraordinaryItems": "eps",
    "BasicEarningsPerShareBeforeExtraordinaryItems": "eps",
    "InterestEarned": "interest_earned",
    "InterestExpended": "interest_expended",
    "OperatingProfitBeforeProvisionAndContingencies": "pre_provision_operating_profit",
    "ProvisionsOtherThanTaxAndContingencies": "provisions",
    "ProfitLossFromOrdinaryActivitiesBeforeTax": "pbt",
    "EmployeesCost": "employee_cost",
    "OperatingExpenses": "other_expenses",
}
# Insurers file neither template above. SEBI gives them their own taxonomies and the names share almost
# nothing with a manufacturer's: a general insurer's top line is premium earned and its profit comes out of
# an underwriting account, a life insurer's is net premium income with the result struck in a shareholders'
# account below a policyholders' one. With only the commercial map, ICICI Lombard yielded 4 metrics of 23
# and HDFC Life 8, so cards for 198 financial companies had almost nothing machine-tagged to stand on.
#
# These are overlays, not additions, because one name means two things: `ProvisionForTax` is the tax on a
# general insurer's profit but a life insurer's POLICYHOLDERS' tax, nowhere near the tax on its result. The
# taxonomy each instance declares picks the overlay, and a None suppresses a commercial tag that would
# otherwise read the wrong account.
GENERAL_INSURANCE_TAGS = {
    "GrossPremiumsWritten": "gross_premium",
    "NetPremiumWritten": "net_premium",
    "PremiumEarned": "revenue",          # net earned premium is the top line of the revenue account
    "IncurredClaims": "incurred_claims",
    "NetCommission": "commission",
    "ProfitOrLossBeforeTax": "pbt",
    "ProfitLossAfterTax": "pat",
    "ProvisionForTax": "tax_expense",
    "BasicAndDilutedEPSAfterExtraordinaryItemsNetOfTaxExpenseForThePeriodNotToBeAnnualized": "eps",
}
LIFE_INSURANCE_TAGS = {
    "GrossPremiumIncome": "gross_premium",
    "NetPremiumIncome": "revenue",
    "IncomeFirstYearPremium": "first_year_premium",
    "IncomeRenewalPremium": "renewal_premium",
    "IncomeSinglePremium": "single_premium",
    "BenefitsPaidNet": "benefits_paid",
    "NetCommission": "commission",
    "NetSurplusDeficit": "surplus",
    "ProfitLossAfterTaxAndExtraordinaryItems": "pat",
    "ProvisionsForTaxes": "tax_expense",      # the shareholders' account, where the result is struck
    "ProvisionForTax": None,                  # the policyholders' account: not the tax on this profit
    "CurrentTax": None,
    "BasicAndDilutedEPSAfterExtraordinaryItemsNetOfTaxExpenseForThePeriodNotToBeAnnualized": "eps",
}
OVERLAYS = {"GI": GENERAL_INSURANCE_TAGS, "LI": LIFE_INSURANCE_TAGS}
# Ratios an insurer reports as a fraction (1.0705) and everyone quotes as a percentage. The combined ratio
# is the one general insurance is read on: above 100% the underwriting itself loses money. Solvency is
# deliberately left out - filers disagree on its scale (0.0275 against 1.8 for the same kind of number).
RATIO_TAGS = {
    "CombinedRatio": "combined_ratio",
    "IncurredClaimRatio": "claims_ratio",
    "NetRetentionRatio": "retention_ratio",
    "ExpensesOfManagementRatio": "expense_ratio",
    # A bank's asset quality and return, on the banking template as fractions (CSB Bank Q3FY25: 0.0158 gross NPA,
    # 0.0064 net, 0.0148 return on assets). A bank is read on these before its profit, and its card had none of them.
    "PercentageOfGrossNpa": "gnpa_pct",
    "PercentageOfNpa": "nnpa_pct",
    "ReturnOnAssets": "roa_pct",
}
# The range a bank ratio can take as a percentage; a filer that already wrote 1.58 for 1.58% would read as 158%.
RATIO_BOUNDS = {"gnpa_pct": (0.0, 60.0), "nnpa_pct": (0.0, 40.0), "roa_pct": (-20.0, 20.0)}
BALANCE_TAGS = {
    "Equity": "net_worth_cr",
    "EquityAttributableToOwnersOfParent": "net_worth_cr",
    "BorrowingsNoncurrent": "debt_noncurrent",
    "BorrowingsCurrent": "debt_current",
    "CashAndCashEquivalents": "cash_cr",
}
PER_SHARE = {"eps"}
PERCENT = {"ebitda_margin", *RATIO_TAGS.values()}
CONFIRM = ("revenue", "pat")  # figures looked for in the PDF text before the file is trusted


@dataclass
class XbrlResult:
    kind: str                                   # RESULTS or SHAREHOLDING
    basis: str | None = None                    # CONSOLIDATED / STANDALONE
    period: str | None = None                   # the latest period reported
    metrics: list[FinancialMetric] = field(default_factory=list)
    balance_sheet: BalanceSheet | None = None
    ownership: Ownership | None = None
    confirmed: bool = True

    def table(self) -> str:
        """The figures as text for the Pass 2 prompt (and for grounding)."""
        if self.kind == "SHAREHOLDING" and self.ownership:
            o = self.ownership
            parts = [f"{k}: {v}" for k, v in o.model_dump().items() if v is not None]
            return "Shareholding pattern (XBRL, exact): " + "; ".join(parts)
        lines = [f"Machine-tagged results (XBRL, {self.basis or 'basis not stated'}, ₹ crore unless noted; exact, "
                 "prefer these over figures read from the PDF):"]
        for m in self.metrics:
            unit = " ₹/share" if m.unit == "INR" else " %" if m.unit == "PCT" else " Cr"
            change = "".join(f", {label} {v:+.1f}%" for label, v in (("YoY", m.yoy_pct), ("QoQ", m.qoq_pct)) if v is not None)
            lines.append(f"- {m.metric} {m.period}: {m.value:g}{unit}{change}")
        if self.balance_sheet and not self.balance_sheet.is_empty():
            b = self.balance_sheet
            lines.append(f"- balance sheet {b.period}: " + ", ".join(
                f"{k} {v:g}" for k, v in b.model_dump().items() if isinstance(v, float)))
        return "\n".join(lines)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _contexts(root) -> dict[str, dict]:
    out = {}
    for ctx in root.iter():
        if _local(ctx.tag) != "context":
            continue
        info: dict = {"dims": {}}
        for el in ctx.iter():
            name = _local(el.tag)
            if name in ("startDate", "endDate", "instant") and el.text:
                try:
                    info[name] = date.fromisoformat(el.text.strip()[:10])
                except ValueError:
                    pass
            elif name in ("explicitMember", "typedMember"):
                info["dims"][_local(el.get("dimension", ""))] = (el.text or "").strip().rsplit(":", 1)[-1]
        out[ctx.get("id")] = info
    return out


def _units(root) -> dict[str, str]:
    """unit id -> MONEY, PER_SHARE, SHARES or PURE."""
    out = {}
    for unit in root.iter():
        if _local(unit.tag) != "unit":
            continue
        measures = [(m.text or "").upper() for m in unit.iter() if _local(m.tag) == "measure"]
        divide = any(_local(el.tag) == "divide" for el in unit.iter())
        if divide:
            out[unit.get("id")] = "PER_SHARE"
        elif any("INR" in m for m in measures):
            out[unit.get("id")] = "MONEY"
        elif any("SHARES" in m for m in measures):
            out[unit.get("id")] = "SHARES"
        else:
            out[unit.get("id")] = "PURE"
    return out


def _facts(root):
    for el in root.iter():
        ctx = el.get("contextRef")
        if ctx is None or el.text is None:
            continue
        yield _local(el.tag), ctx, el.get("unitRef"), el.text.strip()


def _num(text: str) -> float | None:
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _months(info: dict) -> int | None:
    if "startDate" not in info or "endDate" not in info:
        return None
    return round(((info["endDate"] - info["startDate"]).days + 1) / 30.44)


def _fy_end(d: date) -> int:
    return d.year if d.month <= 3 else d.year + 1


def period_label(info: dict) -> str | None:
    months, end = _months(info), info.get("endDate")
    if not end or months is None:
        return None
    if months == 3:
        return canonical_period(f"quarter ended {end:%d.%m.%Y}")
    fy = f"FY{_fy_end(end) % 100:02d}"
    if months == 12 and end.month == 3:
        return fy
    if months == 6 and end.month in (9, 3):
        return ("H1" if end.month == 9 else "H2") + fy
    if months == 9 and end.month == 12:
        return "9M" + fy
    return None


_TAXONOMY = re.compile(rb"IntegratedFinance_(\w+)")


def taxonomy(data: bytes) -> str:
    """Which SEBI template this instance was filed on: INDAS, NBFC, BANKING, GI or LI ("" if it says)."""
    m = _TAXONOMY.search(data[:8000])
    return m.group(1).decode("ascii", "ignore").upper() if m else ""


def parse(data: bytes) -> XbrlResult | None:
    """Parse an XBRL instance; None when it is not one or holds nothing we use."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    contexts = _contexts(root)
    if not contexts:
        return None
    units = _units(root)
    facts = list(_facts(root))
    names = {name for name, *_ in facts}
    text_facts = {name: value for name, ctx, unit, value in facts if unit is None}
    tags = {**RESULT_TAGS, **OVERLAYS.get(taxonomy(data), {})}
    tags = {name: metric for name, metric in tags.items() if metric}
    if any("Shareholding" in n or "Shareholder" in n for n in names) and not names & set(tags):
        return _shareholding(facts, contexts)
    return _results(facts, contexts, units, text_facts, tags)


def _results(facts, contexts, units, text_facts, tags: dict[str, str] | None = None) -> XbrlResult | None:
    nature = " ".join(v for k, v in text_facts.items() if "Standalone" in k or "Consolidated" in k or k == "NatureOfReport").lower()
    basis = "CONSOLIDATED" if "consolidated" in nature else "STANDALONE" if "standalone" in nature else None
    tags = tags or RESULT_TAGS
    values: dict[tuple[str, str], float] = {}
    ends: dict[str, date] = {}
    balance: dict[str, float] = {}
    balance_date: date | None = None
    for name, ctx, unit, raw in facts:
        info = contexts.get(ctx)
        value = _num(raw)
        if info is None or value is None or info["dims"]:
            continue  # segment and other dimensional facts are not totals
        kind = units.get(unit or "", "PURE")
        if name in tags or name in RATIO_TAGS:
            label = period_label(info)
            if not label:
                continue
            if name in RATIO_TAGS:
                metric = RATIO_TAGS[name]
                if kind != "PURE":
                    continue
                # filed as a fraction, read as a percentage; a bank ratio above 1 was already written as one
                # (assumption, not seen yet: the SEBI template asks for the fraction, CSB Bank files 0.0158)
                if not (metric in RATIO_BOUNDS and abs(value) > 1):
                    value *= 100
                low, high = RATIO_BOUNDS.get(metric, (-math.inf, math.inf))
                if not low <= value <= high:
                    continue
            else:
                metric = tags[name]
                if metric in PER_SHARE:
                    if kind != "PER_SHARE" and kind != "PURE":
                        continue
                elif kind != "MONEY":
                    continue
                else:
                    value = value / 1e7
            values.setdefault((metric, label), value)
            ends[label] = info["endDate"]
        elif name in BALANCE_TAGS and kind == "MONEY" and info.get("instant"):
            if balance_date is None or info["instant"] > balance_date:
                balance, balance_date = {}, info["instant"]
            if info["instant"] == balance_date:
                balance.setdefault(BALANCE_TAGS[name], value / 1e7)
    if not values:
        return None
    # Net NPA cannot exceed gross NPA: when it does, one of the two was read at the wrong scale, so neither is kept
    for label in {p for m, p in values if m == "nnpa_pct"}:
        gross, net = values.get(("gnpa_pct", label)), values.get(("nnpa_pct", label))
        if gross is not None and net is not None and net > gross + 0.005:
            values.pop(("gnpa_pct", label)), values.pop(("nnpa_pct", label))
    # EBITDA = PBT + finance cost + depreciation - other income (exceptional items added back)
    for label in {p for _, p in values}:
        parts = [values.get((m, label)) for m in ("pbt", "finance_cost", "depreciation")]
        if all(v is not None for v in parts):
            ebitda = sum(parts) - (values.get(("other_income", label)) or 0) - (values.get(("exceptional_items", label)) or 0)
            values[("ebitda", label)] = ebitda
            revenue = values.get(("revenue", label))
            if revenue:
                values[("ebitda_margin", label)] = ebitda / revenue * 100
    latest = max(ends, key=lambda p: (ends[p], p.startswith("Q")))
    quarter = max((p for p in ends if p.startswith("Q")), key=lambda p: ends[p], default=None)
    metrics = []
    for (metric, label), value in sorted(values.items(), key=lambda kv: (ends.get(kv[0][1]) or date.min, kv[0][0])):
        unit = "INR" if metric in PER_SHARE else "PCT" if metric in PERCENT else "INR_CR"
        yoy = qoq = None
        if metric not in PERCENT:
            yoy = _change(value, _match(values, ends, metric, label, years=1))
            if label.startswith("Q"):
                qoq = _change(value, _match(values, ends, metric, label, months=3))
        metrics.append(FinancialMetric(metric=metric, period=label, value=round(value, 2), unit=unit,
                                       yoy_pct=yoy, qoq_pct=qoq))
    sheet = None
    if balance:
        debt = [balance[k] for k in ("debt_noncurrent", "debt_current") if k in balance]
        sheet = BalanceSheet(period=canonical_period(f"quarter ended {balance_date:%d.%m.%Y}"),
                             net_worth_cr=_r(balance.get("net_worth_cr")), cash_cr=_r(balance.get("cash_cr")),
                             gross_debt_cr=_r(sum(debt)) if debt else None)
        if sheet.gross_debt_cr is not None and sheet.cash_cr is not None:
            sheet.net_debt_cr = _r(sheet.gross_debt_cr - sheet.cash_cr)
    return XbrlResult("RESULTS", basis, quarter or latest, metrics, sheet)


def _r(v: float | None) -> float | None:
    return round(v, 2) if v is not None else None


def _match(values, ends, metric, label, years: int = 0, months: int = 0) -> float | None:
    end = ends[label]
    target_month = end.month - months
    target = date(end.year - years + (target_month - 1) // 12, (target_month - 1) % 12 + 1, 1)
    kind = re.match(r"(9M|Q|H|FY)", label)
    for other, other_end in ends.items():
        same_kind = re.match(r"(9M|Q|H|FY)", other)
        if other != label and same_kind and kind and same_kind[1] == kind[1] \
                and (other_end.year, other_end.month) == (target.year, target.month):
            return values.get((metric, other))
    return None


def _change(now: float, before: float | None) -> float | None:
    if before is None or before <= 0:
        return None
    return round((now / before - 1) * 100, 1)


def _shareholding(facts, contexts) -> XbrlResult | None:
    """Promoter / FII / DII % and small-holder count from category members."""
    pct: dict[str, list[float]] = {"promoter": [], "fii": [], "dii": [], "pledge": []}
    holders: list[float] = []
    as_of: date | None = None
    for name, ctx, _unit, raw in facts:
        info, value = contexts.get(ctx), _num(raw)
        if info is None or value is None:
            continue
        instant = info.get("instant") or info.get("endDate")
        if instant and (as_of is None or instant > as_of):
            as_of = instant
        members = " ".join(info["dims"].values()).lower()
        lowered = name.lower()
        if "percentage" in lowered and "pledged" in lowered and "promoter" in members:
            pct["pledge"].append(value)
        elif ("percentage" in lowered and ("totalnumberofshares" in lowered or "shareholding" in lowered)
              # A percentage of the holder's own stake, not of the company: CSB Bank's promoter locked-in
              # shares were 80.45% of its holding while the promoter held 49.72% (NSE's own list disagreed,
              # and the seed's cross-check refused to store either figure).
              and not any(w in lowered for w in ("lockedin", "encumber", "assumingfullconversion", "underlyingoutstanding"))):
            if "promoter" in members and "nonpromoter" not in members and "public" not in members:
                pct["promoter"].append(value)
            elif "foreignportfolio" in members or "foreigninstitution" in members or "institutionsforeign" in members:
                pct["fii"].append(value)
            elif "institutionsdomestic" in members or "domesticinstitution" in members:
                pct["dii"].append(value)
        elif "numberofshareholders" in lowered and ("uptorstwolakh" in members or "nominalsharecapitalupto" in members):
            holders.append(value)
    if not pct["promoter"] and not pct["fii"] and not pct["dii"]:
        return None
    scale = 100.0 if max(pct["promoter"] + pct["fii"] + pct["dii"]) <= 1.0 else 1.0  # fractions or percentages

    def top(values: list[float]) -> float | None:  # the category total is the largest of its members
        return round(max(values) * scale, 2) if values else None

    period = canonical_period(f"quarter ended {as_of:%d.%m.%Y}") if as_of else None
    own = Ownership(period=period or "", promoter_pct=top(pct["promoter"]), fii_pct=top(pct["fii"]),
                    dii_pct=top(pct["dii"]), pledge_pct=top(pct["pledge"]),
                    retail_holders=max(holders) if holders else None)
    return XbrlResult("SHAREHOLDING", period=period, ownership=own) if period else None


def confirm(result: XbrlResult, text: str) -> bool:
    """True when the latest revenue or profit appears in the PDF text in ₹ crore, lakh, million or
    thousand (or there is no text to check against). Guards against a file filed in the wrong scale."""
    if not text or result.kind != "RESULTS":
        return True
    figures = {m.metric: m.value for m in result.metrics if m.period == result.period and m.metric in CONFIRM}
    # Every figure zero (a shell company's quarter: no revenue, nil profit) cannot be looked for at any unit;
    # that is no evidence of a wrong scale, and refusing the file left the card to read the PDF alone.
    return appears_in(list(figures.values()), text) is not False


def appears_in(crores: list[float], text: str) -> bool | None:
    """Whether any of these ₹ crore figures is in the text in crore, lakh, million, thousand or rupees: None
    when none is large enough to tell apart from any other number in it (or there are none)."""
    numbers = {round(float(n.replace(",", "")), 0) for n in re.findall(r"\d[\d,]*\.?\d*", text or "")
               if n.replace(",", "").replace(".", "").isdigit()}
    checked = False
    for crore in crores:
        for scale in (1, 100, 10, 10_000, 1e7):  # crore, lakh, million, thousand, rupees
            if abs(crore) * scale < 10:
                continue  # too small to tell apart from any other number in the text
            checked = True
            if round(abs(crore) * scale, 0) in numbers or round(abs(crore) * scale + 0.5, 0) in numbers \
                    or round(abs(crore) * scale - 0.5, 0) in numbers:
                return True
    return False if checked else None


_SCALE_REFERENCE = ("revenue", "total_income", "interest_earned")
_SCALE_TOLERANCE = 0.2   # in powers of ten: within 0.63x-1.58x of an exact 10^k


def _quarters(metrics) -> dict[str, dict[str, float]]:
    """{quarter: {metric: value}} for the single-quarter figures among metrics (XBRL's or memory's)."""
    out: dict[str, dict[str, float]] = {}
    for m in metrics or []:
        get = m.get if isinstance(m, dict) else (lambda key, m=m: getattr(m, key, None))
        period, value = get("period") or "", get("value")
        if re.fullmatch(r"Q[1-4]FY\d\d", period) and isinstance(value, (int, float)) and not isinstance(value, bool):
            out.setdefault(period, {})[get("metric")] = float(value)
    return out


def _shares(figures: dict[str, float]) -> float | None:
    """The share count a quarter's profit and EPS imply, in crore: EPS is per share and keeps its value
    whatever unit a file's amounts are tagged in, so a file in the wrong unit moves this with them."""
    pat, eps = figures.get("pat"), figures.get("eps")
    if pat and eps and abs(eps) >= 0.5 and abs(pat) >= 0.5:
        return abs(pat / eps)
    return None


def scale_slip(result: XbrlResult, history) -> int:
    """The power of ten a results file's amounts are off by, against the company's other quarters; 0 when
    they fit or there is too little to tell.

    Jubilant Pharmova's Q4FY24 file tags revenue as 1,758,600,000 INR with its rounding declared "Lakhs";
    the statement is in millions and the quarter was ₹1,758.6 Cr. Every amount in the file is a tenth of
    its value, so memory held FY24 at ₹670 Cr and the FY25 cards said revenue +979% YoY (2026-10-17).
    confirm() passed it, since 175.86 crore is the statement's 17,586 read as lakh. A slip is told from a
    real fall by two things moving together by the same power of ten: the quarter's revenue, and the share
    count its profit and EPS imply. A business that shrinks keeps its shares; a file in the wrong unit
    does not."""
    if result.kind != "RESULTS" or not result.period:
        return 0
    own = _quarters(result.metrics).get(result.period) or {}
    others = [f for period, f in _quarters(history).items() if period != result.period]

    def power(mine: float | None, theirs: list) -> int | None:
        theirs = [t for t in theirs if t and t > 0]
        if not mine or mine <= 0 or len(theirs) < 2:
            return None
        ratio = math.log10(statistics.median(theirs) / mine)
        k = round(ratio)
        return k if k and abs(ratio - k) <= _SCALE_TOLERANCE else None

    metric = next((m for m in _SCALE_REFERENCE if own.get(m)), None)
    if metric is None:
        return 0
    by_revenue = power(own[metric], [f.get(metric) for f in others])
    by_shares = power(_shares(own), [_shares(f) for f in others])
    return by_revenue if by_revenue is not None and by_revenue == by_shares else 0


def fix_scale(result: XbrlResult | None, history, source: str = "") -> int:
    """Put a results file tagged in the wrong unit right (scale_slip): every ₹ crore amount, the balance
    sheet's included, times the power of ten found. EPS, per-share and percentage figures are left as
    they are. Returns the power applied, 0 for none."""
    k = scale_slip(result, history) if result else 0
    if not k:
        return 0
    factor = 10 ** k
    for m in result.metrics:
        if m.unit == "INR_CR" and m.value is not None:
            m.value = round(m.value * factor, 2)
    if result.balance_sheet:
        for name, value in result.balance_sheet.model_dump().items():
            if name.endswith("_cr") and isinstance(value, (int, float)):
                setattr(result.balance_sheet, name, round(value * factor, 2))
    log.warning("XBRL %s %s: amounts tagged at 10^%d of their value (revenue and the share count its profit "
                "and EPS imply both off by it against the company's other quarters); multiplied by %g",
                source, result.period, -k, factor)
    return k


def add_comparatives(result: XbrlResult, *earlier: XbrlResult) -> int:
    """YoY and QoQ for a results file from the year-ago and previous quarters' own files. BSE's files
    carry only the current quarter and the year to date (Ahluwalia Q3FY25: Q3FY25 and 9MFY25), so the
    changes come from those quarters' filings. Their figures are added for memory too. Returns how
    many changes were filled."""
    if result.kind != "RESULTS":
        return 0
    known = {(m.metric, m.period): m for m in result.metrics}
    for other in earlier:
        if other and other.kind == "RESULTS" and (not result.basis or other.basis in (None, result.basis)):
            for m in other.metrics:
                if (m.metric, m.period) not in known:
                    known[(m.metric, m.period)] = m
                    result.metrics.append(m)
    filled = 0
    for m in result.metrics:
        if m.unit == "PCT" or m.value is None:
            continue
        year_ago = known.get((m.metric, prior_year_period(m.period) or ""))
        if m.yoy_pct is None and year_ago and year_ago.value:
            m.yoy_pct, filled = _change(m.value, year_ago.value), filled + 1
        before = known.get((m.metric, prior_quarter_period(m.period) or "")) if m.period.startswith("Q") else None
        if m.qoq_pct is None and before and before.value:
            m.qoq_pct, filled = _change(m.value, before.value), filled + 1
    return filled
