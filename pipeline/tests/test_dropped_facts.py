"""A fact whose quote is not the filing's own words is kept when its figures, dates, ratings - or with none, its
names - are printed in the filing (audit round 2: 50 of the 60 facts the quote check dropped were true,
dropped_facts.md). Each test is a round-2 card."""
from __future__ import annotations

from bse_intel import gate
from bse_intel.models import Pass2Output
from bse_intel.pipeline import check_quotes


def _check(text: str, *facts: tuple[str, str]):
    out = Pass2Output.model_validate({
        "is_material": True, "event_type": "OTHER", "timeline_entry": "x",
        "card": {"impact_level": "LOW", "headline": "Company files an update with the exchange",
                 "what_happened": [{"text": "Filing received", "quote": "The company has filed"},
                                   *({"text": t, "quote": q} for t, q in facts)]}})
    _, _, dropped, _ = check_quotes(out, "The company has filed this disclosure. " + text)
    return [f.text for f in out.card.what_happened][1:], dropped


def test_kanoria_a_stake_from_an_annexure_table_is_kept():
    """ae81308e: "Post-disposal stake falls to 86.21%" quoted from cells of the Reg 30 annexure."""
    kept, _ = _check("Shareholding after disposal | 86.21% | To be entered | By April 2025",
                     ("Post-disposal stake falls to 86.21%", "stake after the disposal will be 86.21%"))
    assert kept == ["Post-disposal stake falls to 86.21%"]


def test_a_gst_order_with_small_amounts_is_kept():
    """055a7fef: a GST demand of ₹6.98 Cr and a penalty of ₹2.72 Cr; the order prints rupees in full."""
    kept, _ = _check("Demand of tax Rs. 6,98,12,345/- and penalty of Rs. 2,72,00,000/- under section 74",
                     ("The order confirms a GST demand of ₹6.98 Cr and a penalty of ₹2.72 Cr", "a demand of Rs 6.98 crore"))
    assert len(kept) == 1


def test_csb_a_labour_code_impact_in_lakh_is_kept_at_the_declared_unit():
    """9531fc86: ₹5.22 Cr is the filing's "522 Lakhs"."""
    kept, _ = _check("The Bank has recognised incremental impact of Rs 522 Lakhs on account of the labour codes.",
                     ("Bank recognised ₹5.22 Cr incremental labour-code impact", "impact of ₹5.22 crore"))
    assert len(kept) == 1


def test_heritage_a_figure_at_the_wrong_unit_is_still_dropped():
    """daee44c8: the (4.77) is renewable energy in INR million, not a ₹4.77 Cr feed loss."""
    kept, dropped = _check("(Rs. in million) Segment results: Feed 12.30 Renewable energy (4.77)",
                           ("Feed segment reported a loss of ₹4.77 Cr in Q3FY25", "Feed segment loss of 4.77"))
    assert kept == [] and "not found: 4.77" in dropped[0]


def test_csb_a_nim_from_another_quarter_is_still_dropped():
    """33717cd4: "NIM 3.86% vs 3.75%" is in neither the PDF nor the XBRL (3.86% was Q3FY26's)."""
    kept, dropped = _check("Net interest margin 3.62% for the quarter against 3.71%",
                           ("Net interest margin was 3.86% in Q1FY27, compared to 3.75% a year ago", "NIM of 3.86%"))
    assert kept == [] and 'quoted: "NIM of 3.86%"' in dropped[0]


def test_a_rating_and_a_date_written_another_way_are_kept():
    """af518a6a: "Crisil AA-/Stable"; 8811eec0: "April 2, 2025" where the notice prints "2nd April, 2025"."""
    kept, _ = _check("Long Term Rating CRISIL AA-/Stable (Reaffirmed). Remote e-voting commences on 2nd April, 2025 "
                     "(9:00 a.m. IST).",
                     ("Long-term rating is Crisil AA-/Stable", "CRISIL AA-/Stable (Reaffirmed) ..."),
                     ("Voting by electronic mode will commence on April 2, 2025", "e-voting will commence on April 2, 2025"))
    assert len(kept) == 2
    _, dropped = _check("Long Term Rating CRISIL A+/Stable", ("Long-term rating is Crisil AA-/Stable", "rated AA-"))
    assert "CRISIL AA-" in dropped[0]


def test_an_appointment_with_no_figure_is_kept_by_its_names():
    """6b244d8e: no figure, date or rating to check; the appointee's name is in the filing."""
    kept, _ = _check("The members approved the appointment of Dr. Muddana Sambasiva Rao as an Independent Director.",
                     ("Shareholders appointed Dr. Muddana Sambasiva Rao as Director", "appointed Dr. M. Sambasiva Rao"))
    assert len(kept) == 1
    kept, _ = _check("The members approved the appointment of Mr. Ravi Kumar as an Independent Director.",
                     ("Shareholders appointed Dr. Muddana Sambasiva Rao as Director", "appointed Dr. M. Sambasiva Rao"))
    assert kept == []


def test_a_word_broken_at_a_line_end_and_ligatures_still_match_the_quote():
    """c6b7260b ("Long- | term"), d4cbdf9f ("EﬀecƟve"), cbd78d5c (a sentence across a page break)."""
    assert gate.quote_found("the Long-term rating of the Company", "ICRA placed on watch the Long-\nterm rating of the Company")
    assert gate.quote_found("Effective date of appointment", "EﬀecƟve date of appointment")
    assert gate.quote_found("a growth of 9.3% in turnover", "registered a growth of 9.3% in\n--- Page 2 of 5 ---\nturnover")
