"""xbrl_extras.py (owner, 30 Oct 2026, TODO 138 and 132): audit status and auditors, cash-flow detail, related parties and ratios
from the stored facts, by code, with the real files."""
from pathlib import Path

from bse_intel import screener_view as sv
from bse_intel import statements, statements_backfill, xbrl_extras, xbrl_facts
from bse_intel.dossier import keep_concurrent_writes

FIXTURES = Path(__file__).parent / "fixtures"
AS_OF, AT = "2026-10-30T18:00:00+05:30", "2026-10-30T18:01:00+05:30"


def _doc(name):
    data = (FIXTURES / name).read_bytes()
    return xbrl_facts.parse_annual_facts(data, "x", "u") if "_ar_" in name else xbrl_facts.parse_facts(data, "x", "u")


def test_audit_status_and_two_auditors_of_a_quarter():
    col, a = xbrl_extras.read(_doc("nse_hdfcbank_q2fy27_cons.xml"))["audit"]
    assert col == "Q2FY27" and a["kind"] == "results"
    assert (a["audited"], a["audited_ytd"]) == ("Unaudited", "Unaudited")
    assert a["opinion"] == "Declaration of unmodified opinion" and a["qualification_status"] == "Unaudited"
    assert a["auditors"] == [{"name": "B S R & Co. LLP", "peer_review_valid": True, "certificate_valid_until": "2028-07-31"},
                             {"name": "Batliboi & Purohit", "peer_review_valid": True, "certificate_valid_until": "2028-04-30"}]
    _, q4 = xbrl_extras.read(_doc("nse_dolphin_q4fy24_cons.xml"))["audit"]
    assert (q4["audited"], q4["audited_ytd"], q4["opinion"]) == ("Audited", "Audited", "Declaration of unmodified opinion")
    assert "auditors" not in q4          # the old taxonomy names no auditor


def test_annual_auditor_flags_keep_the_clauses_whole():
    _, a = xbrl_extras.read(_doc("nse_ar_kanorichem_fy25_standalone.xml"))["audit"]
    assert a["kind"] == "annual" and a["qualified"] is False
    assert a["auditors"] == [{"name": "Singhi & Co", "signing_partner": "RAHUL BOTHRA", "signed_on": "2025-05-21",
                           "firm_registration_no": "302049E"}]
    assert set(a["clauses"]) == {"default_in_repayment", "fraud", "statutory_dues"}
    assert a["clauses"]["default_in_repayment"]["remark"] == "ClauseNotApplicable"
    assert len(a["clauses"]["statutory_dues"]["text"]) > 1000, "cut at 1,000 characters before TODO 139"
    _, s = xbrl_extras.read(_doc("nse_ar_shivamauto_fy25_standalone.xml"))["audit"]
    assert s["clauses"]["fraud"]["remark"] == "AuditorsFavourableRemark" and s["auditors"][0]["name"] == "NSBP & Co"
    assert "audit" in xbrl_extras.read(_doc("nse_ar_kanorichem_fy25_consolidated.xml"))      # no clauses, still the flag
    assert "clauses" not in xbrl_extras.read(_doc("nse_ar_kanorichem_fy25_consolidated.xml"))["audit"][1]


def test_text_of_the_named_elements_is_not_cut_at_1000():
    doc = _doc("nse_ar_shivamauto_fy25_standalone.xml")
    long = [v for el, _, _, v, _ in doc["facts"] if el == "DisclosureInAuditorsReportRelatingToStatutoryDuesExplanatory"]
    assert long and len(long[0]) > xbrl_facts.TEXT_MAX
    whole = [v for el, _, _, v, _ in doc["facts"] if el == "DisclosureInAuditorsReportExplanatory"]
    assert whole and len(whole[0]) == xbrl_facts.TEXT_MAX      # the whole report keeps the old cut
    assert xbrl_facts.FULL_TEXT.search("RemarksOnApprovalByAuditCommittee") and not xbrl_facts.FULL_TEXT.search("OtherExpenses")


