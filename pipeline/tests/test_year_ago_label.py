"""CARD_YEAR_AGO_LABEL (blind audit 1 Nov 2026): a year-ago label two years back is put right, in a comparison only."""

import copy

from bse_intel import year_ago_label as Y

# GICRE nse-106837460, an H1FY27 card (live sentences)
GICRE = {
    "headline": "GIC Re H1 FY27 consolidated PAT falls to ₹4,709 Cr; solvency at 4.18",
    "what_happened": [
        {"text": "Consolidated **profit after tax** declined to **₹4,709.36 Cr** for H1 FY27 from ₹5,404.12 Cr in H1 FY25.",
         "quote": "Consolidated Profit After Tax for the half year ended 30.09.2026 was 4,709.36 crore"},
        {"text": "Consolidated **underwriting loss** widened to **₹1,575.04 Cr** for H1 FY27 against ₹1,021.98 Cr in H1 FY25."}],
    "timeline_entry": "GIC Re reported H1 FY27 consolidated gross premium of ₹24,713 Cr and PAT of ₹4,709 Cr on October 30, 2026.",
}
# HEGAM nse-106837190, a Q2FY27 card (live sentences)
HEGAM = {
    "headline": "HEG Limited Q2FY27 revenue at ₹740.40 Cr; net profit at ₹156.51 Cr",
    "what_happened": [{"text": "Quarterly **revenue from operations** reached **₹740.40 Cr**, compared to **₹696.85 Cr** in Q2FY25."}],
    "why_it_matters": [{"text": "Profit before exceptional items and tax rose to ₹192.47 Cr from ₹151.23 Cr in Q2FY25, reflecting improved efficiency."}],
}


def on(monkeypatch):
    monkeypatch.setenv("CARD_YEAR_AGO_LABEL", "1")


def test_gicre_and_hegam_labels_are_corrected(monkeypatch):
    on(monkeypatch)
    g = copy.deepcopy(GICRE)
    notes = Y.apply_card_json(g)
    assert [i["text"] for i in g["what_happened"]] == [
        "Consolidated **profit after tax** declined to **₹4,709.36 Cr** for H1 FY27 from ₹5,404.12 Cr in H1 FY26.",
        "Consolidated **underwriting loss** widened to **₹1,575.04 Cr** for H1 FY27 against ₹1,021.98 Cr in H1 FY26."]
    assert g["what_happened"][0]["quote"] == GICRE["what_happened"][0]["quote"] and len(notes) == 2
    h = copy.deepcopy(HEGAM)
    assert len(Y.apply_card_json(h)) == 2
    assert h["what_happened"][0]["text"].endswith("in Q2FY26.")
    assert "from ₹151.23 Cr in Q2FY26, reflecting" in h["why_it_matters"][0]["text"]


def test_off_changes_nothing(monkeypatch):
    monkeypatch.delenv("CARD_YEAR_AGO_LABEL", raising=False)
    for card in (GICRE, HEGAM):
        c = copy.deepcopy(card)
        assert Y.apply_card_json(c) == [] and c == card


def test_not_touched(monkeypatch):
    on(monkeypatch)
    card = {"headline": "Acme Q2FY27 revenue at ₹740 Cr", "results": {"period": "Q2FY27"},
            "takeaway": "Q2FY27 is the best quarter; the highest since Q2FY25. FY25 guidance was Q2FY25 based.",
            "what_happened": [{"text": "Revenue was ₹740 Cr in Q2FY27, from ₹700 Cr in Q2FY26."},          # own period, right year-ago
                              {"text": "Margin was the highest since Q2FY25."},                              # on purpose
                              {"text": "Management reaffirmed the Q2FY25 guidance of 18%."},                 # guidance
                              {"text": "The Q2FY25 base was flattered by a one-off."}],                      # no comparison context
            "key_numbers": [{"label": "Revenue", "change": "+6% vs Q2FY26"}]}
    before = copy.deepcopy(card)
    assert Y.apply_card_json(card) == [] and card == before


def test_other_period_kinds_and_the_table_period(monkeypatch):
    on(monkeypatch)
    card = {"headline": "x", "results": {"period": "FY27"}, "takeaway": "PAT rose from ₹10 Cr in FY25.",
            "key_numbers": [{"label": "Revenue vs 9MFY25", "change": "+5% vs FY25"}]}
    notes = Y.apply_card_json(card)
    assert card["takeaway"] == "PAT rose from ₹10 Cr in FY26." and card["key_numbers"][0]["change"] == "+5% vs FY26"
    assert card["key_numbers"][0]["label"] == "Revenue vs 9MFY25" and len(notes) == 2   # a 9M label is not an FY card's year-ago
