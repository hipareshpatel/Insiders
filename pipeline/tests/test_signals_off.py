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
