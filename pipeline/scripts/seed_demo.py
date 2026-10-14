"""Seed a local platform with FICTIONAL demo data by running the real pipeline.

Every company here is invented ("Demo ... Ltd", scrip codes 9990xx, which BSE
does not use). Filings, PDFs and AI replies are scripted, but everything else
is the production code path: rules, PDF extraction, prompt assembly, the AI
gateway (with a fake client), grounding, dossier merges, signals, catalysts,
and writes through PlatformSink to the Worker's internal API.

Usage (with `npm run dev` running in web/):
    BSE_INTEL_SINK=platform PLATFORM_API_URL=http://localhost:5173 \
    INGEST_TOKEN=dev-local-token python scripts/seed_demo.py
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace

import pymupdf

from bse_intel.ai.gateway import AIGateway
from bse_intel.models import Filing
from bse_intel.pipeline import Pipeline
from bse_intel.settings import get_settings
from bse_intel.sinks import make_sink
from bse_intel.timeutil import IST, now_iso, today_ist

TODAY = today_ist()


def at(days_ago: int, hh: int, mm: int) -> datetime:
    d = TODAY - timedelta(days=days_ago)
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=IST)


COMPANIES = [
    {"scrip_code": "999001", "company_name": "Demo Cement Ltd", "symbol": "DEMOCEM", "industry": "Cement & Cement Products",
     "sector": "cement", "shares_outstanding": 117_600_000, "last_price": 412.5, "market_cap_cr": 4851.0, "size_category": "SMALL",
     "ret_1w": -8.9, "ret_1m": -4.2, "ret_1y": 21.4},
    {"scrip_code": "999002", "company_name": "Demo Chemicals Ltd", "symbol": "DEMOCHEM", "industry": "Specialty Chemicals",
     "sector": "chemicals", "shares_outstanding": 43_700_000, "last_price": 184.4, "market_cap_cr": 806.0, "size_category": "MICRO",
     "ret_1w": 6.1, "ret_1m": 12.8, "ret_1y": 34.0},
    {"scrip_code": "999003", "company_name": "Demo Auto Components Ltd", "symbol": "DEMOAUTO", "industry": "Auto Components & Equipments",
     "sector": "auto_components", "shares_outstanding": 310_000_000, "last_price": 400.0, "market_cap_cr": 12400.0, "size_category": "SMALL",
     "ret_1w": 2.3, "ret_1m": 7.5, "ret_1y": 18.2},
    {"scrip_code": "999004", "company_name": "Demo Finance Ltd", "symbol": "DEMOFIN", "industry": "Non Banking Financial Company (NBFC)",
     "sector": "nbfc", "shares_outstanding": 250_000_000, "last_price": 86.0, "market_cap_cr": 2150.0, "size_category": "MICRO",
     "ret_1w": -3.4, "ret_1m": -11.0, "ret_1y": -6.5},
    {"scrip_code": "999005", "company_name": "Demo Pharma Ltd", "symbol": "DEMOPHARMA", "industry": "Pharmaceuticals",
     "sector": "pharma", "shares_outstanding": 520_000_000, "last_price": 748.0, "market_cap_cr": 38896.0, "size_category": "MID",
     "ret_1w": -1.2, "ret_1m": -14.6, "ret_1y": 9.8},
    {"scrip_code": "999006", "company_name": "Demo Forgings Ltd", "symbol": "DEMOFORGE", "industry": "Auto Components & Equipments",
     "sector": "auto_components", "shares_outstanding": 95_000_000, "last_price": 610.0, "market_cap_cr": 5795.0, "size_category": "SMALL",
     "ret_1w": 1.1, "ret_1m": 3.9, "ret_1y": 12.0},
]
NAMES = {c["scrip_code"]: c for c in COMPANIES}

# (key, scrip, when, category, subcategory, headline, pdf text)
FILINGS = [
    ("cem-q1", "999001", at(85, 17, 5), "Result", "Financial Results",
     "Unaudited Financial Results for the quarter ended June 30, 2026",
     "Statement of unaudited standalone financial results (Rs. in crore). Quarter ended 30.06.2026 vs 30.06.2025: "
     "Revenue from operations 412.30 vs 351.00. EBITDA 73.39 vs 61.43. EBITDA margin 17.8% vs 17.5%. Net profit 38.20 vs 31.10. "
     "Sales volume 0.92 million tonnes vs 0.81 million tonnes."),
    ("chem-agm", "999002", at(60, 19, 40), "AGM/EGM", "", "Transcript of AGM speech and investor Q&A",
     "Chairman's address at the 52nd AGM. We will commission the 12 TPD Triacetin plant at Dahej by Q3 FY27 within the "
     "approved capex of Rs. 64 crore, funded from internal accruals. We target specialty chemicals to exceed 40% of revenue by FY28 "
     "from 31% in FY26. Revenue for FY26 was Rs. 590 crore. Net debt stood at Rs. 38 crore on 31 March 2026."),
    ("pharma-usfda", "999005", at(40, 20, 15), "Company Update", "", "Receipt of Warning Letter from USFDA for Unit III, Pithampur",
     "The Company has received a Warning Letter from the US FDA for its oral solids facility, Unit III, following the inspection "
     "conducted in March 2026. Unit III contributed approximately 18% of US revenues (Rs. 610 crore in FY26). The Company will "
     "submit a comprehensive response within 15 working days and expects re-inspection in 9 to 12 months. Existing supplies continue."),
    ("forge-sep", "999006", at(13, 18, 0), "Company Update", "", "Monthly business update: September 2026 sales volumes",
     "Business update for September 2026. Total shipments 41,200 tonnes, up 22% YoY from 33,770 tonnes. Export shipments "
     "16,900 tonnes, up 28% YoY from 13,200 tonnes, led by North American commercial vehicle demand."),
    ("fin-rights", "999004", at(14, 21, 10), "Company Update", "", "Approval of Rights Issue of equity shares",
     "The Board approved a rights issue of up to 6,25,00,000 equity shares of face value Rs. 10 at an issue price of Rs. 70 per share "
     "aggregating up to Rs. 437.50 crore, in the ratio 1:4. Record date: 20 October 2026. Issue opens 27 October 2026 and closes "
     "10 November 2026. Proceeds will augment the capital base; capital adequacy was 16.2% at 30 June 2026. Subject to approval of "
     "the Letter of Offer by the stock exchange."),
    ("auto-sep", "999003", at(11, 17, 30), "Company Update", "", "Monthly business update: September 2026",
     "September 2026 update. Revenue from operations Rs. 318 crore, up 19% YoY from Rs. 267 crore. Exports Rs. 141 crore, up 35% YoY "
     "from Rs. 104 crore, now 44% of revenue. Domestic replacement demand was flat."),
    ("chem-plant", "999002", at(6, 18, 45), "Company Update", "", "Commencement of commercial production at Triacetin plant, Dahej",
     "We are pleased to inform that commercial production has commenced at the 12 TPD Triacetin plant at Dahej, Gujarat, on "
     "07 October 2026. The project was completed at a cost of Rs. 61 crore against the approved Rs. 64 crore."),
    ("cem-q2", "999001", at(2, 16, 50), "Result", "Financial Results",
     "Unaudited Financial Results for the quarter and half year ended September 30, 2026",
     "Statement of unaudited standalone financial results (Rs. in crore). Quarter ended 30.09.2026 vs 30.09.2025: Revenue from "
     "operations 455.60 vs 380.90. EBITDA 67.88 vs 70.85. EBITDA margin 14.9% vs 18.6%. Net profit 29.40 vs 36.80. Half year "
     "ended 30.09.2026 vs 30.09.2025: Revenue 867.90 vs 731.90. Statement of assets and liabilities as at 30.09.2026 vs "
     "30.09.2025: Trade receivables 318.00 vs 205.00. Inventories 142.00 vs 131.00. Borrowings 640.00 vs 420.00. Total equity 1,210.00."),
    ("fin-rating", "999004", at(1, 19, 20), "Company Update", "Credit Rating", "Credit Rating revised by CARE Ratings",
     "CARE Ratings has revised the rating on the Company's long term bank facilities of Rs. 1,800 crore to CARE A- (Negative) from "
     "CARE A (Stable), citing rising Stage 3 assets of 4.9% and moderation in profitability."),
    ("noise-1", "999005", at(0, 9, 5), "Company Update", "Trading Window", "Closure of Trading Window", ""),
    ("noise-2", "999003", at(0, 9, 30), "Company Update", "", "Intimation of loss of share certificates", ""),
    ("noise-3", "999001", at(0, 10, 15), "Result", "", "Copy of Newspaper Publication of financial results", ""),
    ("cal-1", "999003", at(0, 11, 0), "Board Meeting", "",
     "Board Meeting Intimation for considering unaudited financial results", "Meeting to be held on 28th October, 2026"),
    ("amb-1", "999006", at(0, 12, 40), "Company Update", "", "Clarification sought by exchange on news item",
     "With reference to the news item, we clarify that the Company has no information that has not been disclosed."),
]


def card(impact, headline, facts, insights, **extra):
    return {"impact_level": impact, "headline": headline, "what_happened": facts,
            "why_it_matters": insights, **extra}


def memory_of(user: str) -> dict:
    m = re.search(r"COMPANY MEMORY \(known before this filing\)\n(.*?)\n\nPEER CONTEXT", user, re.S)
    try:
        return json.loads(m.group(1)) if m else {}
    except json.JSONDecodeError:
        return {}


def pass2_reply(key: str, user: str) -> dict:
    memory = memory_of(user)
    def guidance_id(word: str) -> str:
        """Find a guidance id in the memory the pipeline put into the prompt."""
        return next((g["id"] for g in memory.get("guidance", []) if word in g["statement"]), "g_missing")

    timeline = memory.get("recent_timeline", [])
    watch = memory.get("watchlist", [])
    replies = {
        "cem-q1": dict(event_type="RESULTS", card=card(
            "MODERATE", "Demo Cement Q1 revenue up 17% YoY to ₹412 Cr; PAT ₹38 Cr",
            ["Revenue ₹412.3 Cr vs ₹351 Cr a year ago", "EBITDA margin 17.8% vs 17.5%", "Volumes 0.92 MT vs 0.81 MT"],
            [{"text": "Volume-led growth with stable margins; no balance-sheet data in a Q1 filing.", "basis": "FILING"}],
            key_numbers=[{"label": "Revenue", "value": "₹412 Cr", "change": "+17%"}, {"label": "PAT", "value": "₹38 Cr", "change": "+23%"}],
            track_next={"kpis_to_verify": [{"kpi": "EBITDA margin holding near 18%", "check_in": "Q2FY27 results"}]}),
            timeline_entry="Q1FY27 revenue ₹412 Cr (+17% YoY), EBITDA margin 17.8%.",
            dossier_delta={"business_summary": "Regional cement maker (fictional demo company).",
                           "financial_metrics": [
                               {"metric": "revenue", "period": "Q1FY27", "value": 412.3, "yoy_pct": 17.5},
                               {"metric": "revenue", "period": "Q1FY26", "value": 351.0},
                               {"metric": "ebitda_margin", "period": "Q1FY27", "value": 17.8, "unit": "PCT"},
                               {"metric": "ebitda_margin", "period": "Q1FY26", "value": 17.5, "unit": "PCT"},
                               {"metric": "ebitda", "period": "Q1FY27", "value": 73.39}, {"metric": "ebitda", "period": "Q1FY26", "value": 61.43},
                               {"metric": "pat", "period": "Q1FY27", "value": 38.2}, {"metric": "pat", "period": "Q1FY26", "value": 31.1}]}),
        "chem-agm": dict(event_type="CONCALL_PRESENTATION", card=card(
            "MODERATE", "Demo Chemicals guides 12 TPD Triacetin plant by Q3FY27 at ₹64 Cr capex",
            ["Triacetin plant at Dahej to be commissioned by Q3FY27", "Capex ₹64 Cr from internal accruals",
             "Specialty share target above 40% by FY28, from 31% in FY26"],
            [{"text": "Funded internally with net debt of only ₹38 Cr, so execution risk is operational, not financial.", "basis": "BALANCE_SHEET"}],
            missing_disclosures=["No revenue potential or payback period given for the new plant"],
            track_next={"milestones": [{"what": "Triacetin plant commissioning", "when": "Q3FY27"}],
                        "kpis_to_verify": [{"kpi": "Specialty share of revenue", "check_in": "FY28", "target": "above 40%"}]}),
            timeline_entry="AGM: guided Triacetin plant by Q3FY27 (₹64 Cr), specialty >40% by FY28.",
            dossier_delta={"business_summary": "Specialty and commodity chemicals producer (fictional demo company).",
                           "guidance": [
                               {"statement": "Commission 12 TPD Triacetin plant at Dahej", "target": "₹64 Cr capex", "due": "Q3FY27", "source_type": "AGM"},
                               {"statement": "Specialty chemicals above 40% of revenue", "target": "40%", "due": "FY28", "source_type": "AGM"}],
                           "financial_metrics": [{"metric": "revenue", "period": "FY26", "value": 590}],
                           "balance_sheet": {"period": "Mar-2026", "net_debt_cr": 38}}),
        "pharma-usfda": dict(event_type="LITIGATION_REGULATORY", card=card(
            "HIGH", "Demo Pharma gets USFDA warning letter for Unit III, ~18% of US revenue",
            ["Warning letter for oral solids Unit III after March 2026 inspection",
             "Unit III ≈18% of US revenue (US revenue ₹610 Cr in FY26)", "Response due in 15 working days; re-inspection expected in 9–12 months"],
            [{"text": "Puts roughly ₹110 Cr of US revenue under a cloud until re-inspection.", "basis": "FILING"}],
            missing_disclosures=["No estimate of remediation cost or launches held back by the warning letter"],
            notable_changes=[{"metric": "Regulatory status, Unit III", "previous": "OAI after inspection", "current": "Warning letter",
                              "direction": "NEGATIVE", "why": "Escalation blocks new approvals from the site"}],
            track_next={"milestones": [{"what": "Response to USFDA", "when": "within 15 working days"}],
                        "kpis_to_verify": [{"kpi": "US revenue growth", "check_in": "Q2FY27 results"}],
                        "risks": ["Import alert if remediation is judged inadequate"]}),
            timeline_entry="USFDA warning letter for Unit III (~18% of US revenue).",
            dossier_delta={"business_summary": "Generic formulations exporter (fictional demo company)."}),
        "forge-sep": dict(event_type="MONTHLY_BUSINESS_UPDATE", card=card(
            "MODERATE", "Demo Forgings September shipments up 22% YoY to 41,200 tonnes; exports +28%",
            ["Shipments 41,200 t vs 33,770 t", "Exports 16,900 t vs 13,200 t"],
            [{"text": "North American truck demand is driving exports.", "basis": "SECTOR"}],
            key_numbers=[{"label": "Shipments", "value": "41,200 t", "change": "+22%"}]),
            timeline_entry="Sep-2026 shipments 41,200 t (+22% YoY), exports +28%.",
            dossier_delta={"financial_metrics": [{"metric": "volumes", "period": "Sep-2026", "value": 41200, "unit": "MT", "yoy_pct": 22}]}),
        "fin-rights": dict(event_type="RIGHTS_ISSUE", card=card(
            "HIGH", "Demo Finance plans ₹437.5 Cr rights issue at ₹70, 1:4 ratio",
            ["Up to 6.25 Cr shares at ₹70 (1:4)", "Record date 20 Oct; issue 27 Oct – 10 Nov 2026",
             "Capital adequacy 16.2% at 30 June 2026"],
            [{"text": "A large raise when capital adequacy is still 16.2% suggests growth or asset-quality buffers ahead.", "basis": "BALANCE_SHEET"}],
            missing_disclosures=["No breakdown of how proceeds will be deployed"],
            track_next={"milestones": [{"what": "Record date", "when": "20 Oct 2026", "date": (TODAY + timedelta(days=6)).isoformat()},
                                       {"what": "Rights issue opens", "when": "27 Oct 2026", "date": (TODAY + timedelta(days=13)).isoformat()},
                                       {"what": "Rights issue closes", "when": "10 Nov 2026", "date": (TODAY + timedelta(days=27)).isoformat()}],
                        "pending_approvals": ["Exchange approval of the Letter of Offer"]}),
            timeline_entry="Board approved ₹437.5 Cr rights issue at ₹70 (1:4).",
            dossier_delta={"business_summary": "Vehicle and MSME lender (fictional demo company).",
                           "capital_actions": [{"instrument": "Rights issue", "new_shares": 62_500_000, "issue_price": 70, "amount_cr": 437.5}],
                           "balance_sheet": {"period": "Jun-2026", "net_worth_cr": 1250},
                           "upcoming_events": [{"event_type": "RECORD_DATE", "date": (TODAY + timedelta(days=6)).isoformat(), "description": "Rights entitlement"},
                                               {"event_type": "RIGHTS_OPEN", "date": (TODAY + timedelta(days=13)).isoformat(), "description": "Rights issue opens"},
                                               {"event_type": "RIGHTS_CLOSE", "date": (TODAY + timedelta(days=27)).isoformat(), "description": "Rights issue closes"}]}),
        "auto-sep": dict(event_type="MONTHLY_BUSINESS_UPDATE", card=card(
            "MODERATE", "Demo Auto Components September exports up 35% YoY to ₹141 Cr",
            ["Revenue ₹318 Cr vs ₹267 Cr (+19%)", "Exports ₹141 Cr vs ₹104 Cr (+35%), 44% of revenue"],
            [{"text": "Outpaces peer Demo Forgings' 28% export growth, pointing to share gains rather than only an industry tailwind.", "basis": "SECTOR"}],
            key_numbers=[{"label": "Exports", "value": "₹141 Cr", "change": "+35%"}]),
            timeline_entry="Sep-2026 exports ₹141 Cr (+35% YoY), 44% of revenue.",
            dossier_delta={"financial_metrics": [{"metric": "exports", "period": "Sep-2026", "value": 141, "yoy_pct": 35}]}),
        "chem-plant": dict(event_type="CAPEX", card=card(
            "HIGH", "Demo Chemicals starts 12 TPD Triacetin plant on schedule at ₹61 Cr, under ₹64 Cr budget",
            ["Commercial production began 07 Oct 2026 at Dahej", "Cost ₹61 Cr vs approved ₹64 Cr"],
            [{"text": "Delivers the plant guided at the AGM, ahead of the Q3FY27 deadline and under budget.", "basis": "MEMORY",
              "memory_refs": [t["id"] for t in timeline[-1:]]}],
            missing_disclosures=["No ramp-up schedule or expected FY27 revenue from the plant"],
            quantified_impact=[
                {"label": "Annual revenue at full utilisation", "formula": "capacity_tpd * operating_days * realisation_per_tonne / 1e7",
                 "inputs": [{"name": "capacity_tpd", "value": 12, "unit": "TPD", "source": "FILING", "note": "plant capacity"},
                            {"name": "operating_days", "value": 330, "unit": "days", "source": "ASSUMPTION", "note": "continuous plant, ~1 month maintenance"},
                            {"name": "realisation_per_tonne", "value": 95000, "unit": "INR/t", "source": "ASSUMPTION", "note": "indicative Triacetin price"}],
                 "result": 37.6, "unit": "INR_CR", "interpretation": "About 6% of FY26 revenue of ₹590 Cr at full ramp-up."},
                {"label": "Pre-tax payback on the plant", "formula": "capex_cr / (annual_revenue_cr * ebitda_margin)",
                 "inputs": [{"name": "capex_cr", "value": 61, "unit": "INR Cr", "source": "FILING", "note": "actual project cost"},
                            {"name": "annual_revenue_cr", "value": 37.6, "unit": "INR Cr", "source": "ASSUMPTION", "note": "estimate above"},
                            {"name": "ebitda_margin", "value": 0.2, "unit": "ratio", "source": "ASSUMPTION", "note": "specialty chemicals peers ~20%"}],
                 "result": 8.1, "unit": "years", "interpretation": "Slow payback unless realisations or margins beat the assumptions."}],
            track_next={"kpis_to_verify": [{"kpi": "Specialty chemicals share of revenue", "check_in": "Q3FY27 results", "target": "above 40%"}],
                        "risks": ["Export realisations for Triacetin vs cheaper imports"]}),
            timeline_entry="Commissioned 12 TPD Triacetin plant at ₹61 Cr (guided ₹64 Cr by Q3FY27).",
            dossier_delta={"promise_updates": [{"guidance_id": guidance_id("Triacetin"), "status": "DELIVERED",
                                                "evidence": "Commercial production began 07 Oct 2026 at ₹61 Cr"}]}),
        "cem-q2": dict(event_type="RESULTS", card=card(
            "HIGH", "Demo Cement Q2 revenue up 20% YoY to ₹456 Cr, but EBITDA margin falls to 14.9%",
            ["Revenue ₹455.6 Cr vs ₹380.9 Cr", "EBITDA margin 14.9% vs 18.6%", "PAT ₹29.4 Cr vs ₹36.8 Cr",
             "Borrowings ₹640 Cr vs ₹420 Cr"],
            [{"text": "Margin slipped below the ~18% run-rate of Q1, reversing the stability seen last quarter.", "basis": "MEMORY",
              "memory_refs": [t["id"] for t in timeline[-1:]]},
             {"text": "Borrowings up ₹220 Cr in a year while receivables jumped: growth is being funded with debt.", "basis": "BALANCE_SHEET"}],
            missing_disclosures=["No volume or realisation per tonne for the quarter"],
            key_numbers=[{"label": "Revenue", "value": "₹456 Cr", "change": "+20%"}, {"label": "EBITDA margin", "value": "14.9%", "change": "-370 bps"},
                         {"label": "PAT", "value": "₹29 Cr", "change": "-20%"}],
            notable_changes=[{"metric": "Trade receivables", "previous": "₹205 Cr (Sep-2025)", "current": "₹318 Cr (Sep-2026)", "change": "+55%",
                              "direction": "NEGATIVE", "why": "Far faster than 19% revenue growth"},
                             {"metric": "Borrowings", "previous": "₹420 Cr", "current": "₹640 Cr", "change": "+52%",
                              "direction": "NEGATIVE", "why": "Leverage rising with no capex announced"}],
            quantified_impact=[
                {"label": "Annual interest on the added debt", "formula": "(debt_now - debt_year_ago) * interest_rate",
                 "inputs": [{"name": "debt_now", "value": 640, "unit": "INR Cr", "source": "FILING", "note": "borrowings 30 Sep 2026"},
                            {"name": "debt_year_ago", "value": 420, "unit": "INR Cr", "source": "FILING", "note": "borrowings 30 Sep 2025"},
                            {"name": "interest_rate", "value": 0.095, "unit": "ratio", "source": "ASSUMPTION", "note": "typical A-rated borrowing cost"}],
                 "result": 20.9, "unit": "INR_CR", "interpretation": "Roughly 18% of annualised Q2 PAT (₹29.4 Cr × 4)."},
                {"label": "Receivable days (H1)", "formula": "receivables / h1_revenue * 183",
                 "inputs": [{"name": "receivables", "value": 318, "unit": "INR Cr", "source": "FILING", "note": "30 Sep 2026"},
                            {"name": "h1_revenue", "value": 867.9, "unit": "INR Cr", "source": "FILING", "note": "half year to 30 Sep 2026"}],
                 "result": 67, "unit": "days", "interpretation": "Up from about 51 days a year earlier (₹205 Cr on ₹731.9 Cr)."}],
            track_next={"kpis_to_verify": [{"kpi": "Receivable days", "check_in": "Q4FY27 results"}],
                        "risks": ["Further price cuts in the region compress margins"]}),
            timeline_entry="Q2FY27 revenue ₹456 Cr (+20%), margin 14.9% (-370 bps), receivables +55%.",
            dossier_delta={"financial_metrics": [
                {"metric": "revenue", "period": "Q2FY27", "value": 455.6, "yoy_pct": 19.6},
                {"metric": "revenue", "period": "Q2FY26", "value": 380.9},
                {"metric": "ebitda_margin", "period": "Q2FY27", "value": 14.9, "unit": "PCT"},
                {"metric": "ebitda_margin", "period": "Q2FY26", "value": 18.6, "unit": "PCT"},
                {"metric": "pat", "period": "Q2FY27", "value": 29.4}, {"metric": "pat", "period": "Q2FY26", "value": 36.8},
                {"metric": "ebitda", "period": "Q2FY27", "value": 67.88}, {"metric": "ebitda", "period": "Q2FY26", "value": 70.85},
                {"metric": "revenue", "period": "H1FY27", "value": 867.9}, {"metric": "revenue", "period": "H1FY26", "value": 731.9},
                {"metric": "trade_receivables", "period": "H1FY27", "value": 318}, {"metric": "trade_receivables", "period": "H1FY26", "value": 205},
                {"metric": "gross_debt", "period": "H1FY27", "value": 640}, {"metric": "gross_debt", "period": "H1FY26", "value": 420}],
                "balance_sheet": {"period": "Sep-2026", "gross_debt_cr": 640, "net_worth_cr": 1210},
                "watch_updates": [{"watch_id": w["id"], "status": "MISSED", "evidence": "Margin fell to 14.9%"} for w in watch][:1]}),
        "fin-rating": dict(event_type="DEBT_RATINGS", card=card(
            "MODERATE", "CARE cuts Demo Finance to A- (Negative) on ₹1,800 Cr facilities",
            ["Rating revised to CARE A- (Negative) from CARE A (Stable)", "Stage 3 assets at 4.9%"],
            [{"text": "Downgrade two weeks after a ₹437.5 Cr rights issue was approved: the raise looks defensive.", "basis": "MEMORY",
              "memory_refs": [t["id"] for t in timeline[-1:]]}]),
            timeline_entry="CARE downgraded to A- (Negative); Stage 3 at 4.9%.",
            dossier_delta={"balance_sheet": {"credit_rating": "CARE A-", "rating_agency": "CARE", "rating_outlook": "Negative"}}),
    }
    reply = replies[key]
    tone, takeaway = TONES[key]
    reply["card"].update(tone=tone, takeaway=takeaway)
    return {"is_material": True, **reply}


TONES = {
    "cem-q1": ("POSITIVE", "Volume-led growth with margins holding near 18%; nothing alarming yet."),
    "chem-agm": ("POSITIVE", "A funded, dated capacity promise: the plant is the test of execution this year."),
    "pharma-usfda": ("NEGATIVE", "Roughly a fifth of US revenue now depends on a clean re-inspection 9–12 months away."),
    "forge-sep": ("POSITIVE", "Export demand from North America is carrying volumes."),
    "fin-rights": ("MIXED", "A 25% dilutive raise at a discount; the use of proceeds is still undisclosed."),
    "auto-sep": ("POSITIVE", "Exports are outgrowing peers, pointing to share gains rather than a tide lifting all."),
    "chem-plant": ("POSITIVE", "Delivered the AGM promise early and under budget; ramp-up and margins are now the question."),
    "cem-q2": ("NEGATIVE", "Growth is being bought with credit: receivables and debt rose far faster than sales."),
    "fin-rating": ("NEGATIVE", "A downgrade right after the rights issue suggests the raise is defensive."),
}


class ScriptedAI:
    def __init__(self, headline_to_key: dict[str, str]):
        self.headline_to_key = headline_to_key
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        system, user = kwargs["messages"][0]["content"], kwargs["messages"][1]["content"]
        if "gatekeeper" in system:
            headline = re.search(r"^Headline: (.*)$", user, re.M).group(1).strip()
            material = not self.headline_to_key.get(headline, "").startswith("amb")
            body = {"is_material": material, "event_type": "OTHER", "confidence": 0.9,
                    "reason": "new decision-relevant information" if material else "routine clarification, nothing new"}
        else:
            headline = re.search(r"^Headline: (.*)$", user, re.M).group(1).strip()
            body = pass2_reply(self.headline_to_key[headline], user)
        text = json.dumps(body, ensure_ascii=False)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
            usage=SimpleNamespace(prompt_tokens=len(user) // 3, completion_tokens=len(text) // 3),
        )


class DemoBse:
    def __init__(self, filings: list[Filing], pdfs: dict[str, bytes]):
        self.filings, self.pdfs = filings, pdfs

    def announcements(self, day, day_to=None):
        return [f.model_copy() for f in self.filings if f.filing_date == day.isoformat()]

    def download(self, url):
        return self.pdfs.get(url)


def pdf(text: str) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 560, 800), text, fontsize=9)
    return doc.tobytes()


def main() -> None:
    settings = get_settings()
    first = min(f[2] for f in FILINGS).date()
    settings = replace(settings, backfill_start=first.isoformat(), workers=1)
    sink = make_sink(settings)
    sink.execute("companies_upsert", [dict(c, updated_at=now_iso()) for c in COMPANIES])

    filings, pdfs, by_headline = [], {}, {}
    for key, scrip, when, category, sub, headline, text in FILINGS:
        news_id = f"demo-{key}"
        url = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{news_id}.pdf" if text else None
        filings.append(Filing(
            news_id=news_id, scrip_code=scrip, company_name=NAMES[scrip]["company_name"], symbol=NAMES[scrip]["symbol"],
            headline=headline, subject=f"{headline}. {text[:80]}" if key.startswith("cal") else headline,
            category=category, subcategory=sub, filed_at=when.isoformat(timespec="seconds"),
            filing_date=when.date().isoformat(), pdf_url=url))
        if url:
            pdfs[url] = pdf(text)
        by_headline[headline] = key

    fake = ScriptedAI(by_headline)
    env = {k: "demo" for k in ("GROQ_API_KEY", "NVIDIA_API_KEY", "MISTRAL_API_KEY", "ZAI_API_KEY")}
    gateway = AIGateway(settings.load_toml("providers.toml"), client_factory=lambda *a: fake, env=env)
    pipeline = Pipeline(settings, sink, gateway, bse=DemoBse(filings, pdfs))
    stats = pipeline.run("all", time_budget_s=300, max_backfill_days=400)
    print(json.dumps(stats.as_dict(), indent=2))
    print("Seeded FICTIONAL demo data. Open the site and set the date range to 'Since 1 Jan 2026' to see every card.")
    if os.getenv("BSE_INTEL_SINK") != "platform":
        print("(local sink: data is in", settings.local_dir, ")")


if __name__ == "__main__":
    main()
