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
    # a quarter with nothing in it - no revenue, nil profit - cannot be looked for at any unit: not refused
    for m in r.metrics:
        m.value = 0.0
    assert xbrl.confirm(r, "Revenue from operations Nil")


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
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(pass2)]})
    stats = pipeline.run("live", time_budget_s=60)
    assert stats.analyzed == 1 and stats.xbrl == 1
    assert "Machine-tagged results (XBRL" in fake.calls[0]["messages"][-1]["content"]
    metrics = {(m["metric"], m["period"]): m["value"] for m in sink.get_dossier("999001")["financial_metrics"]}
    assert metrics[("revenue", "Q2FY27")] == 120.0 and metrics[("ebitda", "Q2FY27")] == 26.0
    assert sink.get_dossier("999001")["balance_sheet"][-1]["net_worth_cr"] == 500.0
    body = json.loads(rows(sink, "select card_json from cards")[0]["card_json"])
    assert {k: body["xbrl"][k] for k in ("basis", "period", "figures")} == \
        {"basis": "CONSOLIDATED", "period": "Q2FY27", "figures": len(xbrl.parse(results_xml()).metrics)}
    assert body["xbrl"]["url"].endswith(".xml")   # the file it was made from (event_catchup.results_catch_up)


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
                                 {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(PASS2)]})
    pipeline.bse.archive = {"999001": archive}
    stats = pipeline.run("live", time_budget_s=60)
    assert stats.analyzed == 1 and stats.xbrl == 1
    assert "Machine-tagged results (XBRL, CONSOLIDATED" in fake.calls[0]["messages"][-1]["content"]


def test_results_card_key_numbers_come_from_xbrl_and_yoy_qoq_mixups_are_flagged():
    """SML's results cards called the fall from the previous quarter a YoY fall and showed PBT as
    EBITDA. With the XBRL file, key numbers take its exact values and YoY; a "% YoY" that is a QoQ
    change is flagged."""
    from bse_intel.models import Pass2Output
    from bse_intel.pipeline import xbrl_key_numbers
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
    out.card.key_numbers[0].quote = "Revenue for the quarter was Rs 952 crore"   # a press release's line
    out.card.key_numbers.append(out.card.key_numbers[1].model_copy(update={"label": "Normalised EBITDA",
                                                                           "value": "₹90 Cr", "change": None}))
    changed = xbrl_key_numbers(out, tagged)
    keys = {k.label: (k.value, k.change) for k in out.card.key_numbers}
    assert keys["Revenue"] == ("₹951.96 Cr", f"{rev.yoy_pct:+.1f}% YoY")
    assert keys["EBITDA"][0] == "₹84.36 Cr" and keys["EBITDA margin"] == ("7.0%", None) and len(changed) == 2
    # the file's figure is quoted from the file's line, not from the press release's rounding (eMudhra, 2026-10-18)
    assert out.card.key_numbers[0].quote.startswith("revenue Q3FY25: 951.96 Cr")
    # and a figure the company defines for itself keeps its own value (Jubilant's normalised PAT became reported PAT)
    assert keys["Normalised EBITDA"] == ("₹90 Cr", None)
    assert period_mixups(out, tagged) == [f"\"{abs(rev.qoq_pct):.1f}% YoY\" is a quarter-on-quarter change, not year-on-year"]
    # unless the filing itself calls it that: Bandhan Bank's "representing a growth of 5.9% YoY" (2026-10-20)
    said = f"Revenue for the quarter, representing a growth of {abs(rev.qoq_pct):.1f}% YoY."
    assert period_mixups(out, tagged, said) == []
    assert period_mixups(out, tagged, f"down {abs(rev.qoq_pct):.1f}% QoQ") != []
    # The same percentage as the nine months' YoY is that change, not a mislabelled QoQ (Jubilant's FY25
    # revenue "+7.9% YoY" was held because only the quarter's changes were compared).
    import copy

    from bse_intel.models import FinancialMetric

    year = copy.deepcopy(tagged)
    year.metrics.append(FinancialMetric(metric="revenue", period="9MFY25", value=2_800.0, yoy_pct=rev.qoq_pct))
    assert period_mixups(out, year), "the card is about Q3: the nine months' change does not answer for it"
    nine_months = out.model_copy(deep=True)
    nine_months.card.what_happened[0].text = f"9MFY25 revenue fell {abs(rev.qoq_pct):.1f}% YoY to ₹2,800 Cr"
    nine_months.card.key_numbers = []
    assert period_mixups(nine_months, year) == []
    nine_months.card.what_happened[0].text = f"Nine-month revenue is ₹2,800 Cr, down {abs(rev.qoq_pct):.1f}% YoY"
    assert period_mixups(nine_months, year) == [], "a period in words (Novartis, loop round 2c)"
    # A loss narrowing from 100 to 94.1 has no XBRL YoY, but it is a 5.9% change all the same (Shivam's FY25
    # "+4.3% YoY (less negative)").
    loss = copy.deepcopy(tagged)
    loss.metrics += [FinancialMetric(metric="pat", period="9MFY24", value=-100.0),
                     FinancialMetric(metric="pat", period="9MFY25", value=-94.1)]
    nine_months.card.what_happened[0].text = f"9MFY25 loss narrowed {abs(rev.qoq_pct):.1f}% YoY to ₹94.1 Cr"
    assert period_mixups(nine_months, loss) == []
    # the period may follow the change: "the 12.3% YoY growth in H1FY26" on a Q2 card whose quarter fell
    # 12.3% QoQ (Novartis, loop round 2e)
    nine_months.card.what_happened[0].text = (f"Q3FY25 revenue was ₹952 Cr, while the {abs(rev.qoq_pct):.1f}% YoY "
                                              "fall in 9MFY25 came from exports")
    assert period_mixups(nine_months, year) == []


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

    # the same filing stating the year-ago figure - as the earlier quarter's file has it, ₹1,026.48 Cr - takes the
    # XBRL YoY. Rebuilt from a YoY rounded to a tenth of a point it is ₹1,026.92 Cr; asked at two decimals that
    # refused the right YoY on most results cards (audit of discard paths, 2026-10-18).
    year_ago = next(m for m in tagged.metrics if m.period == "Q3FY24" and m.metric == "revenue").value
    assert round(year_ago, 2) == 1026.48 and abs(prior - year_ago) > 0.3
    out = card()
    xbrl_key_numbers(out, tagged, sources=(f"Revenue 951.96 against {year_ago:,.2f} in the corresponding quarter",))
    assert [(k.value, k.change) for k in out.card.key_numbers] == [("₹951.96 Cr", f"{rev.yoy_pct:+.1f}% YoY")]
    # without the earlier quarter's file the figure rebuilt from the YoY is matched within that rounding
    alone = xbrl.parse((FIXTURES / "bse_main_ind_as_532811_q3fy25.xml").read_bytes())
    for m in alone.metrics:
        if m.period == "Q3FY25" and m.metric == "revenue":
            m.yoy_pct = rev.yoy_pct
    out = card()
    xbrl_key_numbers(out, alone, sources=(f"Revenue 951.96 against {year_ago:,.2f} in the corresponding quarter",))
    assert [(k.value, k.change) for k in out.card.key_numbers] == [("₹951.96 Cr", f"{rev.yoy_pct:+.1f}% YoY")]


