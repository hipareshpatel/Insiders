"""The six other lines of screener's quarterly table (27 Oct 2026): parsing, tolerances, screener's own rules as classes, the
lender skip, and that the referees downstream pass the new metrics through."""

from bse_intel import screener_crosscheck as sc
from bse_intel import screener_xbrl_referee as sx
from bse_intel.screener_fill import parse_full

Q = "Q4FY25"


def table(rows, basis="Consolidated", periods=(("Mar", 2025),)):
    head = "".join(f"<th>{m} {y}</th>" for m, y in periods)
    body = "".join(f"<tr><td>{label}&nbsp;+</td>" + "".join(f"<td>{v}</td>" for v in vals) + "</tr>" for label, vals in rows)
    return (f'<section id="quarters"><p>{basis} Figures in Rs. Crores</p><table><thead><tr><th></th>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></section>")


NON_LENDER = [("Sales", [100]), ("Expenses", [80]), ("Operating Profit", [20]), ("OPM %", [20]), ("Other Income", [4582]),
              ("Interest", [5]), ("Depreciation", [6]), ("Profit before tax", [4591]), ("Tax %", [25]), ("Net Profit", [3443]),
              ("EPS in Rs", [3.5])]
LENDER = [("Revenue", [100]), ("Interest", [40]), ("Expenses", [60]), ("Financing Profit", [40]), ("Financing Margin %", [40]),
          ("Other Income", [3]), ("Depreciation", [2]), ("Profit before tax", [41]), ("Tax %", [26]), ("Net Profit", [30]),
          ("EPS in Rs", [3.0])]


def entry(metric, value, period=Q):
    return {"metric": metric, "period": period, "value": value, "unit": "INR_CR", "basis": "CONSOLIDATED",
            "as_of": "2025-05-01", "source_news_id": f"xbrl:res:1:{period}"}


def dossier(metrics, lender=False):
    d = {"financial_metrics": [entry(m, v) for m, v in metrics.items()], "balance_sheet": [], "sector": "Demo"}
    if lender:
        d["industry"] = "Financial Services > Banks > Private Sector Bank"
    return d


OURS = {"revenue": 100.0, "pat": 3443.2, "ebitda": 20.2, "other_income": 635.78, "exceptional_items": 3945.73,
        "finance_cost": 5.3, "depreciation": 5.8, "pbt": 4591.3, "tax_expense": 1147.9}


def run(d, rows):
    return sc.compare_company(d, {"CONSOLIDATED": parse_full(table(rows))}, "1", "DEMO")


def six(result, metric):
    return next(p for p in result["six_pairs"] if p["metric"] == metric)


def metrics_of(result):
    return {p["metric"] for p in result["six_pairs"]}


def test_parse_full_reads_the_six_rows_by_their_labels():
    q = parse_full(table(NON_LENDER))["quarters"][Q]
    assert (q["ebitda"], q["other_income"], q["finance_cost"], q["depreciation"], q["pbt"], q["tax_pct"]) == \
        (20.0, 4582.0, 5.0, 6.0, 4591.0, 25.0)
    assert parse_full(table(NON_LENDER))["lender_layout"] is False
    page = parse_full(table(LENDER))
    assert page["lender_layout"] is True and page["quarters"][Q]["ebitda"] is None and page["quarters"][Q]["tax_pct"] == 26.0


def test_the_six_lines_match_within_half_a_crore_and_a_percentage_point():
    result = run(dossier(OURS), NON_LENDER)
    # other income 635.78 against 4,582 is the exceptional-items rule, every other line is within its rounding
    assert {p["metric"]: p["class"] for p in result["six_pairs"]} == {
        "ebitda": "match", "other_income": "matches_screener_view:exceptional_in_other_income", "finance_cost": "match", "depreciation": "match",
        "pbt": "match", "tax_pct": "match"}
    assert abs(six(result, "tax_pct")["memory_value"] - 25.0) < 0.01          # 1147.9 / 4591.3
    assert {p["metric"] for p in result["pairs"]} == {"revenue", "pat"}      # the core three are untouched


def test_adanient_other_income_holds_the_exceptional_items():
    # ADANIENT Q4FY25: 635.78 + 3,945.73 = 4,581.51, screener 4,582
    pair = six(run(dossier(OURS), NON_LENDER), "other_income")
    assert pair["class"] == "matches_screener_view:exceptional_in_other_income" and "4581.51" in pair["note"]
    assert pair["memory_value"] == 635.78 and pair["screener_value"] == 4582.0


def test_a_gap_inside_the_tolerance_or_without_a_rule_is_not_explained():
    # within twice the tolerance a second line matches by chance: plain mismatch
    d = dossier({**OURS, "other_income": 4558.0, "exceptional_items": 24.4})    # gap 24 is past 0.5% (22.9) but not twice it
    assert six(run(d, NON_LENDER), "other_income")["class"] == "mismatch"
    d = dossier({**OURS, "exceptional_items": 10.0})                              # no rule closes 635.78 -> 4,582
    assert six(run(d, NON_LENDER), "other_income")["class"] == "mismatch"
    d = dossier({**OURS, "finance_cost": 9.0, "tax_expense": 600.0})
    result = run(d, NON_LENDER)
    assert six(result, "finance_cost")["class"] == "mismatch" and six(result, "tax_pct")["class"] == "mismatch"


def test_operating_profit_named_by_excise_or_by_exceptional_items():
    excise = run(dossier({**OURS, "ebitda": 30.0, "excise_duty": 10.0}), NON_LENDER)
    assert six(excise, "ebitda")["class"] == "matches_screener_view:excise"
    exceptional = run(dossier({**OURS, "ebitda": 8.0, "exceptional_items": 12.0}), NON_LENDER)
    assert six(exceptional, "ebitda")["class"] == "exceptional_in_operating_profit"
    plain = run(dossier({**OURS, "ebitda": 33.0}), NON_LENDER)
    assert six(plain, "ebitda")["class"] == "mismatch"


def test_tax_is_current_plus_deferred_when_there_is_no_total():
    metrics = {k: v for k, v in OURS.items() if k != "tax_expense"}
    assert "tax_pct" not in metrics_of(run(dossier({**metrics, "current_tax": 1000.0}), NON_LENDER))
    result = run(dossier({**metrics, "current_tax": 1100.0, "deferred_tax": 47.9}), NON_LENDER)
    assert six(result, "tax_pct")["class"] == "match"


def test_a_lender_page_is_not_read_for_operating_profit_and_interest():
    d = dossier({**OURS, "finance_cost": 77.0, "ebitda": 1.0}, lender=True)
    assert metrics_of(run(d, LENDER)) == {"other_income", "depreciation", "pbt", "tax_pct"}
    # the page's layout alone also skips them, for a company memory does not call a lender
    other = metrics_of(run(dossier({**OURS, "finance_cost": 77.0, "ebitda": 1.0}), LENDER))
    assert "finance_cost" not in other and "ebitda" not in other


def test_summary_counts_the_six_apart_and_the_rows_reach_the_csv():
    result = run(dossier(OURS), NON_LENDER)
    out = sc.summarise([result], "2026-10-27")
    assert out["six_pairs"] == 6 and out["pairs"] == 2        # the core table is unchanged (revenue, profit)
    assert out["six_by_class"]["other_income"]["matches_screener_view:exceptional_in_other_income"] == 1
    assert out["six_by_class"]["pbt"]["match"] == 1
    assert out["by_class"]["match"] == 2
    csv_text = sc.to_csv(out)
    assert "matches_screener_view:exceptional_in_other_income" in csv_text
    assert "six other lines" in sc.render(out) and "## The six other lines" in sc.to_markdown(out, "2026-10-27")


def test_the_referees_pass_the_six_lines_through_unread():
    rows = [{"scrip": "1", "symbol": "DEMO", "basis": "CONSOLIDATED", "period": Q, "metric": "pbt", "class": "mismatch",
             "memory_value": "100", "screener_value": "120", "shifted": ""},
            {"scrip": "1", "symbol": "DEMO", "basis": "CONSOLIDATED", "period": Q, "metric": "other_income",
             "class": "matches_screener_view:exceptional_in_other_income", "memory_value": "1", "screener_value": "9", "shifted": ""}]

    class NoNse:
        def financial_results(self, symbol):
            raise AssertionError("no results list is fetched for the six lines")

    out = sx.run(NoNse(), rows)
    assert out["pairs"] == 1 and out["rows"][0]["verdict"] == "not_run" and out["rows"][0]["reason"] == "metric not refereed"
    assert out["calls"] == {"results_lists": 0, "files": 0}


# --- the screener view of our figures ------------------------------------------------------------------------------

def figs(metrics):
    return {(m, Q): entry(m, v) for m, v in metrics.items()}


def test_the_view_applies_each_rule_and_never_touches_the_figures():
    f = figs({"revenue": 200.0, "ebitda": 50.0, "excise_duty": 15.0, "other_income": 10.0, "exceptional_items": 90.0,
              "pbt": 400.0, "tax_expense": 100.0})
    v = sc.screener_view({}, f, Q)
    assert v["revenue"] == (185.0, "excise") and v["ebitda"] == (35.0, "excise")
    assert v["other_income"] == (100.0, "exceptional_in_other_income")
    assert v["exceptional_after_tax"][0] == 67.5          # article 42: tax on the item = 100 x 90 / 400 = 22.5
    assert f[("revenue", Q)]["value"] == 200.0
    big = sc.screener_view({}, figs({"exceptional_items": 10.0, "pbt": 20.0, "tax_expense": 100.0}), Q)
    assert big["exceptional_after_tax"][0] == 10.0        # a tax bigger than the item: the item is taken whole
    assert sc.screener_view({}, figs({"revenue": 200.0}), Q) == {}


def test_revenue_less_excise_is_credited_only_for_a_gap_well_outside_rounding():
    rows = [("Sales", [185]), ("Net Profit", [3443])]
    d = dossier({"revenue": 200.0, "pat": 3443.0, "excise_duty": 15.0})
    # the core revenue line keeps its existing "naming" class for revenue less excise (the view agrees with it)
    assert next(p for p in run(d, rows)["pairs"] if p["metric"] == "revenue")["class"] == "naming"
    assert sc.screener_view({}, figs({"revenue": 200.0, "excise_duty": 15.0}), Q)["revenue"] == (185.0, "excise")
    raw = dossier({"revenue": 185.0, "pat": 3443.0, "excise_duty": 15.0})         # a raw match stays a raw match
    assert next(p for p in run(raw, rows)["pairs"] if p["metric"] == "revenue")["class"] == "match"


def test_an_eps_before_a_bonus_is_put_on_todays_share_count():
    rows = [("Sales", [100]), ("Net Profit", [100]), ("EPS in Rs", [5.0])]
    d = dossier({"revenue": 100.0, "pat": 100.0, "eps": 10.0})
    d["corporate_actions"] = [{"kind": "BONUS", "factor": 2.0, "ex_date": "2026-01-10", "subject": "Bonus 1:1"}]
    assert next(p for p in run(d, rows)["pairs"] if p["metric"] == "eps")["class"] == "matches_screener_view:share_adjust"
    d["corporate_actions"] = []
    assert next(p for p in run(d, rows)["pairs"] if p["metric"] == "eps")["class"] == "mismatch"
