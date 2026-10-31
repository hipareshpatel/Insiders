import json

from bse_intel.radar import summarize


def _m(metric, period, value, as_of, yoy=None):
    return {"metric": metric, "period": period, "value": value, "unit": "INR_CR", "yoy_pct": yoy, "as_of": as_of}


def dossier():
    return {
        "guidance": [
            {"id": "g1", "statement": "Commission 2 MTPA grinding unit", "due": "Q4FY26", "due_date": "2026-03-31",
             "given_on": "2025-05-10T10:00:00+05:30", "status": "OPEN",
             "status_history": [{"status": "DELIVERED", "as_of": "2026-08-01T10:00:00+05:30"}]},
            {"id": "g2", "statement": "Debt-free by FY26", "due": "FY26", "due_date": "2026-03-31",
             "given_on": "2025-06-01T10:00:00+05:30", "status": "OPEN", "status_history": []},
            {"id": "g3", "statement": "Revenue ₹500 Cr in FY27", "due": "FY27", "due_date": "2027-03-31",
             "given_on": "2026-05-01T10:00:00+05:30", "status": "OPEN",
             "status_history": [{"status": "ON_TRACK", "as_of": "2026-08-01T10:00:00+05:30"}]},
        ],
        "financial_metrics": [
            _m("ebitda_margin", "Q1FY26", 12.0, "2025-08-10T10:00:00+05:30"),
            _m("ebitda_margin", "Q1FY27", 14.0, "2026-08-10T10:00:00+05:30"),
            _m("revenue", "Q1FY27", 120.0, "2026-08-10T10:00:00+05:30"),
            _m("sales_volume", "JUL-2026", 1000, "2026-08-02T10:00:00+05:30", yoy=24),
            _m("sales_volume", "AUG-2026", 1100, "2026-09-02T10:00:00+05:30", yoy=31),
        ],
        "balance_sheet": [{"gross_debt_cr": 200.0, "as_of": "2026-05-01T10:00:00+05:30"},
                          {"gross_debt_cr": 150.0, "as_of": "2026-08-10T10:00:00+05:30"}],
        "ownership": [{"period": "Q4FY26", "promoter_pct": 50, "fii_pct": 5, "dii_pct": 5, "as_of": "2026-04-20T10:00:00+05:30"},
                      {"period": "Q1FY27", "promoter_pct": 50, "fii_pct": 5.5, "dii_pct": 5.2, "as_of": "2026-07-20T10:00:00+05:30"}],
        "deals": [{"id": "d1", "kind": "CAPEX", "stage": "IN_PROGRESS", "as_of": "2026-01-01T10:00:00+05:30"}],
    }


def test_summary_lists_open_promises_by_due_date_and_triggers():
    s = summarize(dossier())
    summary = s["memory_summary_json"]
    assert [p["id"] for p in summary["open_promises"]] == ["g2", "g3"]  # g1 delivered
    assert s["earliest_open_due"] == "2026-05-30"
    kinds = {t["kind"]: t for t in summary["triggers"]}
    assert set(kinds) == {"CAPEX_COMMISSIONED", "VOLUME_STREAK", "MARGIN_EXPANSION", "DELEVERAGING"}
    assert kinds["MARGIN_EXPANSION"]["text"].endswith("+200 bps YoY")
    assert kinds["DELEVERAGING"]["text"] == "Gross debt down 25% to ₹150 Cr"
    assert s["inflection_last_at"] == "2026-09-02"
    assert summary["active_capex"] == 1 and summary["revenue"] == {"period": "Q1FY27", "value": 120.0}
    json.dumps(s)  # stored as JSON


def test_smart_money_needs_a_full_point():
    d = dossier()
    d["ownership"][1]["fii_pct"] = 6.0
    assert "SMART_MONEY" in {t["kind"] for t in summarize(d)["memory_summary_json"]["triggers"]}
    assert summarize({})["inflection_last_at"] is None


def test_period_deadline_is_overdue_only_once_its_results_are_due():
    """Stock-page audit 137, B1: a Q2FY27 promise showed '30 days overdue' on 30 Oct, before the 14 Nov results window."""
    from bse_intel.radar import open_promises

    d = {"guidance": [
        {"id": "q2", "statement": "Margin 18% in Q2FY27", "due": "Q2FY27", "due_date": "2026-09-30",
         "given_on": "2026-07-20T10:00:00+05:30", "status": "OPEN", "status_history": []},
        {"id": "day", "statement": "Plant live by 30 Sep 2026", "due": "30 Sep 2026", "due_date": "2026-09-30",
         "given_on": "2026-07-20T10:00:00+05:30", "status": "OPEN", "status_history": []}]}
    got = {p["id"]: p for p in open_promises(d)}
    assert got["q2"]["due_date"] == "2026-09-30" and got["q2"]["overdue_from"] == "2026-11-14"
    assert got["day"]["overdue_from"] == "2026-09-30"
    assert summarize(dict(d, financial_metrics=[], balance_sheet=[]))["earliest_open_due"] == "2026-09-30"


