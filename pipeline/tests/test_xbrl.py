import json
from datetime import timedelta

from bse_intel import xbrl
from bse_intel.timeutil import now_ist

from test_pipeline import PASS2, _filing, _pdf, build, rows


def _ctx(cid, start=None, end=None, instant=None, member=None):
    period = f"<xbrli:instant>{instant}</xbrli:instant>" if instant else \
        f"<xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate>"
    seg = (f'<xbrli:segment><xbrldi:explicitMember dimension="in-bse-shp:CategoryAxis">in-bse-shp:{member}'
           "</xbrldi:explicitMember></xbrli:segment>") if member else ""
    return (f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com">500001'
            f"</xbrli:identifier>{seg}</xbrli:entity><xbrli:period>{period}</xbrli:period></xbrli:context>")


HEAD = ('<?xml version="1.0"?><xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" '
        'xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" '
        'xmlns:in-bse-fin="http://www.bseindia.com/xbrl/fin" xmlns:in-bse-shp="http://www.bseindia.com/xbrl/shp">'
        '<xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>'
        '<xbrli:unit id="INRPerShare"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:INR</xbrli:measure>'
        "</xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator>"
        '</xbrli:divide></xbrli:unit><xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>')


def _fact(name, ctx, value, unit="INR"):
    return f'<in-bse-fin:{name} contextRef="{ctx}" unitRef="{unit}" decimals="-5">{value}</in-bse-fin:{name}>'


