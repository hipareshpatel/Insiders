import json
from datetime import timedelta
from pathlib import Path

from bse_intel import xbrl
from bse_intel.bse import XbrlLink, parse_results_archive
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
                                 {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(pass2)]})
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


FIXTURES = Path(__file__).parent / "fixtures"


def test_results_archive_rows_become_quarter_links():
    """BSE's results archive (Result_Arch_ng), as returned for Ahluwalia Contracts: announcement rows
    carry no XBRL link, this does. Yearly rows repeat the quarter's file and are skipped."""
    rows = [
        {"Quarter": "Consolidated-Dec-24;DQ2024-2025;124.00;c", "Fld_QuarterName": "Quarter", "stand_xbrl_link": None,
         "conso_xbrl_link": "/XBRLFILES/FourOneUploadDocument/Main_Ind_As_532811_1222025155245.xml",
         "Filing_Date_Time": "2025-02-12T15:53:53.533", "Revised_Date_Time": None},
        {"Quarter": "Standalone-Dec-24;DQ2024-2025;124.00;D", "Fld_QuarterName": "Quarter",
         "stand_xbrl_link": "/XBRLFILES/FourOneUploadDocument/Main_Ind_As_532811_1222025155130.xml", "conso_xbrl_link": None,
         "Filing_Date_Time": "2025-02-12T15:52:35.207", "Revised_Date_Time": None},
        {"Quarter": "Standalone-Mar-25;MC2024-2025;125.50;D", "Fld_QuarterName": "Year",
         "stand_xbrl_link": "/XBRLFILES/IFIndasUploadDocument/Integrated_Finance_Ind_As_532811_166202510955.xml",
         "conso_xbrl_link": None, "Filing_Date_Time": "2025-06-16T10:10:03.393", "Revised_Date_Time": None},
        {"Quarter": "Standalone-Mar-25;MQ2024-2025;125.00;D", "Fld_QuarterName": "Quarter",
         "stand_xbrl_link": "/XBRLFILES/IFIndasUploadDocument/Integrated_Finance_Ind_As_532811_972026133555.xml",
         "conso_xbrl_link": None, "Filing_Date_Time": None, "Revised_Date_Time": "2026-07-09T13:36:48.993"},
    ]
    links = parse_results_archive(rows)
    assert [(link.period, link.basis) for link in links] == [
        ("Q4FY25", "STANDALONE"), ("Q3FY25", "CONSOLIDATED"), ("Q3FY25", "STANDALONE")]
    assert links[1].url == "https://www.bseindia.com/XBRLFILES/FourOneUploadDocument/Main_Ind_As_532811_1222025155245.xml"


def test_real_bse_results_file_parses_to_the_statement_figures():
    """Ahluwalia Contracts' standalone Q3FY25 XBRL file from BSE (Feb 2025). Its card had read the
    lakh table as crore: EBITDA "₹756 Cr", PAT "₹495 Cr", finance cost "₹145 Cr"."""
    result = xbrl.parse((FIXTURES / "bse_main_ind_as_532811_q3fy25.xml").read_bytes())
    assert (result.kind, result.period, result.basis) == ("RESULTS", "Q3FY25", "STANDALONE")
    now = {m.metric: m.value for m in result.metrics if m.period == "Q3FY25"}
    assert now["revenue"] == 951.96 and now["pat"] == 49.39 and now["finance_cost"] == 14.55
    assert now["ebitda"] == 84.36 and now["eps"] == 7.37