def test_the_xbrl_table_cannot_verify_its_own_comparative():
    """The table is prepended to the filing text the model reads, so it also arrives in the sources the
    guard checks against. Were it left there, the year-ago figure would be found in the table it came from,
    every YoY would verify and the guard would be a no-op - which is what shipped first."""
    from bse_intel.models import Pass2Output
    from bse_intel.pipeline import xbrl_key_numbers
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


def test_a_banks_results_are_read_from_the_banking_template():
    """A bank files the banking template, so none of the commercial names appear on its results and its
    memory held almost nothing: no top line, no PBT, no cost of funds (CSB Bank, audit round 1 - 6 of 12
    metrics, and the card's "other income jumped 75%" had no machine-tagged comparative to be checked
    against). Interest earned is a bank's top line, interest expended its cost of funds, and operating
    profit before provisions the figure it is read on rather than EBITDA."""
    result = xbrl.parse((FIXTURES / "bse_bank_542867_q3fy25.xml").read_bytes())
    assert result is not None and result.kind == "RESULTS" and result.period == "Q3FY25"
    now = {m.metric: m.value for m in result.metrics if m.period == "Q3FY25"}
    assert now["interest_earned"] == 919.38
    assert now["interest_expended"] == 543.93
    assert now["pre_provision_operating_profit"] == 220.65
    assert now["provisions"] == 16.53
    assert now["pbt"] == 204.12          # ProfitLossFromOrdinaryActivitiesBeforeTax, not ProfitBeforeTax
    assert now["pat"] == 151.63          # the figure the audited card carried
    assert now["total_income"] == 1138.75
    # EPS comes from the RBI Form B names (before/after extraordinary items), not the commercial tag
    assert now["eps"] == 8.74
    # the identity holds on the bank's own statement: income less expenditure, before provisions
    assert abs(now["pbt"] - (now["pre_provision_operating_profit"] - now["provisions"])) < 0.05
    # asset quality and return, filed as fractions and read as percentages (owner, 2026-10-19: a bank's card had none)
    assert (round(now["gnpa_pct"], 2), round(now["nnpa_pct"], 2), round(now["roa_pct"], 2)) == (1.58, 0.64, 1.48)
    assert {m.unit for m in result.metrics if m.metric in ("gnpa_pct", "nnpa_pct")} == {"PCT"}


def test_nse_results_rows_are_read_and_matched_by_date():
    """BSE lists the NBFC and life-insurance templates under paths that serve nothing, so those companies
    had no machine-tagged results at all. NSE lists the same filings; the rows are matched to the BSE one
    by its filing date, within a week, because the two exchanges stamp the same filing a day or two apart."""
    from bse_intel.nse import parse_results_rows

    rows = parse_results_rows([
        {"xbrl": "/corporate/xbrl/NBFC_INDAS_1_29012025.xml", "filingDate": "29-Jan-2025",
         "consolidated": "Consolidated", "audited": "Un-Audited", "bank": "No", "period": "Quarterly"},
        {"xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/NBFC_INDAS_2_29012025.xml",
         "filingDate": "29-Jan-2025", "consolidated": "Non-Consolidated", "audited": "Un-Audited", "bank": "No"},
        {"xbrl": "", "filingDate": "29-Jan-2025"},          # no instance: dropped
        {"xbrl": "/corporate/xbrl/OLD_1_22102024.xml", "filingDate": "22-Oct-2024", "consolidated": "Consolidated"},
    ])
    assert len(rows) == 3, "rows without an XBRL instance are dropped"
    assert rows[0].filed_at == "2025-01-29" and rows[-1].filed_at == "2024-10-22"   # newest first
    assert rows[0].xbrl_url.startswith("https://nsearchives.nseindia.com/"), "a relative path is made absolute"
    assert rows[1].xbrl_url.startswith("https://nsearchives.nseindia.com/"), "an absolute one is left alone"
    assert rows[0].consolidated is True and rows[1].consolidated is False   # "Non-Consolidated" is not consolidated
    assert rows[0].is_bank is False


