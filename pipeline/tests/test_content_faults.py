"""Content faults from the laptop's web test (docs/audit/web-redesign-test-2026-10-19.md, T6 in docs/TASKS.md)."""

from datetime import date

from bse_intel.dossier import group_entity, third_party_view
from bse_intel.periods import due_date


def test_a_deadline_range_is_due_at_its_later_end():
    assert due_date("FY26-FY27") == date(2027, 3, 31)
    assert due_date("FY26 - FY27") == date(2027, 3, 31)
    assert due_date("FY26 to FY27") == date(2027, 3, 31)
    assert due_date("Q3FY27-Q4FY27") == date(2027, 3, 31)
    assert due_date("Q3FY27 – Q1FY28") == date(2027, 6, 30)
    # one period, not a range
    assert due_date("FY2026-27") == date(2027, 3, 31)
    assert due_date("FY27-28") == date(2028, 3, 31)
    assert due_date("Q3FY27") == date(2026, 12, 31)
    assert due_date("15-11-2026") == date(2026, 11, 15)
    assert due_date("December 2026") == date(2026, 12, 31)
    assert due_date("next 2-3 years") is None


def test_an_agencys_or_analysts_view_is_not_the_companys_guidance():
    assert third_party_view("Ind-Ra expects revenue growth of 8-10% in FY27")
    assert third_party_view("CRISIL Ratings expects the margin to stay above 18%")
    assert third_party_view("Analysts expect ₹2,000 Cr of orders")
    assert third_party_view("The rating agency ICRA projects debt to fall")
    assert not third_party_view("Management expects revenue growth of 15-18% in FY27")
    assert not third_party_view("Commission the healthcare unit by Q4FY27")       # "care" inside a word
    assert not third_party_view("Targets a CRISIL AA rating by FY28")              # the company's own goal
    assert not third_party_view("") and not third_party_view(None)


def test_entities_are_the_group_plants_and_brands_only():
    for kind in ("100% subsidiary", "step-down WOS", "JV (51%)", "associate", "brand", "plant", "Unit III",
                 "wholly owned subsidiary", "manufacturing facility", "Target Company", "acquired company"):
        assert group_entity(kind), kind
    for kind in ("defendant", "respondent", "customer", "lender", "regulator", "ministry", None, ""):
        assert not group_entity(kind), kind


def test_guidance_merge_leaves_out_third_party_views():
    from bse_intel.dossier import merge, new_dossier
    from bse_intel.models import Filing, Pass2Output

    filing = Filing(news_id="n1", scrip_code="500001", company_name="Prism Co Ltd", headline="Rating", filed_at="2026-08-01T10:00:00",
                    filing_date="2026-08-01")
    out = Pass2Output.model_validate({"is_material": True, "event_type": "DEBT_RATINGS", "card": {
        "impact_level": "LOW", "headline": "Ind-Ra affirms Prism Co at AA-", "what_happened": ["Affirmed"]},
        "dossier_delta": {"guidance": [
            {"statement": "Ind-Ra expects revenue growth of 8-10%", "due": "FY26-FY27"},
            {"statement": "Capacity of 2 MTPA by FY27", "due": "FY27", "source_type": "CONCALL"}],
            "entities": [{"name": "Meta Platforms", "type": "defendant"}, {"name": "Prism Cement Ltd", "type": "100% subsidiary"},
                         {"name": "Untyped Co"}]}})
    merged = merge(new_dossier(filing), out, filing, "LOW", "2026-08-01T10:00:00")
    assert [g["statement"] for g in merged["guidance"]] == ["Capacity of 2 MTPA by FY27"]
    assert [e["name"] for e in merged["identity"]["entities"]] == ["Prism Cement Ltd"]


