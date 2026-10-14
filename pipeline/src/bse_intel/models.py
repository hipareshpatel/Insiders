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
            "headline": self.headline,
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

_NUM_CLEAN = re.compile(r"[₹,\s]|(?i:rs\.?|inr|crores?|cr\.?|lakhs?|%)")


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _NUM_CLEAN.sub("", str(value))
    if text in ("", "-", "NA", "N/A", "null", "None"):
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


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
    value: str
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
    target: OptStr = None


class TrackNext(_Lenient):
    """Forward-looking triggers: what an investor should watch after this filing."""

    milestones: Annotated[list[Milestone], _drop_invalid(Milestone)] = Field(default_factory=list)
    kpis_to_verify: Annotated[list[KpiWatch], _drop_invalid(KpiWatch)] = Field(default_factory=list)
    pending_approvals: StrList = Field(default_factory=list)
    risks: StrList = Field(default_factory=list)


class Card(_Lenient):
    impact_level: ImpactLevel
    headline: str
    what_happened: StrList = Field(min_length=1)
    why_it_matters: Annotated[list[Insight], BeforeValidator(_insights)] = Field(default_factory=list)
    missing_disclosures: StrList = Field(default_factory=list)
    key_numbers: list[KeyNumber] = Field(default_factory=list)
    notable_changes: Annotated[list[NotableChange], _drop_invalid(NotableChange)] = Field(default_factory=list)
    track_next: TrackNext = Field(default_factory=TrackNext)

    @field_validator("headline")
    @classmethod
    def _headline(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 8:
            raise ValueError("headline too short")
        return value[:220]


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


class DossierDelta(_Lenient):
    business_summary: OptStr = None
    financial_metrics: Annotated[list[FinancialMetric], _drop_invalid(FinancialMetric)] = Field(default_factory=list)
    segment_mix: Annotated[list[SegmentShare], _drop_invalid(SegmentShare)] = Field(default_factory=list)
    guidance: Annotated[list[GuidanceItem], _drop_invalid(GuidanceItem)] = Field(default_factory=list)
    promise_updates: Annotated[list[PromiseUpdate], _drop_invalid(PromiseUpdate)] = Field(default_factory=list)
    watch_updates: Annotated[list[WatchUpdate], _drop_invalid(WatchUpdate)] = Field(default_factory=list)
    balance_sheet: BalanceSheet | None = None
    capital_actions: Annotated[list[CapitalAction], _drop_invalid(CapitalAction)] = Field(default_factory=list)
    upcoming_events: Annotated[list[UpcomingEvent], _drop_invalid(UpcomingEvent)] = Field(default_factory=list)


class Pass2Output(_Lenient):
    is_material: bool
    event_type: EventType = "OTHER"
    card: Card | None = None
    timeline_entry: str = ""
    dossier_delta: DossierDelta = Field(default_factory=DossierDelta)

    @model_validator(mode="after")
    def _card_required(self) -> "Pass2Output":
        if self.is_material and self.card is None:
            raise ValueError("is_material is true but no card was returned")
        if self.is_material and not self.timeline_entry.strip():
            self.timeline_entry = self.card.headline if self.card else ""
        return self
