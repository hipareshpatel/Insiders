"""The row-name map (line_map.py, TODO 93, F209): it matches the code's own tables, the sample files carry the names it says
they do, the refactored readers kept their old names, and the coverage script runs on stored files with no network."""
import gzip
import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from bse_intel import line_map as lm
from bse_intel import screener_crosscheck as sc
from bse_intel import tijori_crosscheck as tc
from bse_intel import xbrl
from bse_intel.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures"
SCRIPT = Path(__file__).parents[1] / "scripts" / "line_map_coverage.py"


def _script():
    spec = importlib.util.spec_from_file_location("line_map_coverage", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- the map equals what xbrl.py reads ---------------------------------------------------------------------------------

def test_result_elements_match_the_code_on_every_template():
    for template in lm.TEMPLATES:
        actual = {**xbrl.RESULT_TAGS, **xbrl.OVERLAYS.get(template, {})}
        for element, metric in actual.items():
            if metric in ("eps",) or element in xbrl.EPS_VARIANTS:
                assert lm.element_metric(template, element) in ("eps", None) or metric is None, (template, element)
                continue
            assert lm.element_metric(template, element) == metric, (template, element, metric)
        # and nothing the map says is read is missing from the code
        for ln in lm.LINES:
            if ln.group in ("ratio", "balance") or ln.key in ("eps_total", "eps_continuing"):
                continue
            for element in lm.elements(ln.key, template):
                assert actual.get(element) == ln.key, (template, ln.key, element)


def test_ratio_balance_and_eps_variant_elements_match_the_code():
    for element, metric in xbrl.RATIO_TAGS.items():
        assert element in lm.elements(metric, "BANKING") and element in lm.elements(metric, "GI"), element
    for element, metric in xbrl.BALANCE_TAGS.items():
        assert element in lm.elements(metric, "NBFC"), (element, metric)
    for element, metric in xbrl.EPS_VARIANTS.items():
        assert lm.elements(metric, "INDAS") == (element,)
    ratio_and_balance = {ln.key for ln in lm.LINES if ln.group in ("ratio", "balance")}
    for key in ratio_and_balance - {"paid_up_capital"}:
        for element in lm.elements(key, "INDAS"):
            assert xbrl.RATIO_TAGS.get(element) == key or xbrl.BALANCE_TAGS.get(element) == key, (key, element)


def test_overlays_and_suppression_follow_the_insurers_tables():
    assert lm.elements("revenue", "GI")[0] == "PremiumEarned" and lm.elements("revenue", "LI")[0] == "NetPremiumIncome"
    assert lm.elements("revenue", "NBFC") == ("RevenueFromOperations",)
    assert lm.element_metric("LI", "ProvisionForTax") is None and lm.element_metric("LI", "CurrentTax") is None
    assert lm.element_metric("GI", "ProvisionForTax") == "tax_expense"
    assert lm.element_metric("LI", "ProvisionsForTaxes") == "tax_expense"


def test_every_key_is_unique_and_derived_lines_have_no_element():
    assert len(lm.BY_KEY) == len(lm.LINES)
    for key in ("ebitda", "ebitda_margin", "nii"):
        assert not any(lm.elements(key, t) for t in lm.TEMPLATES)
    assert "xbrl" in lm.unverified("fees_commission_income") or lm.elements("fees_commission_income", "NBFC") == ()


# --- the sample files carry the names claimed for them -----------------------------------------------------------------

def _names(fixture: str) -> set[str]:
    root = ET.parse(FIXTURES / f"{fixture}.xml").getroot()
    return {el.tag.rsplit("}", 1)[-1] for el in root.iter() if el.get("contextRef") and el.get("unitRef")}


def test_seen_not_read_names_are_in_a_sample_of_that_template_and_not_read_by_the_code():
    for ln in lm.LINES:
        for template, names in ln.xbrl_seen.items():
            present = set().union(*(_names(f) for f in lm.FIXTURES[template]))
            for name in names:
                assert name in present, (ln.key, template, name)
                assert name not in {**xbrl.RESULT_TAGS, **xbrl.OVERLAYS.get(template, {})} or name == "NetPremium", name


def test_fixture_templates_are_what_the_files_declare():
    for template, files in lm.FIXTURES.items():
        for f in files:
            declared = xbrl.taxonomy((FIXTURES / f"{f}.xml").read_bytes())
            assert declared in (template, ""), (f, declared)


def test_screener_and_tijori_names_are_the_ones_the_sample_pages_print():
    from bse_intel.screener_fill import _section_table
    pages = {"abb": "screener_abb_standalone", "hdfc": "screener_hdfcbank_consolidated"}
    seen = set()
    for name in pages.values():
        seen |= set(_section_table((FIXTURES / f"{name}.html").read_text(encoding="utf-8", errors="ignore"), "quarters")[1])
    for key in ("revenue", "pat", "eps", "other_income", "depreciation", "pbt", "total_expenses", "ebitda", "gnpa_pct",
                "nnpa_pct", "pre_provision_operating_profit", "ebitda_margin"):
        assert set(lm.screener_rows(key)) & seen, key
    assert "Revenue" in seen and "Sales" in seen          # a bank's page names its top line Revenue
    assert set(lm.known_screener_rows()) >= seen          # every row of the four sample pages is accounted for
    names = set()
    for f in ("tijori_abb", "tijori_apar"):
        names |= set(_tijori_names(json.loads((FIXTURES / f"{f}.json").read_text())))
    assert names == {"Net Sales", "Net Profit", "Quarterly Ratios", "EPS", "Sales"}
    assert names <= lm.known_tijori_rows()


def _tijori_names(data):
    return _script().tijori_rows(data)["qt_c"] + _script().tijori_rows(data)["pl_c_s"]


# --- the readers that moved to the map kept their names ----------------------------------------------------------------

def test_tijori_crosscheck_names_are_what_they_were():
    assert tc.REVENUE_LINES == ("Net Sales", "Sales")
    assert tc.LENDER_REVENUE_LINES == ("Net Sales", "Sales", "Revenue", "Total Income", "Interest Earned", "Income from Operations")
    assert tc.PROFIT_LINES == ("Net Profit",) and tc.EPS_LINES == ("EPS",)


def test_screener_crosscheck_names_are_what_they_were():
    assert sc._OURS == {"revenue": ("revenue",), "pat": ("pat",), "eps": ("eps", "basic_eps")}
    assert sc._LENDER_OURS == {"revenue": ("revenue", "interest_earned"), "pat": ("pat",), "eps": ("eps", "basic_eps")}


def test_screener_row_pick_is_the_old_or_chain():
    from bse_intel.screener_fill import _row_of
    assert _row_of({"Sales": [1.0], "Revenue": [2.0]}, "revenue") == [1.0]
    assert _row_of({"Sales": [], "Revenue": [2.0]}, "revenue") == [2.0]
    assert _row_of({"Revenue": [2.0]}, "revenue") == [2.0]
    assert _row_of({}, "revenue") == [] and _row_of({"Net Profit": [3.0]}, "pat") == [3.0]
    assert _row_of({"EPS in Rs": [4.0]}, "eps") == [4.0]


def test_the_switch_is_off_by_default(monkeypatch):
    monkeypatch.delenv("LINE_MAP", raising=False)
    assert Settings().line_map is False
    monkeypatch.setenv("LINE_MAP", "1")
    assert Settings().line_map is True


# --- the coverage script -----------------------------------------------------------------------------------------------

def test_coverage_script_reads_stored_files_offline(tmp_path):
    mod = _script()
    xdir, sdir, tdir = tmp_path / "x", tmp_path / "s", tmp_path / "t"
    for d in (xdir, sdir, tdir):
        d.mkdir()
    for name in ("nse_irfc_q4fy26_nbfc", "nse_hdfcbank_q2fy27_cons", "nse_hdfclife_q2fy27_cons"):
        (xdir / f"{name}.xml.gz").write_bytes(gzip.compress((FIXTURES / f"{name}.xml").read_bytes()))
    (sdir / "HDFCBANK_c.html.gz").write_bytes(gzip.compress((FIXTURES / "screener_hdfcbank_consolidated.html").read_bytes()))
    (tdir / "ABB.json").write_bytes((FIXTURES / "tijori_abb.json").read_bytes())
    report = mod.build(str(xdir), str(sdir), str(tdir), top=10)
    assert set(report["xbrl"]) == {"NBFC", "BANKING", "LI"}
    nbfc = report["xbrl"]["NBFC"]
    assert nbfc["files"] == 1 and nbfc["covered"]["revenue"] == 1 and nbfc["covered"]["interest_earned"] == 1
    assert "fees_commission_income" in nbfc["seen_not_read"] and "pat_owners" in nbfc["read_but_in_no_file"]
    assert report["xbrl"]["BANKING"]["covered"]["gnpa_pct"] == 1 and "pat_minority" in report["xbrl"]["BANKING"]["seen_not_read"]
    assert report["xbrl"]["LI"]["covered"]["revenue"] == 1
    assert report["screener"]["pages"] == 1 and report["screener"]["unmapped_rows"] == []
    assert report["tijori"]["pages"] == 1 and report["tijori"]["lender_revenue_rows_present"] == ["Net Sales", "Sales"]
    text = mod.render(report)
    assert "NBFC" in text and "Screener pages" in text
    out, js = tmp_path / "r.md", tmp_path / "r.json"
    assert mod.main(["--xbrl", str(xdir), "--out", str(out), "--json", str(js)]) == 0
    assert out.read_text().startswith("# Line map coverage") and "xbrl" in json.loads(js.read_text())


def test_coverage_script_needs_a_directory():
    with pytest.raises(SystemExit):
        _script().main([])