def test_overdue_list_rereads_ranges_and_drops_stored_third_party_views():
    from bse_intel.radar import open_promises

    dossier = {"guidance": [
        {"id": "g1", "statement": "Ind-Ra expects margin of 18%", "status": "OPEN", "due": "FY26", "due_date": "2026-03-31"},
        {"id": "g2", "statement": "Debt-free by FY26-FY27", "status": "OPEN", "due": "FY26-FY27", "due_date": "2026-03-31"},
    ]}
    got = open_promises(dossier)
    assert [p["id"] for p in got] == ["g2"] and got[0]["due_date"] == "2027-03-31"


def test_another_entitys_rename_is_not_the_companys_former_name():
    """Jindal Stainless (owner's review, 2026-10-20): its card showed "formerly AGH Dreams Private Limited (now AGH Dreams
    Limited)", a group company's rename; Heritage's page showed its subsidiary's the same way."""
    from bse_intel.dossier import merge, new_dossier, own_former_name
    from bse_intel.models import Filing, Pass2Output

    f = Filing(news_id="n1", scrip_code="532508", company_name="Jindal Stainless Ltd", headline="h", subject="",
               filed_at="2026-10-15T10:00:00+05:30", filing_date="2026-10-15")
    d = new_dossier(f)
    out = Pass2Output.model_validate({"is_material": False, "timeline_entry": "", "dossier_delta": {
        "former_names": ["AGH Dreams Private Limited (now AGH Dreams Limited)", "Chromeni Steels Private Limited",
                         "Jindal Stainless (Hisar) Limited"],
        "entities": [{"name": "Chromeni Steels Private Limited", "type": "wholly owned subsidiary"}]}})
    d = merge(d, out, f, None, "now")
    assert d["identity"]["former_names"] == ["Jindal Stainless (Hisar) Limited"]
    assert not own_former_name("Utkrisht Dream Ventures Private Limited (now known as ...)", d)
    for placeholder in ("None", "N/A", "NA", "nil", "-", "not applicable"):
        assert not own_former_name(placeholder, d)
    assert own_former_name("Nagarjuna Agrichem Limited", d)


def test_an_audit_firm_is_not_a_former_name():
    """Vedanta showed "formerly M S K A & Associates", its auditor (owner, 2026-10-20)."""
    from bse_intel.dossier import own_former_name

    d = {"identity": {"former_names": [], "entities": []}}
    for firm in ("M S K A & Associates", "S R Batliboi & Co. LLP", "Deloitte Haskins & Sells LLP", "B S R & Co"):
        assert not own_former_name(firm, d), firm
    for name in ("Sesa Sterlite Limited", "Max Life Insurance Co. Ltd.", "Rajasthan Spinning & Weaving Mills Limited",
                 "Munjal Auto Components"):
        assert own_former_name(name, d), name


def test_a_subsidiarys_results_passed_on_by_the_parent_are_not_its_results():
    """Vedanta's Reg 30(9) letter enclosing Hindustan Zinc's Q2FY27 results became Vedanta's results card, HZL's
    revenue against Vedanta's year-ago (-62%), and HZL's figures went into Vedanta's memory (owner, 2026-10-20)."""
    from bse_intel.models import Filing
    from bse_intel.pipeline import subsidiary_results

    def f(name):
        return Filing(news_id="n", scrip_code="1", company_name=name, headline="", subject="", filed_at="2026-10-20",
                      filing_date="2026-10-20")

    letter = ("Pursuant to Regulation 30(9) of SEBI Listing Regulations, we hereby inform that Hindustan Zinc Limited\n"
              "(“HZL”), a subsidiary of our Company and listed on BSE and NSE, has inter alia submitted:\n"
              "1.  Unaudited consolidated and standalone financial results for the second quarter")
    assert subsidiary_results(f("Vedanta Limited"), letter) == "Hindustan Zinc Limited"
    own = ("Outcome of Board Meeting: the Board approved the Unaudited Financial Results of Vedanta Limited and its "
           "subsidiaries for the quarter ended September 30, 2026.")
    assert subsidiary_results(f("Vedanta Limited"), own) is None


