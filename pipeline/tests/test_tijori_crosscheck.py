"""The Tijori cross-check (F189): row reading on real samples, each class, the tight tolerance, the screener leads, the
reports, the run over a fake sink."""

import json
from pathlib import Path

from bse_intel import tijori
from bse_intel import tijori_crosscheck as tc

FIXTURES = Path(__file__).parent / "fixtures"


def tables(name):
    return json.loads((FIXTURES / f"tijori_{name}.json").read_text(encoding="utf-8"))["fin_tables_data"]


def entry(metric, period, value, source=None, as_of="2026-10-01"):
    return {"metric": metric, "period": period, "value": value, "unit": "INR_CR", "basis": "CONSOLIDATED", "as_of": as_of,
            "source_news_id": source or f"xbrl:res:1:{period}"}


def dossier(entries, **kw):
    return {"financial_metrics": list(entries), "balance_sheet": [], "sector": "Demo", **kw}


def apar_memory(**changes):
    """Apar as memory held it on 26 Oct 2026 (TODO 90): owners' profit and its EPS with the wrong sign for Q1FY27."""
    values = {"revenue": 6591.06, "pat": -138.56, "eps": -116.37, **changes}
    return dossier([entry("revenue", "Q1FY27", values["revenue"]), entry("pat", "Q1FY27", values["pat"]),
                    entry("eps", "Q1FY27", values["eps"]), entry("revenue", "Q4FY26", 6602.81),
                    entry("pat", "Q4FY26", 253.44), entry("eps", "Q4FY26", 63.09)])


def by(result):
    return {(p["period"], p["metric"]): p for p in result["pairs"]}


# --- reading the sections ----------------------------------------------------------------------------------------

def test_quarters_are_read_by_row_name_with_eps_from_the_ratios_sub_row():
    page = tc.parse_tables(tables("apar"), "CONSOLIDATED")
    assert page["quarters"]["Q1FY27"] == {"revenue": 6591.06, "pat": 467.45, "eps": 116.3679}
    assert page["quarters"]["Q2FY25"]["revenue"] == 4644.51
    assert page["lines"] == {"revenue": "Net Sales", "pat": "Net Profit", "eps": "EPS"}


def test_the_standalone_basis_reads_the_standalone_section():
    assert tc.parse_tables(tables("apar"), "STANDALONE")["quarters"]["Q1FY27"]["revenue"] == 6477.35


def test_skipped_dates_are_left_out_and_a_december_quarter_is_the_third_of_the_next_year():
    page = tc.parse_tables(tables("abb"), "CONSOLIDATED")
    assert "Q4FY24" not in page["quarters"] and "Q1FY25" not in page["quarters"]     # ABB's Mar and Jun 2024: zeros, skipped
    assert page["quarters"]["Q3FY26"]["revenue"] == 3557.01


def test_years_are_march_columns_only_and_the_ttm_column_is_not_a_year():
    apar = tc.parse_tables(tables("apar"), "CONSOLIDATED")["annual"]
    assert apar["FY26"]["revenue"] == 22902.12 and apar["FY26"]["eps"] is None and "FY27" not in apar
    assert tc.parse_tables(tables("abb"), "CONSOLIDATED")["annual"] == {}              # ABB's years end in December


# --- the classes -------------------------------------------------------------------------------------------------

def test_abb_dec_2025_net_sales_is_an_exact_match():
    result = tc.compare_company(dossier([entry("revenue", "Q3FY26", 3557.01), entry("pat", "Q3FY26", 362.3)]),
                                tables("abb"), "1", "ABB")
    assert by(result)[("Q3FY26", "revenue")]["class"] == "match"


def test_apars_sign_case_the_eps_is_a_sign_difference_and_the_profit_a_mismatch():
    result = tc.compare_company(apar_memory(), tables("apar"), "1", "APARINDS")
    pairs = by(result)
    assert pairs[("Q1FY27", "eps")]["class"] == "sign" and pairs[("Q1FY27", "eps")]["tijori_value"] == 116.3679
    assert pairs[("Q1FY27", "pat")]["class"] == "mismatch" and pairs[("Q1FY27", "pat")]["tijori_value"] == 467.45
    assert pairs[("Q1FY27", "revenue")]["class"] == "match" and pairs[("Q4FY26", "pat")]["class"] == "match"


