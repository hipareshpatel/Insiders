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
