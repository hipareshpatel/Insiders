"""Direction claims checked against the filing's XBRL (directions.py), on round 4's WRONG cards (2026-10-19)."""

from __future__ import annotations

from types import SimpleNamespace

from bse_intel import directions
from bse_intel.models import FinancialMetric, Pass2Output


def _tagged(**metrics):
    rows = []
    for name, (value, yoy, qoq) in metrics.items():
        rows.append(FinancialMetric(metric=name, period="Q1FY27", value=value, yoy_pct=yoy, qoq_pct=qoq))
    return SimpleNamespace(kind="RESULTS", period="Q1FY27", metrics=rows)


def _out(headline, takeaway="", facts=("Results",), why=(), timeline=""):
    return Pass2Output.model_validate({
        "is_material": True, "event_type": "RESULTS", "timeline_entry": timeline,
        "card": {"impact_level": "MODERATE", "headline": headline, "takeaway": takeaway,
                 "what_happened": list(facts), "why_it_matters": [{"text": w} for w in why]}})


def test_lower_tax_claimed_when_tax_rose_is_cut():
    # RSWM Q1FY27: total tax 2.66 -> 7.66 Cr, PAT up because PBT rose
    out = _out("RSWM Q1 PAT jumps 135% to ₹19.65 Cr on lower tax",
               takeaway="Profit more than doubled, helped by a deferred tax credit of ₹7.66 Cr.",
               timeline="Q1FY27 PAT ₹19.65 Cr (+135% YoY) on lower tax")
    tagged = _tagged(tax_expense=(7.66, 188.0, None), deferred_tax=(7.66, None, None))
    notes = directions.guard(out, tagged)
    assert out.card.headline == "RSWM Q1 PAT jumps 135% to ₹19.65 Cr"
    assert out.card.takeaway == "Profit more than doubled."
    assert out.timeline_entry == "Q1FY27 PAT ₹19.65 Cr (+135% YoY)"
    assert len(notes) == 3


def test_inventory_and_eps_directions():
    # Nestle Q1FY27: change in inventories +94.93 Cr (stock fell), EPS +48% YoY
    out = _out("Nestle India Q1 PAT up 49%", facts=["Inventory build-up of ₹94.93 Cr signals cautious demand.",
                                                    "Revenue rose 25% to ₹6,180 Cr."],
               why=["EPS declined to ₹4.97 due to the bonus issue."])
    tagged = _tagged(inventory_change=(94.93, None, None), eps=(4.97, 48.4, None))
    directions.guard(out, tagged)
    assert [f.text for f in out.card.what_happened] == ["Revenue rose 25% to ₹6,180 Cr."]
    assert out.card.why_it_matters == []


def test_a_true_claim_stands_and_qoq_is_read_as_qoq():
    out = _out("PAT up 20% on lower tax", takeaway="Credit costs were lower sequentially; inventory drawdown freed cash.")
    tagged = _tagged(tax_expense=(10.0, -12.0, 5.0), provisions=(50.0, 53.0, -8.0), inventory_change=(12.0, None, None))
    assert directions.guard(out, tagged) == []
    assert out.card.headline == "PAT up 20% on lower tax"
    # "lower credit costs" against the year-ago quarter, when provisions rose 53% (RBL Q2FY27): cut
    out = _out("RBL Q2 PAT up 170%, driven by lower credit costs and higher NII")
    directions.guard(out, _tagged(provisions=(771.0, 53.3, 4.0)))
    assert out.card.headline == "RBL Q2 PAT up 170%"


def test_nothing_without_the_files_figures():
    out = _out("PAT up 20% on lower tax")
    assert directions.guard(out, None) == [] and out.card.headline == "PAT up 20% on lower tax"
    assert directions.guard(out, SimpleNamespace(kind="SHAREHOLDING", period="Q1FY27", metrics=[])) == []


def test_a_tax_rate_or_slower_growth_is_not_a_direction_of_the_line():
    """A lower effective tax rate is often true while tax expense rises with profit, and "EPS growth moderated" says
    growth slowed, not that EPS fell: neither is cut."""
    tagged = _tagged(tax_expense=(120.0, 10.0, 5.0), eps=(12.0, 8.0, 2.0))
    figures = directions._current(tagged)
    for text in ("PAT rose 30% on a lower effective tax rate.", "Net profit grew, helped by a lower tax rate.",
                 "EPS growth moderated to 8% from 25%.", "Lower EPS growth than last year."):
        assert directions.contradicted(text, figures) == [], text
    assert [n for n, _ in directions.contradicted("PAT rose on lower tax.", figures)] == ["lower tax"]
    assert [n for n, _ in directions.contradicted("EPS declined 4%.", figures)] == ["EPS fell"]


def test_re_run_misses_reversal_wording_and_notable_change_names():
    """Round 4's re-run: RSWM's "reversal of deferred tax of ₹7.66 Cr" (a charge), and an inventory change carried
    in a notable change named "inventory_change" with "drawdown" when stock was built up."""
    from bse_intel.models import NotableChange

    out = _out("RSWM Q1 PAT up 135%", takeaway="PAT jumped on a reversal of deferred tax of ₹7.66 Cr.")
    out.card.notable_changes = [NotableChange(metric="inventory_change", previous="₹4.1 Cr", current="₹(31.68) Cr",
                                              change="drawdown improving working capital"),
                                NotableChange(metric="revenue", previous="₹1,170 Cr", current="₹1,161 Cr", change="-0.7% YoY")]
    directions.guard(out, _tagged(deferred_tax=(7.66, None, None), inventory_change=(-31.68, None, None)))
    assert out.card.takeaway == "PAT jumped." and [c.metric for c in out.card.notable_changes] == ["revenue"]
