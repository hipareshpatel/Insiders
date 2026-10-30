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
    # a 0 cover ratio may be true (no debt to serve) and stays while other ratios of the quarter are not 0
    assert nbfc["values"] == {"DebtEquityRatio": 0.0769, "DebtServiceCoverageRatio": 0, "InterestServiceCoverageRatio": 0}
    _, life = xbrl_extras.read(_doc("nse_hdfclife_q2fy27_cons.xml"))["fin_ratios"]
    v = life["values"]
    assert v["SolvencyRatio"] == 1.8 and v["PersistencyRatio13ThMonth"] == 0.794 and v["PersistencyRatio61ThMonth"] == 0.6591
    assert v["GrossNPAsShareholdersFund"] == 13.4062
    assert "fin_ratios" not in xbrl_extras.read(_doc("nse_dolphin_q4fy24_cons.xml"))


def test_stored_filler_zero_ratios_are_dropped_when_a_file_is_read_again():
    """Stock-page audit, 30 Oct 2026: SBI's CET1, NPAs and ROA stored as 0.0 for 12 quarters, the template's filler."""
    d = {"fin_ratios": [{"period": "Q2FY24", "basis": "STANDALONE", "values": {"CET1Ratio": 0.0, "ReturnOnAssets": 0.0}},
                        {"period": "Q3FY24", "basis": "STANDALONE", "values": {"CET1Ratio": 0.0, "PercentageOfGrossNpa": 0.0,
                                                                                "ReturnOnAssets": 0.011}}]}
    xbrl_extras.remember(d, _doc("nse_dolphin_q4fy24_cons.xml"), "n1", AS_OF, AT, replace=False)
    # all zero: filler, gone; a 0 CET1 is never real; a 0 NPA beside a real ROA may be true and stays
    assert [(e["period"], e["values"]) for e in d["fin_ratios"]] == [("Q3FY24", {"PercentageOfGrossNpa": 0.0, "ReturnOnAssets": 0.011})]


def test_remember_labels_replaces_a_revised_file_and_keeps_both_bases():
    doc = _doc("nse_hdfcbank_q2fy27_cons.xml")
    d = {}
    # audit and cash flow; the file's ratios are all the template's filler zeros (HDFC Bank's CET1 is not 0)
    assert xbrl_extras.remember(d, doc, "n1", AS_OF, AT) == 4     # + face value and segment assets (second group)
    assert set(d) == {"audit", "cash_flow_detail", "dividends", "segment_balance"}
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
    assert added == 11 and d["audit"][0]["lab"]["from"] == "stored facts"
    assert {(e["period"], e["kind"]) for e in d["audit"]} == {("Q4FY26", "results"), ("FY25", "annual")}
    assert [e["period"] for e in d["cash_flow_detail"]] == ["FY25", "FY26"]
    assert statements_backfill.fill_extras(cf, d, AT) == 0, "nothing added twice"


def test_a_concurrent_writer_keeps_the_extras_of_both():
    read = {}
    merged = {"audit": [{"period": "Q2FY27", "basis": "CONSOLIDATED", "kind": "results"}]}
    fresh = {"audit": [{"period": "Q1FY27", "basis": "CONSOLIDATED", "kind": "results"}]}
    keep_concurrent_writes(merged, {"audit": [{"period": "Q4FY26", "basis": "CONSOLIDATED", "kind": "results"}]}, fresh)
    assert [e["period"] for e in merged["audit"]] == ["Q1FY27", "Q2FY27"] or len(merged["audit"]) == 2


# --- the second group (TODO 138 / 132): OCI, discontinued operations, segment balances, dividends, KMP pay, contingent liabilities ---

SECOND = ("oci", "discontinued", "segment_balance", "dividends", "kmp_pay", "contingent_liabilities")


def test_the_second_group_keys_are_the_dossiers_keyed_lists():
    from bse_intel import dossier
    assert set(xbrl_extras.KEYS) == set(dossier._EXTRAS_KEYS) <= set(dossier._KEYED_LISTS)
    assert set(SECOND) <= set(xbrl_extras.MAX_ENTRIES)