def test_the_tolerance_is_tight_a_rupee_is_a_difference_a_paisa_is_not():
    assert tc.close(467.45, 467.46, "pat") and not tc.close(467.45, 468.45, "pat")
    assert tc.close(24389.02, 24389.02 + 12.0, "revenue")            # 0.05% of 24,389 is 12.2
    assert not tc.close(24389.02, 24389.02 + 13.0, "revenue")
    assert tc.close(116.37, 116.3679, "eps") and not tc.close(116.37, 116.39, "eps")


def test_a_year_ago_figure_stored_as_current_is_wrong_quarter_with_both_labels():
    d = dossier([entry("revenue", "Q1FY27", 5715.42), entry("pat", "Q1FY27", 467.45)])    # Q2FY26's figure under Q1FY27
    pair = by(tc.compare_company(d, tables("apar"), "1", "APARINDS"))[("Q1FY27", "revenue")]
    assert pair["class"] == "wrong_quarter" and pair["shifted"] == ["Q2FY26"]
    assert "Q1FY27" in pair["note"]


def test_a_unit_slip_is_scale_and_another_official_line_is_naming():
    d = dossier([entry("revenue", "Q1FY27", 659.106), entry("pat", "Q1FY27", 467.45)])
    assert by(tc.compare_company(d, tables("apar"), "1", "APARINDS"))[("Q1FY27", "revenue")]["class"] == "scale"
    d = dossier([entry("revenue", "Q1FY27", 6000.0), entry("total_income", "Q1FY27", 6591.06), entry("pat", "Q1FY27", 467.45)])
    pair = by(tc.compare_company(d, tables("apar"), "1", "APARINDS"))[("Q1FY27", "revenue")]
    assert pair["class"] == "naming" and pair["note"] == "tijori Net Sales = our total_income"


def test_a_company_without_a_table_on_its_basis_or_a_basis_is_skipped():
    assert tc.compare_company(apar_memory(), {}, "1", "X")["skipped"]
    assert tc.compare_company(dossier([]), tables("apar"), "1", "X")["skipped"] == "no memory basis"


# --- lenders: the unconfirmed row names --------------------------------------------------------------------------

def lender_tables(row):
    return {"qt_c": {"report_dates": ["Jun 2026"], "data": [
        {"name": row, "value": [980.5], "sub_section": []}, {"name": "Net Profit", "value": [200.0], "sub_section": []}]}}


def test_a_lenders_revenue_is_compared_with_the_first_known_top_line_and_the_row_is_recorded():
    d = dossier([entry("interest_earned", "Q1FY27", 980.5), entry("pat", "Q1FY27", 200.0)])
    result = tc.compare_company(d, lender_tables("Total Income"), "1", "BANK")
    assert result["lender"] and by(result)[("Q1FY27", "revenue")]["class"] == "match"
    assert result["lines"]["revenue"] == "Total Income"
    assert tc.summarise([result])["lender_lines_used"] == {"Total Income": 1}


def test_the_lender_lines_are_configurable_and_an_unknown_one_is_listed_not_guessed(monkeypatch):
    d = dossier([entry("interest_earned", "Q1FY27", 980.5), entry("pat", "Q1FY27", 200.0)])
    pairs = by(tc.compare_company(d, lender_tables("Interest Income"), "1", "BANK"))
    assert ("Q1FY27", "revenue") not in pairs and ("Q1FY27", "pat") in pairs
    monkeypatch.setenv("TIJORI_LENDER_REVENUE_LINES", "Interest Income, Other Line")
    result = tc.compare_company(d, lender_tables("Interest Income"), "1", "BANK")
    assert by(result)[("Q1FY27", "revenue")]["class"] == "match" and result["lines"]["revenue"] == "Interest Income"


def test_a_lender_that_has_no_known_line_lists_the_rows_it_does_have():
    d = dossier([entry("interest_earned", "Q1FY27", 980.5), entry("pat", "Q1FY27", 200.0)])
    result = tc.compare_company(d, {"qt_c": {"report_dates": ["Jun 2026"], "data": [
        {"name": "Weird Top Line", "value": [980.5], "sub_section": []}]}}, "1", "BANK")
    assert result["rows_seen"] == ["Weird Top Line"] and ("Q1FY27", "revenue") not in by(result)
    assert tc.summarise([result])["lender_rows_unmatched"] == {"Weird Top Line": 1}


# --- the leads, the reports, the run -----------------------------------------------------------------------------

def screener_page(revenue=6591.0, pat=468.0, eps=116.37):
    return {"CONSOLIDATED": {"basis": "CONSOLIDATED", "annual": {},
                             "quarters": {"Q1FY27": {"revenue": revenue, "pat": pat, "eps": eps}}}}


