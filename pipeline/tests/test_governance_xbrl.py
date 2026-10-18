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


def test_memory_keeps_quarters_a_revision_replaces_its_quarter_and_the_view_is_dated():
    from bse_intel.dossier import governance_view, merge_governance, view_as_of

    d = {"company_name": "Chennai Petroleum", "governance": {"auditor": None, "auditor_history": []}}
    q2 = _report("chennpetro").memory()
    q1 = dict(q2, quarter_end="2026-06-30", exceptions=[], board=q2["board"][1:] + [
        {"name": "Former Director", "category": "Non-Executive - Independent Director", "role": None, "appointed": None,
         "ceased": None, "cessation_reason": None, "tenure_months": None}])
    assert merge_governance(d, q1, "2026-07-20T18:00:00+05:30", "https://x/q1.xml")
    assert merge_governance(d, q2, "2026-10-17T18:00:00+05:30", "https://x/q2.xml")
    assert not merge_governance(d, q2, "2026-10-17T18:00:00+05:30", "https://x/q2.xml")       # the same file twice
    assert merge_governance(d, q2, "2026-10-18T09:00:00+05:30", "https://x/q2-revised.xml")   # a revision replaces it
    assert [q["source"] for q in d["governance"]["quarters"]] == ["https://x/q1.xml", "https://x/q2-revised.xml"]
    view = governance_view(d["governance"]["quarters"])
    assert view["board_size"] == 11 and view["independent_directors"] == 1
    assert view["exceptions"][0] == "board composition not in terms of SEBI's rules"
    assert view["board_changes"] == {"joined": ["Arvinder Singh Sahney"], "left": ["Former Director"]}
    # A card filed in August sees the June quarter only, which was clean
    august = view_as_of(d, "2026-08-10T10:00:00+05:30")
    assert august["governance"]["quarter_end"] == "2026-06-30" and "exceptions" not in august["governance"]
    assert view_as_of(d, "2026-10-19T10:00:00+05:30")["governance"]["quarter_end"] == "2026-09-30"


class GovNse:
    def __init__(self, rows, files):
        self.rows, self.files, self.downloads = rows, files, []

    def integrated_list(self, kind, page=1, size=500):
        assert kind == "Integrated Filing- Governance"
        return self.rows if page == 1 else []

    def download(self, url, max_bytes=None):
        self.downloads.append(url)
        return self.files.get(url)


def test_sync_files_the_universe_companies_reports_once(settings):
    import json
    import time
    from types import SimpleNamespace

    from bse_intel import governance_memory, universe
    from bse_intel.sinks.local import LocalSink

    sink = LocalSink(settings)
    sink.put_object(universe.UNIVERSE_KEY, json.dumps({"source": "nse", "included": ["500110"],
                                                       "symbols": {"CHENNPETRO": "500110", "TINY": "500999"}, "isins": {}}).encode())
    url_old, url_new = "https://x/INTEGRATED_FILING_GOVERNANCE_1.xml", "https://x/INTEGRATED_FILING_GOVERNANCE_2.xml"
    rows = [{"symbol": "CHENNPETRO", "qe_Date": "30-SEP-2026", "xbrl": url_new, "type_Sub": "Revision",
             "revised_Date": "18-OCT-2026 21:27:17", "broadcast_Date": None, "smName": "Chennai Petroleum"},
            {"symbol": "CHENNPETRO", "qe_Date": "30-SEP-2026", "xbrl": url_old, "type_Sub": "New",
             "broadcast_Date": "17-Oct-2026 18:00:00"},
            {"symbol": "TINY", "qe_Date": "30-SEP-2026", "xbrl": "https://x/tiny.xml", "broadcast_Date": "17-Oct-2026 18:00:00"}]
    body = (FIX / "nse_gov_chennpetro_q2fy27.xml").read_bytes()
    pipe = SimpleNamespace(nse=GovNse(rows, {url_new: body}), sink=sink, _nse_refused=False)
    first = governance_memory.sync(pipe, time.monotonic() + 60)
    assert first["filed"] == 1 and first["in_universe"] == 1 and pipe.nse.downloads == [url_new]   # the revision only
    quarters = sink.get_dossier("500110")["governance"]["quarters"]
    assert quarters[0]["as_of"] == "2026-10-18T21:27:17+05:30" and quarters[0]["source"] == url_new
    again = governance_memory.sync(pipe, time.monotonic() + 60)
    assert again["filed"] == 0 and again["known"] == 1 and pipe.nse.downloads == [url_new]
