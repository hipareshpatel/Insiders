"""The screener cross-check (F163): each class, memory's own period checks, the referee's verdicts, the reports."""

import json
from pathlib import Path

from bse_intel import screener_crosscheck as sc
from bse_intel import screener_download as sd
from bse_intel import screener_referee as ref
from bse_intel.screener_fill import parse_full

FIXTURES = Path(__file__).parent / "fixtures"
QUARTERS = ["Q1FY25", "Q2FY25", "Q3FY25", "Q4FY25", "Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26"]
REVENUE = [1210.4, 1304.9, 1417.2, 1522.6, 1633.1, 1748.5, 1861.3, 1979.8]
PROFIT = [101.2, 117.8, 126.4, 140.9, 155.3, 171.6, 183.2, 199.7]


def entry(metric, period, value, source=None, as_of="2027-01-01"):
    return {"metric": metric, "period": period, "value": value, "unit": "INR_CR", "basis": "CONSOLIDATED", "as_of": as_of,
            "source_news_id": source or f"xbrl:res:1:{period}"}


def dossier(extra=(), revenue=REVENUE, profit=PROFIT, lender=False, **kw):
    rows = []
    for period, r, p in zip(QUARTERS, revenue, profit):
        rows.append(entry("interest_earned" if lender else "revenue", period, r, **kw))
        rows.append(entry("pat", period, p, **kw))
    return {"financial_metrics": rows + list(extra), "balance_sheet": [], "sector": "Demo"}


def page(revenue=REVENUE, profit=PROFIT, eps=None, annual=None):
    return {"CONSOLIDATED": {"basis": "CONSOLIDATED", "annual": annual or {},
                             "quarters": {q: {"revenue": r, "pat": p, "eps": e}
                                          for q, r, p, e in zip(QUARTERS, revenue, profit, eps or [None] * 8)}}}


def classes(result, metric=None, period=None):
    return {(p["period"], p["metric"]): p["class"] for p in result["pairs"]
            if (metric is None or p["metric"] == metric) and (period is None or p["period"] == period)}


def run(d, pages):
    return sc.compare_company(d, pages, "1", "DEMO")


# --- the classes -----------------------------------------------------------------------------------------------------

def test_match_within_a_crore_or_half_a_percent():
    near = [round(r) for r in REVENUE]
    result = run(dossier(), page(revenue=near))
    assert set(classes(result).values()) == {"match"} and len(result["pairs"]) == 16


def test_a_mislabelled_quarter_is_wrong_quarter_with_both_labels():
    revenue = list(REVENUE)
    revenue[5] = REVENUE[1]              # memory's Q2FY26 holds the figure of Q2FY25 (a year-ago comparative stored as current)
    result = run(dossier(revenue=revenue), page())
    assert classes(result, "revenue")[("Q2FY26", "revenue")] == "wrong_quarter"
    pair = next(p for p in result["pairs"] if p["period"] == "Q2FY26" and p["metric"] == "revenue")
    assert pair["shifted"] == ["Q2FY25"] and "Q2FY26" in pair["note"] and "Q2FY25" in pair["note"]


def test_a_wrong_quarter_match_needs_a_figure_of_five_crore_and_reports_chance_risk():
    small = run(dossier(profit=[1.2, 3.3, 2.1, 4.4, 3.3, 2.0, 1.9, 4.1]), page(profit=[1.2, 3.3, 2.1, 4.4, 2.0, 3.3, 1.9, 4.1]))
    assert classes(small, "pat")[("Q1FY26", "pat")] == "mismatch"
    revenue = list(REVENUE)
    revenue[5] = 1500.0
    theirs = list(REVENUE)
    theirs[1] = theirs[3] = 1500.0       # two other columns hold the same figure
    wide = run(dossier(revenue=revenue), page(revenue=theirs))
    pair = next(p for p in wide["pairs"] if p["period"] == "Q2FY26" and p["metric"] == "revenue")
    assert pair["class"] == "wrong_quarter" and "chance risk: 2" in pair["note"]


def test_a_unit_slip_is_scale():
    revenue = list(REVENUE)
    revenue[3] = REVENUE[3] * 10
    assert classes(run(dossier(revenue=revenue), page()), "revenue")[("Q4FY25", "revenue")] == "scale"


def test_screener_equal_to_another_official_line_is_naming():
    extra = [entry("total_income", q, r) for q, r in zip(QUARTERS, REVENUE)]
    result = run(dossier(extra=extra, revenue=[r - 25.0 for r in REVENUE]), page())
    assert set(classes(result, "revenue").values()) == {"naming"}
    note = next(p["note"] for p in result["pairs"] if p["metric"] == "revenue")
    assert note == "screener Sales = our total_income"


