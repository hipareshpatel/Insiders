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
    no_eps.drop_eps(out)
    card = out.card
    assert [f.text for f in card.what_happened] == ["Revenue ₹1,100 Cr.", "Dividend of ₹2 per share declared."]
    assert [i.text for i in card.why_it_matters] == ["Margin held."]
    assert [k.label for k in card.key_numbers] == ["Dividend", "PAT"]


CUTS = [   # text, what cut_text gives (None: the item is dropped)
    ("Revenue ₹100 Cr, EPS ₹5 and net interest margin 3%", None),
    ("EPS ₹5, NIM 3%", None),
    ("Revenue ₹10 Cr (EPS ₹5)", None),
    ("Revenue ₹1,200 Cr, up 10%, EPS ₹5.2 (+8% YoY)", "Revenue ₹1,200 Cr, up 10%"),
    ("Revenue ₹10 Cr — basic and diluted EPS ₹2.1 vs ₹1.9 a year ago", "Revenue ₹10 Cr"),
    ("Revenue ₹10 Cr | Diluted EPS ₹3", "Revenue ₹10 Cr"),
    ("Revenue ₹10 Cr, earnings per share ₹५.२", "Revenue ₹10 Cr"),
    ("Revenue ₹5 Cr; profit after tax per share ₹3", "Revenue ₹5 Cr"),
    ("Revenue ₹5 Cr, PAT/share ₹3", "Revenue ₹5 Cr"),
    ("Revenue ₹5 Cr, earnings of ₹ 5 / share", "Revenue ₹5 Cr"),
    ("Revenue ₹5 Cr, earnings per ₹10 share 4", "Revenue ₹5 Cr"),
    ("Net profit ₹5 Cr, Earnings per equity share of ₹10 each: 4.5", "Net profit ₹5 Cr"),
    ("Dividend ₹2 per share", "Dividend ₹2 per share"),
    ("Book value per share ₹40", "Book value per share ₹40"),
    ("Revenue ₹5 Cr, NAV per share ₹12", "Revenue ₹5 Cr, NAV per share ₹12"),
    ("earnings ₹5 per share", None),
    ("Revenue ₹5 Cr, earning ₹5/share", "Revenue ₹5 Cr"),
    ("Acme: dividend ₹2 per share and EPS ₹7", None),
    ("Revenue ₹5 Cr, EPS ₹2.10, up 12%", None),
    ("Revenue ₹5 Cr, profit/share ₹4", "Revenue ₹5 Cr"),
    ("Revenue ₹5 Cr, EPS 2.1 (vs 1.9 a year ago)", "Revenue ₹5 Cr"),
    ("Revenue ₹10 Cr, EPS ₹2.1 and PAT ₹5 Cr", None),
    ("Acme Q1FY27 EPS rises 12% to ₹5.2", None),
    ("Revenue ₹5 Cr, EPS (basic) ₹3", "Revenue ₹5 Cr"),
    ("Revenue ₹5 Cr, EPS of Rs. 2.10/- per share", "Revenue ₹5 Cr"),
    ("Net profit ₹46 Cr", "Net profit ₹46 Cr"),
]


def test_cut_text_on_a_list_of_lines():
    for text, expected in CUTS:
        assert no_eps.cut_text(text) == expected, text


def test_eps_in_the_middle_of_a_sentence_drops_the_item_so_no_figure_is_misattributed():
    for t in ["Revenue ₹100 Cr, EPS ₹5 and net interest margin 3%", "EPS ₹5, NIM 3%", "Revenue ₹10 Cr, EPS ₹5, AUM ₹2,000 Cr",
              "Acme: dividend ₹2 per share and EPS ₹7", "Revenue ₹10 Cr (EPS ₹5)", "Revenue ₹10 Cr, EPS ₹2.1 and PAT ₹5 Cr", "Basic EPS ₹2.1, up 12%"]:
        assert no_eps.cut_text(t) is None, t
    out = _out(what_happened=[{"text": "Revenue ₹100 Cr, EPS ₹5 and net interest margin 3%", "quote": "100"}, {"text": "PAT ₹5 Cr.", "quote": "5"}],
               why_it_matters=[{"text": "EPS ₹5, NIM 3%", "basis": "FILING"}],
               missing_disclosures=["EPS ₹5 and AUM not given", "Order book not given"])
    no_eps.drop_eps(out)
    assert [f.text for f in out.card.what_happened] == ["PAT ₹5 Cr."]
    assert out.card.why_it_matters == [] and out.card.missing_disclosures == ["Order book not given"]