def _insurance_xml(family: str, facts: str) -> bytes:
    """An instance on one of SEBI's insurance templates, which the parser tells apart by namespace."""
    head = ('<?xml version="1.0"?><xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" '
            'xmlns:iso4217="http://www.xbrl.org/2003/iso4217" '
            f'xmlns:in-capmkt-ent="http://www.sebi.gov.in/xbrl/IntegratedFinance_{family}/2025-01-31/'
            'in-capmkt/in-capmkt-ent" xmlns:in-capmkt="http://www.sebi.gov.in/xbrl/2025-01-31/in-capmkt">'
            '<xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>'
            '<xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>')
    return (head + _ctx("Q", "2026-07-01", "2026-09-30")
            + '<in-capmkt:NatureOfReportStandaloneConsolidated contextRef="Q">Standalone'
              "</in-capmkt:NatureOfReportStandaloneConsolidated>"
            + facts + "</xbrli:xbrl>").encode()


def _cap(name, value, unit="INR"):
    return f'<in-capmkt:{name} contextRef="Q" unitRef="{unit}">{value}</in-capmkt:{name}>'


def test_a_general_insurer_is_read_from_its_own_template():
    """Premium is the top line, and the combined ratio is filed as a fraction but read as a percentage."""
    xml = _insurance_xml("GI", _cap("PremiumEarned", 66_518_700_000) + _cap("GrossPremiumsWritten", 77_020_900_000)
                         + _cap("IncurredClaims", 48_388_400_000) + _cap("ProfitOrLossBeforeTax", 12_474_100_000)
                         + _cap("ProvisionForTax", 3_010_100_000) + _cap("ProfitLossAfterTax", 9_464_000_000)
                         + _cap("CombinedRatio", "1.0705", "pure"))
    result = xbrl.parse(xml)
    figures = {m.metric: m.value for m in result.metrics}
    assert figures["revenue"] == 6651.87 and figures["gross_premium"] == 7702.09
    assert figures["incurred_claims"] == 4838.84
    # the three profit figures have to reconcile, or the overlay has picked the wrong account
    assert round(figures["pbt"] - figures["tax_expense"], 2) == figures["pat"] == 946.4
    assert figures["combined_ratio"] == 107.05
    assert next(m for m in result.metrics if m.metric == "combined_ratio").unit == "PCT"


def test_a_life_insurers_tax_comes_from_the_account_its_profit_does():
    """`ProvisionForTax` is the general insurer's tax on profit and the life insurer's POLICYHOLDERS'
    tax, twenty times larger and unrelated to the result. The shareholders' account is the right one."""
    xml = _insurance_xml("LI", _cap("NetPremiumIncome", 218_557_900_000) + _cap("GrossPremiumIncome", 225_021_500_000)
                         + _cap("ProfitLossBeforeTax", 5_405_000_000) + _cap("ProvisionsForTaxes", 189_000_000)
                         + _cap("ProvisionForTax", 381_600_000) + _cap("CurrentTax", 381_600_000)
                         + _cap("ProfitLossAfterTaxAndExtraordinaryItems", 5_216_000_000)
                         + _cap("NetSurplusDeficit", 2_893_900_000))
    figures = {m.metric: m.value for m in xbrl.parse(xml).metrics}
    assert figures["revenue"] == 21855.79 and figures["gross_premium"] == 22502.15
    assert figures["tax_expense"] == 18.9
    assert round(figures["pbt"] - figures["tax_expense"], 2) == figures["pat"] == 521.6
    assert "current_tax" not in figures  # the policyholders' tax, suppressed rather than mislabelled
    assert figures["surplus"] == 289.39


def test_the_same_instance_on_the_commercial_template_keeps_the_commercial_reading():
    """The overlay must apply only where the insurance taxonomy is declared."""
    xml = _insurance_xml("IndAS", _cap("ProfitLossBeforeTax", 5_405_000_000) + _cap("CurrentTax", 381_600_000))
    figures = {m.metric: m.value for m in xbrl.parse(xml).metrics}
    assert figures["current_tax"] == 38.16


def test_integrated_filing_rows_keep_the_revision_and_name_the_template():
    from bse_intel.nse import parse_integrated_rows

    rows = [
        {"symbol": "ICICIGI", "qe_Date": "30-SEP-2026", "consolidated": "Standalone", "type_Sub": "Original",
         "audited": "Audited", "broadcast_Date": "14-Oct-2026 10:36:36",
         "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_GI_1738196_14102026103636_WEB.xml"},
        {"symbol": "ICICIGI", "qe_Date": "30-SEP-2026", "consolidated": "Standalone", "type_Sub": "Revision",
         "audited": "Audited", "broadcast_Date": None, "revised_Date": "16-OCT-2026 19:35:22",
         "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_GI_1740432_16102026073544_WEB.xml"},
        {"symbol": "PNB", "qe_Date": "30-JUN-2026", "consolidated": "Consolidated", "type_Sub": "Original",
         "audited": "Un-Audited", "broadcast_Date": "18-Jul-2026 04:24:21",
         "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_BANKING_1696149_18072026042421_WEB.xml"},
        {"symbol": "X", "qe_Date": "30-JUN-2026", "consolidated": "Standalone", "type_Sub": "Original", "xbrl": ""},
    ]
    filings = parse_integrated_rows(rows)
    assert [f.period_end for f in filings] == ["2026-09-30", "2026-06-30"]
    newest = filings[0]
    assert newest.revised and newest.taxonomy == "GI" and not newest.is_bank
    assert newest.filed_at == "2026-10-16" and "1740432" in newest.xbrl_url
    bank = filings[1]
    assert bank.is_bank and bank.taxonomy == "BANKING" and bank.consolidated