def test_other_comprehensive_income_with_its_items_by_group():
    col, o = xbrl_extras.read(_doc("nse_irfc_q4fy26_nbfc.xml"))["oci"]
    v = o["values"]
    assert col == "Q4FY26" and o["kind"] == "results"
    assert (v["oci_net_cr"], v["total_comprehensive_cr"], v["profit_cr"]) == (-189.68, 1494.63, 1684.31)
    assert (v["not_reclassified_cr"], v["reclassified_cr"]) == (-14.5, -175.18)
    assert {i["group"] for i in o["items"]} == {"not_reclassified", "reclassified"} and len(o["items"]) == 5
    # the legacy file's year-ago "Four" members are not the quarter's items
    _, t = xbrl_extras.read(_doc("nse_old_titan_q2fy24.xml"))["oci"]
    assert [i["amount_cr"] for i in t["items"]] == [-17.0, -1.0] and t["values"]["total_comprehensive_owners_cr"] == 902.0
    # a zero owners' part beside a real total is filler (Q3FY24)
    _, q = xbrl_extras.read(_doc("bse_main_ind_as_532811_q3fy24.xml"))["oci"]
    assert q["values"]["total_comprehensive_cr"] == 70.9575 and "total_comprehensive_owners_cr" not in q["values"]


def test_discontinued_operations_are_stored_only_when_there_is_one():
    doc = _doc("nse_irfc_q4fy26_nbfc.xml")
    assert "discontinued" not in xbrl_extras.read(doc), "every fixture files 0: the template's filler"
    for row in doc["facts"]:
        if row[0] == "ProfitLossFromDiscontinuedOperationsAfterTax" and (doc["contexts"][row[1]] or {}).get("m") == 3:
            row[3] = -250000000
    col, d = xbrl_extras.read(doc)["discontinued"]
    assert col == "Q4FY26" and d["values"]["after_tax_cr"] == -25.0 and d["values"]["continuing_profit_cr"] == 1684.31


def test_segment_assets_and_liabilities_by_segment_name():
    col, s = xbrl_extras.read(_doc("nse_old_titan_q2fy24.xml"))["segment_balance"]
    assert col == "Q2FY24" and s["n_segments"] == 5
    jewellery = next(r for r in s["segments"] if r["segment"] == "Jewellery")
    assert (jewellery["assets_cr"], jewellery["liabilities_cr"]) == (21250.0, 13375.0)
    assert s["totals"]["assets_cr"] == 32932.0 and s["totals"]["net_liabilities_cr"] == 20467.0
    _, b = xbrl_extras.read(_doc("nse_hdfcbank_q2fy27_cons.xml"))["segment_balance"]
    assert b["n_segments"] == 7 and b["totals"]["assets_cr"] == 5165841.58
    assert "segment_balance" not in xbrl_extras.read(_doc("nse_irfc_q4fy26_nbfc.xml"))


def test_face_value_and_dividends_never_store_the_filler():
    _, d = xbrl_extras.read(_doc("nse_irfc_q4fy26_nbfc.xml"))["dividends"]
    assert d["values"] == {"face_value": 10}
    assert xbrl_extras.read(_doc("nse_hdfclife_q2fy27_cons.xml")).get("dividends") is None, "FinalDividend and InterimDividend are 0 there"
    doc = _doc("nse_hdfclife_q2fy27_cons.xml")
    for row in doc["facts"]:
        if row[0] == "FinalDividend":
            row[3] = 1500000000
    assert xbrl_extras.read(doc)["dividends"][1]["values"]["final_cr"] == 150.0


def test_annual_kmp_pay_and_contingent_liabilities():
    col, k = xbrl_extras.read(_doc("nse_ar_kanorichem_fy25_standalone.xml"))["kmp_pay"]
    assert col == "FY25" and k["kind"] == "annual" and k["n_people"] == 13 and "totals" not in k, "the 0 totals are filler"
    assert k["people"][0] == {"name": "Rajya Vardhan Kanoria", "designation": "Managing Director", "pay_cr": 3.15}
    _, shivam = xbrl_extras.read(_doc("nse_ar_shivamauto_fy25_standalone.xml"))["kmp_pay"]
    assert shivam["people"][0]["pay_cr"] == 2.2567
    _, c = xbrl_extras.read(_doc("nse_ar_kanorichem_fy25_consolidated.xml"))["contingent_liabilities"]
    assert c["has_contingent"] is True and "total_cr" not in c
    assert [(r["class"], r["amount_cr"]) for r in c["classes"]] == [("ContingentLiabilityOnDisputedIncomeTax", 5.837), ("TaxContingentLiability", 0.982)]
    _, none = xbrl_extras.read(_doc("nse_ar_shivamauto_fy25_standalone.xml"))["contingent_liabilities"]
    assert none["has_contingent"] is False and none["classes"] == []
    assert not set(SECOND[:4]) & set(xbrl_extras.read(_doc("nse_ar_kanorichem_fy25_standalone.xml")))
    assert not set(SECOND[4:]) & set(xbrl_extras.read(_doc("nse_irfc_q4fy26_nbfc.xml")))


