"""CARD_ADJUSTED_PROFIT_LABEL (blind audit 1 Nov 2026, TI nse-106837308): Tilaknagar's release headlined its PAT before
exceptional items and acquisition amortisation, "PAT ₹68 Cr, +30%", and the card showed it bare as "PAT" above its own results
table's reported ₹22.27 Cr (-57.7% YoY). The card below is the stored card's own fields."""

import copy

from bse_intel import results_one_line as R

TI = {
    "headline": "Tilaknagar Industries Q2FY27 revenue rose 173% YoY to ₹1,035 Cr; PAT up 30% to ₹68 Cr",
    "takeaway": "Q2FY27 showed robust revenue and volume expansion.",
    "key_numbers": [
        {"label": "EBITDA", "value": "₹148 Cr", "change": "+146% YoY", "quote": "EBITDA grew by 146% to Rs. 148 crore"},
        {"label": "PAT", "value": "₹68 Cr", "change": "+30% YoY", "quote": "PAT1 increased by 30% to Rs. 68 crore"}],
    "results": {"period": "Q2FY27", "pat": {"value": 22.27, "prev_year": 52.68, "yoy_pct": -57.7},
                "revenue": {"value": 2437.56}, "lines": [{"key": "revenue"}, {"key": "pat", "label": "PAT"}]},
}


def on(monkeypatch):
    monkeypatch.setenv("CARD_ADJUSTED_PROFIT_LABEL", "1")


def test_an_adjusted_pat_beside_the_reported_one_is_labelled(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(TI)
    notes = R.profit_label_card_json(card)
    assert len(notes) == 2
    assert card["key_numbers"][1]["label"] == "PAT (company-reported; reported PAT ₹22.27 Cr)"
    assert card["headline"].endswith("PAT up 30% to ₹68 Cr (company-reported; reported PAT ₹22.27 Cr)")
    assert card["key_numbers"][0]["label"] == "EBITDA"   # not a profit figure


def test_the_companys_own_words_for_its_basis_go_in_the_label(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(TI)
    card["key_numbers"][1]["quote"] = "PAT before exceptional items increased by 30% to Rs. 68 crore"
    R.profit_label_card_json(card)
    assert card["key_numbers"][1]["label"] == "PAT (company-reported, before exceptional items; reported PAT ₹22.27 Cr)"


def test_the_reported_profit_a_loss_an_earlier_figure_and_a_labelled_one_are_left_alone(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(TI)
    card["headline"] = "Tilaknagar Q2FY27 PAT falls 58% to ₹22.27 Cr vs ₹52.68 Cr"
    card["key_numbers"][1].update(value="₹22.3 Cr")
    assert R.profit_label_card_json(card) == []
    loss = copy.deepcopy(TI)
    loss["results"]["pat"]["value"] = -68.0
    loss["headline"] = "Acme Q2FY27 net loss of ₹68 Cr"
    loss["key_numbers"] = [{"label": "Net loss", "value": "₹-68 Cr", "quote": "loss of Rs 68 crore"}]
    assert R.profit_label_card_json(loss) == []
    stated = copy.deepcopy(TI)
    stated["key_numbers"][1]["label"] = "Adjusted PAT"
    stated["headline"] = "Tilaknagar Q2FY27 adjusted PAT up 30% to ₹68 Cr"
    assert R.profit_label_card_json(stated) == []


def test_a_figure_of_another_period_is_not_compared(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(TI)
    card["headline"] = "Tilaknagar H1FY27 PAT at ₹68 Cr"
    card["key_numbers"] = [{"label": "H1FY27 PAT", "value": "₹68 Cr"}]
    assert R.profit_label_card_json(card) == []


def test_off_by_default_nothing_changes(monkeypatch):
    monkeypatch.delenv("CARD_ADJUSTED_PROFIT_LABEL", raising=False)
    monkeypatch.delenv("REPO_VARS", raising=False)
    monkeypatch.setenv("BSE_INTEL_SWITCHES", "/no/such/file.toml")
    card = copy.deepcopy(TI)
    assert R.profit_label_card_json(card) == [] and card == TI


def test_another_profit_line_in_the_headline_is_not_pat(monkeypatch):
    """Lead's review of #323: a bare "profit" bound "operating profit ₹412 Cr", "profit before tax" and segment profit."""
    on(monkeypatch)
    for headline in ("Acme Q2FY27 operating profit rises to ₹412 Cr", "Acme Q2FY27 profit before tax at ₹412 Cr",
                     "Acme Q2FY27 gross profit ₹412 Cr", "Acme Q2FY27 segment profit of ₹412 Cr",
                     "Acme Q2FY27 profit from operations ₹412 Cr"):
        card = copy.deepcopy(TI)
        card["headline"], card["key_numbers"] = headline, []
        assert R.profit_label_card_json(card) == [], headline
    card = copy.deepcopy(TI)
    card["headline"], card["key_numbers"] = "Acme Q2FY27 profit jumps to ₹68 Cr", []
    assert len(R.profit_label_card_json(card)) == 1   # a bare profit that is the headline's PAT is still compared
