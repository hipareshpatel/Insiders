"""Code computes, the model describes (audit round 2): a change, margin or ratio on a card stands only if code
produced it from tagged figures on a like-for-like base, or the filing prints it. Each test is a round-2 card."""
from __future__ import annotations

from bse_intel import computed
from bse_intel.models import FinancialMetric, Pass2Output
from bse_intel.xbrl import XbrlResult


def _out(card: dict, timeline: str = "x") -> Pass2Output:
    base = {"impact_level": "MODERATE", "headline": "A company reports results", "what_happened": ["x"]}
    return Pass2Output.model_validate({"is_material": True, "event_type": "RESULTS", "timeline_entry": timeline,
                                       "card": {**base, **card}})


def _tagged(*metrics: FinancialMetric, period: str) -> XbrlResult:
    return XbrlResult("RESULTS", "STANDALONE", period, list(metrics))


def test_skf_india_a_year_ago_from_before_the_demerger_gives_no_change():
    """22568035 / bc3e32e7: the XBRL year-ago (₹1,283.15 Cr) still held the demerged industrial business; the release
    prints the like-for-like continuing base (4,625.0 million) and its own +27.1%. The card's -54% is removed, the
    filing's +27.1% stays."""
    filing = ("Financial Highlights (Q1 FY 2026-27) - Standalone (Rs in million)\nRevenue from operations 5,877.9 4,625.0 "
              "Growth 27.1%\nEBITDA 1,003.9 Margin 17.1%")
    tagged = _tagged(FinancialMetric(metric="revenue", period="Q1FY27", value=587.79, unit="INR_CR", yoy_pct=-54.2),
                     period="Q1FY27")
    history = [{"metric": "revenue", "period": "Q1FY26", "value": 1283.15, "value_news_id": "xbrl:res:500472:Q1FY26"}]
    pool = computed.build_pool(filing, tagged, history=history)
    out = _out({"headline": "SKF India Q1FY27 revenue up 27.1% YoY to ₹587.8 Cr",
                "key_numbers": [{"label": "Revenue", "value": "₹587.79 Cr", "change": "-54.2% YoY"}],
                "why_it_matters": [{"text": "Employee cost fell 49.5% YoY from ₹99.7 Cr", "basis": "FILING"},
                                   {"text": "EBITDA margin was 17.1%", "basis": "FILING"}]})
    notes = computed.enforce(out, pool)
    assert out.card.headline == "SKF India Q1FY27 revenue up 27.1% YoY to ₹587.8 Cr"
    assert out.card.key_numbers[0].change is None
    assert [w.text for w in out.card.why_it_matters] == ["EBITDA margin was 17.1%"]
    assert any("-54.2%" in n for n in notes) and any("49.5%" in n for n in notes)


def test_adani_power_eps_before_a_split_gives_no_change_but_a_like_for_like_one_stays():
    """dcadcb1d: EPS "down 71% YoY" set ₹2.49 against an EPS from before the share split. The filing prints the
    restated year-ago EPS (1.69), not 8.59, so code gives no change from 8.59; PAT's base is printed and its +47.2%
    stands."""
    filing = "PAT 4,867.10 3,305.40 Earnings per share 2.49 1.69 (Rs crore except EPS)"
    tagged = _tagged(FinancialMetric(metric="eps", period="Q1FY27", value=2.49, unit="INR", yoy_pct=-71.0),
                     FinancialMetric(metric="pat", period="Q1FY27", value=4867.10, unit="INR_CR", yoy_pct=47.2),
                     period="Q1FY27")
    pool = computed.build_pool(filing, tagged)
    out = _out({"key_numbers": [{"label": "EPS", "value": "₹2.49", "change": "-71% YoY"},
                                {"label": "PAT", "value": "₹4,867.10 Cr", "change": "+47.2% YoY"}]})
    computed.enforce(out, pool)
    assert [(k.label, k.change) for k in out.card.key_numbers] == [("EPS", None), ("PAT", "+47.2% YoY")]


def test_jindal_stainless_a_margin_fall_called_an_improvement_is_removed():
    """6192cdc5: operating margin 11.78% against 12.83% a year ago is a 105 bps fall; "improved by 105 bps" is not
    the move code computed."""
    tagged = _tagged(FinancialMetric(metric="ebitda_margin", period="Q1FY27", value=11.78, unit="PCT"), period="Q1FY27")
    history = [{"metric": "ebitda_margin", "period": "Q1FY26", "value": 12.83, "value_news_id": "xbrl:res:532508:Q1FY26"}]
    pool = computed.build_pool("Operating margin 11.78% 12.83%", tagged, history=history)
    out = _out({"what_happened": ["Operating margin improved by 105 bps to 11.78% in Q1FY27, from 12.83% a year earlier",
                                  "Operating margin fell 105 bps to 11.78% from 12.83% a year ago"]})
    computed.enforce(out, pool)
    texts = [f.text for f in out.card.what_happened]
    assert "Operating margin fell 105 bps to 11.78% from 12.83% a year ago" in texts
    assert not any("improved by 105 bps" in t for t in texts)

    # A year-ago margin the filing does not print (memory's, from before a demerger or on another basis) is no base:
    # the move against it is removed, not stated
    pool = computed.build_pool("Operating margin 11.78% for the quarter", tagged, history=history)
    out = _out({"what_happened": ["Operating margin fell 105 bps to 11.78% from 12.83% a year ago"]})
    computed.enforce(out, pool)
    assert not any("105 bps" in f.text for f in out.card.what_happened)