def test_a_full_year_key_number_is_not_overwritten_with_the_quarters_figure():
    """Our own fixer was writing wrong numbers over right ones, for the third time (D25).

    A Q4 results file carries the quarter AND the year it closes. The override matched a key number by
    metric alone, so "FY25 revenue" took the Q4 fact: in the 2026-10-17 round SML's FY25 revenue went
    from Rs 453.98 Cr to Rs 107.84 Cr - a fifth of itself - with the year's own YoY left beside it, and
    FY25 PAT from -Rs 48.04 Cr to -Rs 14.76 Cr. The label names its period; it has to be read.
    """
    from bse_intel.models import FinancialMetric, Pass2Output
    from bse_intel.pipeline import xbrl_key_numbers

    tagged = xbrl.XbrlResult("RESULTS", "STANDALONE", "Q4FY25", [
        FinancialMetric(metric="revenue", period="Q4FY25", value=107.84, unit="INR_CR", yoy_pct=-12.0),
        FinancialMetric(metric="revenue", period="FY25", value=453.98, unit="INR_CR", yoy_pct=-3.3),
        FinancialMetric(metric="pat", period="Q4FY25", value=-14.76, unit="INR_CR"),
        FinancialMetric(metric="ebitda", period="Q4FY25", value=8.2, unit="INR_CR"),
    ])
    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "FY25 results",
        "card": {"impact_level": "MODERATE", "headline": "FY25 results", "basis": "STANDALONE",
                 "what_happened": ["FY25 results declared"],
                 "key_numbers": [{"label": "FY25 revenue", "value": "₹453.98 Cr", "change": "-3.3% YoY"},
                                 {"label": "Q4 EBITDA", "value": "₹8.2 Cr", "change": None},
                                 {"label": "FY25 PBT", "value": "₹5 Cr", "change": None},
                                 {"label": "Revenue", "value": "₹100 Cr", "change": None},
                                 {"label": "PAT", "value": "₹-48.04 Cr", "change": "+4.3% YoY"}]}})
    xbrl_key_numbers(out, tagged)
    keys = {k.label: k.value for k in out.card.key_numbers}
    changes = {k.label: k.change for k in out.card.key_numbers}
    assert keys["FY25 revenue"] == "₹453.98 Cr", "the year keeps the year's figure"
    assert changes["FY25 revenue"] == "-3.3% YoY", "a figure left alone keeps its change"
    assert keys["Q4 EBITDA"] == "₹8.20 Cr", "a bare quarter is the quarter of the year reported"
    assert keys["FY25 PBT"] == "₹5 Cr", "the file carries no PBT for the year: left to the model"
    assert keys["Revenue"] == "₹453.98 Cr", "a bare label follows the period the card is about"

    # the same file, read by a card about the quarter: now a bare label is the quarter's
    out.card.headline = out.timeline_entry = "Q4FY25 results"
    out.card.key_numbers[3].value, out.card.key_numbers[3].change = "₹100 Cr", "+4.3% YoY"
    out.card.key_numbers[4].value, out.card.key_numbers[4].change = "₹-48.04 Cr", "+4.3% YoY"
    xbrl_key_numbers(out, tagged)
    keys = {k.label: k.value for k in out.card.key_numbers}
    changes = {k.label: k.change for k in out.card.key_numbers}
    assert keys["Revenue"] == "₹107.84 Cr" and changes["Revenue"] == "-12.0% YoY"
    assert keys["PAT"] == "₹-14.76 Cr" and changes["PAT"] is None,         "a figure replaced by another period's loses the change that belonged to the one it replaced"


def _quarter(period, revenue, pat, eps, scale=1.0):
    from bse_intel.models import BalanceSheet, FinancialMetric

    return xbrl.XbrlResult(kind="RESULTS", basis="CONSOLIDATED", period=period, metrics=[
        FinancialMetric(metric="revenue", period=period, value=revenue * scale),
        FinancialMetric(metric="pat", period=period, value=pat * scale),
        FinancialMetric(metric="eps", period=period, value=eps, unit="INR"),
        FinancialMetric(metric="ebitda_margin", period=period, value=14.2, unit="PCT")],
        balance_sheet=BalanceSheet(period=period, net_worth_cr=6_100 * scale))


def test_a_results_file_tagged_in_the_wrong_unit_is_put_right_and_a_real_fall_is_not():
    """Jubilant Pharmova's Q4FY24 file tags every amount at a tenth of its value ("Lakhs" declared for a
    statement in millions): memory held FY24 revenue at Rs 670 Cr, and the FY25 cards said +979% YoY. A
    slip moves revenue and the share count profit/EPS imply by the same power of ten; a real fall does not."""
    others = [_quarter("Q1FY24", 1586.9, 60.0, 3.77), _quarter("Q2FY24", 1680.3, 62.1, 3.90),
              _quarter("Q3FY24", 1677.1, 66.4, 4.17), _quarter("Q1FY25", 1731.7, 481.8, 30.25)]
    history = [m for q in others for m in q.metrics]

    slipped = _quarter("Q4FY24", 1758.6, -61.8, -3.69, scale=0.1)
    assert xbrl.scale_slip(slipped, history) == 1
    assert xbrl.fix_scale(slipped, history, "530019") == 1
    figures = {m.metric: m.value for m in slipped.metrics}
    assert figures == {"revenue": 1758.6, "pat": -61.8, "eps": -3.69, "ebitda_margin": 14.2}
    assert slipped.balance_sheet.net_worth_cr == 6100.0

    # Revenue down to a tenth after a demerger: same shares, so profit/EPS says the unit is right.
    shrunk = _quarter("Q4FY24", 170.0, 6.4, 0.40)
    assert xbrl.scale_slip(shrunk, history) == 0
    assert xbrl.scale_slip(_quarter("Q4FY24", 1758.6, -61.8, -3.69), history) == 0, "a file in the right unit"
    assert xbrl.scale_slip(slipped, history[:4]) == 0, "one other quarter is too little to judge by"
    assert xbrl.fix_scale(None, history) == 0