def test_deadline_before_it_was_said_is_dropped_and_a_december_year_is_read():
    """Audit 137, B3: Castrol (December year end) said 'FY26' on 10 Aug 2026 and got 31 Mar 2026, 'overdue' at birth."""
    from bse_intel.dossier import merge, new_dossier
    from bse_intel.models import Filing, Pass2Output
    from bse_intel.periods import due_date, results_due
    from bse_intel.radar import open_promises

    assert due_date("FY26", 12).isoformat() == "2026-12-31"
    assert due_date("Q2FY27", 12).isoformat() == "2027-06-30"
    assert due_date("H1FY27", 12).isoformat() == "2027-06-30"
    assert due_date("Q4FY26", 12).isoformat() == "2026-12-31"
    assert due_date("FY26", 3).isoformat() == "2026-03-31" == due_date("FY26").isoformat()
    assert results_due("FY26", 12).isoformat() == "2027-03-01"
    f = Filing(news_id="n1", scrip_code="500870", company_name="Castrol India Ltd", headline="Call", filed_at="2026-08-10T10:00:00",
               filing_date="2026-08-10")
    out = Pass2Output.model_validate({"is_material": True, "event_type": "EARNINGS_CALL", "card": {
        "impact_level": "LOW", "headline": "Castrol call guidance", "what_happened": ["x"]},
        "dossier_delta": {"guidance": [{"statement": "Revenue growth of 8% in FY26", "due": "FY26"},
                                       {"statement": "Capex of 100 Cr in Q1FY25", "due": "Q1FY25"}]}})
    seed = new_dossier(f)
    seed["fy_end_month"] = 12
    g = merge(seed, out, f, "LOW", "2026-08-10T10:00:00")["guidance"]
    assert next(x for x in g if "FY26" in x["statement"])["due_date"] == "2026-12-31"
    assert next(x for x in g if "Q1FY25" in x["statement"])["due_date"] is None   # earlier than the day it was said
    # stored rows with a wrong date are not shown overdue at birth either
    old = {"guidance": [{"id": "o", "statement": "s", "due": "FY26", "due_date": "2026-03-31", "given_on": "2026-08-10T10:00:00",
                         "status": "OPEN", "status_history": []}], "fy_end_month": 12}
    assert open_promises(old)[0]["due_date"] == "2026-12-31"


def test_judged_date_not_period_end_decides_a_deadline_said_after_its_period():
    """Review fix: H1FY27 said on 16 Oct ends 30 Sep but is judged 14 Nov, so it keeps its date; Q4FY26 said in May too."""
    from bse_intel.dossier import merge, new_dossier
    from bse_intel.models import Filing, Pass2Output
    from bse_intel.radar import open_promises

    def run(filed, due, text):
        f = Filing(news_id="n1", scrip_code="500001", company_name="Prism Co Ltd", headline="Call", filed_at=f"{filed}T10:00:00",
                   filing_date=filed)
        out = Pass2Output.model_validate({"is_material": True, "event_type": "EARNINGS_CALL", "card": {
            "impact_level": "LOW", "headline": "Prism call guidance", "what_happened": ["x"]},
            "dossier_delta": {"guidance": [{"statement": text, "due": due}]}})
        return merge(new_dossier(f), out, f, "LOW", f"{filed}T10:00:00")["guidance"][0]

    assert run("2026-10-16", "H1FY27", "Margin of 18% in H1FY27")["due_date"] == "2026-09-30"
    assert run("2026-05-15", "Q4FY26", "Capex done in Q4FY26")["due_date"] == "2026-03-31"
    assert run("2026-06-15", "Q4FY26", "Capex done in Q4FY26")["due_date"] is None   # results were due 30 May: misread
    g = {"id": "h", "statement": "s", "due": "H1FY27", "due_date": "2026-09-30", "given_on": "2026-10-16T10:00:00",
         "status": "OPEN", "status_history": []}
    got = open_promises({"guidance": [g]})[0]
    assert got["due_date"] == "2026-09-30" and got["overdue_from"] == "2026-11-14"


def test_latest_revenue_and_ebitda_come_from_the_statements_when_stored():
    d = dossier()
    d["statements"] = [
        {"period": "Q1FY27", "basis": "STANDALONE", "table": "quarters", "rows": {"Sales": 90.0, "Operating Profit": 9.0}},
        {"period": "Q4FY26", "basis": "CONSOLIDATED", "table": "quarters", "rows": {"Sales": 100.0, "Operating Profit": 12.0}},
        {"period": "Q1FY27", "basis": "CONSOLIDATED", "table": "quarters", "rows": {"Sales": 130.0, "Operating Profit": 15.5}},
    ]
    summary = summarize(d)["memory_summary_json"]
    assert summary["revenue"] == {"period": "Q1FY27", "value": 130.0}
    assert summary["ebitda"] == {"period": "Q1FY27", "value": 15.5}
    d["statements"] = [{"period": "Q1FY27", "basis": "STANDALONE", "table": "quarters", "rows": {"Revenue": 50.0, "Financing Profit": 20.0}}]
    summary = summarize(d)["memory_summary_json"]
    assert summary["revenue"] == {"period": "Q1FY27", "value": 50.0} and summary["ebitda"] == {"period": "Q1FY27", "value": 20.0}
