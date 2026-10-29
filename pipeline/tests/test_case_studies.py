"""The blueprint's six worked case studies (§8.2) as fixtures for the deterministic layer.

The AI writes the words; these tests pin down what code computes from the figures each case states:
session tags, the math check, dilution, promise delivery, volume streaks and the quarter preview,
size against market cap, funding and brownfield scoring, and former-name continuity. Inputs are the
case studies' own numbers; where the blueprint states a computed figure, the test asserts it.
"""

import pytest

from bse_intel.dossier import dossier_as_of, merge, new_dossier
from bse_intel.models import Filing, Pass2Output, QuantifiedImpact
from bse_intel.quality import quality_signals
from bse_intel.quant import check as check_quant
from bse_intel.scoring import score
from bse_intel.signals import compute
from bse_intel.timeutil import market_session


def _filing(news_id, scrip, name, when, headline, event):
    return Filing(news_id=news_id, scrip_code=scrip, company_name=name, headline=headline, subject=headline,
                  filed_at=when, filing_date=when[:10], event_type=event, route="FAST_TRACK")


def _run(dossier, filing, payload, company):
    out = Pass2Output.model_validate(payload)
    after = merge(dossier, out, filing, out.card.impact_level, filing.filed_at)
    before = dossier_as_of(dossier, filing.filed_at, inclusive=False)
    current = dossier_as_of(after, filing.filed_at)
    signals = compute(before, current, out, filing, company, every=True)
    return out, current, signals


def _card(headline, **extra):
    return {"impact_level": "HIGH", "headline": headline, "what_happened": [extra.pop("fact", headline)], **extra}


@pytest.mark.switches_off("CARD_GUIDANCE_DATED")   # the behaviour before the switch; the switch has its own tests
def test_case_1_kanoria_chemicals_triacetin_launch():
    assert market_session("2026-10-07T17:50:00+05:30") == "AFTER_MARKET"
    # Show Working: full_cap_rev_cr (250, MEMORY) * fy27_util (0.40, MEMORY) = ₹100 Cr, and 12 TPD x 330 days
    est = [QuantifiedImpact(label="FY27 incremental revenue", formula="full_cap_rev_cr * fy27_util", unit="INR_CR", result=100,
                            inputs=[{"name": "full_cap_rev_cr", "value": 250, "source": "MEMORY"},
                                    {"name": "fy27_util", "value": 0.40, "source": "MEMORY"}]),
           QuantifiedImpact(label="Annual capacity", formula="tpd * operating_days", unit="MT", result=3960,
                            inputs=[{"name": "tpd", "value": 12, "source": "FILING"},
                                    {"name": "operating_days", "value": 330, "source": "ASSUMPTION"}])]
    q = check_quant(est, "a 12 TPD plant", '{"full_cap_rev_cr": 250, "fy27_util": 0.40}')
    assert [i["check"] for i in q.items] == ["VERIFIED", "VERIFIED"] and q.mismatches == 0

    filing = _filing("kan-1", "506525", "Kanoria Chemicals & Industries Ltd", "2026-10-07T17:50:00+05:30",
                     "Commencement of commercial production of Triacetin plant", "CAPEX")
    dossier = new_dossier(filing)
    dossier["guidance"] = [{"id": "g_tri", "statement": "Commission Triacetin capacity in FY27", "due": "FY27",
                            "due_date": "2027-03-31", "given_on": "2026-09-20T11:00:00+05:30", "source_type": "AGM",
                            "source_news_id": "agm", "status": "OPEN", "status_history": []}]
    payload = {"is_material": True, "event_type": "CAPEX", "timeline_entry": "Triacetin plant launched",
               "card": _card("Kanoria Chemicals launches 12 TPD Triacetin plant at Ankleshwar",
                             fact="Launched a 12 TPD Triacetin facility at its existing GIDC Ankleshwar site",
                             deal_value={"kind": "CAPEX", "stage": "COMPLETED", "expansion": "BROWNFIELD", "usage": "MERCHANT_SALE"}),
               "dossier_delta": {"promise_updates": [{"guidance_id": "g_tri", "status": "DELIVERED", "evidence": "plant launched"}]}}
    out, current, signals = _run(dossier, filing, payload, {"market_cap_cr": 806, "median_turnover_cr": 3.8})
    assert any(s["type"] == "PROMISE_DELIVERED" for s in signals)
    s = score(payload["card"], "CAPEX", signals, current, {"market_cap_cr": 806, "ret_1m": 17.0, "ret_1w": -8.9,
                                                          "median_turnover_cr": 3.8}, needs_review=False, model_impact="HIGH")
    assert s.gates["inflection"] and s.pillars["margin"] >= 20  # promise delivered, brownfield at an existing site
    assert s.pillars["credibility"] == 15


