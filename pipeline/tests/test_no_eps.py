"""Owner rule 26 Oct 2026: no EPS on a card or a stock page. Memory keeps every EPS figure; the results table, the
model's input and the card text do not carry it, and a card line that states it is dropped (dividends stay)."""

from bse_intel import no_eps
from bse_intel.dossier import results_snapshot, view_as_of
from bse_intel.models import Card, Pass2Output
from bse_intel.xbrl import FinancialMetric, XbrlResult


def _m(metric, period, value, news="n2", unit="INR_CR"):
    return {"metric": metric, "period": period, "value": value, "unit": unit, "as_of": "2026-10-15", "source_news_id": news,
            "sources": [{"news_id": news, "as_of": "2026-10-15", "value": value, "unit": unit, "basis": "CONSOLIDATED"}]}


def _dossier():
    rows = []
    for k, (a, b) in {"revenue": (1100.0, 1000.0), "ebitda": (150.0, 160.0), "pat": (70.0, 85.0), "eps": (7.0, 8.5),
                      "pbt": (90.0, 110.0)}.items():
        rows += [_m(k, "Q2FY27", a, unit="INR" if k == "eps" else "INR_CR"), _m(k, "Q2FY26", b, "n1", "INR" if k == "eps" else "INR_CR")]
    return {"financial_metrics": rows}


def test_the_results_table_has_no_eps_line_but_memory_keeps_it():
    snap = results_snapshot(_dossier(), "n2")
    assert snap is not None and "eps" not in snap and "eps_hidden" not in snap
    assert all(line["key"] != "eps" for line in snap["lines"])
    assert any(m["metric"] == "eps" for m in _dossier()["financial_metrics"])
    kept = results_snapshot(_dossier(), "n2", with_eps=True)   # the memory-side logic still works (tests only)
    assert kept["eps"]["value"] == 7.0


def test_the_models_input_has_no_eps():
    table = XbrlResult("RESULTS", "CONSOLIDATED", "Q2FY27", [
        FinancialMetric(metric="eps", period="Q2FY27", value=7.0, unit="INR"),
        FinancialMetric(metric="pat", period="Q2FY27", value=70.0)]).table()
    assert "pat Q2FY27" in table and "eps" not in table and "share" not in table
    assert "eps" not in str(view_as_of(_dossier(), "2027-01-01")) and "revenue" in str(view_as_of(_dossier(), "2027-01-01"))


def _out(**card):
    base = dict(impact_level="HIGH", headline="Acme Q2FY27: revenue ₹1,100 Cr", what_happened=[{"text": "Revenue ₹1,100 Cr.", "quote": "1,100"}])
    return Pass2Output(is_material=True, card=Card(**{**base, **card}), timeline_entry="Q2 results")


def test_a_card_line_that_states_eps_is_dropped_and_a_dividend_per_share_stays():
    out = _out(what_happened=[{"text": "Revenue ₹1,100 Cr.", "quote": "1,100"}, {"text": "Basic EPS ₹7.00 a share.", "quote": "7.00"},
                              {"text": "Dividend of ₹2 per share declared.", "quote": "2"}],
               why_it_matters=[{"text": "Earnings per share fell 18% YoY.", "basis": "FILING"}, {"text": "Margin held.", "basis": "FILING"}],
               key_numbers=[{"label": "EPS", "value": "₹7.00 per share", "change": "-18% YoY"},
                            {"label": "Dividend", "value": "₹2 per share"}, {"label": "PAT", "value": "₹70 Cr"}])
    dropped = no_eps.drop_eps(out)
    card = out.card
    assert [f.text for f in card.what_happened] == ["Revenue ₹1,100 Cr.", "Dividend of ₹2 per share declared."]
    assert [i.text for i in card.why_it_matters] == ["Margin held."]
    assert [k.label for k in card.key_numbers] == ["Dividend", "PAT"]
    assert len(dropped) == 4   # the takeaway, copied from the dropped insight, is rebuilt too


def test_an_eps_clause_is_cut_from_a_headline_and_a_card_with_no_eps_is_untouched():
    out = _out(headline="Acme Q2FY27: revenue ₹1,100 Cr, EPS ₹7.00 (-18% YoY)")
    assert no_eps.drop_eps(out) == ["headline: EPS clause"]
    assert out.card.headline == "Acme Q2FY27: revenue ₹1,100 Cr"
    assert no_eps.drop_eps(_out()) == []


