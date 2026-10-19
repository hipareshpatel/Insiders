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
    assert s["earliest_open_due"] == "2026-03-31"
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
