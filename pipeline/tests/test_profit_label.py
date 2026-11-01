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


# memory's profit lines for the card's quarter and the half it closes: a figure is tagged only when it is one of the half's
# (reviews of #363)
MEM = {"financial_metrics": [{"metric": "pat", "period": "Q2FY27", "value": 22.27},
                             {"metric": "pat_owners", "period": "Q2FY27", "value": 22.27},
                             {"metric": "pat", "period": "H1FY27", "value": 60.0}]}


def on(monkeypatch):
    monkeypatch.setenv("CARD_ADJUSTED_PROFIT_LABEL", "1")


def test_an_adjusted_pat_memory_does_not_hold_gets_no_label(monkeypatch):
    """TI's ₹68 Cr (PAT before exceptional items) is no profit line memory holds: no "company-reported" guess any more (lead's
    review of #363), nothing changes."""
    on(monkeypatch)
    card = copy.deepcopy(TI)
    assert R.profit_label_card_json(card, MEM) == [] and card == TI


def test_the_reported_profit_a_loss_an_earlier_figure_and_a_labelled_one_are_left_alone(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(TI)
    card["headline"] = "Tilaknagar Q2FY27 PAT falls 58% to ₹22.27 Cr vs ₹52.68 Cr"
    card["key_numbers"][1].update(value="₹22.3 Cr")
    assert R.profit_label_card_json(card, MEM) == []
    loss = copy.deepcopy(TI)
    loss["results"]["pat"]["value"] = -68.0
    loss["headline"] = "Acme Q2FY27 net loss of ₹68 Cr"
    loss["key_numbers"] = [{"label": "Net loss", "value": "₹-68 Cr", "quote": "loss of Rs 68 crore"}]
    assert R.profit_label_card_json(loss, MEM) == []
    stated = copy.deepcopy(TI)
    stated["key_numbers"][1]["label"] = "Adjusted PAT"
    stated["headline"] = "Tilaknagar Q2FY27 adjusted PAT up 30% to ₹68 Cr"
    assert R.profit_label_card_json(stated, MEM) == []


def test_a_figure_of_another_period_is_not_compared(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(TI)
    card["headline"] = "Tilaknagar H1FY27 PAT at ₹68 Cr"
    card["key_numbers"] = [{"label": "H1FY27 PAT", "value": "₹68 Cr"}]
    assert R.profit_label_card_json(card, MEM) == []


def test_off_by_default_nothing_changes(monkeypatch):
    monkeypatch.delenv("CARD_ADJUSTED_PROFIT_LABEL", raising=False)
    monkeypatch.delenv("REPO_VARS", raising=False)
    monkeypatch.setenv("BSE_INTEL_SWITCHES", "/no/such/file.toml")
    card = copy.deepcopy(TI)
    assert R.profit_label_card_json(card, MEM) == [] and card == TI


def test_another_profit_line_in_the_headline_is_not_pat(monkeypatch):
    """Lead's review of #323: a bare "profit" bound "operating profit ₹412 Cr", "profit before tax" and segment profit."""
    on(monkeypatch)
    for headline in ("Acme Q2FY27 operating profit rises to ₹412 Cr", "Acme Q2FY27 profit before tax at ₹412 Cr",
                     "Acme Q2FY27 gross profit ₹412 Cr", "Acme Q2FY27 segment profit of ₹412 Cr",
                     "Acme Q2FY27 profit from operations ₹412 Cr"):
        card = copy.deepcopy(TI)
        card["headline"], card["key_numbers"] = headline, []
        assert R.profit_label_card_json(card, MEM) == [], headline
    card = copy.deepcopy(TI)
    card["headline"], card["key_numbers"] = "Acme Q2FY27 profit jumps to ₹60 Cr", []
    assert len(R.profit_label_card_json(card, MEM)) == 1   # a bare profit that is memory's H1 is still tagged


def _headline(monkeypatch, text, results=None):
    on(monkeypatch)
    card = copy.deepcopy(TI)
    card["headline"], card["key_numbers"] = text, []
    if results is not None:
        card["results"] = results
    return card, R.profit_label_card_json(card, MEM)


def test_the_earlier_periods_figure_is_not_labelled(monkeypatch):
    for text in ("Acme Q2FY27 net profit of ₹68 Cr against net profit of ₹52 Cr a year earlier",
                 "Acme Q2FY27 PAT rose to ₹68 Cr from ₹52 Cr",
                 "Acme Q2FY27 net profit ₹52 Cr a year ago",
                 "Acme Q2FY27 PAT of ₹68 Cr compared with ₹52 Cr last year",
                 "Acme Q2FY27 PAT of ₹68 Cr versus ₹52 Cr in the previous quarter"):
        card, notes = _headline(monkeypatch, text)
        assert all("₹52" not in n for n in notes), text
        assert "₹52 Cr (company" not in card["headline"], text
    card, notes = _headline(monkeypatch, "Acme Q2FY27 net profit of ₹60 Cr against net profit of ₹52 Cr a year earlier")
    assert "net profit of ₹60 Cr (H1FY27)" in card["headline"]   # the current figure is still compared


def test_a_figure_after_on_is_the_base_not_profit(monkeypatch):
    _, notes = _headline(monkeypatch, "Jubilant Q2FY27 PAT ₹22.27 Cr on ₹671.5 Cr revenue")
    assert notes == []
    _, notes = _headline(monkeypatch, "Acme Q2FY27 PAT on ₹671.5 Cr revenue")
    assert notes == []


def test_a_pat_of_zero_or_none_skips_the_card(monkeypatch):
    for pat in ({"value": 0}, {"value": None}, None):
        res = copy.deepcopy(TI["results"])
        res["pat"] = pat
        card, notes = _headline(monkeypatch, "Acme Q2FY27 PAT up 30% to ₹68 Cr", res)
        assert notes == [] and "reported PAT" not in card["headline"]


def test_a_year_nine_months_or_half_against_a_quarter_table_is_skipped(monkeypatch):
    for text in ("Acme FY26 PAT at ₹68 Cr", "Acme 9M PAT at ₹68 Cr", "Acme 9MFY27 PAT at ₹68 Cr",
                 "Acme nine months PAT at ₹68 Cr", "Acme H1FY27 PAT at ₹68 Cr", "Acme PAT at ₹68 Cr for 9M",
                 "Acme PAT at ₹68 Cr in FY26"):
        _, notes = _headline(monkeypatch, text)
        assert notes == [], text


def test_an_existing_bracketed_label_is_not_relabelled(monkeypatch):
    text = "Acme Q2FY27 PAT ₹22.27 Cr (PAT from discontinued operations ₹68 Cr)"
    card, notes = _headline(monkeypatch, text)
    assert notes == [] and card["headline"] == text
    on(monkeypatch)
    key = copy.deepcopy(TI)
    key["key_numbers"] = [{"label": "PAT (from discontinued operations)", "value": "₹68 Cr"}]
    assert R.profit_label_card_json(key, MEM) == [] or key["key_numbers"][0]["label"] == "PAT (from discontinued operations)"
    assert key["key_numbers"][0]["label"] == "PAT (from discontinued operations)"


def test_any_of_total_owners_or_continuing_profit_is_not_other(monkeypatch):
    on(monkeypatch)
    mm = {"period": "Q2FY27", "pat": {"value": 5259.91}, "pat_owners": {"value": 4667.57}, "pat_continuing": {"value": 5100.0},
          "lines": [{"key": "pat_owners", "label": "PAT"}]}
    for value in ("₹5,259.91 Cr", "₹4,667.57 Cr", "₹5,100 Cr"):
        card = copy.deepcopy(TI)
        card["results"] = copy.deepcopy(mm)
        card["headline"] = "Mahindra Q2FY27 net profit ₹%s Cr" % value[1:-3]
        card["key_numbers"] = [{"label": "Net profit", "value": value}]
        assert R.profit_label_card_json(card, MEM) == [], value


# --- release-check triage of run 41318733817 (1 Nov 2026): 285 cards, most of them code against code -----------------------------

def _card(period, table_pat, key_label, key_value, key_quote, takeaway="Strong quarter."):
    return {"headline": f"Acme {period} results", "takeaway": takeaway,
            "key_numbers": [{"label": key_label, "value": key_value, "change": None, "quote": key_quote}],
            "results": {"period": period, "pat": {"value": table_pat}, "lines": [{"key": "pat", "label": "PAT"}]}}


def test_tatacomm_a_key_number_code_wrote_is_not_labelled(monkeypatch):
    # TATACOMM Q4FY26: the key "Net profit ₹259.27 Cr" is results_card's (quote: the table line), the table's PAT row 263.24
    card = _card("Q4FY26", 263.24, "Net profit", "₹259.27 Cr", "- pat Q4FY26: 259.27 Cr, YoY -40.2%")
    for switch in ("0", "1"):
        monkeypatch.setenv("CARD_ADJUSTED_PROFIT_LABEL", switch)
        c = copy.deepcopy(card)
        assert R.profit_label_card_json(c, MEM) == [] and c["key_numbers"][0]["label"] == "Net profit"


def test_swsolar_the_takeaway_code_wrote_is_not_labelled(monkeypatch):
    on(monkeypatch)
    text = ("Q4FY26 net profit of ₹141.59 Cr against net profit of ₹55.01 Cr a year earlier; the largest move was other income of "
            "₹52.93 Cr against ₹12.1 Cr a year earlier.")
    card = _card("Q4FY26", 134.57, "EBITDA", "₹300 Cr", "x", takeaway=text)
    assert R.profit_label_card_json(card, MEM) == [] and card["takeaway"] == text
    figures = _card("Q4FY26", 134.57, "EBITDA", "₹300 Cr", "x", takeaway="Q4FY26: revenue ₹1,200 Cr, net profit ₹141.59 Cr.")
    assert R.profit_label_card_json(figures, MEM) == []


def test_kanorichem_a_key_naming_its_basis_is_left_alone(monkeypatch):
    on(monkeypatch)
    card = _card("Q4FY25", 30.06, "Standalone PAT", "-₹37.98 Cr", "Standalone loss of Rs 37.98 crore")
    assert R.profit_label_card_json(card, MEM) == [] and card["key_numbers"][0]["label"] == "Standalone PAT"


def test_emudhra_a_year_figure_on_a_q4_card_is_named_with_its_year(monkeypatch):
    on(monkeypatch)
    memory = {"financial_metrics": [{"metric": "pat", "period": "FY25", "value": 87.23}, {"metric": "pat", "period": "Q4FY25", "value": 23.89}]}
    card = _card("Q4FY25", 23.89, "PAT", "₹87.23 Cr", "Profit after tax of Rs 87.23 crore")
    notes = R.profit_label_card_json(card, memory)
    assert card["key_numbers"][0]["label"] == "PAT (FY25)" and "memory's FY25 profit" in notes[0]
    # no memory year that matches: no label (reviews of #363)
    other = _card("Q4FY25", 23.89, "PAT", "₹87.23 Cr", "Profit after tax of Rs 87.23 crore")
    R.profit_label_card_json(other, {"financial_metrics": [{"metric": "pat", "period": "FY25", "value": 99.0},
                                                           {"metric": "pat", "period": "Q4FY25", "value": 23.89}]})
    assert other["key_numbers"][0]["label"] == "PAT"   # memory lacks the quarter's owners' line: no guess (review of #363)
    monkeypatch.setenv("CARD_ADJUSTED_PROFIT_LABEL", "0")
    off = _card("Q4FY25", 23.89, "PAT", "₹87.23 Cr", "Profit after tax of Rs 87.23 crore")
    assert R.profit_label_card_json(off, memory) == [] and off["key_numbers"][0]["label"] == "PAT"


# --- blind review of release check 41338082613 (ON better 7, OFF better 12; WRONG lines ON 13, OFF 1) ---------------------------

def test_the_whole_profit_beside_an_owners_table_is_not_company_reported(monkeypatch):
    """TECHM Q2FY27: the standard whole PAT 1,609.7 against the table's owners' 1,585.6 was labelled company-reported."""
    on(monkeypatch)
    card = _card("Q2FY27", 1585.6, "Net profit", "₹1,609.70 Cr", "Net profit of Rs 1,609.7 crore")
    memory = {"financial_metrics": [{"metric": "pat_owners", "period": "Q2FY27", "value": 1585.6},
                                    {"metric": "pat", "period": "Q2FY27", "value": 1609.7}]}
    assert R.profit_label_card_json(card, memory) == [] and card["key_numbers"][0]["label"] == "Net profit"


def test_a_continuing_or_standalone_profit_in_memory_is_not_company_reported(monkeypatch):
    on(monkeypatch)
    # c07: the continuing-operations profit 151.8 beside owners' 351.24
    card = _card("Q2FY27", 351.24, "PAT", "₹151.80 Cr", "Profit from continuing operations 151.8 crore")
    memory = {"financial_metrics": [{"metric": "pat_owners", "period": "Q2FY27", "value": 351.24},
                                    {"metric": "pat_continuing", "period": "Q2FY27", "value": 151.8}]}
    assert R.profit_label_card_json(card, memory) == []
    # the standalone block's profit is memory's too
    card = _card("Q2FY27", 351.24, "PAT", "₹120.00 Cr", "PAT of Rs 120 crore")
    memory = {"financial_metrics": [{"metric": "pat", "period": "Q2FY27", "value": 351.24}],
              "standalone": {"metrics": [{"metric": "pat", "period": "Q2FY27", "value": 120.0}]}}
    assert R.profit_label_card_json(card, memory) == []


def test_a_nine_month_figure_gets_its_period_and_no_memory_labels_nothing(monkeypatch):
    on(monkeypatch)
    # c17: a nine-month 150 against the quarter's 43.05 (the nine months in the standalone block)
    card = _card("Q3FY27", 43.05, "PAT", "₹150.00 Cr", "PAT of Rs 150 crore")
    card["basis"] = "STANDALONE"
    memory = {"financial_metrics": [{"metric": "pat", "period": "Q3FY27", "value": 43.05}],
              "standalone": {"metrics": [{"metric": "pat", "period": "9MFY27", "value": 150.0}]}}
    R.profit_label_card_json(card, memory)
    assert card["key_numbers"][0]["label"] == "PAT (9MFY27)"
    # memory without the quarter's profit: nothing is labelled
    card = _card("Q3FY27", 43.05, "PAT", "₹68.00 Cr", "PAT of Rs 68 crore")
    assert R.profit_label_card_json(card, {"financial_metrics": []}) == [] and R.profit_label_card_json(card, None) == []


# --- review of #363: memory that cannot rule out the missing line labels nothing -------------------------------------------------

def test_a_figure_memory_does_not_hold_is_never_labelled(monkeypatch):
    """Reviews of #363: every "company-reported" rule leaked, so a figure memory does not hold gets nothing, however complete."""
    on(monkeypatch)
    card = _card("Q2FY27", 1585.6, "Net profit", "₹1,609.70 Cr", "Net profit of Rs 1,609.7 crore")
    owners_only = {"financial_metrics": [{"metric": "pat_owners", "period": "Q2FY27", "value": 1585.6},
                                         {"metric": "pat", "period": "H1FY27", "value": 3100.0}]}
    assert R.profit_label_card_json(card, owners_only) == [] and card["key_numbers"][0]["label"] == "Net profit"
    card = _card("Q4FY25", 23.89, "PAT", "₹87.23 Cr", "Profit after tax of Rs 87.23 crore")
    quarter_only = {"financial_metrics": [{"metric": "pat", "period": "Q4FY25", "value": 23.89},
                                          {"metric": "pat_owners", "period": "Q4FY25", "value": 23.89}]}
    assert R.profit_label_card_json(card, quarter_only) == [] and card["key_numbers"][0]["label"] == "PAT"
    # Q2 whole = owners' 22.27 and H1 60: "PAT ₹30 Cr" could be a continuing or before-minority figure: nothing
    card = _card("Q2FY27", 22.27, "PAT", "₹30.00 Cr", "PAT of Rs 30 crore")
    assert R.profit_label_card_json(card, MEM) == [] and card["key_numbers"][0]["label"] == "PAT"
    # an H1 that holds only the owners' line, and memory mixing the two blocks, label nothing that does not match
    card = _card("Q2FY27", 22.27, "PAT", "₹30.00 Cr", "PAT of Rs 30 crore")
    mixed = {"financial_metrics": [{"metric": "pat", "period": "Q2FY27", "value": 22.27},
                                   {"metric": "pat_owners", "period": "H1FY27", "value": 55.0}],
             "standalone": {"metrics": [{"metric": "pat_owners", "period": "Q2FY27", "value": 22.0}]}}
    assert R.profit_label_card_json(card, mixed) == []


def test_the_other_blocks_figure_never_tags_a_card(monkeypatch):
    # a consolidated card's ₹30 equals the standalone block's H1: not its basis, no tag
    on(monkeypatch)
    card = _card("Q2FY27", 22.27, "PAT", "₹30.00 Cr", "PAT of Rs 30 crore")
    card["basis"] = "CONSOLIDATED"
    memory = {"financial_metrics": [{"metric": "pat", "period": "Q2FY27", "value": 22.27}],
              "standalone": {"metrics": [{"metric": "pat", "period": "H1FY27", "value": 30.0}]}}
    assert R.profit_label_card_json(card, memory) == []
    card["basis"] = "STANDALONE"
    R.profit_label_card_json(card, memory)
    assert card["key_numbers"][0]["label"] == "PAT (H1FY27)"


def test_a_headline_figure_that_is_memorys_half_gets_the_half_tag(monkeypatch):
    on(monkeypatch)
    card = copy.deepcopy(TI)
    card["headline"], card["key_numbers"] = "Acme Q2FY27 PAT at ₹60 Cr", []
    notes = R.profit_label_card_json(card, MEM)
    assert card["headline"] == "Acme Q2FY27 PAT at ₹60 Cr (H1FY27)" and len(notes) == 1


def test_the_quarters_own_profit_near_its_half_gets_no_tag(monkeypatch):
    """Lead's read of #363: Q1 1.2, Q2 100, H1 101.2; the Q2 card's real PAT of 100 is within 1.5% of the half."""
    on(monkeypatch)
    memory = {"financial_metrics": [{"metric": "pat", "period": "Q1FY27", "value": 1.2},
                                    {"metric": "pat", "period": "Q2FY27", "value": 100.0},
                                    {"metric": "pat", "period": "H1FY27", "value": 101.2}]}
    card = _card("Q2FY27", 100.0, "PAT", "₹100.00 Cr", "PAT of Rs 100 crore")
    assert R.profit_label_card_json(card, memory) == [] and card["key_numbers"][0]["label"] == "PAT"
    # a half's figure apart from the quarter's still gets its tag (Q1 30, Q2 100, H1 130)
    apart = {"financial_metrics": [{"metric": "pat", "period": "Q1FY27", "value": 30.0},
                                   {"metric": "pat", "period": "Q2FY27", "value": 100.0},
                                   {"metric": "pat", "period": "H1FY27", "value": 130.0}]}
    card = _card("Q2FY27", 100.0, "PAT", "₹130.00 Cr", "PAT of Rs 130 crore for the half")
    R.profit_label_card_json(card, apart)
    assert card["key_numbers"][0]["label"] == "PAT (H1FY27)"