def test_emudhra_a_consolidated_quarter_against_a_standalone_one_gives_no_change():
    """cc896891: memory's Q1FY26 revenue (₹55.51 Cr) was standalone; the filing is consolidated and prints its own
    Q1FY26 (₹150.20 Cr). A change against 55.51 is on another basis and is removed; one against 150.20 stands."""
    filing = "Consolidated revenue from operations 1,728.8 1,502.0 (INR million)"
    tagged = _tagged(FinancialMetric(metric="revenue", period="Q2FY26", value=172.88, unit="INR_CR"), period="Q2FY26")
    history = [{"metric": "revenue", "period": "Q1FY26", "value": 55.51, "value_news_id": "xbrl:res:543533:Q1FY26"}]
    pool = computed.build_pool(filing, tagged, history=history)
    assert computed.unproduced("Revenue rose 211% QoQ", pool) == ["211%"]
    history[0]["value"] = 150.20
    pool = computed.build_pool(filing, tagged, history=history)
    assert computed.unproduced("Revenue rose 15.1% QoQ", pool) == []


def test_a_figure_the_filing_prints_stays_and_one_it_does_not_goes():
    """Without tagged figures a card states the filing's own figures and no computed changes (Lehar, Poddar)."""
    pool = computed.build_pool("Revenue 74.95 against 141.40; dividend 25%; stake 51%")
    out = _out({"headline": "Lehar Footwears Q1 revenue fell 47% YoY to ₹74.95 Cr; 51% stake in subsidiary",
                "what_happened": ["Board declared a 25% dividend", "Revenue fell 47% YoY to ₹74.95 Cr from ₹141.40 Cr"]})
    computed.enforce(out, pool)
    assert "47%" not in out.card.headline and "51% stake" in out.card.headline
    assert [f.text for f in out.card.what_happened][0] == "Board declared a 25% dividend"
    assert all("47%" not in f.text for f in out.card.what_happened)


def test_britannia_a_change_across_a_sign_flip_is_said_in_words():
    """0c00a45a: inventory change "+894.4%" from ₹1.43 Cr to -₹14.22 Cr; CSB's provisions "+1713%" off a write-back."""
    from bse_intel.pipeline import fix_change_percentages

    out = _out({"notable_changes": [
        {"metric": "inventory_change", "previous": "₹1.43 Cr", "current": "-₹14.22 Cr", "change": "+894.4%"},
        {"metric": "provisions", "previous": "₹(4.54) Cr", "current": "₹16.53 Cr", "change": "+464% YoY"},
        {"metric": "pat", "previous": "-₹19.76 Cr", "current": "-₹10.33 Cr", "change": "+48% YoY"}]})
    fix_change_percentages(out)
    assert [c.change for c in out.card.notable_changes] == ["turned negative", "turned positive YoY", "loss narrowed YoY"]


def test_heg_no_percentage_off_a_loss_in_a_signal():
    """ef8fc04d / bc3e32e7: "PAT up 208% vs Q4FY26" and "PAT up 413%" were moves from a loss; the signal now says the
    profit line turned, and a non-profit line off a negative base gives none."""
    from bse_intel.signals import _change

    assert _change({"metric": "pat", "value": 61.92, "unit": "INR_CR"}, {"value": -19.76}) == (3.0, "TURN")
    assert _change({"metric": "deferred_tax", "value": 6.72, "unit": "INR_CR"}, {"value": -1.5}) is None
    assert _change({"metric": "pat", "value": 50.0, "unit": "INR_CR"}, {"value": 30.0})[1] == "67%"


def test_britannia_a_vote_share_printed_without_a_percent_sign_stays():
    """17762e34 / 558fc7e9: the scrutiniser prints 97.0846 and 2.9154 under "% of votes"; the card's 97.08% and
    2.92% were removed as unproduced and left "** ** of valid votes were in favour"."""
    pool = computed.build_pool("Votes in favour of the resolution 2,302 18,79,81,898 97.0846 "
                               "Votes against the resolution 263 56,44,992 2.9154")
    out = _out({"what_happened": ["**97.08%** of valid votes were in favour and **2.92%** against"]})
    assert computed.enforce(out, pool) == []
    # only to two decimals: a one-decimal or whole share could land on any table figure
    assert computed.unproduced("97.1% in favour", pool) == ["97.1%"]