def results_xml(nature="Consolidated"):
    body = HEAD + _ctx("OneD", "2026-07-01", "2026-09-30") + _ctx("TwoD", "2026-04-01", "2026-06-30") \
        + _ctx("ThreeD", "2025-07-01", "2025-09-30") + _ctx("FourD", "2026-04-01", "2026-09-30") \
        + _ctx("OneI", instant="2026-09-30") + _ctx("Seg", "2026-07-01", "2026-09-30", member="CementMember")
    body += f'<in-bse-fin:NatureOfReportStandaloneConsolidated contextRef="OneD">{nature}</in-bse-fin:NatureOfReportStandaloneConsolidated>'
    for ctx, rev, pat in (("OneD", 1_200_000_000, 150_000_000), ("TwoD", 1_000_000_000, 100_000_000),
                          ("ThreeD", 909_100_000, 90_000_000), ("FourD", 2_200_000_000, 250_000_000)):
        body += _fact("RevenueFromOperations", ctx, rev) + _fact("ProfitLossForPeriod", ctx, pat)
        body += _fact("OtherIncome", ctx, 20_000_000) + _fact("FinanceCosts", ctx, 30_000_000)
        body += _fact("DepreciationDepletionAndAmortisationExpense", ctx, 50_000_000)
        body += _fact("ProfitBeforeTax", ctx, pat * 4 // 3)
    body += _fact("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations", "OneD", "4.25", "INRPerShare")
    body += _fact("RevenueFromOperations", "Seg", 800_000_000)  # a segment: not the total
    body += _fact("Equity", "OneI", 5_000_000_000) + _fact("BorrowingsNoncurrent", "OneI", 700_000_000)
    body += _fact("BorrowingsCurrent", "OneI", 300_000_000) + _fact("CashAndCashEquivalents", "OneI", 400_000_000)
    return (body + "</xbrli:xbrl>").encode()


def shp_xml():
    body = HEAD + "".join(_ctx(m, instant="2026-09-30", member=m) for m in (
        "PromoterAndPromoterGroupMember", "IndianPromotersMember", "InstitutionsForeignMember",
        "ForeignPortfolioInvestorsCategoryOneMember", "InstitutionsDomesticMember", "MutualFundsMember",
        "ResidentIndividualShareholdersHoldingNominalShareCapitalUpToRsTwoLakhsMember"))
    for member, pct in (("PromoterAndPromoterGroupMember", "0.5523"), ("IndianPromotersMember", "0.5"),
                        ("InstitutionsForeignMember", "0.081"), ("ForeignPortfolioInvestorsCategoryOneMember", "0.07"),
                        ("InstitutionsDomesticMember", "0.1204"), ("MutualFundsMember", "0.1")):
        body += (f'<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="{member}" unitRef="pure">{pct}'
                 "</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>")
    body += ('<in-bse-shp:NumberOfShareholders contextRef="ResidentIndividualShareholdersHoldingNominalShareCapitalUpToRsTwoLakhsMember" '
             'unitRef="pure">48211</in-bse-shp:NumberOfShareholders>')
    return (body + "</xbrli:xbrl>").encode()


def test_results_xbrl_gives_exact_crore_figures_with_changes():
    r = xbrl.parse(results_xml())
    assert r.kind == "RESULTS" and r.basis == "CONSOLIDATED" and r.period == "Q2FY27"
    by = {(m.metric, m.period): m for m in r.metrics}
    rev = by[("revenue", "Q2FY27")]
    assert rev.value == 120.0 and rev.yoy_pct == 32.0 and rev.qoq_pct == 20.0 and rev.unit == "INR_CR"
    assert by[("revenue", "H1FY27")].value == 220.0 and by[("pat", "Q2FY26")].value == 9.0
    assert by[("eps", "Q2FY27")].value == 4.25 and by[("eps", "Q2FY27")].unit == "INR"
    # EBITDA = PBT 20 + finance 3 + depreciation 5 - other income 2 = 26; margin 21.67%
    assert by[("ebitda", "Q2FY27")].value == 26.0 and by[("ebitda_margin", "Q2FY27")].value == 21.67
    assert r.balance_sheet.net_worth_cr == 500.0 and r.balance_sheet.gross_debt_cr == 100.0
    assert r.balance_sheet.net_debt_cr == 60.0 and r.balance_sheet.period == "Q2FY27"
    assert "revenue Q2FY27: 120 Cr, YoY +32.0%" in r.table()


def test_results_xbrl_is_confirmed_against_the_pdf_scale():
    r = xbrl.parse(results_xml())
    assert xbrl.confirm(r, "Revenue from operations 12,000.00 (Rs. in lakhs)")
    assert xbrl.confirm(r, "Revenue 120.00 crore")
    assert not xbrl.confirm(r, "Revenue from operations 1,234.56 and profit 78.9")


def test_shareholding_xbrl_takes_category_totals():
    r = xbrl.parse(shp_xml())
    assert r.kind == "SHAREHOLDING" and r.period == "Q2FY27"
    o = r.ownership
    assert (o.promoter_pct, o.fii_pct, o.dii_pct, o.retail_holders) == (55.23, 8.1, 12.04, 48211)


def test_not_xbrl_is_ignored():
    assert xbrl.parse(b"<html>blocked</html>") is None
    assert xbrl.parse(b"not xml") is None


def test_results_card_uses_xbrl_figures_in_memory(settings):
    now = now_ist() - timedelta(minutes=30)
    filing = _filing("n-res", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    filing.xbrl_url = "https://bse.invalid/n-res.xml"
    text = ("Statement of unaudited consolidated financial results for the quarter ended 30.09.2026 (Rs. in lakhs). "
            "Revenue from operations 12,000.00 9,091.00. Net profit 1,500.00.")
    pass2 = json.loads(json.dumps(PASS2))
    pass2["card"]["basis"] = "CONSOLIDATED"
    pass2["dossier_delta"]["financial_metrics"][0]["value"] = 119  # the model misread the PDF
    pipeline, sink, fake = build(settings, [filing], {filing.pdf_url: _pdf(text), filing.xbrl_url: results_xml()},
                                 {"deepseek-ai/deepseek-r1": [json.dumps(pass2)]})
    stats = pipeline.run("live", time_budget_s=60)
    assert stats.analyzed == 1 and stats.xbrl == 1
    assert "Machine-tagged results (XBRL" in fake.calls[0]["messages"][-1]["content"]
    metrics = {(m["metric"], m["period"]): m["value"] for m in sink.get_dossier("999001")["financial_metrics"]}
    assert metrics[("revenue", "Q2FY27")] == 120.0 and metrics[("ebitda", "Q2FY27")] == 26.0
    assert sink.get_dossier("999001")["balance_sheet"][-1]["net_worth_cr"] == 500.0
    body = json.loads(rows(sink, "select card_json from cards")[0]["card_json"])
    assert body["xbrl"] == {"basis": "CONSOLIDATED", "period": "Q2FY27", "figures": len(xbrl.parse(results_xml()).metrics)}


def test_shareholding_pattern_goes_to_memory_without_ai(settings):
    now = now_ist() - timedelta(minutes=30)
    with_file = _filing("n-shp", "Shareholding Pattern for the quarter ended September 2026", now, "Company Update",
                        "Shareholding Pattern")
    with_file.xbrl_url = "https://bse.invalid/n-shp.xml"
    without = _filing("n-shp2", "Shareholding Pattern", now, "Company Update", "Shareholding Pattern", scrip="999002")
    pipeline, sink, fake = build(settings, [with_file, without], {with_file.xbrl_url: shp_xml()}, {})
    stats = pipeline.run("live", time_budget_s=60)
    assert fake.calls == [] and stats.analyzed == 0 and stats.dropped_rule == 1
    (row,) = rows(sink, "select status, event_type, reason, route from filings")
    assert row["status"] == "NOT_MATERIAL" and row["event_type"] == "SHAREHOLDING" and row["route"] == "XBRL"
    (own,) = sink.get_dossier("999001")["ownership"]
    assert own["period"] == "Q2FY27" and own["promoter_pct"] == 55.23 and own["source_news_id"] == "n-shp"