def test_a_trailing_eps_clause_is_cut_with_its_separator_and_dangling_words():
    assert no_eps.cut_text("Revenue ₹1,200 Cr, up 10%, EPS ₹5.2 (+8% YoY)") == "Revenue ₹1,200 Cr, up 10%"
    assert no_eps.cut_text("Revenue ₹10 Cr — basic and diluted EPS ₹2.1 vs ₹1.9 a year ago") == "Revenue ₹10 Cr"
    assert no_eps.cut_text("Revenue ₹10 Cr; net EPS ₹2") == "Revenue ₹10 Cr"
    assert no_eps.cut_text("EPS ₹2.10") is None                  # about nothing else
    out = _out(what_happened=[{"text": "Net profit ₹70 Cr, down 18% YoY, EPS ₹7.00", "quote": "Net profit 70, EPS 7.00"}])
    no_eps.drop_eps(out)
    fact = out.card.what_happened[0]
    assert fact.text == "Net profit ₹70 Cr, down 18% YoY" and fact.quote == "Net profit 70, EPS 7.00"   # the quote is left as it is


def test_a_headline_takeaway_and_timeline_that_are_about_eps_are_rebuilt_without_it():
    out = _out(headline="Acme Q1FY27 EPS rises 12% to ₹5.2", takeaway="EPS ₹5.2 up 12%", core_catalyst="Higher EPS on volume",
               what_happened=[{"text": "Revenue ₹1,100 Cr.", "quote": "1,100"}],
               why_it_matters=[{"text": "Margin held.", "basis": "FILING"}])
    out.timeline_entry = "Q1 EPS up 12%"
    no_eps.drop_eps(out)
    card = out.card
    assert card.headline == "Acme Q1FY27: Revenue ₹1,100 Cr"
    assert card.takeaway == "" and card.core_catalyst is None   # not cut: left off, never the insight twice
    assert not no_eps.mentions_eps(out.timeline_entry) and out.timeline_entry == card.headline


def test_a_headline_with_a_trailing_eps_clause_is_cut_and_a_headline_with_a_figure_before_eps_is_rebuilt():
    out = _out(headline="Acme Q2FY27: revenue ₹1,100 Cr, EPS ₹7.00 (-18% YoY)")
    assert no_eps.drop_eps(out) == ["headline: EPS clause cut"]
    assert out.card.headline == "Acme Q2FY27: revenue ₹1,100 Cr"
    assert no_eps.drop_eps(_out()) == []
    out = _out(headline="Acme Q2FY27 revenue ₹1,100 Cr and EPS ₹7", what_happened=[{"text": "PAT ₹70 Cr.", "quote": "70"}])
    no_eps.drop_eps(out)
    assert out.card.headline == "Acme Q2FY27: PAT ₹70 Cr"


def test_with_nothing_else_to_say_the_headline_is_the_company_and_period_and_takeaway_may_be_empty():
    out = _out(headline="Acme Q1FY27 EPS rises 12% to ₹5.2", takeaway="EPS ₹5.2 up 12%", core_catalyst="EPS up",
               what_happened=[{"text": "EPS rose 12% to ₹5.2.", "quote": "5.2"}])
    no_eps.drop_eps(out)
    card = out.card
    assert card.headline == "Acme Q1FY27: results"
    assert [f.text for f in card.what_happened] == ["Acme Q1FY27: results"]
    assert card.takeaway in ("", "Acme Q1FY27: results") and card.core_catalyst in (None, "Acme Q1FY27: results")
    assert not no_eps.mentions_eps(card.takeaway) and not no_eps.mentions_eps(card.core_catalyst or "")


