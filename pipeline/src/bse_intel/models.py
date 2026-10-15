"""Data models: filings, and the strict schemas AI output is validated against.

The AI schemas are deliberately forgiving on *shape* (a string where a list
was expected, "₹1,234.5 Cr" where a number was expected, "HIGH IMPACT" for
"HIGH") and strict on *meaning* (unknown enums, impossible dates, a material
verdict without a card).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

EVENT_TYPES = (
    "RESULTS",
    "CONCALL_PRESENTATION",
    "RIGHTS_ISSUE",
    "FUNDRAISE",
    "CAPEX",
    "M_AND_A",
    "ORDER_WIN",
    "MONTHLY_BUSINESS_UPDATE",
    "DEBT_RATINGS",
    "CORPORATE_ACTION",
    "GOVERNANCE",
    "MANAGEMENT_CHANGE",
    "LITIGATION_REGULATORY",
    "PRODUCT_LAUNCH",
    "OTHER",
)

EVENT_TAGS = {
    "RESULTS": "RESULTS",
    "CONCALL_PRESENTATION": "CONCALL",
    "RIGHTS_ISSUE": "RIGHTS",
    "FUNDRAISE": "FUNDRAISE",
    "CAPEX": "CAPEX",
    "M_AND_A": "M&A",
    "ORDER_WIN": "ORDER WIN",
    "MONTHLY_BUSINESS_UPDATE": "BUSINESS UPDATE",
    "DEBT_RATINGS": "RATINGS",
    "CORPORATE_ACTION": "CORP ACTION",
    "GOVERNANCE": "GOVERNANCE",
    "MANAGEMENT_CHANGE": "MANAGEMENT",
    "LITIGATION_REGULATORY": "REGULATORY",
    "PRODUCT_LAUNCH": "LAUNCH",
    "OTHER": "UPDATE",
}


class Filing(BaseModel):
    """One BSE announcement, as discovered (and as stored in the D1 ledger)."""

    model_config = ConfigDict(extra="ignore")

    news_id: str
    scrip_code: str
    company_name: str
    symbol: str | None = None
    headline: str = ""
    subject: str = ""

    @field_validator("headline", "subject", "category", "subcategory", mode="before")
    @classmethod
    def _text(cls, v: Any) -> str:
        return v or ""  # ledger rows written before these columns existed hold NULL
    category: str = ""
    subcategory: str = ""
    filed_at: str
    filing_date: str
    pdf_url: str | None = None
    attachment_size: Any = None
    critical: bool = False
    # Ledger fields
    status: str = "PENDING"
    route: str = "NONE"
    event_type: str | None = None
    reason: str | None = None
    attempts: int = 0

    def ledger_row(self, updated_at: str) -> dict:
        return {
            "news_id": self.news_id,
            "scrip_code": self.scrip_code,
            "company_name": self.company_name,
            "symbol": self.symbol,
            "headline": self.headline,
            "subject": self.subject,
            "category": self.category,
            "subcategory": self.subcategory,
            "filed_at": self.filed_at,
            "filing_date": self.filing_date,
            "pdf_url": self.pdf_url,
            "status": self.status,
            "route": self.route,
            "event_type": self.event_type,
            "reason": self.reason,
            "updated_at": updated_at,
        }


# --------------------------------------------------------------------------- coercion helpers

_NUM_CLEAN = re.compile(r"[₹,\s]|(?i:rs\.?|inr|%)")
# Unit words scaled to ₹ crore (the unit of every amount field) before they are stripped.
_SCALE_WORDS = (
    (re.compile(r"lakh\s*crores?|lac\s*crores?|lakh\s*cr\b", re.I), 1e5),
    (re.compile(r"\bcrores?\b|\bcr\.?(?![a-z])", re.I), 1.0),
    (re.compile(r"\blakhs?\b|\blacs?\b", re.I), 0.01),
    (re.compile(r"\bbillions?\b|\bbn\b", re.I), 100.0),
    (re.compile(r"\bmillions?\b|\bmn\b|\bmio\b", re.I), 0.1),
    (re.compile(r"\bthousands?\b|\b000s\b", re.I), 1e-4),
)


def _to_float(value: Any) -> float | None:
    """A number from model output: "₹1,250 Cr" -> 1250, "₹85.50 lakh" -> 0.855 (crore), "(12.5)" -> -12.5."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    scale = 1.0
    for pattern, factor in _SCALE_WORDS:
        if pattern.search(text):
            scale = factor
            text = pattern.sub("", text)
            break
    text = _NUM_CLEAN.sub("", text)
    if text in ("", "-", "NA", "N/A", "null", "None"):
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        number = float(text) * scale
    except ValueError:
        return None
    number = round(number, 6) if scale != 1.0 else number
    return -number if negative else number