def test_how_many_fixture_filings_fill_each_second_group_key():
    got = {k: 0 for k in SECOND}
    for path in sorted(FIXTURES.glob("*.xml")):
        try:
            doc = _doc(path.name)
        except Exception:      # noqa: BLE001 - an event file or another is no results or annual file
            continue
        for k in (xbrl_extras.read(doc) if doc else {}):
            if k in got:
                got[k] += 1
    assert got == {"oci": 9, "discontinued": 0, "segment_balance": 7, "dividends": 11, "kmp_pay": 2, "contingent_liabilities": 3}


def test_the_second_group_is_remembered_replaced_capped_and_backfilled(settings):
    d = {}
    xbrl_extras.remember(d, _doc("nse_old_titan_q2fy24.xml"), "n1", AS_OF, AT)
    xbrl_extras.remember(d, _doc("nse_ar_kanorichem_fy25_standalone.xml"), "n2", AS_OF, AT)
    assert {"oci", "segment_balance", "dividends", "kmp_pay", "contingent_liabilities"} <= set(d) and "discontinued" not in d
    assert d["kmp_pay"][0]["lab"]["by"] == "file" and d["oci"][0]["lab"]["rules"] == "xbrl_extras"
    xbrl_extras.remember(d, _doc("nse_old_titan_q2fy24.xml"), "n3", AS_OF, AT)
    assert len(d["oci"]) == 1 and d["oci"][0]["source_news_id"] == "n3", "a revised file takes the place of the same period and basis"
    slipped = {"scale_held": [{"period": "Q2FY24"}]}
    xbrl_extras.remember(slipped, _doc("nse_old_titan_q2fy24.xml"), "n1", AS_OF, AT)
    assert not set(SECOND) & set(slipped)
    full = {"oci": [{"period": f"Q{q}FY{y}", "basis": "CONSOLIDATED", "kind": "results"} for y in range(10, 26) for q in (1, 2, 3, 4)]}
    xbrl_extras.remember(full, _doc("nse_irfc_q4fy26_nbfc.xml"), "n1", AS_OF, AT)
    assert len(full["oci"]) == xbrl_extras.MAX_ENTRIES["oci"] and full["oci"][-1]["period"] == "Q4FY26"
    from bse_intel.sinks.local import LocalSink
    sink = LocalSink(settings)
    xbrl_facts.save(sink, "1", "Q2FY24", "CONSOLIDATED", _doc("nse_old_titan_q2fy24.xml"))
    xbrl_facts.save_annual(sink, "1", "FY25", "STANDALONE", _doc("nse_ar_kanorichem_fy25_standalone.xml"))
    cf = sv.CompanyFacts(sink.list_objects(f"{xbrl_facts.PREFIX}1/"), sink.get_object)
    filled = {}
    statements_backfill.fill_extras(cf, filled, AT)
    assert {"oci", "segment_balance", "kmp_pay", "contingent_liabilities", "dividends"} <= set(filled)


def test_a_concurrent_writer_keeps_the_second_group_of_both():
    mine = {"oci": [{"period": "Q2FY27", "basis": "CONSOLIDATED", "kind": "results"}]}
    fresh = {"oci": [{"period": "Q1FY27", "basis": "CONSOLIDATED", "kind": "results"}]}
    keep_concurrent_writes(mine, {"oci": []}, fresh)
    assert [e["period"] for e in mine["oci"]] == ["Q1FY27", "Q2FY27"]


def test_a_half_year_profit_is_not_an_oci_entry_and_one_failing_reader_keeps_the_others(monkeypatch):
    """Review of the second group (30 Oct 2026): Vesuvius's half-yearly file has no OCI figure, only its 6-month profit, which was
    stored as Q3FY26's OCI entry; and one reader raising lost every key of the file."""
    doc = xbrl_facts.parse_facts((FIXTURES / "nse_vesuvius_halfyearly_dec_h2fy26.xml").read_bytes(), "520113", "u")
    assert xbrl_extras.OCI not in xbrl_extras.read(doc)
    hdfc = next(xbrl_facts.parse_facts(p.read_bytes(), "x", "u") for p in sorted(FIXTURES.glob("*.xml"))
                if xbrl_extras.SEGMENT_BALANCE in xbrl_extras.read(xbrl_facts.parse_facts(p.read_bytes(), "x", "u")))
    monkeypatch.setattr(xbrl_extras, "_oci", lambda *a: 1 / 0)
    assert xbrl_extras.SEGMENT_BALANCE in xbrl_extras.read(hdfc)
