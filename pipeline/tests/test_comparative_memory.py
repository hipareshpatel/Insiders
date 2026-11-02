"""CARD_COMPARATIVE_MATCHES_MEMORY (blind audit 1 Nov 2026, MASKINVEST nse-106838206): a scanned statement read with its columns
out of order; the card's Q1FY27 figures were the year-ago quarter's. The texts and memory are the live card's and memory's.

Blind read of release check 41345924894 (ON better 11, OFF better 9): a hold only on the card's own basis, only against a figure
the exchange's own file gave, at the card's printed precision, and never for an adjusted figure."""

from bse_intel import comparative_memory as C


def _f(metric, period, value, basis="STANDALONE", by="file"):
    """A memory row whose one source is labelled ``by`` on ``basis``."""
    return {"metric": metric, "period": period, "value": value,
            "sources": [{"news_id": f"xbrl:res:1:{period}", "value": value, "basis": basis, "lab": {"by": by, "basis": basis}}]}


MEMORY = {"financial_metrics": [_f("pat", "Q1FY27", -0.02), _f("revenue", "Q1FY27", 0.02),
                                _f("pat", "Q1FY26", -0.04), _f("revenue", "Q1FY26", 0.03)]}
TEXTS = ["Total revenue for Q2FY27 stood at **₹0.04 Cr** compared to **₹0.03 Cr** in Q1FY27.",
         "The company reported a net loss of **₹0.02 Cr** in Q2FY27 versus a net loss of **₹0.04 Cr** in Q1FY27."]


def on(monkeypatch):
    monkeypatch.setenv("CARD_COMPARATIVE_MATCHES_MEMORY", "1")


def test_earlier_quarters_that_contradict_memory_are_found(monkeypatch):
    on(monkeypatch)
    found = C.contradictions(TEXTS, MEMORY, "STANDALONE")
    assert found == ["revenue Q1FY27: the card says ₹0.03 Cr, memory (the exchange's file) ₹0.02 Cr",
                     "pat Q1FY27: the card says ₹0.04 Cr, memory (the exchange's file) ₹0.02 Cr"]


def test_figures_that_agree_or_that_memory_lacks_are_left(monkeypatch):
    on(monkeypatch)
    right = ["Revenue of ₹0.04 Cr against ₹0.02 Cr in Q1FY27; net loss of ₹0.01 Cr versus ₹0.02 Cr in Q1FY27."]
    assert C.contradictions(right, MEMORY, "STANDALONE") == []
    assert C.contradictions(["Revenue ₹5 Cr against ₹4 Cr in Q4FY25."], MEMORY, "STANDALONE") == []   # memory has no Q4FY25
    assert C.contradictions(TEXTS, None, "STANDALONE") == [] and C.contradictions(TEXTS, {}, "STANDALONE") == []


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("CARD_COMPARATIVE_MATCHES_MEMORY", raising=False)
    monkeypatch.delenv("REPO_VARS", raising=False)
    monkeypatch.setenv("BSE_INTEL_SWITCHES", "/no/such/file.toml")
    assert C.contradictions(TEXTS, MEMORY, "STANDALONE") == []


def test_a_standalone_figure_is_never_set_against_consolidated_memory(monkeypatch):
    """c06 (standalone revenue 1,276.25 against consolidated 1,308.14), c16 (standalone PAT 1,065.59 against 1,530.10)."""
    on(monkeypatch)
    memory = {"financial_metrics": [_f("revenue", "Q1FY27", 1308.14, "CONSOLIDATED"), _f("pat", "Q1FY27", 1530.10, "CONSOLIDATED")]}
    assert C.contradictions(["Revenue of ₹1,350 Cr against ₹1,276.25 Cr in Q1FY27."], memory, "STANDALONE") == []
    assert C.contradictions(["Standalone PAT of ₹1,100 Cr against ₹1,065.59 Cr in Q1FY27."], memory, "CONSOLIDATED") == []
    # the card's basis unknown: no hold
    assert C.contradictions(["Revenue of ₹1,350 Cr against ₹1,276.25 Cr in Q1FY27."], memory) == []
    # memory with no basis: no hold
    bare = {"financial_metrics": [{"metric": "revenue", "period": "Q1FY27", "value": 1308.14,
                                   "sources": [{"news_id": "x", "value": 1308.14, "lab": {"by": "file"}}]}]}
    assert C.contradictions(["Revenue of ₹1,350 Cr against ₹1,276.25 Cr in Q1FY27."], bare, "CONSOLIDATED") == []


