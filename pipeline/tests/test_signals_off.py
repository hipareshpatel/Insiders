"""Signals that contradicted their card in audit round 2 are off the card and out of the score until each is checked.
Each test is a round-2 card."""
from __future__ import annotations

from bse_intel.dossier import new_dossier
from bse_intel.models import Filing, Pass2Output
from bse_intel.scoring import score
from bse_intel.signals import misfires


def _out(event: str, deal: dict | None = None, headline: str = "A company files something") -> Pass2Output:
    card = {"impact_level": "MODERATE", "headline": headline, "what_happened": ["x"]}
    if deal:
        card["deal_value"] = deal
    return Pass2Output.model_validate({"is_material": True, "event_type": event, "timeline_entry": "x", "card": card})


def test_magellanic_dilution_is_off():
    """cac7f199: "6.3% more shares" counted 3.69 Cr equity shares and left out 12.67 Cr warrants (about 27.8%)."""
    assert misfires({"type": "DILUTION", "text": "6.3% more shares (5.9% post-money dilution)"}, _out("FUNDRAISE"))


def test_lehar_a_rating_action_is_not_a_fundraise():
    """46a22751 / reviewer_02: a rating reaffirmation on ₹105 Cr of bank limits read "₹105 Cr raise = 29% of market cap"."""
    out = _out("DEBT_RATINGS", {"kind": "FUNDRAISE", "amount_cr": 105})
    assert misfires({"type": "SCALE", "text": "₹105 Cr raise = 29% of market cap"}, out)
    assert not misfires({"type": "SCALE", "text": "₹396.5 Cr order = 10% of revenue"}, _out("ORDER_WIN", {"kind": "ORDER", "amount_cr": 396.5}))


def test_adani_power_an_approval_met_on_an_unrelated_order_is_off():
    """799d649d: the GVK Energy approvals were marked met on NCLT Mumbai's sanction of an unrelated amalgamation."""
    assert misfires({"type": "WATCH_RESOLVED", "text": "Approval met: NCLT Hyderabad sanction"}, _out("M_AND_A"))
    assert not misfires({"type": "WATCH_RESOLVED", "text": "Approval missed: deadline passed"}, _out("M_AND_A"))


def test_novartis_an_open_offer_does_not_set_the_size_score():
    """277aec74: a daily tender count for Novartis's open offer ranked first, sized by the offer's value."""
    f = Filing(news_id="n", scrip_code="500672", company_name="Novartis India Ltd", headline="Open offer update",
               filed_at="2026-06-11T18:00:00+05:30", filing_date="2026-06-11")
    d = new_dossier(f)
    card = {"headline": "Novartis India open offer at ₹860.64 for 26%: 1,200 shares tendered on day 3",
            "what_happened": ["Open offer tendering continues"], "deal_value": {"kind": "ACQUISITION", "amount_cr": 552.5},
            "impact_level": "HIGH"}
    result = score(card, "M_AND_A", [], d, {"market_cap_cr": 2000}, False, "HIGH")
    assert not any("% of market cap" in r for r in result.reasons), result.reasons

    # the same amount on an acquisition the company makes is sized against market cap
    card = {**card, "headline": "Novartis India to acquire a plant for ₹552.5 Cr", "what_happened": ["Acquisition agreed"]}
    result = score(card, "M_AND_A", [], d, {"market_cap_cr": 2000}, False, "HIGH")
    assert "Size: 28% of market cap" in result.reasons


def test_round_4_false_signals():
    """Round 4 (blind agents): an 8-hour "board meeting" that was a postal ballot's e-voting window (Torrent), the Para B
    threshold claimed where the filing says "no major financial impact" (Nuvoco), interest cover on a lender (HUDCO),
    and JAWS / CAPITAL_DILUTER on mixed bases."""
    from bse_intel.forensics import text_signals
    from bse_intel.quality import quality_signals
    from bse_intel.signals import SIGNALS_OFF

    ballot = ("Results of postal ballot. The remote e-voting commenced at 9:00 a.m. on 10 September and ended at 5:00 p.m. "
              "on 9 October 2026. The scrutinizer's report is enclosed.")
    assert text_signals(ballot, "GOVERNANCE") == []
    board = "The meeting of the Board of Directors commenced at 10:00 a.m. and concluded at 6:30 p.m."
    assert [s["type"] for s in text_signals(board, "RESULTS")] == ["BOARD_DELIBERATION"]
    para_b = ("Disclosure under Para B of Schedule III: a show cause notice of Rs 15.41 Cr. The company believes it will have "
              "no major financial impact.")
    assert text_signals(para_b, "LITIGATION_REGULATORY") == []
    assert [s["type"] for s in text_signals("Disclosure under Para B of Schedule III: an order.", "ORDER_WIN")] == ["REG30_THRESHOLD"]
    assert {"JAWS", "CAPITAL_DILUTER"} <= set(SIGNALS_OFF)
    lender = {"sector": "nbfc", "financial_metrics": [
        {"metric": m, "period": "Q1FY27", "value": v, "unit": "INR_CR", "as_of": "2026-08-10", "source_news_id": "n"}
        for m, v in (("revenue", 3000.0), ("finance", 2000.0), ("ebitda", 2700.0), ("depreciation", 10.0))]}
    assert not [s for s in quality_signals(lender, "n") if s["type"] == "DISTRESS"]


def test_the_site_hides_the_same_signal_types():
    """Cards written before a type was turned off still carry it; the site drops those at parse time
    (FilingCard.tsx SIGNALS_OFF). The two lists must match (live reviews 1-2, 2026-10-20)."""
    import re
    from pathlib import Path

    from bse_intel.signals import SIGNALS_OFF

    tsx = (Path(__file__).resolve().parents[2] / "web/src/components/FilingCard.tsx").read_text(encoding="utf-8")
    block = re.search(r"SIGNALS_OFF = new Set<string>\(\[(.*?)\]\)", tsx, re.S).group(1)
    assert set(re.findall(r'"([A-Z_]+)"', block)) == set(SIGNALS_OFF)