def test_half_year_and_year_cash_flow_detail():
    col, h1 = xbrl_extras.read(_doc("nse_old_titan_q2fy24.xml"))["cash_flow_detail"]
    assert col == "Q2FY24" and h1["span"] == "H1" and h1["months"] == 6
    rows = h1["rows"]
    assert len(rows) > 80
    for name in ("CashFlowsFromUsedInOperatingActivities", "ProceedsFromBorrowingsClassifiedAsFinancingActivities",
                 "RepaymentsOfBorrowingsClassifiedAsFinancingActivities", "DividendsPaidClassifiedAsFinancingActivities",
                 "InterestPaidClassifiedAsFinancingActivities", "PaymentsOfLeaseLiabilitiesClassifiedAsFinancingActivities",
                 "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "AdjustmentsForDecreaseIncreaseInInventories"):
        assert name in rows, name
    assert not any(k.startswith(("Revenue", "ProfitBeforeTax", "Segment", "AmountOfItem")) for k in rows)
    assert not {"Purchases", "PurchasesOfStockInTrade"} & set(rows)   # the P&L's purchases, not a cash-flow line
    assert all(xbrl_extras.CASH_FLOW_NOT.match(n) for n in ("Purchases", "PurchasesOfStockInTrade"))
    col, fy = xbrl_extras.read(_doc("nse_dolphin_q4fy24_cons.xml"))["cash_flow_detail"]
    assert col == "FY24" and fy["span"] == "FY" and fy["months"] == 12 and len(fy["rows"]) > 80
    q3 = xbrl_extras.read(_doc("bse_main_ind_as_532811_q3fy25.xml"))
    assert "cash_flow_detail" not in q3      # a nine-month file holds no cash flow
    # the cash flow's own total agrees with the one screener_view keeps
    facts = xbrl_facts.Facts(_doc("nse_old_titan_q2fy24.xml"))
    assert rows["CashFlowsFromUsedInOperatingActivities"] == round(facts.cr("CashFlowsFromUsedInOperatingActivities", end=__import__("datetime").date(2023, 9, 30), months=6), 4)


def test_quarterly_related_party_transactions():
    col, r = xbrl_extras.read(_doc("nse_irfc_q4fy26_nbfc.xml"))["related_parties"]
    assert col == "Q4FY26" and r["kind"] == "results" and r["entered"] is True and r["n_items"] == len(r["items"]) == 19
    top = r["items"][0]      # the largest first
    assert top["amount_cr"] == 9821.0 and top["type"] == "Loan" and top["opening_cr"] == 0.0 and top["closing_cr"] == 9821.0
    assert top["counterparty"].startswith("Dedicated Freight") and top["relationship"].startswith("Entity under control")
    pay = next(i for i in r["items"] if i["type"] == "Remuneration")
    assert pay["amount_cr"] == 0.7 and pay["remarks"] == "No Remarks" and pay["approved_cr"] == 0.0
    assert pay["counterparty"].startswith("Mr. Manoj Kumar Dubey") and pay["relationship"] == "Key Managerial Personal"
    sitting = next(i for i in r["items"] if i.get("other_details") == "Sitting Fees")
    assert sitting["type"] == "Any other transaction" and sitting["amount_cr"] == 0.07
    assert "PAN" not in str(r)
    assert "related_parties" not in xbrl_extras.read(_doc("nse_old_titan_q2fy24.xml"))


def test_annual_related_parties_by_party_and_category():
    _, r = xbrl_extras.read(_doc("nse_ar_kanorichem_fy25_standalone.xml"))["related_parties"]
    assert r["kind"] == "annual" and r["has_transactions"] is True and r["n_parties"] == len(r["parties"]) >= 15
    velleyan = next(p for p in r["parties"] if p["party"] == "Mr. A. Velleyan")
    assert velleyan["category"] == "KeyManagementPersonnelOfEntityOrParent"
    assert velleyan["flows"]["OtherRelatedPartyTransactionsExpense"] == 0.014       # this year's, not 2024's 0.027
    assert any(p["balances"] for p in r["parties"])


def test_bank_nbfc_and_insurer_ratios():
    _, bank = xbrl_extras.read(_doc("bse_bank_542867_q3fy25.xml"))["fin_ratios"]
    assert bank["values"]["CET1Ratio"] == 0.1973 and bank["values"]["PercentageOfGrossNpa"] == 0.0158
    assert bank["values"]["GrossNonPerformingAssets"] == 458.17 and bank["values"]["NonPerformingAssets"] == 182.71
    _, nbfc = xbrl_extras.read(_doc("nse_irfc_q4fy26_nbfc.xml"))["fin_ratios"]
    assert nbfc["values"] == {"DebtEquityRatio": 0.0769, "DebtServiceCoverageRatio": 0, "InterestServiceCoverageRatio": 0}
    _, life = xbrl_extras.read(_doc("nse_hdfclife_q2fy27_cons.xml"))["fin_ratios"]
    v = life["values"]
    assert v["SolvencyRatio"] == 1.8 and v["PersistencyRatio13ThMonth"] == 0.794 and v["PersistencyRatio61ThMonth"] == 0.6591
    assert v["GrossNPAsShareholdersFund"] == 13.4062
    assert "fin_ratios" not in xbrl_extras.read(_doc("nse_dolphin_q4fy24_cons.xml"))


def test_remember_labels_replaces_a_revised_file_and_keeps_both_bases():
    doc = _doc("nse_hdfcbank_q2fy27_cons.xml")
    d = {}
    assert xbrl_extras.remember(d, doc, "n1", AS_OF, AT) == 3          # audit, cash flow, ratios
    assert set(d) == {"audit", "cash_flow_detail", "fin_ratios"}
    e = d["audit"][0]
    assert (e["period"], e["basis"], e["lab"]["by"], e["source_news_id"]) == ("Q2FY27", "CONSOLIDATED", "file", "n1")
    revised = dict(doc, basis="STANDALONE")
    xbrl_extras.remember(d, revised, "n2", AS_OF, AT)
    assert [x["basis"] for x in d["audit"]] == ["CONSOLIDATED", "STANDALONE"]
    xbrl_extras.remember(d, doc, "n3", AS_OF, AT)                     # the same period and basis again: replaced
    assert len(d["audit"]) == 2 and {x["source_news_id"] for x in d["audit"]} == {"n2", "n3"}
    assert xbrl_extras.remember(d, doc, "n4", AS_OF, AT, replace=False) == 0
    assert {x["source_news_id"] for x in d["audit"]} == {"n2", "n3"}


def test_a_quarter_held_as_unit_slipped_gets_no_amounts_but_keeps_the_audit_status():
    d = {"scale_held": [{"period": "Q2FY27"}]}
    xbrl_extras.remember(d, _doc("nse_hdfcbank_q2fy27_cons.xml"), "n1", AS_OF, AT)
    assert set(d) == {"scale_held", "audit"}


def test_the_newest_entries_are_kept():
    d = {"audit": [{"period": f"Q{q}FY{y}", "basis": "CONSOLIDATED", "kind": "results"} for y in range(10, 26) for q in (1, 2, 3, 4)]}
    xbrl_extras.remember(d, _doc("nse_hdfcbank_q2fy27_cons.xml"), "n1", AS_OF, AT)
    assert len(d["audit"]) == xbrl_extras.MAX_ENTRIES["audit"] and d["audit"][-1]["period"] == "Q2FY27"


def test_the_live_path_writes_the_extras_beside_the_statements():
    d = {}
    statements.from_file(None, d, (FIXTURES / "nse_irfc_q4fy26_nbfc.xml").read_bytes(), "1", "u", "n1", AS_OF, AT)
    assert {"audit", "cash_flow_detail", "related_parties", "fin_ratios"} <= set(d)


def test_the_backfill_fills_from_stored_facts_without_a_download(settings):
    from bse_intel.sinks.local import LocalSink
    sink = LocalSink(settings)
    for name, scrip in (("nse_irfc_q4fy26_nbfc.xml", "1"), ("nse_ar_kanorichem_fy25_standalone.xml", "1")):
        doc = _doc(name)
        if doc.get("kind") == "annual":
            xbrl_facts.save_annual(sink, scrip, doc["fy"], doc["basis"], doc)
        else:
            xbrl_facts.save(sink, scrip, doc["period"], doc["basis"], doc)
    cf = sv.CompanyFacts(sink.list_objects(f"{xbrl_facts.PREFIX}1/"), sink.get_object)
    d = {}
    added = statements_backfill.fill_extras(cf, d, AT)
    assert added == 7 and d["audit"][0]["lab"]["from"] == "stored facts"
    assert {(e["period"], e["kind"]) for e in d["audit"]} == {("Q4FY26", "results"), ("FY25", "annual")}
    assert [e["period"] for e in d["cash_flow_detail"]] == ["FY25", "FY26"]
    assert statements_backfill.fill_extras(cf, d, AT) == 0, "nothing added twice"


def test_a_concurrent_writer_keeps_the_extras_of_both():
    read = {}
    merged = {"audit": [{"period": "Q2FY27", "basis": "CONSOLIDATED", "kind": "results"}]}
    fresh = {"audit": [{"period": "Q1FY27", "basis": "CONSOLIDATED", "kind": "results"}]}
    keep_concurrent_writes(merged, {"audit": [{"period": "Q4FY26", "basis": "CONSOLIDATED", "kind": "results"}]}, fresh)
    assert [e["period"] for e in merged["audit"]] == ["Q1FY27", "Q2FY27"] or len(merged["audit"]) == 2