def test_a_lead_is_a_pair_where_tijori_and_screener_both_differ_from_memory_and_agree():
    result = tc.compare_company(apar_memory(), tables("apar"), "1", "APARINDS", screener_page())
    pairs = by(result)
    assert pairs[("Q1FY27", "pat")]["lead"] and pairs[("Q1FY27", "pat")]["screener_value"] == 468.0
    assert "screener agrees with tijori" in pairs[("Q1FY27", "pat")]["note"]
    assert not pairs[("Q1FY27", "revenue")]["lead"]                    # memory agrees with both
    other = tc.compare_company(apar_memory(), tables("apar"), "1", "APARINDS", screener_page(pat=-139.0))
    assert not by(other)[("Q1FY27", "pat")]["lead"]                    # screener sides with memory: not a lead
    assert not by(tc.compare_company(apar_memory(), tables("apar"), "1", "APARINDS"))[("Q1FY27", "pat")]["lead"]


def test_summary_csv_and_markdown_count_pairs_matches_classes_and_leads():
    result = tc.compare_company(apar_memory(), tables("apar"), "1", "APARINDS", screener_page())
    summary = tc.summarise([result, tc.compare_company(dossier([]), {}, "2", "NONE")], "2026-10-27")
    assert summary["pairs"] == 6 and summary["matches"] == 4 and summary["differences"] == 2
    assert summary["by_class"]["sign"] == 1 and summary["by_class"]["mismatch"] == 1 and summary["leads"] == 2
    assert summary["skipped"] == {"no memory basis": 1}
    rows = list(__import__("csv").DictReader(tc.to_csv(summary).splitlines()))
    assert {(r["period"], r["metric"], r["class"]) for r in rows} == {("Q1FY27", "pat", "mismatch"), ("Q1FY27", "eps", "sign")}
    assert next(r for r in rows if r["metric"] == "eps" and r["period"] == "Q1FY27")["tijori_value"] == "116.368"
    md = tc.to_markdown(summary, "2026-10-27")
    assert md.index("## Leads") < md.index("## Sign differences") < md.index("## Counts by class") and "Net Sales" in md
    assert "leads" in tc.render(summary) and "rows" not in json.loads(tc.to_json(summary))


class RunSink:
    def __init__(self, memory, objects):
        self.memory, self.objects = memory, objects

    def list_objects(self, prefix):
        return sorted(k for k in self.objects if k.startswith(prefix))

    def get_object(self, key):
        return self.objects.get(key)

    def get_dossier(self, scrip):
        return self.memory.get(scrip)


def test_the_run_reads_the_newest_stored_page_of_each_symbol_and_counts_a_company_without_one():
    old = {"qt_c": {"report_dates": ["Jun 2026"], "data": []}}
    objects = {
        "raw/tijori/2026-10-20/APARINDS.json.gz": tijori.pack(json.dumps(old)),
        "raw/tijori/2026-10-27/APARINDS.json.gz": tijori.pack(json.dumps(tables("apar"))),
        "raw/tijori/2026-10-28/ABB.json.gz": tijori.pack(json.dumps(tables("abb")))}
    sink = RunSink({"1": apar_memory(), "2": dossier([entry("revenue", "Q3FY26", 3557.01)]), "3": apar_memory()}, objects)
    out = tc.run(sink, [("1", "APARINDS"), ("2", "ABB"), ("3", "GONE")], day="2026-10-27")
    assert out["pages_day"] == "2026-10-27"             # the 28th is after --day
    assert out["skipped"] == {"no stored page": 2} and out["companies_compared"] == 1 and out["by_class"]["sign"] == 1
    assert tc.stored_tables(sink)[1] == "2026-10-28"