def test_memory_not_from_the_exchanges_file_holds_nothing(monkeypatch):
    """c02 IOB PAT 1,912 against memory's 1,962.67 (not in the filing), c03 STARHEALTH loss 55.4 against 111.33, c19 TAJGVK 28.60
    against 34.8, c09 EBITDA (19.2) against a calculated figure."""
    on(monkeypatch)
    for metric, value, by, text in (("pat", 1962.67, "ai", "Net profit of ₹2,000 Cr against ₹1,912 Cr in Q1FY27."),
                                    ("pat", -111.33, "ai", "Net loss of ₹40 Cr against a loss of ₹55.4 Cr in Q1FY27."),
                                    ("pat", 34.8, "unknown", "PAT of ₹30 Cr against ₹28.60 Cr in Q1FY27."),
                                    ("ebitda", -5.6, "calc", "EBITDA of ₹-10 Cr against ₹-19.2 Cr in Q1FY27.")):
        memory = {"financial_metrics": [_f(metric, "Q1FY27", value, "CONSOLIDATED", by)]}
        assert C.contradictions([text], memory, "CONSOLIDATED") == [], text


def test_a_figure_is_compared_at_its_printed_precision(monkeypatch):
    """c17: the card's whole-crore "₹3 Cr" is memory's 3.11."""
    on(monkeypatch)
    memory = {"financial_metrics": [_f("pat", "Q1FY27", 3.11, "CONSOLIDATED")]}
    assert C.contradictions(["PAT of ₹4 Cr against ₹3 Cr in Q1FY27."], memory, "CONSOLIDATED") == []
    assert C.contradictions(["PAT of ₹4 Cr against ₹3.50 Cr in Q1FY27."], memory, "CONSOLIDATED") != []   # a two-decimal figure is


def test_an_adjusted_figure_is_never_held(monkeypatch):
    """c13 BLUESTONE: adjusted EBITDA 147.4 against the reported 125.74."""
    on(monkeypatch)
    memory = {"financial_metrics": [_f("ebitda", "Q1FY27", 125.74, "CONSOLIDATED")]}
    assert C.contradictions(["Adjusted EBITDA of ₹160 Cr against ₹147.4 Cr in Q1FY27."], memory, "CONSOLIDATED") == []


def test_a_segment_figure_given_as_revenue_is_still_held(monkeypatch):
    """c10, a right hold: the CDMO segment's 1,708 given as the company's revenue against the file's 2,752."""
    on(monkeypatch)
    memory = {"financial_metrics": [_f("revenue", "Q1FY27", 2752.0, "CONSOLIDATED")]}
    assert C.contradictions(["Revenue of ₹1,900 Cr against ₹1,708 Cr in Q1FY27."], memory, "CONSOLIDATED") == [
        "revenue Q1FY27: the card says ₹1708 Cr, memory (the exchange's file) ₹2752 Cr"]


def test_a_source_stored_in_lakh_is_compared_in_crore(monkeypatch):
    """Lead's review of #369: a file source of 500 in lakh is ₹5 Cr, never ₹500 Cr."""
    on(monkeypatch)
    row = _f("revenue", "Q1FY27", 500.0, "CONSOLIDATED")
    row["sources"][0]["unit"] = "INR_LAKH"
    memory = {"financial_metrics": [row]}
    assert C.contradictions(["Revenue of ₹6 Cr against ₹5 Cr in Q1FY27."], memory, "CONSOLIDATED") == []
    assert C.contradictions(["Revenue of ₹6 Cr against ₹50 Cr in Q1FY27."], memory, "CONSOLIDATED") == [
        "revenue Q1FY27: the card says ₹50 Cr, memory (the exchange's file) ₹5 Cr"]


def test_a_dollar_or_share_count_source_is_no_crore_figure(monkeypatch):
    """Lead's review of #370: USD_MN 5 was read as ₹50 Cr (USD_* and SHARES_* are in the stored-scale table)."""
    on(monkeypatch)
    for unit in ("USD_MN", "SHARES_CR", "PCT"):
        row = _f("revenue", "Q1FY27", 5.0, "CONSOLIDATED")
        row["sources"][0]["unit"] = unit
        assert C.contradictions(["Revenue of ₹60 Cr against ₹50 Cr in Q1FY27."], {"financial_metrics": [row]}, "CONSOLIDATED") == [], unit
    row = _f("revenue", "Q1FY27", 500.0, "CONSOLIDATED")
    row["sources"][0]["unit"] = "INR_MN"
    assert C.contradictions(["Revenue of ₹60 Cr against ₹50 Cr in Q1FY27."], {"financial_metrics": [row]}, "CONSOLIDATED") == []
