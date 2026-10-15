"""Taxonomy-driven prompt assembly: base template + event module + sector module."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from string import Template

from ..grounding import UNIT_NAMES, declared_unit
from ..models import EVENT_TYPES, Filing
from ..settings import Settings

PASS2_SCHEMA = {
    "is_material": True,
    "event_type": "RESULTS",
    "card": {
        "impact_level": "HIGH | MODERATE | LOW",
        "tone": "POSITIVE | NEGATIVE | MIXED | NEUTRAL",
        "headline": "string",
        "core_catalyst": "string",
        "takeaway": "string",
        "basis": "CONSOLIDATED | STANDALONE | PROFORMA | null",
        "themes": ["Renewables", "Infra / EPC"],
        "what_happened": ["string with **key name** and **₹ figure** marked"],
        "why_it_matters": [{"text": "string", "basis": "MEMORY | BALANCE_SHEET | SECTOR | FILING", "memory_refs": ["g_..."]}],
        "missing_disclosures": ["string"],
        "key_numbers": [{"label": "Revenue", "value": "₹120 Cr", "change": "+32% YoY"}],
        "notable_changes": [{"metric": "inventories", "previous": "₹40 Cr (Mar-2026)", "current": "₹66 Cr (Sep-2026)", "change": "+65%", "direction": "NEGATIVE", "why": "string"}],
        "quantified_impact": [{
            "label": "Annual revenue at full utilisation", "formula": "capacity_mw * 1000 * plf * 8760 * tariff_inr / 1e7",
            "inputs": [{"name": "capacity_mw", "value": 50, "unit": "MW", "source": "FILING", "note": "commissioned capacity"},
                       {"name": "plf", "value": 0.22, "unit": "ratio", "source": "ASSUMPTION", "note": "typical for hybrid assets"},
                       {"name": "tariff_inr", "value": 3.25, "unit": "INR/kWh", "source": "FILING", "note": "PPA tariff"}],
            "result": 31.3, "unit": "INR_CR", "interpretation": "string"}],
        "track_next": {
            "milestones": [{"what": "string", "when": "as written", "date": "YYYY-MM-DD or null"}],
            "kpis_to_verify": [{"kpi": "string", "check_in": "Q3FY27 results", "target": "string or null",
                                "metric": "finance_cost", "period": "Q3FY27", "value": 16.0, "comparison": "<="}],
            "pending_approvals": ["string"],
            "catalysts": ["string"],
            "risks": ["string"],
        },
        "deal_value": {"kind": "ORDER | FUNDRAISE | CAPEX | ACQUISITION | DIVESTMENT | OTHER", "amount_cr": 228.0,
                       "includes_gst": False, "counterparty": "string", "stage": "L1_BIDDER | LOI | LOA | WORK_ORDER | CONTRACT | MOU | DEVELOPMENT_ORDER | PROPOSED | BOARD_APPROVED | TERMS_FINALISED | SHAREHOLDER_APPROVED | IN_PROGRESS | PARTIALLY_COMPLETED | COMPLETED | CANCELLED",
                       "segment": "wind EPC", "execution_by": "31 July 2027", "expansion": "BROWNFIELD | GREENFIELD | null",
                       "usage": "MERCHANT_SALE | CAPTIVE | HYBRID | null", "progress": "40 MW of 60 MW commissioned or null",
                       "updates_deal_id": "d_... from memory's deals, or null"},
        "call_read": {"guidance": "RAISED | LOWERED | MAINTAINED | NEW | WITHDRAWN | NONE", "management_tone": "OPTIMISTIC | NEUTRAL | CAUTIOUS",
                      "transparency": "HIGH | MEDIUM | LOW", "story": "GROWTH | COMPOUNDER | TURNAROUND | CYCLICAL | STRESSED | TRANSITION | VALUE"},
    },
    "timeline_entry": "one sentence for the company's chronological timeline",
    "dossier_delta": {
        "business_summary": "string or null",
        "financial_metrics": [{"metric": "revenue", "period": "Q2FY27", "value": 120.0, "unit": "INR_CR", "yoy_pct": 32.0, "qoq_pct": None}],
        "segment_mix": [{"segment": "string", "period": "Q2FY27", "revenue_cr": 0.0, "share_pct": 0.0}],
        "guidance": [{"statement": "string", "metric": "string", "target": "string", "due": "FY27", "source_type": "CONCALL"}],
        "promise_updates": [{"guidance_id": "g_...", "status": "ON_TRACK", "evidence": "string"}],
        "watch_updates": [{"watch_id": "w_...", "status": "MET", "evidence": "string"}],
        "balance_sheet": {"period": "Sep-2026", "gross_debt_cr": None, "cash_cr": None, "net_debt_cr": None, "net_worth_cr": None, "credit_rating": None, "rating_agency": None, "rating_outlook": None},
        "capital_actions": [{"instrument": "Rights issue", "new_shares": None, "existing_shares": None, "ratio": "19:25 or null", "issue_price": None, "amount_cr": None}],
        "upcoming_events": [{"event_type": "RECORD_DATE", "date": "YYYY-MM-DD", "description": "string"}],
        "analyst_concerns": [{"concern": "string", "management_response": "string"}],
        "operating_notes": ["string"],
        "former_names": ["string"],
        "entities": [{"name": "Jubilant Draximage Inc.", "type": "step-down wholly owned subsidiary"}],
        "ownership": {"period": "Sep-2026", "promoter_pct": None, "pledge_pct": None, "fii_pct": None, "dii_pct": None, "retail_holders": None},
        "auditor": {"name": None, "opinion": "UNMODIFIED | EMPHASIS_OF_MATTER | QUALIFIED | ADVERSE | DISCLAIMER", "note": None, "change": None},
    },
}


def _unit_note(text: str | None) -> str:
    """A line naming the filing's unit when it is not ₹ crore: models copy "2,863" from a lakh
    statement as "₹2,863 Cr". Stated in code so the model does not have to notice the header."""
    unit = declared_unit(text)
    if not unit:
        return ""
    return (f"UNITS: this filing states its amounts in {UNIT_NAMES[unit]}. Every amount on the card, in key_numbers, "
            f"results and fundamentals is in ₹ crore: divide the filing's figures by {unit:,} "
            f"(e.g. 12,345 in the filing is ₹{12345 / unit:,.2f} Cr).\n\n")


def _examples_text(examples: dict[str, list[dict]]) -> str:
    """The owner's rated cards for this kind of filing, as compact examples (blueprint Loop 3)."""
    def brief(card: dict) -> str:
        facts = "; ".join(str(f) for f in (card.get("what_happened") or [])[:2])
        insights = "; ".join(str(i.get("text", i)) for i in (card.get("why_it_matters") or [])[:2])
        return f"  headline: {card.get('headline', '')}\n  facts: {facts}\n  why: {insights}"[:900]
    parts = []
    if examples.get("STARRED"):
        parts.append("OWNER'S STARRED CARDS for this kind of filing (match their depth and focus, not their facts):\n"
                     + "\n---\n".join(brief(c) for c in examples["STARRED"]))
    if examples.get("NOISE"):
        parts.append("OWNER MARKED THIS AS NOISE (avoid writing a card like it):\n"
                     + "\n---\n".join(brief(c) for c in examples["NOISE"]))
    return "\n\n".join(parts)