def test_continuing_and_discontinued_pat_are_not_the_files_total_pat():
    from bse_intel.models import Pass2Output
    from bse_intel.pipeline import xbrl_key_numbers

    """Siemens Q1FY27 (round 4, 2026-10-19): "PAT (Continuing) ₹343 Cr" was overwritten with total PAT ₹2,143.10 Cr,
    which carries the demerged business's gain, and -18.7% YoY became +406%. A continuing label takes the file's
    continuing-operations profit when it has one, and is left as read otherwise; a discontinued one is never touched."""
    tagged = xbrl.parse((FIXTURES / "bse_main_ind_as_532811_q3fy25.xml").read_bytes())
    pat = next(m for m in tagged.metrics if m.period == "Q3FY25" and m.metric == "pat")
    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": "Q3FY25 results",
        "card": {"impact_level": "MODERATE", "headline": "Ahluwalia Q3FY25 results", "basis": "STANDALONE",
                 "what_happened": ["Results"],
                 "key_numbers": [{"label": "PAT (Continuing)", "value": "₹10 Cr", "change": "-18.7% YoY"},
                                 {"label": "PAT from discontinued operations", "value": "₹1,800 Cr", "change": None},
                                 {"label": "PAT", "value": "₹1 Cr", "change": None}]}})
    xbrl_key_numbers(out, tagged)
    keys = {k.label: k.value for k in out.card.key_numbers}
    continuing = next((m for m in tagged.metrics if m.period == "Q3FY25" and m.metric == "pat_continuing"), None)
    assert keys["PAT (Continuing)"] == (f"₹{continuing.value:,.2f} Cr" if continuing else "₹10 Cr")
    assert keys["PAT (Continuing)"] != f"₹{pat.value:,.2f} Cr" or (continuing and continuing.value == pat.value)
    assert keys["PAT from discontinued operations"] == "₹1,800 Cr"
    assert keys["PAT"] == f"₹{pat.value:,.2f} Cr"      # the plain label still takes the file's PAT


def test_a_results_file_whose_statement_the_text_lacks_is_used_when_memory_agrees(settings):
    """Ceigall Q1FY27 (round 5 arm B): the statement's pages were missing from the text read, so the file was refused
    and the model wrote Q1FY26's profit as Q1FY27's. When the file's own year-ago figures are memory's, it is the right
    company, scale and basis: the card is built from it."""
    now = now_ist() - timedelta(minutes=30)
    filing = _filing("n-res", "Unaudited Financial Results for the quarter ended September 30, 2026", now, "Result")
    filing.xbrl_url = "https://bse.invalid/n-res.xml"
    garbled = "Statement of unaudited consolidated financial results ... (page not readable)"
    pass2 = json.loads(json.dumps(PASS2))

    def run(memory_revenue):
        pipeline, sink, fake = build(settings, [filing], {filing.pdf_url: _pdf(garbled), filing.xbrl_url: results_xml()},
                                     {"nvidia/nemotron-3.5-super-vl:free": [json.dumps(pass2)] * 2})
        dossier = {"financial_metrics": [{"metric": "revenue", "period": "Q2FY26", "value": memory_revenue, "unit": "INR_CR",
                                          "as_of": "2025-11-10T18:00:00+05:30"}]}
        sink.put_dossier("999001", dossier)
        pipeline.run("live", time_budget_s=60)
        return fake.calls[0]["messages"][-1]["content"]

    assert "Machine-tagged results (XBRL" in run(90.91)          # memory holds the file's year-ago quarter
    # a file at another scale than memory (9.091 against 90.91) is refused as before: results_card.agrees_with_memory,
    # test_results_card.test_memory_points_need_memory_and_the_file_to_agree_on_the_basis


def test_bank_ratios_already_in_percent_or_inconsistent_are_not_misread():
    """A bank ratio above 1 was written as a percentage and is kept as one; net NPA above gross means one of them was
    read at the wrong scale, and neither is kept (a "net NPA 25%" headline from a mis-scaled 0.25)."""
    def bank(gross, net, roa="0.0148"):
        return f"""<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-bse-fin="http://www.bseindia.com/xbrl/fin/2020-03-31/in-bse-fin"
 xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
<xbrli:context id="OneD"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit><xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>
<in-bse-fin:InterestEarned contextRef="OneD" unitRef="INR" decimals="-5">32133700000</in-bse-fin:InterestEarned>
<in-bse-fin:ProfitLossForThePeriod contextRef="OneD" unitRef="INR" decimals="-5">3315100000</in-bse-fin:ProfitLossForThePeriod>
<in-bse-fin:PercentageOfGrossNpa contextRef="OneD" unitRef="pure" decimals="INF">{gross}</in-bse-fin:PercentageOfGrossNpa>
<in-bse-fin:PercentageOfNpa contextRef="OneD" unitRef="pure" decimals="INF">{net}</in-bse-fin:PercentageOfNpa>
<in-bse-fin:ReturnOnAssets contextRef="OneD" unitRef="pure" decimals="INF">{roa}</in-bse-fin:ReturnOnAssets>
</xbrli:xbrl>""".encode()

    def ratios(raw):
        result = xbrl.parse(raw)
        return {m.metric: round(m.value, 2) for m in result.metrics if m.metric.endswith("_pct")}

    assert ratios(bank("0.0221", "0.0065")) == {"gnpa_pct": 2.21, "nnpa_pct": 0.65, "roa_pct": 1.48}
    assert ratios(bank("2.21", "0.0065")) == {"gnpa_pct": 2.21, "nnpa_pct": 0.65, "roa_pct": 1.48}   # one in percent
    assert ratios(bank("0.0221", "0.25")) == {"roa_pct": 1.48}        # net 25% above gross 2.21%: both dropped
    assert "roa_pct" not in ratios(bank("0.0221", "0.0065", roa="0.9"))  # RoA 90%: out of range