def test_profit_attributable_to_owners_is_naming_and_net_of_excise_too():
    extra = [entry("pat_owners", q, p) for q, p in zip(QUARTERS, PROFIT)]
    extra += [entry("excise_duty", q, 40.0) for q in QUARTERS]
    result = run(dossier(extra=extra, profit=[p + 4 for p in PROFIT], revenue=[r + 40.0 for r in REVENUE]), page())
    assert set(classes(result, "pat").values()) == {"naming"}
    assert set(classes(result, "revenue").values()) == {"naming"}
    assert next(p["note"] for p in result["pairs"] if p["metric"] == "revenue") == "screener Sales = our revenue less excise_duty"


def test_a_steady_difference_in_sales_is_a_definition_not_a_mismatch():
    result = run(dossier(), page(revenue=[r - 133.0 for r in REVENUE]))
    assert set(classes(result, "revenue").values()) == {"steady_line_difference"}


def test_two_odd_quarters_are_mismatches_not_steady():
    theirs = list(REVENUE)
    theirs[0] += 300
    theirs[6] -= 90
    assert set(classes(run(dossier(), page(revenue=theirs)), "revenue").values()) == {"match", "mismatch"}


def test_a_lenders_profit_and_income_are_a_definition_difference():
    d = dossier(lender=True)
    result = run(d, page(profit=[p * 1.9 for p in PROFIT], revenue=[r * 1.31 for r in REVENUE]))
    assert set(classes(result).values()) == {"lender_definition"}


def test_eps_is_compared_where_both_have_it():
    d = dossier(extra=[entry("eps", "Q4FY26", 12.34)])
    assert classes(run(d, page(eps=[None] * 7 + [12.34])), "eps") == {("Q4FY26", "eps"): "match"}
    assert classes(run(d, page(eps=[None] * 7 + [13.9])), "eps") == {("Q4FY26", "eps"): "mismatch"}


def test_the_annual_row_is_compared_too():
    d = dossier(extra=[entry("revenue", "FY25", 5455.1)])
    result = run(d, page(annual={"FY25": {"revenue": 5455.0, "pat": None, "eps": None}}))
    assert classes(result, "revenue")[("FY25", "revenue")] == "match"


def test_gaps_both_ways_inside_screeners_span():
    d = dossier()
    d["financial_metrics"] = [e for e in d["financial_metrics"] if e["period"] != "Q2FY25"]
    p = page()
    del p["CONSOLIDATED"]["quarters"]["Q3FY26"]
    result = run(d, p)
    assert {(g["period"], g["class"]) for g in result["gaps"]} == {("Q2FY25", "screener_only"), ("Q3FY26", "memory_only")}


def test_a_company_without_a_page_on_its_basis_is_skipped():
    assert run(dossier(), {})["skipped"]


# --- memory's own period checks ---------------------------------------------------------------------------------------

def figures_of(d):
    from bse_intel.metrics import _figures
    return _figures(d, "CONSOLIDATED")[0]


def test_the_same_value_stored_for_two_quarters_is_suspect():
    revenue = list(REVENUE)
    revenue[4] = revenue[3]
    found = sc.memory_suspects(figures_of(dossier(revenue=revenue)))
    assert {(s["period"], s["kind"]) for s in found} == {("Q4FY25", "copy_forward"), ("Q1FY26", "copy_forward")}
    assert all(s["class"] == "memory_period_suspect" for s in found)


def test_a_source_filed_before_its_quarter_ended_is_suspect():
    d = dossier()
    for e in d["financial_metrics"]:
        if e["period"] == "Q4FY26" and e["metric"] == "revenue":
            e["as_of"] = "2026-02-01"      # the quarter ends 2026-03-31
    found = sc.memory_suspects(figures_of(d))
    assert [(s["period"], s["metric"], s["kind"]) for s in found] == [("Q4FY26", "revenue", "filed_before_quarter_end")]


def test_a_quarter_whose_source_file_is_labelled_for_another_quarter_is_suspect():
    d = dossier()
    for e in d["financial_metrics"]:
        if e["period"] == "Q3FY26" and e["metric"] == "pat":
            e["source_news_id"] = "xbrl:res:1:Q2FY26"
    found = sc.memory_suspects(figures_of(d))
    assert [(s["period"], s["kind"]) for s in found] == [("Q3FY26", "source_label_differs")]
    assert "Q2FY26" in found[0]["note"]


def test_a_clean_company_has_no_suspects_and_they_ride_with_the_result():
    assert run(dossier(), page())["suspects"] == []
    revenue = list(REVENUE)
    revenue[1] = revenue[0]
    assert len(run(dossier(revenue=revenue), page())["suspects"]) == 2
    assert len(run(dossier(revenue=revenue), {})["suspects"]) == 2     # no screener page needed