def test_results_filing_finds_its_xbrl_in_the_archive(settings):
    """No link on the announcement: the archive's file for the statement's quarter is used,
    consolidated over standalone, the timely revision over a later one."""
    now = now_ist() - timedelta(minutes=30)
    filing = _filing("n-arc", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    text = ("Statement of unaudited consolidated financial results for the quarter ended 30.09.2026 (Rs. in lakhs). "
            "Revenue from operations 12,000.00 9,091.00. Net profit 1,500.00.")
    day = now.date()
    archive = [XbrlLink("Q2FY27", "STANDALONE", "https://bse.invalid/sa.xml", f"{day}T18:00:00"),
               XbrlLink("Q2FY27", "CONSOLIDATED", "https://bse.invalid/co.xml", f"{day}T18:05:00"),
               XbrlLink("Q2FY27", "CONSOLIDATED", "https://bse.invalid/co-late.xml", f"{day + timedelta(days=200)}T10:00:00"),
               XbrlLink("Q1FY27", "CONSOLIDATED", "https://bse.invalid/q1.xml", f"{day - timedelta(days=90)}T10:00:00")]
    pipeline, sink, fake = build(settings, [filing], {filing.pdf_url: _pdf(text), "https://bse.invalid/co.xml": results_xml()},
                                 {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(PASS2)]})
    pipeline.bse.archive = {"999001": archive}
    stats = pipeline.run("live", time_budget_s=60)
    assert stats.analyzed == 1 and stats.xbrl == 1
    assert "Machine-tagged results (XBRL, CONSOLIDATED" in fake.calls[0]["messages"][-1]["content"]


def test_results_card_key_numbers_come_from_xbrl_and_yoy_qoq_mixups_are_flagged():
    """SML's results cards called the fall from the previous quarter a YoY fall and showed PBT as
    EBITDA. With the XBRL file, key numbers take its exact values and YoY; a "% YoY" that is a QoQ
    change is flagged."""
    from bse_intel.models import Pass2Output
    from bse_intel.pipeline import period_mixups, xbrl_key_numbers

    tagged = xbrl.parse((FIXTURES / "bse_main_ind_as_532811_q3fy25.xml").read_bytes())
    assert xbrl.add_comparatives(tagged, *(xbrl.parse((FIXTURES / f"bse_main_ind_as_532811_{q}.xml").read_bytes())
                                           for q in ("q3fy24", "q2fy25")))
    now = {m.metric: m for m in tagged.metrics if m.period == "Q3FY25"}
    rev, pbt = now["revenue"], now["pbt"]
    assert (rev.yoy_pct, rev.qoq_pct, now["pat"].yoy_pct) == (-7.3, -5.9, -30.1)  # BSE's files carry no comparatives
    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "Q3FY25 results",
        "card": {"impact_level": "MODERATE", "headline": "Ahluwalia Q3FY25 results", "basis": "STANDALONE",
                 "what_happened": [f"Revenue fell {abs(rev.qoq_pct):.1f}% YoY to ₹952 Cr"],
                 "key_numbers": [{"label": "Revenue", "value": "₹952 Cr", "change": f"{rev.qoq_pct:+.1f}% YoY"},
                                 {"label": "EBITDA", "value": f"₹{pbt.value} Cr", "change": "-20% YoY"},
                                 {"label": "EBITDA margin", "value": "7.0%", "change": None}]}})
    changed = xbrl_key_numbers(out, tagged)
    keys = {k.label: (k.value, k.change) for k in out.card.key_numbers}
    assert keys["Revenue"] == ("₹951.96 Cr", f"{rev.yoy_pct:+.1f}% YoY")
    assert keys["EBITDA"][0] == "₹84.36 Cr" and keys["EBITDA margin"] == ("7.0%", None) and len(changed) == 2
    assert period_mixups(out, tagged) == [f"\"{abs(rev.qoq_pct):.1f}% YoY\" is a quarter-on-quarter change, not year-on-year"]


def test_promoter_locked_in_shares_are_not_the_promoter_holding():
    """CSB Bank's shareholding XBRL (from NSE): the promoter group's locked-in shares are 80.45% of its own
    holding, while the promoter held 49.72% of the company. The old rule took the larger of every promoter
    percentage; the seed's cross-check against NSE's own list caught it on six quarters."""
    result = xbrl.parse((FIXTURES / "nse_shp_csbbank_q1fy24.xml").read_bytes())
    assert result.kind == "SHAREHOLDING"
    own = result.ownership
    assert own.promoter_pct == 49.72 and own.pledge_pct == 0.0
    assert own.fii_pct == 5.9 and own.dii_pct == 12.25 and own.retail_holders == 54796