def _bank_file(ratios: dict[str, tuple[str, str, str]]) -> bytes:
    """A banking file with one context per period id: {"Q": (gross, net, roa), "H1": (...)} (start dates differ)."""
    starts = {"Q": "2026-07-01", "H1": "2026-04-01"}
    body = []
    for cid, (gross, net, roa) in ratios.items():
        body.append(f"""<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:startDate>{starts[cid]}</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period></xbrli:context>
<in-bse-fin:InterestEarned contextRef="{cid}" unitRef="INR" decimals="-5">32133700000</in-bse-fin:InterestEarned>
<in-bse-fin:ProfitLossForThePeriod contextRef="{cid}" unitRef="INR" decimals="-5">3315100000</in-bse-fin:ProfitLossForThePeriod>
<in-bse-fin:PercentageOfGrossNpa contextRef="{cid}" unitRef="pure" decimals="INF">{gross}</in-bse-fin:PercentageOfGrossNpa>
<in-bse-fin:PercentageOfNpa contextRef="{cid}" unitRef="pure" decimals="INF">{net}</in-bse-fin:PercentageOfNpa>
<in-bse-fin:ReturnOnAssets contextRef="{cid}" unitRef="pure" decimals="INF">{roa}</in-bse-fin:ReturnOnAssets>""")
    return f"""<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-bse-fin="http://www.bseindia.com/xbrl/fin/2020-03-31/in-bse-fin">
<xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit><xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>
{''.join(body)}
</xbrli:xbrl>""".encode()


def _bank_ratios(raw: bytes) -> dict:
    return {(m.metric, m.period): round(m.value, 2) for m in xbrl.parse(raw).metrics if m.metric.endswith("_pct")}


def test_consolidated_bank_file_zero_ratios_are_fillers_not_values():
    # SBI, HDFC Bank and IDFC First's consolidated files: 0 for all three (T2, measured 2026-10-20)
    assert _bank_ratios(_bank_file({"Q": ("0", "0", "0")})) == {}
    # a net NPA of nil beside real ratios is a value
    assert _bank_ratios(_bank_file({"Q": ("0.0069", "0", "0.021")})) == {
        ("gnpa_pct", "Q2FY27"): 0.69, ("nnpa_pct", "Q2FY27"): 0.0, ("roa_pct", "Q2FY27"): 2.1}


def test_roa_put_on_a_yearly_basis_only_when_the_file_is_not():
    # HDFC Bank Q2FY27: quarter 0.45% beside half-year 0.91% -> the period's own return; x4 and x2
    hdfc = _bank_ratios(_bank_file({"Q": ("0.0111", "0.0037", "0.0045"), "H1": ("0.0111", "0.0037", "0.0091")}))
    assert (hdfc[("roa_pct", "Q2FY27")], hdfc[("roa_pct", "H1FY27")]) == (1.8, 1.82)
    # KVB Q2FY27: quarter 2.10% equals half-year 2.11% -> already annualised, left as filed
    kvb = _bank_ratios(_bank_file({"Q": ("0.0069", "0.0018", "0.0210"), "H1": ("0.0069", "0.0018", "0.0211")}))
    assert (kvb[("roa_pct", "Q2FY27")], kvb[("roa_pct", "H1FY27")]) == (2.1, 2.11)
    # the quarter alone: no way to tell, left as filed
    assert _bank_ratios(_bank_file({"Q": ("0.0111", "0.0037", "0.0045")}))[("roa_pct", "Q2FY27")] == 0.45


def test_a_consolidated_bank_card_takes_its_ratios_from_the_standalone_file():
    from bse_intel.models import FinancialMetric

    consolidated = xbrl.XbrlResult("RESULTS", "CONSOLIDATED", "Q2FY27",
                                   [FinancialMetric(metric="pat", period="Q2FY27", value=19000.0)], template="BANKING")
    assert xbrl.needs_standalone_bank_ratios(consolidated)
    standalone = xbrl.XbrlResult("RESULTS", "STANDALONE", "Q2FY27", [
        FinancialMetric(metric="pat", period="Q2FY27", value=18000.0),
        FinancialMetric(metric="gnpa_pct", period="Q2FY27", value=1.11, unit="PCT"),
        FinancialMetric(metric="nnpa_pct", period="Q2FY27", value=0.37, unit="PCT"),
        FinancialMetric(metric="gnpa_pct", period="Q2FY26", value=1.24, unit="PCT")])   # no such period in the card
    assert xbrl.add_bank_ratios(consolidated, standalone) == 2
    assert {m.metric for m in consolidated.metrics} == {"pat", "gnpa_pct", "nnpa_pct"}
    assert consolidated.metrics[0].value == 19000.0   # the card's own profit stays consolidated
    assert "gnpa_pct Q2FY27 (standalone): 1.11 %" in consolidated.table()
    assert not xbrl.needs_standalone_bank_ratios(consolidated)
    # not a bank, or already standalone: nothing to fetch
    assert not xbrl.needs_standalone_bank_ratios(xbrl.XbrlResult("RESULTS", "CONSOLIDATED", "Q2FY27", [], template="INDAS"))
    assert not xbrl.needs_standalone_bank_ratios(xbrl.XbrlResult("RESULTS", "STANDALONE", "Q2FY27", [], template="BANKING"))