def test_the_what_happened_fallback_never_keeps_an_eps_line():
    out = _out(what_happened=[{"text": "Basic EPS ₹7.00 a share.", "quote": "7.00"}, {"text": "Diluted EPS ₹6.90.", "quote": "6.90"}])
    no_eps.drop_eps(out)
    assert [f.text for f in out.card.what_happened] == ["Acme Q2FY27: revenue ₹1,100 Cr"]


def test_only_the_text_of_a_line_is_judged_not_its_quote():
    out = _out(what_happened=[{"text": "PAT ₹46 Cr.", "quote": "PAT 46 EPS 5.2"}],
               why_it_matters=[{"text": "PAT ₹46 Cr is steady.", "quote": "PAT 46 EPS 5.2", "basis": "FILING"}])
    assert no_eps.drop_eps(out) == []
    assert out.card.what_happened[0].quote == "PAT 46 EPS 5.2" and len(out.card.why_it_matters) == 1


def test_more_ways_to_write_eps_and_the_per_share_figures_that_are_not():
    for t in ["E.P.S. ₹5", "earnings of ₹5 a share", "earnings/share ₹5", "PAT per share ₹3", "diluted earnings per ordinary share ₹4",
              "Earnings per equity share 3", "profit after tax per share ₹3", "PAT/share 3", "profit/share 3", "earnings ₹5 per share",
              "earning ₹5/share", "earnings of ₹ 5 / share", "earnings per ₹10 share 4", "Earnings per equity share of ₹10 each 4.5",
              "earnings per share ₹५.२"]:
        assert no_eps.mentions_eps(t), t
    for t in ["Dividend ₹5 per share", "DPS ₹5", "Book value per share ₹40", "NAV per share ₹12", "Issue price ₹10 per share",
              "Net profit ₹5 Cr", "Interim dividend 250% (₹2.5 a share)", "Final dividend of ₹५ per share"]:
        assert not no_eps.mentions_eps(t), t


LEAKS = ["loss per share ₹5.2", "Profit/(loss) per share ₹5", "Earnings-per-share ₹5.2", "net loss per equity share ₹5.2", "LPS ₹5.2",
         "Earnings were ₹5.2 per share", "Earnings: ₹5.2 per share", "profit worked out to ₹5 per share", "each share earned ₹5",
         "profit attributable to owners per share ₹5", "earnings after tax per share", "E P S ₹5", "basic_eps 5.2", "EPS5.2",
         "e-p-s 5", "Ｅｐｓ ₹5", "E\u00adPS ₹5", "EPS\u200b ₹5", "per share earnings of 5", "earnings of ₹5 pershare", "₹5/sh profit"]
KEEPS = ["dividend ₹5 per share", "DPS ₹2", "book value per share ₹120", "NAV per unit", "price per share", "face value ₹10 per share",
         "buyback at ₹1,200 per share", "rights issue at ₹50 a share", "Net profit / share capital 12%", "Profit per shareholder",
         "EBITDA per share ₹5", "earnings rose 10%", "EPSILON Corp", "Repsol deposits", "steps taken", "Revenue ₹5 Cr, price ₹5 per share",
         "Preferential issue at ₹250 per share", "Net profit ₹46 Cr", "Share of profit ₹5 Cr", "Revenue 5 helps", "Q1FY27 revenue up 10%"]


def test_a_per_share_figure_next_to_earnings_wording_is_eps_and_other_per_share_items_are_not():
    for t in LEAKS:
        assert no_eps.mentions_eps(t), t
    for t in KEEPS:
        assert not no_eps.mentions_eps(t), t


