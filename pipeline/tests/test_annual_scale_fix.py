"""ANNUAL_SCALE_FIX: an annual report whose money facts are a power of ten off (TD Power, MSP Steel: lakh with no scale, 1e5 small)
is read at the factor its year's four stored quarters prove, on Sales AND Net Profit alike; nothing else changes."""
from bse_intel import screener_view as sv
from bse_intel import xbrl_facts

CR = xbrl_facts.CRORE
ENDS = {1: "2023-06-30", 2: "2023-09-30", 3: "2023-12-31", 4: "2024-03-31"}
SALES, PROFIT = (300.0, 310.0, 320.0, 330.0), (20.0, 22.0, 24.0, 26.0)     # crore a quarter: a year of 1,260 and 92


def _doc(rows: dict[str, float], months_ends: list[tuple[int, str]], kind="results") -> dict:
    contexts, facts = {}, []
    for i, (m, end) in enumerate(months_ends):
        contexts[f"c{i}"] = {"e": end, "m": m}
        for name, value in rows.items():
            facts.append([name, f"c{i}", "INR", value, 2])
    return {"v": 1, "kind": kind, "contexts": contexts, "units": {"INR": "MONEY"}, "facts": facts, "template": "INDAS"}


def _company(year_sales: float, year_profit: float, monkeypatch, on=True):
    monkeypatch.setenv("ANNUAL_SCALE_FIX", "1" if on else "0")
    store, keys = {}, []
    for q, end in ENDS.items():
        key = f"raw/xbrl-facts/533553/Q{q}FY24-consolidated.json.gz"
        store[key] = xbrl_facts.dumps(_doc({"RevenueFromOperations": SALES[q - 1] * CR, "ProfitLossForPeriod": PROFIT[q - 1] * CR},
                                           [(3, end)]))
        keys.append(key)
    akey = "raw/xbrl-facts/533553/annual-FY24-consolidated.json.gz"
    store[akey] = xbrl_facts.dumps(_doc({"RevenueFromOperations": year_sales, "ProfitLossForPeriod": year_profit},
                                        [(12, "2024-03-31")], kind="annual"))
    return sv.CompanyFacts(keys + [akey], store.get), akey


def _year(cf):
    f, label, _ = cf.year("FY24", "CONSOLIDATED", sv.CORPORATE)
    end = sv._fy_end("FY24")
    return f.cr("RevenueFromOperations", end=end, months=12), f.cr("ProfitLossForPeriod", end=end, months=12), label


def test_a_report_1e5_small_on_both_rows_is_rescaled(monkeypatch):
    cf, _ = _company(1260.0 * CR / 1e5, 92.0 * CR / 1e5, monkeypatch)
    sales, profit, label = _year(cf)
    assert abs(sales - 1260.0) < 1e-6 and abs(profit - 92.0) < 1e-6
    assert "rescaled x1e5" in label


def test_a_right_report_is_untouched(monkeypatch):
    cf, _ = _company(1260.0 * CR, 92.0 * CR, monkeypatch)
    sales, profit, label = _year(cf)
    assert sales == 1260.0 and profit == 92.0 and "rescaled" not in label


def test_a_report_off_on_one_row_only_is_untouched(monkeypatch):
    cf, _ = _company(1260.0 * CR, 92.0 * CR / 1e5, monkeypatch)
    sales, profit, label = _year(cf)
    assert sales == 1260.0 and abs(profit - 92.0 / 1e5) < 1e-12 and "rescaled" not in label


def test_a_report_off_by_two_factors_is_untouched(monkeypatch):
    cf, _ = _company(1260.0 * CR / 1e5, 92.0 * CR / 1e3, monkeypatch)
    assert "rescaled" not in _year(cf)[2]


def test_a_year_a_few_percent_off_is_not_a_slip(monkeypatch):
    cf, _ = _company(1260.0 * CR / 1e5 * 1.05, 92.0 * CR / 1e5, monkeypatch)
    assert "rescaled" not in _year(cf)[2]


def test_the_switch_off_changes_nothing(monkeypatch):
    cf, _ = _company(1260.0 * CR / 1e5, 92.0 * CR / 1e5, monkeypatch, on=False)
    sales, _, label = _year(cf)
    assert abs(sales - 1260.0 / 1e5) < 1e-9 and "rescaled" not in label