def test_a_line_with_profit_and_eps_keeps_the_profit():
    from bse_intel.no_eps import _scrub
    assert _scrub("Net profit ₹50.2 Cr, up 12% YoY, EPS ₹2.10") == "Net profit ₹50.2 Cr, up 12% YoY"
    assert _scrub("EPS ₹2.10, up 12%") == "EPS ₹2.10, up 12%"     # about nothing else: the caller drops the line


def test_a_card_line_with_profit_and_eps_loses_only_the_eps():
    out = _out(what_happened=[{"text": "Net profit ₹70 Cr, down 18% YoY, EPS ₹7.00", "quote": "70"}])
    no_eps.drop_eps(out)
    assert [f.text for f in out.card.what_happened] == ["Net profit ₹70 Cr, down 18% YoY"]


def test_a_headline_takeaway_and_timeline_that_are_about_eps_are_rebuilt_without_it():
    out = _out(headline="Acme Q1FY27 EPS rises 12% to ₹5.2", takeaway="EPS ₹5.2 up 12%", core_catalyst="Higher EPS on volume",
               what_happened=[{"text": "Revenue ₹1,100 Cr.", "quote": "1,100"}],
               why_it_matters=[{"text": "Margin held.", "basis": "FILING"}])
    out.timeline_entry = "Q1 EPS up 12%"
    no_eps.drop_eps(out)
    card = out.card
    assert card.headline == "Acme Q1FY27: Revenue ₹1,100 Cr"
    assert card.takeaway == "Margin held." and card.core_catalyst == "Margin held."
    assert not no_eps.mentions_eps(out.timeline_entry) and out.timeline_entry == card.headline


def test_with_nothing_else_to_say_the_headline_is_the_company_and_period_and_takeaway_may_be_empty():
    out = _out(headline="Acme Q1FY27 EPS rises 12% to ₹5.2", takeaway="EPS ₹5.2 up 12%", core_catalyst="EPS up",
               what_happened=[{"text": "EPS rose 12% to ₹5.2.", "quote": "5.2"}])
    no_eps.drop_eps(out)
    card = out.card
    assert card.headline == "Acme Q1FY27: results"
    assert len(card.what_happened) == 1 and not no_eps.mentions_eps(card.what_happened[0].text)
    assert card.takeaway == "Acme Q1FY27: results" or card.takeaway == ""
    assert not no_eps.mentions_eps(card.takeaway) and not no_eps.mentions_eps(card.core_catalyst or "")


def test_the_what_happened_fallback_never_keeps_an_eps_line():
    out = _out(what_happened=[{"text": "Basic EPS ₹7.00 a share.", "quote": "7.00"}, {"text": "Diluted EPS ₹6.90.", "quote": "6.90"}])
    no_eps.drop_eps(out)
    assert [f.text for f in out.card.what_happened] == ["Acme Q2FY27: revenue ₹1,100 Cr"]


def test_the_eps_clause_stops_at_and_or_another_metric_and_takes_a_bare_change_with_it():
    from bse_intel.no_eps import _scrub
    assert _scrub("Revenue ₹10 Cr, EPS ₹2.10 (+1.5% YoY) and PAT ₹5 Cr") == "Revenue ₹10 Cr and PAT ₹5 Cr"
    assert _scrub("Revenue ₹10 Cr, EPS ₹2.1, up 12%") == "Revenue ₹10 Cr"
    assert _scrub("Revenue ₹10 Cr, EPS ₹2.1, PAT ₹5 Cr") == "Revenue ₹10 Cr, PAT ₹5 Cr"
    assert _scrub("Revenue ₹1,000 Cr, EPS ₹2.1; margin 12%") == "Revenue ₹1,000 Cr; margin 12%"


def test_only_the_text_of_a_line_is_judged_not_its_quote():
    out = _out(what_happened=[{"text": "PAT ₹46 Cr.", "quote": "PAT 46 EPS 5.2"}],
               why_it_matters=[{"text": "PAT ₹46 Cr is steady.", "quote": "PAT 46 EPS 5.2", "basis": "FILING"}])
    assert no_eps.drop_eps(out) == []
    assert out.card.what_happened[0].quote == "PAT 46 EPS 5.2" and len(out.card.why_it_matters) == 1


def test_more_ways_to_write_eps_and_the_per_share_figures_that_are_not():
    for t in ["E.P.S. ₹5", "earnings of ₹5 a share", "earnings/share ₹5", "PAT per share ₹3", "diluted earnings per ordinary share ₹4",
              "Earnings per equity share 3"]:
        assert no_eps.mentions_eps(t), t
    for t in ["Dividend ₹5 per share", "Book value per share ₹40", "NAV per share ₹12", "Issue price ₹10 per share", "Net profit ₹5 Cr"]:
        assert not no_eps.mentions_eps(t), t