# --- the referee ------------------------------------------------------------------------------------------------------

TEXT = """Statement of unaudited results
Particulars Quarter ended Quarter ended Quarter ended
30.09.2025 30.06.2025 30.09.2024
1 Revenue from operations 1,748.50 1,633.10 1,304.90
2 Total income 1,800.00 1,700.00 1,350.00
Basic EPS 12.34 11.00 9.50
"""


def pair(ours, theirs, cls="mismatch", metric="revenue", period="Q2FY26"):
    return {"memory_value": ours, "screener_value": theirs, "class": cls, "metric": metric, "period": period}


def test_referee_ours_matches_official():
    out = ref.referee(pair(1748.5, 1790.0), [TEXT])
    assert out["verdict"] == "ours_matches_official" and "1,748.50" in out["snippet"]


def test_referee_screener_matches_official_with_its_whole_crore_rounding():
    assert ref.referee(pair(1799.4, 1748.0), [TEXT])["verdict"] == "screener_matches_official"


def test_referee_both_match_when_they_are_two_different_lines():
    assert ref.referee(pair(1748.5, 1800.0), [TEXT])["verdict"] == "both_match"


def test_referee_neither():
    assert ref.referee(pair(1111.0, 2222.0), [TEXT])["verdict"] == "neither"


def test_referee_no_official_text():
    assert ref.referee(pair(1748.5, 1800.0), [])["verdict"] == "no_official_text"


def test_a_prior_column_is_not_taken_for_the_current_quarter():
    out = ref.referee(pair(1633.1, 2222.0), [TEXT])     # 1,633.10 is the June quarter, second on its line
    assert out["verdict"] == "neither"


def test_the_printed_unit_is_respected():
    lakh = "Revenue from operations 1,74,850.00 1,63,310.00\n"
    assert ref.referee(pair(1748.5, 2222.0), [lakh])["verdict"] == "ours_matches_official"
    mn = "Revenue from operations 17,485.00 16,331.00\n"
    assert ref.referee(pair(1748.5, 2222.0), [mn])["verdict"] == "ours_matches_official"


def test_referee_eps_at_its_own_scale():
    assert ref.referee(pair(12.34, 12.9, metric="eps"), [TEXT])["verdict"] == "ours_matches_official"


def test_referee_says_which_period_the_value_sits_under():
    wrong = pair(1304.9, 1748.0, cls="wrong_quarter")       # memory's Q2FY26 holds the Sep 2024 figure
    assert ref.referee(wrong, [TEXT])["verdict"] == "official_says_Q2FY25"
    june = pair(1633.1, 1748.0, cls="wrong_quarter")
    assert ref.referee(june, [TEXT])["verdict"] == "official_says_Q1FY26"


def test_the_column_period_reads_the_nearest_header_above():
    lines = TEXT.splitlines()
    assert ref.column_period(lines, 4, 0) == "Q2FY26" and ref.column_period(lines, 4, 2) == "Q2FY25"
    assert ref.column_period(lines, 4, 3) is None


# --- the run and the reports --------------------------------------------------------------------------------------------

class Sink:
    def __init__(self, dossiers, cards=None):
        self.dossiers, self.objects, self.cards = dossiers, {}, cards or {}

    def list_objects(self, prefix):
        return sorted(k for k in self.objects if k.startswith(prefix))

    def get_object(self, key):
        return self.objects.get(key)

    def get_dossier(self, scrip):
        return self.dossiers.get(scrip)

    def query(self, name, params):
        assert name == "results_cards_company"
        return self.cards.get(params[0], [])


def html_for(revenue, profit):
    head = "".join(f"<th>{m} {y}</th>" for m, y in [("Jun", 2024), ("Sep", 2024), ("Dec", 2024), ("Mar", 2025), ("Jun", 2025),
                                                    ("Sep", 2025), ("Dec", 2025), ("Mar", 2026)])
    row = lambda label, vals: f"<tr><td>{label}</td>" + "".join(f"<td>{v}</td>" for v in vals) + "</tr>"  # noqa: E731
    return (f'<section id="quarters"><p>Consolidated Figures in Rs. Crores</p><table><thead><tr><th></th>{head}</tr></thead>'
            f'<tbody>{row("Sales&nbsp;+", revenue)}{row("Net Profit&nbsp;+", profit)}{row("EPS in Rs", [1.5] * 8)}</tbody></table></section>')