@dataclass(frozen=True)
class SectorModule:
    name: str
    patterns: tuple[re.Pattern, ...]
    kpis: tuple[str, ...]
    context: str
    footer: tuple[dict, ...] = ()   # card-footer metrics: {metric, label, format, aliases}
    asset_turn: tuple[float, float] | None = None   # normal revenue per rupee of gross capex (module 2)
    asset_turn_note: str = ""
    drivers: str = ""               # feedstock / spread driver and seasonality
    red_flag: str = ""              # the sector's main forensic trap

    def lens(self) -> str:
        """Context for the prompt: how to read the sector, its normal asset turns, drivers and trap."""
        parts = [self.context]
        if self.asset_turn_note:
            parts.append(f"Normal asset turns: {self.asset_turn_note}.")
        if self.drivers:
            parts.append(f"Drivers and seasonality: {self.drivers}")
        if self.red_flag:
            parts.append(f"Forensic red flag to check: {self.red_flag}")
        return " ".join(p for p in parts if p)


class PromptEngine:
    def __init__(self, settings: Settings):
        prompts = settings.config_dir / "prompts"
        self._pass1 = Template((prompts / "pass1.md").read_text())
        self._pass2 = Template((prompts / "pass2.md").read_text())
        self._pass2_user = Template((prompts / "pass2_user.md").read_text())
        self._verify = (prompts / "verify.md").read_text()
        self.memory_start = settings.backfill_start
        self.events: dict = settings.load_toml("events.toml")
        self.sectors: list[SectorModule] = []
        for name, entry in settings.load_toml("sectors.toml").items():
            self.sectors.append(SectorModule(
                name=name,
                patterns=tuple(re.compile(r"\b" + re.escape(m), re.I) for m in entry.get("match", [])),
                kpis=tuple(entry.get("kpis", [])),
                context=entry.get("context", ""),
                footer=tuple(entry.get("footer", [])),
                asset_turn=tuple(entry["asset_turn"]) if entry.get("asset_turn") else None,
                asset_turn_note=entry.get("asset_turn_note", ""),
                drivers=entry.get("drivers", ""),
                red_flag=entry.get("red_flag", ""),
            ))

    def sector_for(self, industry: str | None) -> SectorModule:
        """The lens for a BSE industry. A classification path ("Consumer Discretionary > Automobile
        and Auto Components > Auto Components > Auto Components & Equipments") is read from its most
        specific level up, so the sub-group decides before the broad sector does."""
        default = next((s for s in self.sectors if s.name == "default"), None)
        for level in reversed([part.strip() for part in (industry or "").split(">") if part.strip()]):
            for module in self.sectors:
                if any(p.search(level) for p in module.patterns):
                    return module
        if default is None:
            return SectorModule("default", (), (), "")
        return default

    def keywords(self, event_type: str) -> list[str]:
        return list(self._event(event_type).get("keywords", []))

    def _event(self, event_type: str) -> dict:
        return self.events.get(event_type) or self.events.get("OTHER", {})

    def pass1(self, filing: Filing, page1_text: str) -> tuple[str, str]:
        system = self._pass1.safe_substitute(event_types=", ".join(EVENT_TYPES))
        user = (
            f"Company: {filing.company_name} (BSE {filing.scrip_code})\n"
            f"BSE category: {filing.category or '-'} / {filing.subcategory or '-'}\n"
            f"Headline: {filing.headline}\n"
            f"Subject: {filing.subject}\n\n"
            f"First page:\n{page1_text or '(no attachment text)'}"
        )
        return system, user

    def verify(self, system: str, user: str, draft: dict, problems: list[str]) -> tuple[str, str]:
        """The second-opinion prompt: the original prompt, the draft reply and what the checks found."""
        return system + self._verify, (
            f"{user}\n\nDRAFT REPLY\n{json.dumps(draft, ensure_ascii=False)}\n\nPROBLEMS\n"
            + "\n".join(f"- {p}" for p in problems)
        )

    def pass2(
        self, filing: Filing, event_type: str, industry: str | None, memory: dict | None, text: str,
        peers: list[dict] | None = None, examples: dict[str, list[dict]] | None = None,
        lessons: list[str] | None = None, reaction: str | None = None,
    ) -> tuple[str, str]:
        sector = self.sector_for(industry)
        system = self._pass2.safe_substitute(
            event_type=event_type,
            event_focus=self._event(event_type).get("focus", "").strip(),
            sector_name=sector.name.replace("_", " "),
            sector_context=sector.lens(),
            sector_kpis=", ".join(sector.kpis) + (
                ". Name these in financial_metrics exactly as: "
                + ", ".join(f"{f['metric']} ({f['label']})" for f in sector.footer) if sector.footer else ""),
            schema=json.dumps({**PASS2_SCHEMA, "event_type": event_type}, ensure_ascii=False, indent=1),
            event_types=", ".join(EVENT_TYPES),
            memory_start=self.memory_start,
        )
        user = self._pass2_user.safe_substitute(
            company_name=filing.company_name,
            scrip_code=filing.scrip_code,
            symbol=f" / {filing.symbol}" if filing.symbol else "",
            industry=industry or "unknown",
            filed_at=filing.filed_at,
            category=filing.category or "-",
            subcategory=filing.subcategory or "-",
            headline=filing.headline,
            memory=json.dumps(memory, ensure_ascii=False, separators=(",", ":")) if memory else "No prior memory.",
            peers="\n".join(
                f"- {p['filed_at'][:10]} {p['company_name']}: {p['headline']}" for p in peers or []
            ) or "None.",
            text=_unit_note(text) + (text or "(attachment had no extractable text; rely on the headline)"),
        )
        shown = _examples_text(examples or {})
        if shown:
            user = shown + "\n\n" + user
        if lessons:
            user = ("LESSONS FROM PAST MARKET REACTIONS (same sector and event type; details the market priced that "
                    "earlier cards underrated)\n" + "\n".join(f"- {x}" for x in lessons) + "\n\n" + user)
        if reaction:
            user += ("\n\nMARKET REACTION AFTER THIS FILING (post-mortem)\n" + reaction + "\nWrite the card as usual, "
                     "then add a top-level field \"lesson\": one sentence naming the specific detail in this filing that "
                     "the market priced, written as a rule for future filings of this sector and event type. If the "
                     "filing holds no such detail (the move came from elsewhere), say so in the lesson.")
        return system, user
