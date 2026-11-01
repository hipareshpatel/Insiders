"""CARD_COMPARATIVE_MATCHES_MEMORY (blind audit 1 Nov 2026, MASKINVEST nse-106838206): a scanned statement read with its columns
out of order; the card's Q1FY27 figures were the year-ago quarter's. The texts and memory are the live card's and memory's."""

from bse_intel import comparative_memory as C

MEMORY = {"financial_metrics": [{"metric": "pat", "period": "Q1FY27", "value": -0.02},
                                {"metric": "revenue", "period": "Q1FY27", "value": 0.02},
                                {"metric": "pat", "period": "Q1FY26", "value": -0.04},
                                {"metric": "revenue", "period": "Q1FY26", "value": 0.03}]}
TEXTS = ["Total revenue for Q2FY27 stood at **₹0.04 Cr** compared to **₹0.03 Cr** in Q1FY27.",
         "The company reported a net loss of **₹0.02 Cr** in Q2FY27 versus a net loss of **₹0.04 Cr** in Q1FY27."]


def test_earlier_quarters_that_contradict_memory_are_found(monkeypatch):
    monkeypatch.setenv("CARD_COMPARATIVE_MATCHES_MEMORY", "1")
    found = C.contradictions(TEXTS, MEMORY)
    assert found == ["revenue Q1FY27: the card says ₹0.03 Cr, memory (the exchange's file) ₹0.02 Cr",
                     "pat Q1FY27: the card says ₹0.04 Cr, memory (the exchange's file) ₹0.02 Cr"]


def test_figures_that_agree_or_that_memory_lacks_are_left(monkeypatch):
    monkeypatch.setenv("CARD_COMPARATIVE_MATCHES_MEMORY", "1")
    right = ["Revenue of ₹0.04 Cr against ₹0.02 Cr in Q1FY27; net loss of ₹0.01 Cr versus ₹0.02 Cr in Q1FY27."]
    assert C.contradictions(right, MEMORY) == []
    assert C.contradictions(["Revenue ₹5 Cr against ₹4 Cr in Q4FY25."], MEMORY) == []   # memory has no Q4FY25
    assert C.contradictions(TEXTS, None) == [] and C.contradictions(TEXTS, {}) == []


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("CARD_COMPARATIVE_MATCHES_MEMORY", raising=False)
    monkeypatch.delenv("REPO_VARS", raising=False)
    monkeypatch.setenv("BSE_INTEL_SWITCHES", "/no/such/file.toml")
    assert C.contradictions(TEXTS, MEMORY) == []


def test_a_standalone_figure_is_never_set_against_consolidated_memory(monkeypatch):
    """Blind review of release check 41318733817: 4 holds set a standalone card figure against consolidated memory
    (1,274.46 vs 1,240.62; 881.52 vs 910.73)."""
    monkeypatch.setenv("CARD_COMPARATIVE_MATCHES_MEMORY", "1")
    m = lambda b, v: {"metric": "revenue", "period": "Q1FY27", "value": v, "basis": b}  # noqa: E731
    memory = {"financial_metrics": [m("CONSOLIDATED", 1240.62), m("STANDALONE", 1274.46)]}
    text = ["Revenue of ₹1,300 Cr against ₹1,274.46 Cr in Q1FY27."]
    assert C.contradictions(text, memory, "STANDALONE") == []                       # main: held against 1,240.62
    assert C.contradictions(["Standalone revenue ₹1,300 Cr against ₹1,274.46 Cr in Q1FY27."], memory, "CONSOLIDATED") == []
    assert C.contradictions(text, memory, "CONSOLIDATED") == [
        "revenue Q1FY27: the card says ₹1274.46 Cr, memory (the exchange's file) ₹1240.62 Cr"]
    # the card's basis unknown and memory on two bases: not judged
    assert C.contradictions(text, memory) == []
    # memory on the other basis only: not judged
    assert C.contradictions(text, {"financial_metrics": [m("CONSOLIDATED", 1240.62)]}, "STANDALONE") == []