def test_a_full_run_stores_nothing_and_reports_each_class_with_the_referee():
    revenue = list(REVENUE)
    revenue[5] = 1500.0                                  # memory's Q2FY26: mismatch
    d = dossier(revenue=revenue)
    sink = Sink({"1": d}, {"1": [{"news_id": "nse-9", "period": "Q2FY26", "basis": "CONSOLIDATED"}]})
    sink.objects["raw/screener/2026-10-27/DEMO_c.html.gz"] = sd.pack(html_for(REVENUE, PROFIT))
    from bse_intel.pipeline import text_key
    import gzip
    # a cached filing text in the pipeline's own format
    cache = {"pages": [{"n": 1, "text": "Quarter ended\n30.09.2025 30.06.2025\nRevenue from operations 1,748.50 1,633.10\n"}]}
    sink.objects[text_key("nse-9")] = gzip.compress(json.dumps(cache).encode())
    original = sc.text_of
    sc.text_of = lambda body: json.loads(gzip.decompress(body))["pages"][0]["text"]
    try:
        out = sc.run(sink, [("1", "DEMO")], workers=1)
    finally:
        sc.text_of = original
    assert out["pages_day"] == "2026-10-27" and out["companies_compared"] == 1
    assert out["by_class"]["mismatch"] == 1 and out["by_class"]["match"] == 15 and out["pairs"] == 16
    assert out["verdicts"] == {"screener_matches_official": 1}
    csv_text = sc.to_csv(out)
    assert csv_text.splitlines()[0].startswith("scrip,symbol,sector,basis,period,metric,class,memory_value,screener_value")
    assert "DEMO" in csv_text and "1500" in csv_text
    assert "screener_matches_official" in sc.to_referee_csv(out)
    md = sc.to_markdown(out, "2026-10-27")
    assert md.index("What is wrong with us") < md.index("Screener errors") < md.index("Naming")
    assert "wrong_quarter" in md and "memory_period_suspect" in md
    assert json.loads(sc.to_json(out))["verdicts"] == {"screener_matches_official": 1}


def test_without_the_query_or_the_text_every_refereed_pair_is_no_official_text():
    revenue = list(REVENUE)
    revenue[5] = 1500.0
    sink = Sink({"1": dossier(revenue=revenue)})
    sink.objects["raw/screener/2026-10-27/DEMO_c.html.gz"] = sd.pack(html_for(REVENUE, PROFIT))
    out = sc.run(sink, [("1", "DEMO")], workers=1)
    assert out["verdicts"] == {"no_official_text": 1}


def test_the_newest_stored_page_is_used_and_a_day_can_be_chosen():
    sink = Sink({})
    for day in ("2026-10-27", "2026-10-29"):
        sink.objects[f"raw/screener/{day}/DEMO_c.html.gz"] = b""
    assert sc.stored_pages(sink)[0]["DEMO"]["CONSOLIDATED"].endswith("2026-10-29/DEMO_c.html.gz")
    assert sc.stored_pages(sink, "2026-10-28")[0]["DEMO"]["CONSOLIDATED"].endswith("2026-10-27/DEMO_c.html.gz")


def test_parse_full_reads_eps_and_the_annual_section():
    body = (FIXTURES / "screener_abb_standalone.html").read_text(encoding="utf-8")
    page_ = parse_full(body)
    assert page_["quarters"]["Q1FY27"]["eps"] is not None and page_["annual"] == {}
    annual = ('<section id="profit-loss"><p>Standalone Figures in Rs. Crores</p><table><thead><tr><th></th><th>Mar 2024</th>'
              '<th>Mar 2025</th><th>TTM</th></tr></thead><tbody><tr><td>Sales&nbsp;+</td><td>100</td><td>120</td><td>130</td></tr>'
              '<tr><td>Net Profit&nbsp;+</td><td>10</td><td>12</td><td>13</td></tr><tr><td>EPS in Rs</td><td>1.0</td><td>1.2</td>'
              '<td>1.3</td></tr></tbody></table></section>')
    full = parse_full(body.replace("</body>", annual + "</body>") if "</body>" in body else body + annual)
    assert full["annual"] == {"FY24": {"revenue": 100.0, "pat": 10.0, "eps": 1.0}, "FY25": {"revenue": 120.0, "pat": 12.0, "eps": 1.2}}


def test_a_lenders_revenue_is_its_revenue_from_operations_not_its_interest_income():
    # Aadhar Housing Q2FY25: memory holds interest income 672.56 and revenue from operations 764.27; screener shows 764
    rows = [entry("interest_earned", q, r * 0.88) for q, r in zip(QUARTERS, REVENUE)] + \
           [entry("revenue", q, r) for q, r in zip(QUARTERS, REVENUE)] + [entry("pat", q, p) for q, p in zip(QUARTERS, PROFIT)]
    d = {"financial_metrics": rows, "balance_sheet": [], "sector": "Demo", "industry": "Financial Services > Finance > Housing Finance Company"}
    assert set(classes(run(d, page()), "revenue").values()) == {"match"}