_PLACEHOLDER = re.compile(r"^(?:[A-Z][A-Z_&]*(?:\s*\|\s*[A-Z][A-Z_&]*)+|string|string or null|YYYY-MM-DD(?: or null)?|g_\.\.\.|w_\.\.\.|d_\.\.\..*)$")


def _strip_placeholders(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_placeholders(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_placeholders(v) for v in value]
    if isinstance(value, str):
        text = value.strip()
        if _PLACEHOLDER.match(text):
            return None
        if text.endswith(" or null"):
            return None  # an answer never ends in "or null"; this is the schema's example
    return value


def _to_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [line.strip(" -•\t") for line in value.splitlines() if line.strip(" -•\t")]
    return [value]


def _to_str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


Num = Annotated[float | None, BeforeValidator(_to_float)]
StrList = Annotated[list[str], BeforeValidator(_to_list)]
OptStr = Annotated[str | None, BeforeValidator(_to_str_or_none)]


def _normalize_event_type(value: Any) -> str:
    text = re.sub(r"[^A-Z]+", "_", str(value or "").upper()).strip("_")
    aliases = {
        "MA": "M_AND_A", "M_A": "M_AND_A", "MERGER": "M_AND_A", "ACQUISITION": "M_AND_A",
        "RIGHTS": "RIGHTS_ISSUE", "RESULT": "RESULTS", "FINANCIAL_RESULTS": "RESULTS",
        "CONCALL": "CONCALL_PRESENTATION", "INVESTOR_PRESENTATION": "CONCALL_PRESENTATION",
        "CREDIT_RATING": "DEBT_RATINGS", "RATINGS": "DEBT_RATINGS", "DEBT": "DEBT_RATINGS",
        "LAUNCH": "PRODUCT_LAUNCH", "ORDER": "ORDER_WIN", "MONTHLY_VOLUMES": "MONTHLY_BUSINESS_UPDATE",
        "BUSINESS_UPDATE": "MONTHLY_BUSINESS_UPDATE", "QIP": "FUNDRAISE", "PREFERENTIAL_ISSUE": "FUNDRAISE",
    }
    text = aliases.get(text, text)
    return text if text in EVENT_TYPES else "OTHER"


EventType = Annotated[str, BeforeValidator(_normalize_event_type)]


def _normalize_impact(value: Any) -> str:
    text = str(value or "").upper()
    for level in ("HIGH", "MODERATE", "LOW"):
        if level in text:
            return level
    if "MEDIUM" in text:
        return "MODERATE"
    raise ValueError(f"unknown impact level: {value!r}")


ImpactLevel = Annotated[Literal["HIGH", "MODERATE", "LOW"], BeforeValidator(_normalize_impact)]


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


# --------------------------------------------------------------------------- Pass 1


class Pass1Result(_Lenient):
    is_material: bool
    event_type: EventType = "OTHER"
    confidence: Num = 0.5
    reason: str = ""


# --------------------------------------------------------------------------- Pass 2


class KeyNumber(_Lenient):
    label: str
    value: Annotated[str, BeforeValidator(lambda v: "" if v is None else str(v))]
    change: OptStr = None


class Insight(_Lenient):
    text: str
    basis: Literal["MEMORY", "BALANCE_SHEET", "FILING", "SECTOR"] = "FILING"
    memory_refs: StrList = Field(default_factory=list)

    @field_validator("basis", mode="before")
    @classmethod
    def _basis(cls, value: Any) -> str:
        text = str(value or "FILING").upper().replace(" ", "_")
        return text if text in ("MEMORY", "BALANCE_SHEET", "FILING", "SECTOR") else "FILING"


def _insights(value: Any) -> list:
    return [{"text": item} if isinstance(item, str) else item for item in _to_list(value)]


def _drop_invalid(model: type[BaseModel]):
    """Keep the valid items of a list and silently discard malformed ones."""

    def validate(value: Any) -> list:
        out = []
        for item in _to_list(value):
            try:
                out.append(model.model_validate(item))
            except Exception:
                continue
        return out

    return BeforeValidator(validate)


class NotableChange(_Lenient):
    """An open-ended significant change the analyst judged decision-relevant."""

    metric: str
    previous: OptStr = None
    current: OptStr = None
    change: OptStr = None
    direction: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"] = "NEUTRAL"
    why: str = ""

    @field_validator("direction", mode="before")
    @classmethod
    def _direction(cls, value: Any) -> str:
        text = str(value or "").upper()
        if text.startswith(("POS", "GOOD", "FAV", "UP")):
            return "POSITIVE"
        if text.startswith(("NEG", "BAD", "ADV", "UNFAV", "DOWN")):
            return "NEGATIVE"
        return "NEUTRAL"


def _enum_early(allowed: tuple[str, ...], aliases: dict[str, str]):
    def validate(value: Any) -> str | None:
        text = str(value or "").strip().upper()
        if text in allowed:
            return text
        text = re.sub(r"[^A-Z]+", "_", text).strip("_")
        return aliases.get(text)
    return BeforeValidator(validate)


class Milestone(_Lenient):
    what: str
    when: OptStr = None          # as stated: "Q1FY28", "Nov 19, 2026"
    date: OptStr = None          # ISO date when the filing gives one

    @field_validator("date", mode="before")
    @classmethod
    def _iso(cls, value: Any) -> str | None:
        try:
            return date.fromisoformat(str(value).strip()[:10]).isoformat() if value else None
        except ValueError:
            return None


class KpiWatch(_Lenient):
    kpi: str
    check_in: OptStr = None      # where to verify it: "Q3FY27 results", "next monthly update"
    # A testable prediction (blueprint Loop 2): the dossier metric, the period it is due for, the
    # number and the comparison. Code checks it when that period's figures arrive.
    metric: OptStr = None        # snake_case financial metric, e.g. "finance_cost", "revenue"
    period: OptStr = None        # "Q3FY27", "FY27"
    value: Num = None
    comparison: Annotated[str | None, _enum_early((">=", "<=", "="), {"GTE": ">=", "LTE": "<=", "EQ": "=", "AT_LEAST": ">=", "AT_MOST": "<=", "ABOVE": ">=", "BELOW": "<="})] = None
    target: OptStr = None


class TrackNext(_Lenient):
    """Forward-looking triggers: what an investor should watch after this filing."""

    milestones: Annotated[list[Milestone], _drop_invalid(Milestone)] = Field(default_factory=list)
    kpis_to_verify: Annotated[list[KpiWatch], _drop_invalid(KpiWatch)] = Field(default_factory=list)
    pending_approvals: StrList = Field(default_factory=list)
    catalysts: StrList = Field(default_factory=list)   # what could make this work better than expected
    risks: StrList = Field(default_factory=list)       # what could make it underperform ("road blockers")


def _enum(allowed: tuple[str, ...], aliases: dict[str, str] | None = None, default: str | None = None):
    """Normalise free-form model output onto a small vocabulary, falling back to ``default``."""

    def validate(value: Any) -> str | None:
        text = re.sub(r"[^A-Z]+", "_", str(value or "").upper()).strip("_")
        text = (aliases or {}).get(text, text)
        if text in allowed:
            return text
        return next((a for a in allowed if text.startswith(a)), default)

    return BeforeValidator(validate)


DEAL_KINDS = ("ORDER", "FUNDRAISE", "CAPEX", "ACQUISITION", "DIVESTMENT", "OTHER")
DEAL_STAGES = ("L1_BIDDER", "LOI", "LOA", "WORK_ORDER", "CONTRACT", "MOU", "DEVELOPMENT_ORDER", "PROPOSED", "BOARD_APPROVED",
               "TERMS_FINALISED", "SHAREHOLDER_APPROVED", "IN_PROGRESS", "PARTIALLY_COMPLETED", "COMPLETED",
               "CANCELLED", "OTHER")


class DealValue(_Lenient):
    """The size of an order, fundraise, capex or deal, so code can put it in proportion."""

    kind: Annotated[str, _enum(DEAL_KINDS, {"CONTRACT": "ORDER", "AWARD": "ORDER", "PREFERENTIAL": "FUNDRAISE",
                                              "WARRANTS": "FUNDRAISE", "QIP": "FUNDRAISE", "M_A": "ACQUISITION"}, "OTHER")] = "OTHER"
    amount_cr: Num = None
    includes_gst: bool | None = None
    counterparty: OptStr = None
    stage: Annotated[str, _enum(DEAL_STAGES, {"LETTER_OF_INTENT": "LOI", "LETTER_OF_ACCEPTANCE": "LOA",
                                                "LETTER_OF_AWARD": "LOA", "PURCHASE_ORDER": "WORK_ORDER", "PO": "WORK_ORDER",
                                                "AGREEMENT": "CONTRACT", "MEMORANDUM_OF_UNDERSTANDING": "MOU",
                                                "APPROVED": "BOARD_APPROVED", "IN_PRINCIPLE": "PROPOSED", "PLANNED": "PROPOSED",
                                                "TERMS_FINALIZED": "TERMS_FINALISED", "COMMISSIONED": "COMPLETED",
                                                "PARTIALLY_COMMISSIONED": "PARTIALLY_COMPLETED", "WITHDRAWN": "CANCELLED",
                                                "UNDER_EXECUTION": "IN_PROGRESS", "L1": "L1_BIDDER", "LOWEST_BIDDER": "L1_BIDDER",
                                                "BOARD_APPROVAL": "BOARD_APPROVED", "SHAREHOLDER_APPROVAL": "SHAREHOLDER_APPROVED",
                                                "IN_PRINCIPLE_APPROVAL": "PROPOSED", "FINAL_TERMS": "TERMS_FINALISED",
                                                "PARTLY_COMMISSIONED": "PARTIALLY_COMPLETED", "PARTLY_COMPLETED": "PARTIALLY_COMPLETED",
                                                "AWARDED": "LOA", "NOTICE_TO_PROCEED": "WORK_ORDER"}, "OTHER")] = "OTHER"
    segment: OptStr = None        # business line, e.g. "wind EPC", "underground cabling"
    # Capex physics (blueprint modules 4-5): new site or existing one; sold outside or used in-house.
    expansion: Annotated[str | None, _enum(("BROWNFIELD", "GREENFIELD"), {"EXISTING_SITE": "BROWNFIELD", "NEW_SITE": "GREENFIELD"})] = None
    usage: Annotated[str | None, _enum(("MERCHANT_SALE", "CAPTIVE", "HYBRID"), {"MERCHANT": "MERCHANT_SALE", "CAPTIVE_INTEGRATION": "CAPTIVE",
                                                                         "CAPTIVE_CONSUMPTION": "CAPTIVE", "BACKWARD_INTEGRATION": "CAPTIVE"})] = None
    execution_by: OptStr = None   # as stated: "31 July 2027", "12 months"
    progress: OptStr = None       # e.g. "40 MW of 60 MW commissioned"
    updates_deal_id: OptStr = None  # a deal already in memory that this filing moves to a new stage

    @field_validator("includes_gst", mode="before")
    @classmethod
    def _gst(cls, value: Any) -> bool | None:
        if isinstance(value, bool) or value is None:
            return value
        text = str(value).strip().lower()
        return True if text in ("true", "yes", "incl", "including") else False if text in ("false", "no", "excl", "excluding") else None


class CallRead(_Lenient):
    """How a concall, presentation or AGM read, compared with the last one."""

    guidance: Annotated[str, _enum(("RAISED", "LOWERED", "MAINTAINED", "NEW", "WITHDRAWN", "NONE"),
                                   {"CUT": "LOWERED", "REDUCED": "LOWERED", "UPGRADED": "RAISED", "INCREASED": "RAISED",
                                    "SAME": "MAINTAINED", "UNCHANGED": "MAINTAINED", "REITERATED": "MAINTAINED",
                                    "SAME_AS_LAST_CALL": "MAINTAINED", "FIRST": "NEW", "NOT_GIVEN": "NONE"}, "NONE")] = "NONE"
    management_tone: Annotated[str, _enum(("OPTIMISTIC", "NEUTRAL", "CAUTIOUS"),
                                          {"CONFIDENT": "OPTIMISTIC", "BULLISH": "OPTIMISTIC", "POSITIVE": "OPTIMISTIC",
                                           "DEFENSIVE": "CAUTIOUS", "CONSERVATIVE": "CAUTIOUS", "NEGATIVE": "CAUTIOUS"},
                                          "NEUTRAL")] = "NEUTRAL"
    transparency: Annotated[str, _enum(("HIGH", "MEDIUM", "LOW"), {"MODERATE": "MEDIUM"}, "MEDIUM")] = "MEDIUM"
    story: Annotated[str | None, _enum(("GROWTH", "COMPOUNDER", "TURNAROUND", "CYCLICAL", "STRESSED", "TRANSITION", "VALUE"),
                                       {"RECOVERY": "TURNAROUND", "CYCLICAL_RECOVERY": "CYCLICAL", "DISTRESS": "STRESSED"})] = None


class QuantInput(_Lenient):
    name: str                   # identifier used in the formula, e.g. capacity_mw
    value: Num
    unit: str = ""
    source: Literal["FILING", "MEMORY", "ASSUMPTION"] = "ASSUMPTION"
    note: str = ""              # where it came from, or why the assumption is reasonable

    @field_validator("name", mode="before")
    @classmethod
    def _identifier(cls, value: Any) -> str:
        return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_") or "x"

    @field_validator("source", mode="before")
    @classmethod
    def _source(cls, value: Any) -> str:
        text = str(value or "").upper()
        return "FILING" if "FILING" in text else "MEMORY" if "MEMORY" in text else "ASSUMPTION"


class QuantifiedImpact(_Lenient):
    """An estimate with its working shown, so code can re-check the arithmetic."""

    label: str                  # "Annual revenue at full utilisation"
    formula: str                # "capacity_mw * plf * 8760 * tariff / 1e4"
    inputs: Annotated[list[QuantInput], _drop_invalid(QuantInput)] = Field(default_factory=list)
    result: Num = None
    unit: str = ""              # "INR_CR", "PCT", "BPS", ...
    interpretation: str = ""    # one line: what the number means for the company


def _normalize_tone(value: Any) -> str:
    text = str(value or "").upper()
    if text.startswith(("POS", "GOOD", "BULL", "FAV", "STRONG")):
        return "POSITIVE"
    if text.startswith(("NEG", "BAD", "BEAR", "ADV", "WEAK", "UNFAV")):
        return "NEGATIVE"
    if text.startswith("MIX"):
        return "MIXED"
    return "NEUTRAL"


Tone = Annotated[Literal["POSITIVE", "NEGATIVE", "MIXED", "NEUTRAL"], BeforeValidator(_normalize_tone)]


# "X posts a key update" says nothing; the validator rejects it so the gateway's repair attempt rewrites it.
_GENERIC_HEADLINE = re.compile(
    r"\b(?:posts?|shares?|announces?|gives?|provides?|issues?|makes?|files?|releases?)\s+(?:an?\s+)?"
    r"(?:key|important|major|significant|new|business|corporate|regulatory|material)?\s*"
    r"(?:update|announcement|disclosure|intimation)s?\s*$",
    re.I,
)


class Card(_Lenient):
    impact_level: ImpactLevel
    tone: Tone = "NEUTRAL"      # for the company's fundamentals, not a price call
    headline: str
    takeaway: Annotated[str, BeforeValidator(lambda v: v or "")] = ""   # one line shown in the collapsed feed row
    core_catalyst: OptStr = None   # one line: the economic driver behind the news (blueprint "📌 Core catalyst")
    what_happened: StrList = Field(min_length=1)
    why_it_matters: Annotated[list[Insight], BeforeValidator(_insights)] = Field(default_factory=list)
    missing_disclosures: StrList = Field(default_factory=list)
    key_numbers: Annotated[list[KeyNumber], _drop_invalid(KeyNumber)] = Field(default_factory=list)
    notable_changes: Annotated[list[NotableChange], _drop_invalid(NotableChange)] = Field(default_factory=list)
    track_next: Annotated[TrackNext, BeforeValidator(lambda v: v if isinstance(v, dict) else {})] = Field(default_factory=TrackNext)
    quantified_impact: Annotated[list[QuantifiedImpact], _drop_invalid(QuantifiedImpact)] = Field(default_factory=list)
    themes: StrList = Field(default_factory=list)          # up to 2 short tags: "Renewables", "Infra / EPC"
    basis: Annotated[str | None, _enum(("CONSOLIDATED", "STANDALONE", "PROFORMA"))] = None
    deal_value: DealValue | None = None
    call_read: CallRead | None = None

    @field_validator("deal_value", "call_read", mode="before")
    @classmethod
    def _optional_block(cls, value: Any) -> Any:
        return value if isinstance(value, dict) and any(v not in (None, "", []) for v in value.values()) else None

    @field_validator("themes")
    @classmethod
    def _themes(cls, value: list[str]) -> list[str]:
        out = []
        for tag in value:
            tag = " ".join(str(tag).split())[:24]
            if tag and tag.lower() not in {t.lower() for t in out}:
                out.append(tag)
        return out[:2]

    @field_validator("headline")
    @classmethod
    def _headline(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 8:
            raise ValueError("headline too short")
        if _GENERIC_HEADLINE.search(value):
            raise ValueError("headline is generic; say what the company actually announced, with its main figure")
        return value[:220]

    @model_validator(mode="after")
    def _default_takeaway(self) -> "Card":
        self.takeaway = " ".join(self.takeaway.split())[:240]
        if not self.takeaway and self.why_it_matters:
            self.takeaway = self.why_it_matters[0].text[:240]
        return self


class FinancialMetric(_Lenient):
    metric: str
    period: str
    value: Num
    unit: str = "INR_CR"
    yoy_pct: Num = None
    qoq_pct: Num = None


class SegmentShare(_Lenient):
    segment: str
    period: str
    revenue_cr: Num = None
    share_pct: Num = None


class GuidanceItem(_Lenient):
    statement: str
    metric: OptStr = None
    target: OptStr = None
    due: OptStr = None
    source_type: str = "FILING"


class PromiseUpdate(_Lenient):
    guidance_id: str
    status: Literal["DELIVERED", "ON_TRACK", "DELAYED", "MISSED", "REVISED", "WITHDRAWN"]
    evidence: str = ""

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, value: Any) -> str:
        return re.sub(r"[^A-Z]+", "_", str(value or "").upper()).strip("_")


class WatchUpdate(_Lenient):
    watch_id: str
    status: Literal["MET", "MISSED", "PARTIAL", "PENDING"]
    evidence: str = ""

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, value: Any) -> str:
        text = re.sub(r"[^A-Z]+", "_", str(value or "").upper()).strip("_")
        return {"ACHIEVED": "MET", "DELIVERED": "MET", "NOT_MET": "MISSED", "FAILED": "MISSED"}.get(text, text)