def test_trailing_cuts_of_the_new_wording():
    assert no_eps.cut_text("Revenue ₹5 Cr, loss per share ₹3") == "Revenue ₹5 Cr"
    assert no_eps.cut_text("Revenue ₹5 Cr, Earnings: ₹5.2 per share") == "Revenue ₹5 Cr"
    assert no_eps.cut_text("Revenue ₹5 Cr, LPS ₹3.1 (vs ₹2 a year ago)") == "Revenue ₹5 Cr"
    assert no_eps.cut_text("Loss per share ₹5.2, revenue ₹5 Cr") is None
    assert no_eps.cut_text("Revenue ₹5 Cr, dividend ₹2 per share") == "Revenue ₹5 Cr, dividend ₹2 per share"


def test_every_text_field_of_an_item_is_judged_and_the_log_names_no_text():
    out = _out(what_happened=[{"text": "Revenue ₹1,100 Cr.", "quote": "1,100"}],
               notable_changes=[{"metric": "PAT", "why": "x", "previous": "EPS 5", "current": "6"},
                                {"metric": "Margin", "why": "y", "change": "loss per share ₹3"},
                                {"metric": "Cash", "why": "z", "previous": "₹5 Cr"}],
               track_next={"kpis_to_verify": [{"kpi": "Revenue", "check_in": "Q3"}, {"kpi": "PAT", "target": "EPS ₹6"},
                                              {"kpi": "PAT", "metric": "eps"}, {"kpi": "NIM", "check_in": "Q3"}]})
    log = no_eps.drop_eps(out)
    assert [c.metric for c in out.card.notable_changes] == ["Cash"]
    assert [k.kpi for k in out.card.track_next.kpis_to_verify] == ["Revenue", "NIM"]
    assert log and all(entry.endswith(": dropped") or entry.endswith(": EPS clause cut") for entry in log)
    assert not any(ch.isdigit() for entry in log for ch in entry)


def test_a_headline_prefix_is_the_company_and_period_never_a_verb_or_a_figure():
    for headline, fact, expected in [
            ("Acme Ltd Reports Q1FY27 EPS of ₹5.2", "Revenue ₹10 Cr.", "Acme Ltd: Revenue ₹10 Cr"),
            ("Acme Bharat (Q1FY27) EPS ₹5", "PAT ₹4 Cr.", "Acme Bharat (Q1FY27): PAT ₹4 Cr"),
            ("Acme Q1 FY27 EPS ₹5", "PAT ₹4 Cr.", "Acme Q1 FY27: PAT ₹4 Cr"),
            ("Acme posts EPS of ₹5", "Acme revenue ₹10 Cr.", "Acme revenue ₹10 Cr"),
            ("Acme Q1FY27 EPS rises to ₹5", "Acme Q1FY27 revenue ₹10 Cr.", "Acme Q1FY27 revenue ₹10 Cr"),
            ("EPS of ₹5 a share", "PAT ₹4 Cr.", "PAT ₹4 Cr"),
            ("Acme Q1FY27 EPS ₹5", "EPS ₹5.", "Acme Q1FY27: results")]:
        out = _out(headline=headline, what_happened=[{"text": fact, "quote": "x"}])
        if "EPS" in fact:
            out = _out(headline=headline, what_happened=[{"text": fact, "quote": "x"}, {"text": "Basic EPS 5", "quote": "5"}])
        no_eps.drop_eps(out)
        assert out.card.headline == expected, headline


def test_issue_and_trade_prices_per_share_are_not_eps():
    # lead's probe: a QIP price was dropped as EPS; issue and insider-trade prices are quoted per share too
    from bse_intel.no_eps import mentions_eps
    for line in ["QIP at ₹1,200 per share", "Promoter sold 5,000 shares at ₹300 per share",
                 "Institutional placement at floor price ₹980 per share", "OFS at ₹410 a share",
                 "Purchased 2,000 shares at ₹55 per share"]:
        assert not mentions_eps(line), line
    assert mentions_eps("Profit per share ₹3 after QIP")     # the EPS wording itself still counts