def test_case_2_shivam_autotech_rights_issue():
    assert market_session("2026-10-08T14:58:00+05:30") == "LIVE_MARKET"
    filing = _filing("shiv-1", "532776", "Shivam Autotech Ltd", "2026-10-08T14:58:00+05:30",
                     "Rights issue terms: 19:25 at Rs 12", "RIGHTS_ISSUE")
    dossier = new_dossier(filing)
    payload = {"is_material": True, "event_type": "RIGHTS_ISSUE", "timeline_entry": "Rights terms set",
               "card": _card("Shivam Autotech sets ₹120 Cr rights issue terms at ₹12 per share", impact_level="MODERATE",
                             deal_value={"kind": "FUNDRAISE", "amount_cr": 120}),
               "dossier_delta": {"capital_actions": [{"instrument": "rights", "ratio": "19:25", "issue_price": 12, "amount_cr": 120}],
                                 "balance_sheet": {"period": "Q1FY27", "gross_debt_cr": 399, "net_worth_cr": -61.67},
                                 "financial_metrics": [{"metric": "revenue", "period": "Q1FY27", "value": 110},
                                                       {"metric": "finance_cost", "period": "Q1FY27", "value": 20.48},
                                                       {"metric": "ebitda", "period": "Q1FY27", "value": 22.0}]}}
    out, current, signals = _run(dossier, filing, payload, {"market_cap_cr": 223})
    (dilution,) = [s for s in signals if s["type"] == "DILUTION"]
    # blueprint: 76.0% more shares, 19 / (25 + 19) = 43.18% post-money dilution
    assert "19:25 entitlement: 76.0% more shares (43.2% post-money dilution)" in dilution["text"]
    distress = [s["text"] for s in quality_signals(current, "shiv-1") if s["type"] == "DISTRESS"]
    assert any(t.startswith("EBIT/interest 1.1x") and "barely covers" in t for t in distress)
    assert any("Negative net worth" in t for t in distress)
    s = score(payload["card"], "RIGHTS_ISSUE", signals, current, {"market_cap_cr": 223, "ret_1m": -3.8, "ret_1w": -2.1},
              needs_review=False, model_impact="MODERATE")
    assert s.pillars["balance_sheet"] == 3 and not s.actionable  # a rescue raise is never a Top Signal


def test_case_3_sml_mahindra_monthly_volumes():
    assert market_session("2026-10-08T15:41:00+05:30") == "AFTER_MARKET"
    filing = _filing("sml-9", "505192", "SML Mahindra Ltd", "2026-10-08T15:41:00+05:30", "Sales for September 2026",
                     "MONTHLY_BUSINESS_UPDATE")
    dossier = new_dossier(filing)
    dossier["identity"]["former_names"] = ["SML Isuzu Limited"]
    history = [("JUL-2025", 700), ("AUG-2025", 760), ("SEP-2025", 812), ("JUL-2026", 950), ("AUG-2026", 1010)]
    dossier["financial_metrics"] = [{"metric": "total_sales", "period": p, "value": v, "unit": "UNITS",
                                     "as_of": "2026-09-02T10:00:00+05:30", "source_news_id": "old"} for p, v in history]
    payload = {"is_material": True, "event_type": "MONTHLY_BUSINESS_UPDATE", "timeline_entry": "Sep sales 1,071",
               "card": _card("SML Mahindra sold 1,071 vehicles in September, up 32% YoY", impact_level="MODERATE"),
               "dossier_delta": {"financial_metrics": [{"metric": "total_sales", "period": "Sep-2026", "value": 1071, "unit": "UNITS"},
                                                       {"metric": "total_sales", "period": "Sep-2025", "value": 812, "unit": "UNITS"}]}}
    out, current, signals = _run(dossier, filing, payload, {"market_cap_cr": 8470})
    kinds = {s["type"]: s["text"] for s in signals}
    assert "up more than 25% YoY for 3 months running (latest +32%, SEP-2026)" in kinds["VOLUME_STREAK"]
    assert "QUARTER_PREVIEW" in kinds  # Jul + Aug + Sep against last year: the Q2 preview
    assert current["identity"]["former_names"] == ["SML Isuzu Limited"]