def test_a_trailing_ttm_column_dated_march_is_dropped():
    section = {"report_dates": ["Mar 2025", "Mar 2026", "Mar 2026"], "table_footer": "TTM Values as of Mar 2026",
               "data": [{"name": "Sales", "value": [10.0, 20.0, 99.0]}]}
    out, _ = tc.parse_section(section, "year", False)
    assert out == {"FY25": {"revenue": 10.0, "pat": None, "eps": None}, "FY26": {"revenue": 20.0, "pat": None, "eps": None}}
    section = {"report_dates": ["Mar 2025", "Mar 2026"], "table_footer": "TTM Values as of Mar 2026",
               "data": [{"name": "Sales", "value": [10.0, 99.0]}]}
    assert list(tc.parse_section(section, "year", False)[0]) == ["FY25", "FY26"]   # a real FY26: the footer's date alone is not a TTM
    section = {"report_dates": ["Mar 2025", "Mar 2026", "Jun 2026"], "table_footer": "TTM Values as of Jun 2026",
               "data": [{"name": "Sales", "value": [10.0, 20.0, 99.0]}]}
    assert list(tc.parse_section(section, "year", False)[0]) == ["FY25", "FY26"]    # the TTM is the odd month out
    section = {"report_dates": ["Mar 2025", "Mar 2026", "Jun 2026"], "table_footer": "Values in crore",
               "data": [{"name": "Sales", "value": [10.0, 20.0, 99.0]}]}
    assert list(tc.parse_section(section, "year", False)[0]) == ["FY25", "FY26"]    # Jun is no March column anyway


def test_an_eps_gap_with_one_factor_across_periods_is_eps_adjusted_not_a_mismatch():
    def qt(values):
        return {"report_dates": ["Jun 2026", "Mar 2026", "Dec 2025"],
                "data": [{"name": "Quarterly Ratios", "value": [], "sub_section": [{"name": "EPS", "value": values}]}]}
    entries = [entry("eps", "Q1FY27", 10.0), entry("eps", "Q4FY26", 20.0), entry("eps", "Q3FY26", 30.0),
               entry("revenue", "Q1FY27", 100.0), entry("pat", "Q1FY27", 5.0)]
    result = tc.compare_company(dossier(entries), {"qt_c": qt([5.0, 10.0, 15.0])}, "1", "X")   # tijori = ours / 2
    assert {p["class"] for p in result["pairs"]} == {"eps_adjusted"}
    result = tc.compare_company(dossier(entries), {"qt_c": qt([5.0, 14.0, 30.0])}, "1", "X")   # no common factor
    assert {p["period"]: p["class"] for p in result["pairs"]} == {"Q1FY27": "mismatch", "Q4FY26": "mismatch", "Q3FY26": "match"}


def _eps_result(ours, theirs, screener=None):
    """EPS-only quarters; the revenue and profit entries only give the dossier a basis (no such row on the page)."""
    periods = ["Jun 2026", "Mar 2026", "Dec 2025"][:len(ours)]
    qt = {"report_dates": periods, "data": [{"name": "Quarterly Ratios", "value": [],
                                             "sub_section": [{"name": "EPS", "value": theirs}]}]}
    entries = [entry("eps", p, v) for p, v in zip(["Q1FY27", "Q4FY26", "Q3FY26"], ours)]
    entries += [entry("revenue", "Q1FY27", 100.0), entry("pat", "Q1FY27", 5.0)]
    return tc.compare_company(dossier(entries), {"qt_c": qt}, "1", "X", screener)


def test_an_eps_slip_of_10_100_1000_on_several_periods_is_scale_not_adjusted():
    result = _eps_result([1.0, 2.0, 3.0], [10.0, 20.0, 30.0])
    assert {p["class"] for p in result["pairs"]} == {"scale"}
    result = _eps_result([100.0, 200.0], [1.0, 2.0])
    assert {p["class"] for p in result["pairs"]} == {"scale"}
    s = tc.summarise([result])
    assert s["by_class"]["scale"] == 2 and s["by_class"]["eps_adjusted"] == 0 and s["worst_companies"][0]["wrong_pairs"] == 2


def test_one_eps_gap_near_one_is_a_mismatch_and_two_with_one_factor_are_adjusted():
    assert [p["class"] for p in _eps_result([10.0], [10.1])["pairs"]] == ["mismatch"]
    assert {p["class"] for p in _eps_result([10.0, 20.0], [10.1, 20.2])["pairs"]} == {"eps_adjusted"}


def test_a_lead_is_never_reclassed_to_eps_adjusted_or_scale():
    pairs = [{"metric": "eps", "class": "mismatch", "memory_value": 10.0, "tijori_value": 5.0, "lead": True, "note": ""},
             {"metric": "eps", "class": "mismatch", "memory_value": 20.0, "tijori_value": 10.0, "lead": False, "note": ""},
             {"metric": "eps", "class": "mismatch", "memory_value": 1.0, "tijori_value": 10.0, "lead": True, "note": ""}]
    tc.mark_eps_adjusted(pairs)
    assert [p["class"] for p in pairs] == ["mismatch", "mismatch", "mismatch"]