def test_adani_a_sentence_left_broken_by_a_removed_figure_is_dropped_or_mended():
    """fc2e28bd / 879e1c65 / 10f81073: "increase stake to via open market purchases", "NCD issuance, of net worth",
    "Only of votes cast were in favour"."""
    pool = computed.build_pool("Market purchase of shares by the promoter group")
    out = _out({"headline": "Adani Power promoters increase stake to 75.5% via open market purchases",
                "what_happened": ["Only 62% of votes cast were in favour of Resolution No. 3", "Promoters bought shares"]})
    computed.enforce(out, pool)
    assert out.card.headline == "Adani Power promoters increase stake via open market purchases"
    assert [f.text for f in out.card.what_happened] == ["Promoters bought shares"]
    assert computed._repair("Home First Finance approved ₹150 Cr NCD issuance, of net worth") == \
        "Home First Finance approved ₹150 Cr NCD issuance"


def test_skf_a_verb_against_its_own_two_levels_becomes_moved():
    """bc3e32e7: "margin slipped to 15.0% from 13.0% a year ago" - both levels right, the verb backwards."""
    pool = computed.build_pool("EBITDA margin 15.0% 13.0%")
    out = _out({"takeaway": "Continuing revenue was flat QoQ, but margin slipped to 15.0% from 13.0% a year ago",
                "what_happened": ["Operating margin fell to 11.78% from 12.83%"]})
    notes = computed.enforce(out, pool)
    assert out.card.takeaway == "Continuing revenue was flat QoQ, but margin moved to 15.0% from 13.0% a year ago"
    assert out.card.what_happened[0].text == "Operating margin fell to 11.78% from 12.83%"
    assert any("slipped" in n for n in notes)


def test_adani_power_a_share_must_be_of_the_base_it_names():
    """c5f4d350: "The borrowing limit increase of ₹1,00,000 Cr is 22.6% of net worth" - 22.6% is what code worked
    out against market cap; against net worth it is 150.6%."""
    scale = ("Amounts written in this filing, in proportion:\n"
             "- ₹1,00,000 Cr = 22.6% of market cap, 150.6% of net worth, 169.4% of FY26 revenue")
    pool = computed.build_pool("borrowings not exceeding Rs. 1,00,000 crore", scale=scale)
    out = _out({"why_it_matters": [
        {"text": "The ₹1,00,000 Cr limit is 22.6% of net worth and 169.4% of TTM revenue", "basis": "BALANCE_SHEET"},
        {"text": "The ₹1,00,000 Cr limit is 150.6% of net worth", "basis": "BALANCE_SHEET"}]})
    computed.enforce(out, pool)
    assert [w.text for w in out.card.why_it_matters] == ["The ₹1,00,000 Cr limit is 150.6% of net worth"]


def test_a_table_rows_columns_count_as_printed_shares():
    """RBL Q1FY27 (round 4): "Gross NPA % 1.30 1.45 2.78" kept only its last column as printed, so the card's true
    "Gross NPA improved to 1.30% (vs 1.45% ... 2.78%)" was stripped to "improved to (vs 1.45% ...)"."""
    from bse_intel import computed

    pool = computed.build_pool("(b) Gross NPA % 1.30 1.45 2.78 1.45\nNet NPA % 0.37 0.39 0.45 0.39")
    assert computed.unproduced("Gross NPA improved to 1.30% (vs 1.45% and 2.78%); Net NPA 0.37%", pool) == []
    assert computed.unproduced("Gross NPA improved to 1.31%", pool) == ["1.31%"]


def test_a_range_or_share_left_without_its_figure_is_broken():
    """PNB's "7-9 bps" less "9 bps" and Atul's "under 1% of market cap" less "1%" (live review, 23 Oct 2026)."""
    from bse_intel.computed import _repair, broken

    assert broken("PNB sees 7- margin boost from repo hike")
    assert _repair("PNB sees 7- margin boost from repo hike") == "PNB sees margin boost from repo hike"
    assert broken("**Management** expects a **7** to further expansion in NIM in Q3")
    assert _repair("The open-market buyback of up to ₹90 Cr represents under of market cap") == \
        "The open-market buyback of up to ₹90 Cr"
    assert broken("The penalty is of FY26 profit and of net worth")
    for whole in ("an 18 to 24 month execution window", "a 5-year OPEX contract", "April 2020 – March 2021",
                  "an ESG score of 56 to the company", "in the form of non-convertible debentures",
                  "swung from a loss in Q2FY26 to a net profit", "Capacity to rise 20 to 30 MTPA"):
        assert not broken(whole), whole