class BalanceSheet(_Lenient):
    period: OptStr = None
    gross_debt_cr: Num = None
    cash_cr: Num = None
    net_debt_cr: Num = None
    net_worth_cr: Num = None
    credit_rating: OptStr = None
    rating_agency: OptStr = None
    rating_outlook: OptStr = None

    def is_empty(self) -> bool:
        return all(v is None for v in self.model_dump().values())


class CapitalAction(_Lenient):
    """A change to the share capital (rights, QIP, preferential, warrants, conversion, buyback).

    The model only extracts the stated figures; dilution, discount and
    price-to-book are computed in signals.py.
    """

    instrument: str
    new_shares: Num = None
    existing_shares: Num = None
    issue_price: Num = None
    amount_cr: Num = None


class UpcomingEvent(_Lenient):
    event_type: str
    date: str
    description: str = ""

    @field_validator("event_type", mode="before")
    @classmethod
    def _etype(cls, value: Any) -> str:
        return re.sub(r"[^A-Z]+", "_", str(value or "OTHER").upper()).strip("_") or "OTHER"

    @field_validator("date")
    @classmethod
    def _date(cls, value: str) -> str:
        return date.fromisoformat(value.strip()[:10]).isoformat()


class AnalystConcern(_Lenient):
    """A red flag analysts pressed management on during a call, and what management said."""

    concern: str
    management_response: OptStr = None


