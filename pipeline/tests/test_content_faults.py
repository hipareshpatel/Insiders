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