def test_the_half_year_file_gives_the_full_balance_sheet_and_cash_flow():
    """Owner (2026-10-21): the company page needs the balance sheet and cash flow as on screener.in. Ahluwalia's Q2FY25
    file: assets equal equity plus liabilities, and the H1 cash flows."""
    from pathlib import Path

    from bse_intel import xbrl

    r = xbrl.parse((Path(__file__).parent / "fixtures" / "bse_main_ind_as_532811_q2fy25.xml").read_bytes())
    b = r.balance_sheet
    assert b.period == "Q2FY25" and b.total_assets_cr == 3392.13
    assert round(b.net_worth_cr + b.total_liabilities_cr, 2) == b.total_assets_cr
    assert (b.fixed_assets_cr, b.inventories_cr, b.receivables_cr, b.payables_cr) == (306.86, 326.94, 659.05, 828.82)
    flows = {m.metric: m.value for m in r.metrics if m.period == "H1FY25"}
    assert (flows["operating_cash_flow"], flows["investing_cash_flow"], flows["financing_cash_flow"]) == (86.01, -102.55, -36.22)
    assert flows["capex"] == 92.39


def test_old_nse_files_give_the_year_not_the_quarter_twice():
    """Deep audit A-03: before the integrated filing, NSE's files tag the year to date ("FourD") with the quarter's own
    dates; Asian Paints' FY24 operating cash flow was stored as Q4FY24's."""
    from pathlib import Path

    from bse_intel import xbrl

    fx = Path(__file__).parent / "fixtures"
    r = xbrl.parse((fx / "nse_old_asianpaint_q4fy24.xml").read_bytes())
    got = {(m.metric, m.period): m.value for m in r.metrics}
    assert got[("revenue", "FY24")] == 35494.73 and got[("revenue", "Q4FY24")] == 8730.76
    assert got[("operating_cash_flow", "FY24")] == 6103.6 and ("operating_cash_flow", "Q4FY24") not in got
    h1 = {(m.metric, m.period): m.value for m in xbrl.parse((fx / "nse_old_titan_q2fy24.xml").read_bytes()).metrics}
    assert ("revenue", "H1FY24") in h1 and ("operating_cash_flow", "Q2FY24") not in h1


def test_bank_nbfc_and_insurer_balance_sheets():
    """Deep audit A-01 and A-10: no bank had a net worth, Bajaj Finance no debt, and an insurer's "Assets" (net of current
    liabilities) was stored as its total."""
    from pathlib import Path

    from bse_intel import xbrl

    fx = Path(__file__).parent / "fixtures"
    bank = xbrl.parse((fx / "nse_hdfcbank_q2fy27_cons.xml").read_bytes()).balance_sheet
    assert bank.net_worth_cr == 603469.05 and bank.deposits_cr == 3324146.36 and bank.advances_cr == 3316057.54
    assert round(bank.net_worth_cr + bank.total_liabilities_cr, 2) == bank.total_assets_cr
    nbfc = xbrl.parse((fx / "nse_bajfin_q2fy27_cons.xml").read_bytes()).balance_sheet
    assert nbfc.gross_debt_cr == 432228.16 and nbfc.advances_cr == 574174.44
    life = xbrl.parse((fx / "nse_hdfclife_q2fy27_cons.xml").read_bytes()).balance_sheet
    assert life.total_assets_cr is None and life.net_worth_cr == 19467.43 and life.investments_cr == 410086.96


def test_older_results_list_rows_carry_their_quarter_but_stay_off_the_cards():
    """Deep audit A-02: the older list's rows had no quarter end, so the seed never reached before Q4FY25."""
    from bse_intel.nse import parse_results_rows, results_links

    rows = parse_results_rows([{"xbrl": "https://x/INDAS_1.xml", "toDate": "31-Mar-2024", "fromDate": "01-Jan-2024",
                                "consolidated": "Consolidated", "filingDate": "25-Apr-2024"}])
    assert rows[0].period_end == "2024-03-31" and rows[0].legacy
    assert results_links(rows) == []


def test_nse_dates_with_hyphens_are_read():
    """Deep audit A-05/A-06: NSE writes "21-Oct-2026"; record dates and quarter ends written so were lost."""
    from bse_intel.periods import explicit_date, statement_quarter
    from bse_intel.rules import extract_date

    assert extract_date("Record date 21-Oct-2026 for the interim dividend", "2026-10-14") == "2026-10-21"
    assert str(explicit_date("30-Sep-2026")) == "2026-09-30"
    assert statement_quarter("quarter ended 30-Sep-2026") == "Q2FY27"