def test_case_4_evonile_pharma_rights_approval():
    filing = _filing("evo-1", "500672", "Evonile Pharma Ltd", "2026-10-08T18:05:00+05:30",
                     "Board approves rights issue of up to Rs 900 crore", "RIGHTS_ISSUE")
    dossier = new_dossier(filing)
    payload = {"is_material": True, "event_type": "RIGHTS_ISSUE", "timeline_entry": "Rights up to ₹900 Cr approved",
               "card": _card("Evonile Pharma board approves rights issue of up to ₹900 Cr", impact_level="MODERATE",
                             deal_value={"kind": "FUNDRAISE", "amount_cr": 900, "stage": "BOARD_APPROVED"}),
               "dossier_delta": {"former_names": ["Novartis India Limited"]}}
    out, current, signals = _run(dossier, filing, payload, {"market_cap_cr": 4905, "price_date": "2026-10-08"})
    scale = [s["text"] for s in signals if s["type"] == "SCALE"]
    assert scale and "18%" in " ".join(scale)  # ₹900 Cr against a ₹4,905 Cr market cap
    assert current["identity"]["former_names"] == ["Novartis India Limited"]


def test_case_5_jubilant_grant_funded_brownfield():
    assert market_session("2026-10-08T11:30:00+05:30") == "LIVE_MARKET"
    card = _card("Jubilant Pharmova to invest CAD 94.5M to double Ruby-Fill capacity",
                 fact="Government of Canada grant of CAD 23.8 million (25.2% of project cost) for expansion at its existing Kirkland facility",
                 deal_value={"kind": "CAPEX", "amount_cr": 580, "expansion": "BROWNFIELD"}, grounding={"ungrounded": []},
                 missing_disclosures=[])
    s = score(card, "CAPEX", [], {"balance_sheet": [{"net_worth_cr": 5620}]},
              {"market_cap_cr": 14849, "ret_1m": -6.6, "ret_1w": -6.7, "median_turnover_cr": 32},
              needs_review=False, model_impact="HIGH")
    assert s.pillars["balance_sheet"] == 18 and any("non-dilutive" in r for r in s.reasons)  # grant funded
    assert s.pillars["margin"] >= 20 and s.gates["price"]  # brownfield, price not run up


@pytest.mark.switches_off("CARD_GUIDANCE_DATED")   # the behaviour before the switch; the switch has its own tests
def test_case_6_hariom_pipe_solar_rollout():
    assert market_session("2026-10-14T20:03:00+05:30") == "AFTER_MARKET"
    filing = _filing("har-1", "543517", "Hariom Pipe Industries Ltd", "2026-10-14T20:03:00+05:30",
                     "Commissioning of 10 MW solar power plants", "CAPEX")
    dossier = new_dossier(filing)
    dossier["guidance"] = [{"id": "g_solar", "statement": "Commission 60 MW captive solar in phases", "due": "FY27",
                            "due_date": "2027-03-31", "given_on": "2026-05-10T11:00:00+05:30", "source_type": "CONCALL",
                            "source_news_id": "cc", "status": "ON_TRACK", "status_history": []}]
    payload = {"is_material": True, "event_type": "CAPEX", "timeline_entry": "40 of 60 MW live",
               "card": _card("Hariom Pipe commissions 10 MW solar units; 40 MW of 60 MW plan now live",
                             deal_value={"kind": "CAPEX", "stage": "PARTIALLY_COMPLETED", "progress": "40 MW of 60 MW",
                                         "usage": "CAPTIVE"}),
               "dossier_delta": {"promise_updates": [{"guidance_id": "g_solar", "status": "ON_TRACK", "evidence": "40 of 60 MW live"}]}}
    out, current, signals = _run(dossier, filing, payload, {"market_cap_cr": 2410})
    g = current["guidance"][0]
    assert g["status_history"][-1]["status"] == "ON_TRACK" and out.card.deal_value.usage == "CAPTIVE"


def test_an_exchange_holiday_is_not_a_trading_day():
    """Data chain audit B4 (22 Oct 2026): Dussehra, 20 Oct 2026, a Tuesday, read as market hours."""
    assert market_session("2026-10-20T11:00:00+05:30") == "NON_TRADING"
    assert market_session("2026-10-21T11:00:00+05:30") == "LIVE_MARKET"
