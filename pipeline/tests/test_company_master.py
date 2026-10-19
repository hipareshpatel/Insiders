"""The company master from NSE (company_master.py; owner, 2026-10-19: everything on NSE)."""

from __future__ import annotations

from bse_intel.company_master import announcement_industries, parse_index_list, plan
from bse_intel.nse import Equity, parse_equity_list

NOW = "2026-10-19T10:00:00+05:30"


def _sector(industry):
    return "banks" if "bank" in (industry or "").lower() else "default"


STORED = [
    {"scrip_code": "500180", "symbol": "HDFCBANK", "isin": "INE040A01034", "company_name": "HDFC Bank Ltd",
     "industry": "Financial Services > Banks > Private Sector Bank", "sector": "banks"},
    {"scrip_code": "543287", "symbol": "ZOMATO", "isin": "INE758T01015", "company_name": "Zomato Ltd",
     "industry": None, "sector": "default"},
]


def test_a_new_listing_is_added_under_its_nse_symbol_and_a_known_company_keeps_its_key():
    equities = [
        Equity("HDFCBANK", "HDFC Bank Limited", "INE040A01034"),
        Equity("ETERNAL", "Eternal Limited", "INE758T01015"),          # Zomato renamed: matched by ISIN
        Equity("NEWCO", "New Co Limited", "INE000N01011"),             # listed after go-live
    ]
    rows, report = plan(equities, STORED, {"INE000N01011": "Banks", "INE758T01015": "E-Retail/ E-Commerce"}, _sector,
                        NOW)
    by_key = {r["scrip_code"]: r for r in rows}
    assert by_key["NEWCO"] == {"scrip_code": "NEWCO", "symbol": "NEWCO", "isin": "INE000N01011",
                               "company_name": "New Co Limited", "industry": "Banks", "sector": "banks",
                               "updated_at": NOW}
    # the renamed company keeps its key; its new symbol, name and the missing industry are filled
    assert by_key["543287"]["symbol"] == "ETERNAL" and by_key["543287"]["company_name"] == "Eternal Limited"
    assert by_key["543287"]["industry"] == "E-Retail/ E-Commerce"
    # HDFC Bank: only its name differs; its stored industry is never overwritten
    assert by_key["500180"] == {"scrip_code": "500180", "company_name": "HDFC Bank Limited", "updated_at": NOW}
    assert report.added == ["NEWCO"] and report.matched == 2 and report.industry_filled == 2


def test_an_unchanged_company_writes_nothing_and_a_new_one_without_industry_is_default():
    equities = [Equity("HDFCBANK", "HDFC Bank Ltd", "INE040A01034"), Equity("ODDCO", "Odd Co Ltd", "INE111O01011")]
    rows, report = plan(equities, STORED, {}, _sector, NOW)
    assert [r["scrip_code"] for r in rows] == ["ODDCO"] and rows[0]["sector"] == "default"
    assert report.without_industry == 1


def test_a_symbol_change_after_a_split_is_matched_by_symbol_when_the_isin_changed():
    rows, _ = plan([Equity("HDFCBANK", "HDFC Bank Ltd", "INE040A01042")], STORED, {}, _sector, NOW)
    assert rows == [{"scrip_code": "500180", "isin": "INE040A01042", "updated_at": NOW}]


def test_nse_industry_sources_parse():
    index = "Company Name,Industry,Symbol,Series,ISIN Code\n360 ONE WAM Ltd.,Financial Services,360ONE,EQ,INE466L01038\n"
    assert parse_index_list(index) == {"INE466L01038": "Financial Services"}
    rows = [{"sm_isin": "INE466L01038", "smIndustry": "Capital Markets"}, {"sm_isin": "INE1", "smIndustry": None},
            {"sm_isin": "INE2", "smIndustry": "-"}]
    assert announcement_industries(rows) == {"INE466L01038": "Capital Markets"}
    equities = parse_equity_list("SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, ISIN NUMBER\n"
                                 "NEWCO,New Co Limited,EQ,19-OCT-2026,INE000N01011\n")
    assert equities[0].symbol == "NEWCO" and equities[0].listed_on == "2026-10-19"
