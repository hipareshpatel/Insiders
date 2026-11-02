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
    assert C.contradictions(["Q2FY27 PAT of ₹4 Cr against ₹3 Cr in Q1FY27."], memory, "CONSOLIDATED") == []
    assert C.contradictions(["Q2FY27 PAT of ₹4 Cr against ₹3.50 Cr in Q1FY27."], memory, "CONSOLIDATED") != []   # a two-decimal figure is


def test_an_adjusted_figure_is_never_held(monkeypatch):
    """c13 BLUESTONE: adjusted EBITDA 147.4 against the reported 125.74."""
    on(monkeypatch)
    memory = {"financial_metrics": [_f("ebitda", "Q1FY27", 125.74, "CONSOLIDATED")]}
    assert C.contradictions(["Adjusted EBITDA of ₹160 Cr against ₹147.4 Cr in Q1FY27."], memory, "CONSOLIDATED") == []


def test_a_segment_figure_given_as_revenue_is_still_held(monkeypatch):
    """c10, a right hold: the CDMO segment's 1,708 given as the company's revenue against the file's 2,752."""
    on(monkeypatch)
    memory = {"financial_metrics": [_f("revenue", "Q1FY27", 2752.0, "CONSOLIDATED")]}
    assert C.contradictions(["Q2FY27 revenue of ₹1,900 Cr against ₹1,708 Cr in Q1FY27."], memory, "CONSOLIDATED") == [
        "revenue Q1FY27: the card says ₹1708 Cr, memory (the exchange's file) ₹2752 Cr"]