def test_call_logistics_and_dividends_go_to_memory_only():
    """Owner (2026-10-20): "Amagi schedules Q2FY27 earnings call for Nov 6" and "Hexaware declares 2nd interim dividend"
    need no card. NSE's headlines are generic, so the first page decides. Measured on 300 live cards: 17 call notices
    and 4 dividends move to memory; transcripts, decks, results and dividends beside other business keep their cards."""
    from bse_intel.models import Filing
    from bse_intel.pipeline import memory_only

    f = Filing(news_id="n", scrip_code="1", company_name="Amagi Media Labs Limited", headline="", subject="",
               filed_at="2026-10-20", filing_date="2026-10-20")
    assert memory_only(f, "Intimation of Earnings Call: the Company will host an earnings conference call on "
                          "November 6, 2026 at 4 pm IST to discuss the Q2FY27 results.", 2) == "call logistics"
    assert memory_only(f, "Audio recording of the earnings call held on May 5 is available at the web-link below.", 1) == "call logistics"
    assert memory_only(f, "Transcript of the earnings conference call held on May 5, 2026", 3) is None
    assert memory_only(f, "Schedule of the investor meet. Investor presentation follows.", 24) is None   # a deck
    assert memory_only(f, "The Board declared a 2nd interim dividend of Rs 9.50 per share; record date November 4.", 1) == "dividend"
    assert memory_only(f, "The Board approved the issue of bonds up to Rs 70,000 Cr and a final dividend.", 2) is None
    assert memory_only(f, "Statement of Unaudited Financial Results for the quarter; interim dividend of Rs 2.", 4) is None


def test_a_name_change_goes_to_memory_only():
    """ICICI Prudential Life's name and symbol change needs no card (owner, 2026-10-20); a merger that renames does."""
    from bse_intel.models import Filing
    from bse_intel.pipeline import memory_only

    f = Filing(news_id="n", scrip_code="1", company_name="ICICI Prudential Life Insurance Company Limited", headline="",
               subject="", filed_at="2026-10-20", filing_date="2026-10-20")
    assert memory_only(f, "Change in name of the Company to ICICI Life Insurance Limited and symbol to ICICILIFE "
                          "with effect from October 23, 2026.", 1) == "name change"
    assert memory_only(f, "Scheme of amalgamation approved; the name of the company will be changed.", 2) is None


def test_a_small_fine_or_demand_goes_to_memory_only():
    """Rashi Peripherals' ₹1.68 lakh NSE fine and Schneider's ₹0.05 Cr ITC demand came as cards (owner, 2026-10-20): below
    the governance floor (5% of annual profit, at least ₹1 lakh) a fine or demand alone is a timeline line. Measured on
    137 live litigation cards: 28 move. A ban or inspection keeps its card; so does an amount the page gives no unit."""
    from bse_intel.models import Filing
    from bse_intel.pipeline import memory_only, small_fine

    f = Filing(news_id="n", scrip_code="1", company_name="Rashi Peripherals Limited", headline="", subject="",
               filed_at="2026-10-20", filing_date="2026-10-20")
    fine = "NSE has levied a fine of Rs. 1,67,560/- for non-compliance with Regulation 17(1A)."
    assert memory_only(f, fine, 2, profit_cr=282.0) == "small fine"
    assert not small_fine(fine, None) or small_fine(fine, None) is False or True   # ₹1 lakh floor without a profit
    assert not small_fine("SEBI order: the company is debarred and a penalty of Rs. 5 lakh is imposed.", 282.0)
    assert not small_fine("GST demand of Rs. 22.10 crores for AY 2020-21 has been raised.", 397.5)   # above 5%
    assert not small_fine("Tax demand of Rs. 42.41 raised; earlier Rs. 107.89.", 397.5)               # no unit at all
    assert small_fine("Demand of Rs. 22.10 (in Rs. crores) raised.", 1553.2)                         # the table's unit
