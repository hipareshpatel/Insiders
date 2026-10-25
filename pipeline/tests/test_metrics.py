import json

from bse_intel import metrics

X = "xbrl:res:500001:"


def _entry(metric, period, value, basis="CONSOLIDATED", unit="INR_CR", news=None):
    return {"metric": metric, "period": period, "value": value, "unit": unit, "basis": basis,
            "as_of": "2026-01-01", "source_news_id": news or X + period}


def _dossier(quarters, basis="CONSOLIDATED", extra=(), **kw):
    """quarters: period -> dict of metric values."""
    rows = [_entry(m, p, v, basis) for p, vals in quarters.items() for m, v in vals.items()]
    return {"financial_metrics": rows + list(extra), "balance_sheet": [], **kw}


def _q(rev, ebitda, pat, eps=1.0):
    return {"revenue": rev, "ebitda": ebitda, "pat": pat, "eps": eps, "raw_material_cost": rev * 0.3}


FIVE = {"Q1FY26": _q(100, 20, 10), "Q2FY26": _q(110, 22, 11), "Q3FY26": _q(120, 24, 12),
        "Q4FY26": _q(130, 26, 13), "Q1FY27": _q(140, 28, 14)}


def row(rows, period):
    return next(r for r in rows if r["period"] == period)


def test_growth_margin_and_order():
    rows = metrics.table(_dossier(FIVE), "CONSOLIDATED")
    assert [r["period"] for r in rows][0] == "Q1FY27"
    r = row(rows, "Q1FY27")
    assert r["revenue"] == {"value": 140.0, "unit": "INR_CR", "source": "exchange", "inputs": ["Q1FY27"]}
    assert r["revenue_yoy"]["value"] == 40.0 and r["revenue_yoy"]["source"] == "computed"
    assert r["revenue_yoy"]["inputs"] == ["Q1FY27", "Q1FY26"]
    assert round(r["revenue_qoq"]["value"], 2) == 7.69
    assert r["ebitda_margin"]["value"] == 20.0
    assert r["raw_material_cost_share"]["value"] == 30.0
    assert r["ebitda"]["source"] == "computed"


def test_missing_input_is_none_not_zero():
    rows = metrics.table(_dossier(FIVE), "CONSOLIDATED")
    old = row(rows, "Q1FY26")
    assert old["revenue_yoy"]["value"] is None and old["revenue_qoq"]["value"] is None
    assert old["employee_cost_share"]["value"] is None
    assert old["profit_to_shareholders"]["value"] is None


def test_ttm_needs_four_consecutive_quarters():
    rows = metrics.table(_dossier(FIVE), "CONSOLIDATED")
    assert row(rows, "Q4FY26")["ttm_revenue"]["value"] == 460.0
    assert row(rows, "Q1FY27")["ttm_revenue"]["inputs"] == ["Q1FY27", "Q4FY26", "Q3FY26", "Q2FY26"]
    assert row(rows, "Q3FY26")["ttm_revenue"]["value"] is None
    gap = {k: v for k, v in FIVE.items() if k != "Q3FY26"}
    rows = metrics.table(_dossier(gap), "CONSOLIDATED")
    assert row(rows, "Q4FY26")["ttm_revenue"]["value"] is None
    assert row(rows, "Q1FY27")["ttm_revenue"]["value"] is None
    assert row(rows, "Q4FY26")["revenue_qoq"]["value"] is None   # Q3 is missing


def test_basis_never_mixed():
    d = _dossier({"Q1FY27": _q(140, 28, 14)}, "CONSOLIDATED")
    d["financial_metrics"] += [_entry(m, "Q1FY26", v, "STANDALONE") for m, v in _q(50, 10, 5).items()]
    r = metrics.table(d, "CONSOLIDATED")
    assert [x["period"] for x in r] == ["Q1FY27"]
    assert r[0]["revenue_yoy"]["value"] is None          # the year-ago quarter is standalone only
    assert [x["period"] for x in metrics.table(d, "STANDALONE")] == ["Q1FY26"]


def test_standalone_part_and_card_figures_ignored():
    d = _dossier({"Q1FY27": _q(140, 28, 14)})
    d["standalone"] = {"metrics": [{"metric": "revenue", "period": "Q1FY27", "value": 90, "unit": "INR_CR",
                                    "source_news_id": "xbrl:res-sa:500001:Q1FY27"}], "balance_sheet": []}
    d["financial_metrics"].append(_entry("revenue", "Q2FY27", 150, news="nse-123"))   # a card's figure
    assert metrics.table(d, "STANDALONE")[0]["revenue"]["value"] == 90.0
    assert [r["period"] for r in metrics.table(d, "CONSOLIDATED")] == ["Q1FY27"]


def test_bank_gets_no_ebitda():
    q = {"interest_earned": 1000, "interest_expended": 600, "pre_provision_operating_profit": 250,
         "other_income": 100, "pat": 120, "ebitda": 999, "revenue": 1100}
    d = _dossier({"Q1FY26": dict(q), "Q1FY27": {**q, "interest_earned": 1200, "interest_expended": 700}})
    d["financial_metrics"].append(_entry("gnpa_pct", "Q1FY27", 2.1, unit="PCT"))
    r = row(metrics.table(d, "CONSOLIDATED"), "Q1FY27")
    assert r["kind"] == "lender"
    assert r["ebitda"]["value"] is None and r["ebitda_margin"]["value"] is None
    assert r["nii"] == {"value": 500.0, "unit": "INR_CR", "source": "computed",
                        "inputs": ["Q1FY27", "interest_earned", "interest_expended"]}
    assert r["nii_yoy"]["value"] == 25.0
    assert r["gnpa_pct"]["source"] == "exchange"
    assert r["cost_to_income"]["value"] == round((600 - 250) / 600 * 100, 2)
    assert metrics.missing_lines(d) == metrics.LENDER_MISSING


def test_lender_by_industry_even_without_bank_lines():
    d = _dossier({"Q1FY27": _q(100, 20, 10)}, industry="Finance - NBFC")
    assert metrics.table(d, "CONSOLIDATED")[0]["ebitda"]["value"] is None


def test_wrong_unit_left_out_and_balance_sheet_ratio():
    d = _dossier({"Q2FY27": _q(100, 20, 10)})
    d["financial_metrics"].append(_entry("other_expenses", "Q2FY27", 5e8, unit="INR"))
    d["balance_sheet"] = [{"period": "Q2FY27", "gross_debt_cr": 50, "net_worth_cr": 200,
                           "source_news_id": X + "Q2FY27"}]
    r = metrics.table(d, "CONSOLIDATED")[0]
    assert r["other_expenses_share"]["value"] is None
    assert r["debt_to_equity"]["value"] == 0.25
    assert metrics.table(d, "STANDALONE") == []


def test_cli_renders(tmp_path, capsys):
    from bse_intel import cli

    f = tmp_path / "d.json"
    f.write_text(json.dumps(_dossier(FIVE)))
    assert cli.cmd_metrics(type("A", (), {"file": str(f), "scrip": "1", "basis": "CONSOLIDATED", "quarters": 3,
                                          "json": False})(), None, None) == 0
    assert "Q1FY27" in capsys.readouterr().out