class Entity(_Lenient):
    name: str
    type: OptStr = None          # "100% subsidiary", "step-down WOS", "JV (51%)", "brand", "plant"


class Ownership(_Lenient):
    """Shareholding for a quarter-end (from a shareholding pattern, results or an annual report)."""

    period: str
    promoter_pct: Num = None
    pledge_pct: Num = None       # promoter shares pledged, % of promoter holding
    fii_pct: Num = None
    dii_pct: Num = None
    retail_holders: Num = None   # number of small shareholders


class Auditor(_Lenient):
    name: OptStr = None
    opinion: Annotated[str | None, _enum(("UNMODIFIED", "EMPHASIS_OF_MATTER", "QUALIFIED", "ADVERSE", "DISCLAIMER"),
                                         {"CLEAN": "UNMODIFIED", "UNQUALIFIED": "UNMODIFIED", "EOM": "EMPHASIS_OF_MATTER",
                                          "EMPHASIS": "EMPHASIS_OF_MATTER", "DISCLAIMER_OF_OPINION": "DISCLAIMER"})] = None
    note: OptStr = None          # the matter qualified or emphasised, with its ₹ figure
    change: OptStr = None        # "resigned", "appointed", when this filing changes the auditor


class DossierDelta(_Lenient):
    business_summary: OptStr = None
    financial_metrics: Annotated[list[FinancialMetric], _drop_invalid(FinancialMetric)] = Field(default_factory=list)
    segment_mix: Annotated[list[SegmentShare], _drop_invalid(SegmentShare)] = Field(default_factory=list)
    guidance: Annotated[list[GuidanceItem], _drop_invalid(GuidanceItem)] = Field(default_factory=list)
    promise_updates: Annotated[list[PromiseUpdate], _drop_invalid(PromiseUpdate)] = Field(default_factory=list)
    watch_updates: Annotated[list[WatchUpdate], _drop_invalid(WatchUpdate)] = Field(default_factory=list)
    balance_sheet: Annotated[BalanceSheet | None, BeforeValidator(lambda v: v if isinstance(v, dict) else None)] = None
    capital_actions: Annotated[list[CapitalAction], _drop_invalid(CapitalAction)] = Field(default_factory=list)
    upcoming_events: Annotated[list[UpcomingEvent], _drop_invalid(UpcomingEvent)] = Field(default_factory=list)
    analyst_concerns: Annotated[list[AnalystConcern], _drop_invalid(AnalystConcern)] = Field(default_factory=list)
    operating_notes: StrList = Field(default_factory=list)  # feedstock, realisations, utilisation, order book...
    former_names: StrList = Field(default_factory=list)     # "Novartis India Limited" (identity, blueprint compartment 1)
    entities: Annotated[list[Entity], _drop_invalid(Entity)] = Field(default_factory=list)
    ownership: Annotated[Ownership | None, BeforeValidator(lambda v: v if isinstance(v, dict) else None)] = None
    auditor: Annotated[Auditor | None, BeforeValidator(lambda v: v if isinstance(v, dict) else None)] = None


class Pass2Output(_Lenient):
    is_material: bool
    event_type: EventType = "OTHER"
    card: Card | None = None
    timeline_entry: Annotated[str, BeforeValidator(lambda v: v if isinstance(v, str) else "")] = ""
    dossier_delta: Annotated[DossierDelta, BeforeValidator(lambda v: v if isinstance(v, dict) else {})] = Field(default_factory=DossierDelta)

    @model_validator(mode="before")
    @classmethod
    def _placeholders(cls, data: Any) -> Any:
        """Schema text copied into a reply ("HIGH | MODERATE | LOW", "string or null") is not an answer."""
        return _strip_placeholders(data)

    @model_validator(mode="after")
    def _card_required(self) -> "Pass2Output":
        if self.is_material and self.card is None:
            raise ValueError("is_material is true but no card was returned")
        if self.is_material and not self.timeline_entry.strip():
            self.timeline_entry = self.card.headline if self.card else ""
        return self