def test_an_xbrl_yoy_is_only_trusted_when_its_comparative_is_in_the_filing():
    """Audit round 1: the XBRL period match put Kanoria's Q1FY27 year-ago revenue at about ₹454 Cr against a
    real ₹201 Cr, and the card's correct "+129% YoY" was rewritten to "+1.5% YoY". The value is one tagged
    fact and is still trusted; the YoY needs a second one, so it is taken only when the year-ago figure it
    implies also appears in the filing."""
    from bse_intel.models import Pass2Output
    from bse_intel.pipeline import xbrl_key_numbers

    tagged = xbrl.parse((FIXTURES / "bse_main_ind_as_532811_q3fy25.xml").read_bytes())
    assert xbrl.add_comparatives(tagged, *(xbrl.parse((FIXTURES / f"bse_main_ind_as_532811_{q}.xml").read_bytes())
                                           for q in ("q3fy24", "q2fy25")))
    rev = next(m for m in tagged.metrics if m.period == "Q3FY25" and m.metric == "revenue")
    prior = rev.value / (1 + rev.yoy_pct / 100)

    def card():
        return Pass2Output.model_validate({
            "is_material": True, "event_type": "RESULTS", "timeline_entry": "Q3FY25 results",
            "card": {"impact_level": "MODERATE", "headline": "Ahluwalia Q3FY25 results", "basis": "STANDALONE",
                     "what_happened": ["Revenue fell to ₹952 Cr"],
                     "key_numbers": [{"label": "Revenue", "value": "₹952 Cr", "change": "-3.0% YoY"}]}})

    # the comparative is nowhere in the filing: the model's own change stands and the value is still corrected
    out = card()
    xbrl_key_numbers(out, tagged, sources=("Revenue for the quarter was 951.96",))
    assert [(k.value, k.change) for k in out.card.key_numbers] == [("₹951.96 Cr", "-3.0% YoY")]

    # the same filing stating the year-ago figure: the XBRL YoY is taken
    out = card()
    xbrl_key_numbers(out, tagged, sources=(f"Revenue 951.96 against {prior:,.2f} in the corresponding quarter",))
    assert [(k.value, k.change) for k in out.card.key_numbers] == [("₹951.96 Cr", f"{rev.yoy_pct:+.1f}% YoY")]


def test_the_xbrl_table_cannot_verify_its_own_comparative():
    """The table is prepended to the filing text the model reads, so it also arrives in the sources the
    guard checks against. Were it left there, the year-ago figure would be found in the table it came from,
    every YoY would verify and the guard would be a no-op - which is what shipped first."""
    from bse_intel.models import Pass2Output
    from bse_intel.pipeline import xbrl_key_numbers

    tagged = xbrl.parse((FIXTURES / "bse_main_ind_as_532811_q3fy25.xml").read_bytes())
    assert xbrl.add_comparatives(tagged, *(xbrl.parse((FIXTURES / f"bse_main_ind_as_532811_{q}.xml").read_bytes())
                                           for q in ("q3fy24", "q2fy25")))
    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "Q3FY25 results",
        "card": {"impact_level": "MODERATE", "headline": "Ahluwalia Q3FY25 results", "basis": "STANDALONE",
                 "what_happened": ["Revenue fell to ₹952 Cr"],
                 "key_numbers": [{"label": "Revenue", "value": "₹952 Cr", "change": "-3.0% YoY"}]}})
    # the table alone as the source, exactly as the pipeline passes it: it must not prove itself
    xbrl_key_numbers(out, tagged, sources=(tagged.table(),))
    assert [(k.value, k.change) for k in out.card.key_numbers] == [("₹951.96 Cr", "-3.0% YoY")]
