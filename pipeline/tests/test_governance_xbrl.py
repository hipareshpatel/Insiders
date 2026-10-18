"""The quarterly governance filing's XBRL (governance_xbrl.py), on NSE's own files for the September 2026 quarter
(directors' PAN and dates of birth removed from the fixtures). Chennai Petroleum: a board and two committees out of
line with SEBI's rules and the exchanges' fines for it; Zydus: three income-tax penalty orders and a minor food-safety
one; Harsha: a ₹648 GST penalty and a nomination committee 141 days between meetings, which no rule limits."""

from __future__ import annotations

from pathlib import Path

from bse_intel import governance_xbrl as g

FIX = Path(__file__).parent / "fixtures"


def _report(name: str) -> g.GovernanceReport:
    return g.parse((FIX / f"nse_gov_{name}_q2fy27.xml").read_bytes())


def test_board_committees_and_compliance_are_read():
    r = _report("chennpetro")
    assert (r.symbol, r.quarter_end, g.quarter_label(r.quarter_end)) == ("CHENNPETRO", "2026-09-30", "Q2FY27")
    assert len(r.board) == 11 and sum("independent" in d.category.lower() for d in r.board) == 1
    assert r.board[0].name == "Arvinder Singh Sahney" and r.board[0].role == "Chairperson related to Promoter"
    assert r.committees["audit committee"] == ["Manoj Kumar Pandey", "DEEPAK SRIVASTAVA", "BABAK BAGHERPOUR"]
    assert r.compliance["board"] is False and r.compliance["audit committee"] is False
    assert r.compliance["stakeholders relationship committee"] is True
    assert r.cyber_incident is False and r.complaints == {"received": 8.0, "disposed": 13.0, "pending": 0.0}


def test_exceptions_name_what_an_investor_would_want_to_hear():
    found = _report("chennpetro").exceptions()
    assert "board composition not in terms of SEBI's rules" in found
    assert "nomination and remuneration committee composition not in terms of SEBI's rules" in found
    fines = [e for e in found if e.startswith("fine or penalty ₹9.66 lakh")]
    assert len(fines) == 2 and "Regulation 17(1)" in fines[0]       # NSE's and BSE's, for the board's composition
    assert "guarantee or comfort to directors and relatives: ₹0.5973 Cr outstanding" in found


def test_penalty_amounts_are_read_from_their_words_and_minor_ones_kept_quiet():
    zydus = _report("zyduslife")
    assert [p["amount_rupees"] for p in zydus.penalties] == [300000.0, 260000.0, 310000.0, 8000.0]
    assert len([e for e in zydus.exceptions() if e.startswith("fine or penalty")]) == 3   # the ₹8,000 one is minor
    harsha = _report("harsha")
    assert harsha.penalties[0]["amount_rupees"] == 648.0 and harsha.exceptions() == []
    assert g.penalty_rupees("Fine of Rs. 9,66,420/- imposed") == 966420.0
    assert g.penalty_rupees("Rs 1.95 lacs") == 195000.0 and g.penalty_rupees("₹2.5 crore") == 25000000.0
    assert g.penalty_rupees("Not a material effect.") is None
    # The impact's amount before the details' (IndusInd, Q2FY27: details "Total SNR of Rs. 16.85 Crores", impact "Rs. 2,250/-")
    assert g.penalty_rupees("Rs. 2,250/-", "Total SNR of Rs. 16.85 Crores remitted") == 2250.0


def test_meeting_gaps_count_only_where_a_rule_sets_a_limit():
    harsha = _report("harsha")
    assert harsha.gaps["nomination and remuneration committee"] == 141.0 and harsha.gaps["board"] == 95.0
    assert not any("days between meetings" in e for e in harsha.exceptions())
    late = g.GovernanceReport(gaps={"board": 140.0, "risk management committee": 200.0, "audit committee": 121.0})
    assert late.exceptions() == ["board: 140 days between meetings (limit 120)",
                                 "audit committee: 121 days between meetings (limit 120)"]


def test_memory_keeps_the_board_and_no_personal_identifiers():
    m = _report("chennpetro").memory()
    assert m["board_size"] == 11 and m["independent_directors"] == 1 and m["quarter_end"] == "2026-09-30"
    assert all(set(d) == {"name", "category", "role", "appointed", "ceased", "cessation_reason", "tenure_months"} for d in m["board"])
    assert m["exceptions"][0] == "board composition not in terms of SEBI's rules"
    assert g.parse(b"<not xml") is None and g.parse(b"") is None