def test_a_year_not_ending_in_march_keeps_quarters_only():
    """22 Oct 2026, Siemens (year to September) in memory: its October-March half stored as FY23 and its full year as
    H1FY24, because every label assumes an April-March year. Quarters are named by calendar months and stay; a half
    year, nine months or year of such a company gets no label, in the parser and in memory."""
    from datetime import date

    from bse_intel.dossier import drop_off_year_periods, march_year
    from bse_intel.xbrl import fy_end_month, period_label

    def ctx(start, end):
        return {"startDate": start, "endDate": end, "dims": False}

    assert fy_end_month({"DateOfEndOfFinancialYear": "2026-09-30"}) == 9
    assert fy_end_month({"DateOfEndOfFinancialYear": "2027-03-31"}) == 3 and fy_end_month({}) is None
    assert period_label(ctx(date(2026, 7, 1), date(2026, 9, 30)), 9) == "Q2FY27"         # a calendar quarter
    assert period_label(ctx(date(2025, 10, 1), date(2026, 9, 30)), 9) is None           # Siemens' year
    assert period_label(ctx(date(2025, 10, 1), date(2026, 3, 31)), 9) is None           # Siemens' first half
    assert period_label(ctx(date(2026, 4, 1), date(2026, 9, 30)), 3) == "H1FY27"        # a March year unchanged
    d = {"fy_end_month": 9, "financial_metrics": [{"metric": "revenue", "period": p, "value": 1.0}
                                                  for p in ("FY23", "H1FY24", "Q2FY27", "Q1CY26", "9MFY26")]}
    assert not march_year(d) and drop_off_year_periods(d) == 4
    assert [m["period"] for m in d["financial_metrics"]] == ["Q2FY27"]
    assert march_year({}) and drop_off_year_periods({"financial_metrics": [{"period": "FY26"}]}) == 0


def test_ebitda_comes_from_profit_before_exceptional_items_whatever_the_charges_sign():
    """Data chain audit A9 (22 Oct 2026): EBITDA as PBT less the exceptional items depends on the sign a filer gives a
    charge; one tagged positive took EBITDA down by twice it. The file's own profit before exceptional items decides."""
    from pathlib import Path

    from bse_intel import xbrl

    raw = (Path(__file__).parent / "fixtures" / "bse_main_ind_as_532811_q2fy25.xml").read_text(encoding="utf-8")
    base = xbrl.parse(raw.encode())
    ebitda = next(m.value for m in base.metrics if m.metric == "ebitda" and m.period == base.period)
    # a ₹10 Cr charge tagged positive, with PBT after it: EBITDA does not move
    charged = raw.replace('<in-bse-fin:ExceptionalItemsBeforeTax contextRef="OneD" unitRef="INR" decimals="-5">0<',
                          '<in-bse-fin:ExceptionalItemsBeforeTax contextRef="OneD" unitRef="INR" decimals="-5">100000000<', 1)
    charged = charged.replace('<in-bse-fin:ProfitBeforeTax contextRef="OneD" unitRef="INR" decimals="-3">525064000<',
                              '<in-bse-fin:ProfitBeforeTax contextRef="OneD" unitRef="INR" decimals="-3">425064000<', 1)
    assert charged != raw
    again = xbrl.parse(charged.encode())
    assert next(m.value for m in again.metrics if m.metric == "ebitda" and m.period == again.period) == ebitda
    assert not any(m.metric == "pbt_before_exceptional" for m in again.metrics)   # used, not kept


def test_a_consolidated_banks_profit_is_after_minorities_and_associates():
    """Indian Bank Q4FY26 (hourly review, 22 Oct 2026): the table's net profit was ProfitLossForThePeriod (₹3,115.2 Cr,
    before minority interest and the associates' share); its EPS is on the group's ₹3,173.05 Cr."""
    from pathlib import Path

    from bse_intel import xbrl

    raw = (Path(__file__).parent / "fixtures" / "nse_hdfcbank_q2fy27_cons.xml").read_text(encoding="utf-8")
    tag = '<in-capmkt:ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates contextRef="OneD" decimals="-5" unitRef="INR">207000300000<'
    assert tag in raw
    moved = xbrl.parse(raw.replace(tag, tag.replace("207000300000", "212000300000"), 1).encode())
    assert next(m.value for m in moved.metrics if m.metric == "pat" and m.period == moved.period) == 21200.03
    assert not any(m.metric == "pat_group" for m in moved.metrics)


def test_a_year_that_is_not_its_four_quarters_is_not_kept():
    # Siemens' Q4FY26 file (consolidated, read 22 Oct 2026): the year to March 2026 is 18 months, dated 1 Apr 2025 -
    # 31 Mar 2026; memory holds Q1, Q2 and Q4 of FY26 (Q3 missing)
    from bse_intel.models import FinancialMetric as FM

    def result():
        return xbrl.XbrlResult(kind="RESULTS", basis="CONSOLIDATED", period="Q4FY26", metrics=[
            FM(metric="revenue", period="Q4FY26", value=4617.5), FM(metric="pat", period="Q4FY26", value=370.4),
            FM(metric="revenue", period="FY26", value=24845.6), FM(metric="pat", period="FY26", value=2754.1),
            FM(metric="eps", period="FY26", value=64.12, unit="INR")])

    history = [{"metric": "revenue", "period": "Q1FY26", "value": 3830.7}]
    assert xbrl.long_year(result(), history) is None                       # Q1 and the file's Q4: too little to tell
    history += [{"metric": "revenue", "period": "Q2FY26", "value": 5171.2},
                {"metric": "revenue", "period": "Q3FY26", "value": 4100.0}]
    r = result()
    why = xbrl.drop_long_year(r, history, "500550")
    assert why and "FY26" in why                                           # four known: 24,845.6 against 17,719.4
    assert {m.period for m in r.metrics} == {"Q4FY26"}                     # the quarter stays, the year goes
    why = xbrl.long_year(result(), history[:2])                            # Siemens as memory holds it: Q1, Q2, Q4
    assert why and "fourth quarter" in why                                 # it leaves ₹11,226 Cr for Q3
    # a true year stands: within 15% of its four quarters
    true_year = result()
    for m in true_year.metrics:
        if m.period == "FY26" and m.metric == "revenue":
            m.value = 17900.0
    assert xbrl.long_year(true_year, history) is None
