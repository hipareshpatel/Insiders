"""Taxonomy-driven prompt assembly: base template + event module + sector module."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from string import Template

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
            "kpis_to_verify": [{"kpi": "string", "check_in": "Q3FY27 results", "target": "string or null"}],
            "pending_approvals": ["string"],
            "catalysts": ["string"],
            "risks": ["string"],
        },
        "deal_value": {"kind": "ORDER | FUNDRAISE | CAPEX | ACQUISITION | DIVESTMENT | OTHER", "amount_cr": 228.0,
                       "includes_gst": False, "counterparty": "string", "stage": "L1_BIDDER | LOI | LOA | WORK_ORDER | CONTRACT | MOU | DEVELOPMENT_ORDER | PROPOSED | BOARD_APPROVED | TERMS_FINALISED | SHAREHOLDER_APPROVED | IN_PROGRESS | PARTIALLY_COMPLETED | COMPLETED | CANCELLED",
                       "segment": "wind EPC", "execution_by": "31 July 2027", "progress": "40 MW of 60 MW commissioned or null",
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
        "capital_actions": [{"instrument": "Rights issue", "new_shares": None, "existing_shares": None, "issue_price": None, "amount_cr": None}],
        "upcoming_events": [{"event_type": "RECORD_DATE", "date": "YYYY-MM-DD", "description": "string"}],
        "analyst_concerns": [{"concern": "string", "management_response": "string"}],
        "operating_notes": ["string"],
    },
}


@dataclass(frozen=True)
class SectorModule:
    name: str
    patterns: tuple[re.Pattern, ...]
    kpis: tuple[str, ...]
    context: str
    footer: tuple[dict, ...] = ()   # card-footer metrics: {metric, label, format, aliases}


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
            ))

    def sector_for(self, industry: str | None) -> SectorModule:
        default = next((s for s in self.sectors if s.name == "default"), None)
        if industry:
            for module in self.sectors:
                if any(p.search(industry) for p in module.patterns):
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
        peers: list[dict] | None = None,
    ) -> tuple[str, str]:
        sector = self.sector_for(industry)
        system = self._pass2.safe_substitute(
            event_type=event_type,
            event_focus=self._event(event_type).get("focus", "").strip(),
            sector_name=sector.name.replace("_", " "),
            sector_context=sector.context,
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
            text=text or "(attachment had no extractable text; rely on the headline)",
        )
        return system, user