def test_a_source_stored_in_lakh_is_compared_in_crore(monkeypatch):
    """Lead's review of #369: a file source of 500 in lakh is ₹5 Cr, never ₹500 Cr."""
    on(monkeypatch)
    row = _f("revenue", "Q1FY27", 500.0, "CONSOLIDATED")
    row["sources"][0]["unit"] = "INR_LAKH"
    memory = {"financial_metrics": [row]}
    assert C.contradictions(["Q2FY27 revenue of ₹6 Cr against ₹5 Cr in Q1FY27."], memory, "CONSOLIDATED") == []
    assert C.contradictions(["Q2FY27 revenue of ₹6 Cr against ₹50 Cr in Q1FY27."], memory, "CONSOLIDATED") == [
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


# --- blind read of release check 41369856320: five right figures held -----------------------------------------------------------

def test_the_cards_own_quarter_is_never_a_comparative(monkeypatch):
    """ABCAPITAL nse-106608107: its own Q4FY26 consolidated PAT 1,124 (the company's figure) against the file's 1,164.72."""
    on(monkeypatch)
    memory = {"financial_metrics": [_f("pat", "Q4FY26", 1164.72, "CONSOLIDATED"), _f("pat", "Q3FY26", 900.0, "CONSOLIDATED")]}
    assert C.contradictions(["Consolidated profit after tax grew 30% YoY to ₹1,124 crore in Q4 FY26."], memory, "CONSOLIDATED") == []
    # an earlier quarter beside it is still compared
    assert C.contradictions(["Consolidated PAT of ₹1,124 crore in Q4 FY26 against ₹800 crore in Q3FY26."], memory,
                            "CONSOLIDATED") == ["pat Q3FY26: the card says ₹800 Cr, memory (the exchange's file) ₹900 Cr"]


def test_net_sales_value_and_net_revenue_are_the_companys_own_measure(monkeypatch):
    """UNITDSPR nse-106623104 (NSV 3,054 against the file's 6,855) and TI nse-106648311 ("net revenue" 384 against 881.18 gross of
    excise)."""
    on(monkeypatch)
    memory = {"financial_metrics": [_f("revenue", "Q4FY25", 881.18, "CONSOLIDATED"), _f("revenue", "Q3FY26", 6600.0, "CONSOLIDATED")]}
    for text in ("Net revenue reached ₹949 crore in Q4FY26 compared to ₹384 crore in Q4 FY25.",
                 "Q4FY26 net sales value of ₹3,054 Cr against ₹2,950 Cr in Q3FY26.",
                 "Q4FY26 NSV at ₹3,054 Cr against ₹2,950 Cr in Q3FY26."):
        assert C.contradictions([text], memory, "CONSOLIDATED") == [], text


def test_a_subsidiarys_figures_are_never_set_against_the_parents_memory(monkeypatch):
    """VEDL nse-106599776: "HZL's Q4 consolidated revenue ... net profit of ₹5,033 Cr, compared to ₹3,003 Cr in Q4 FY25" against
    Vedanta's own Q4FY25 PAT 4,961."""
    on(monkeypatch)
    memory = {"financial_metrics": [_f("pat", "Q4FY25", 4961.0, "CONSOLIDATED")]}
    for text in ("HZL's Q4FY26 consolidated revenue reached ₹13,544 Cr with net profit of ₹5,033 Cr, compared to ₹3,003 Cr in Q4 FY25.",
                 "The subsidiary's Q4FY26 net profit was ₹5,033 Cr against ₹3,003 Cr in Q4FY25."):
        assert C.contradictions([text], memory, "CONSOLIDATED") == [], text
    # the company's own words still hold, its own name's possessive too (lead, 2 Nov 2026)
    assert C.contradictions(["Q4FY26 consolidated net profit ₹5,033 Cr against ₹3,003 Cr in Q4FY25."], memory, "CONSOLIDATED") != []
    names = ("Vedanta Limited", "VEDL")
    assert C.contradictions(["HZL's Q4FY26 net profit ₹5,033 Cr against ₹3,003 Cr in Q4 FY25."], memory, "CONSOLIDATED", names) == []
    assert C.contradictions(["Vedanta's Q4FY26 net profit ₹5,033 Cr against ₹3,003 Cr in Q4FY25."], memory, "CONSOLIDATED", names) != []


def test_the_cards_own_company_possessive_still_holds(monkeypatch):
    """Lead, 2 Nov 2026: "Infosys's Q3FY26 PAT" on an Infosys card is its own figure; HZL's on it is not."""
    on(monkeypatch)
    memory = {"financial_metrics": [_f("pat", "Q3FY26", 6800.0, "CONSOLIDATED")]}
    text = "Infosys's Q4FY26 PAT of ₹7,000 Cr against ₹6,500 Cr in Q3FY26."
    assert C.contradictions([text], memory, "CONSOLIDATED", ("Infosys Limited", "INFY")) == [
        "pat Q3FY26: the card says ₹6500 Cr, memory (the exchange's file) ₹6800 Cr"]
    assert C.contradictions(["INFY's Q4FY26 PAT of ₹7,000 Cr against ₹6,500 Cr in Q3FY26."], memory, "CONSOLIDATED",
                            ("Infosys Limited", "INFY")) != []
    assert C.contradictions(["Wipro's Q4FY26 PAT of ₹7,000 Cr against ₹6,500 Cr in Q3FY26."], memory, "CONSOLIDATED",
                            ("Infosys Limited", "INFY")) == []
    assert C.contradictions([text], memory, "CONSOLIDATED") == []   # no names known: a named possessive is another's (safe side)
    # "The Company's" is the card's own
    assert C.contradictions(["The Company's Q4FY26 PAT of ₹7,000 Cr against ₹6,500 Cr in Q3FY26."], memory, "CONSOLIDATED") != []
    assert C._own_names(("Hindustan Zinc Limited", "HINDZINC")) >= {"hindustan", "zinc", "hz", "hzl", "hindzinc"}


# --- STARHEALTH nse-106715707: insurers moved to Ind AS 117 in FY27 (facts-dump 41383638958) ------------------------------------

def _filed(metric, period, value, url, basis="STANDALONE"):
    row = _f(metric, period, value, basis)
    row["sources"][0]["lab"]["file_url"] = url
    return row


GI_Q4FY26 = "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_GI_1660681_28042026085314_WEB.xml"
IND_AS_Q1FY27 = "https://nsearchives.nseindia.com/corporate/xbrl/IF_INS_COM_IND_AS_19799_WebXMLFile_20261020_191249443.xml"


def test_an_insurers_igaap_figure_is_never_set_against_its_ind_as_restatement(monkeypatch):
    """The Q4FY26 GI file states PAT 111.33 Cr (ProfitLossAfterTax); the Q1FY27 Ind AS filing restates the quarter as a loss of
    ₹55.4 Cr. Both are right, under two standards."""
    on(monkeypatch)
    memory = {"financial_metrics": [_filed("pat", "Q4FY26", 111.33, GI_Q4FY26)]}
    text = "Star Health Q1FY27 PAT of ₹549.7 Cr against a loss of ₹55.4 Cr in Q4FY26."
    assert C.contradictions([text], memory, "STANDALONE") == []
    # a card of FY26 itself against the same file is still compared
    assert C.contradictions(["Star Health Q4FY26 PAT of ₹200 Cr against ₹55.4 Cr in Q3FY26."],
                            {"financial_metrics": [_filed("pat", "Q3FY26", 128.22, GI_Q4FY26)]}, "STANDALONE") != []


def test_an_ind_as_to_ind_as_comparison_still_holds(monkeypatch):
    on(monkeypatch)
    memory = {"financial_metrics": [_filed("pat", "Q1FY27", 549.73, IND_AS_Q1FY27)]}
    assert C.contradictions(["Star Health Q2FY27 PAT of ₹264.8 Cr against ₹600 Cr in Q1FY27."], memory, "STANDALONE") == [
        "pat Q1FY27: the card says ₹600 Cr, memory (the exchange's file) ₹549.73 Cr"]
