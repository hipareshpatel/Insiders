from pathlib import Path

from bse_intel import gate


def test_results_cards_recent_is_newest_first():
    """F156: oldest first spent the run's company slots on the cards least likely to be due."""
    sql = (Path(__file__).resolve().parents[2] / "db" / "queries" / "results_cards_recent.sql").read_text(encoding="utf-8")
    order = [l for l in sql.splitlines() if l.strip().startswith("ORDER BY")]
    assert order and "c.filed_at DESC" in order[0]


def test_quote_exact_numbers_switch(monkeypatch):
    """F156: the digit-prefix match ("95" of "951.96", "951.96" of "95") is off under QUOTE_EXACT_NUMBERS=1."""
    monkeypatch.delenv("QUOTE_EXACT_NUMBERS", raising=False)
    quote = "Revenue 951.96"
    assert gate.numbers_in_quote("Sales of 95 units", quote) == []                     # old: "95" passes by prefix
    monkeypatch.setenv("QUOTE_EXACT_NUMBERS", "1")
    assert gate.numbers_in_quote("Sales of 95 units", quote) == ["95"]
    assert gate.numbers_in_quote("Revenue 951.96", "Revenue 95") == ["951.96"]
    assert gate.numbers_in_quote("Revenue ₹951.96 Cr", "Revenue 9,51.96") == []              # grouping is not part of it
    assert gate.numbers_in_quote("Revenue ₹952 Cr", quote) == []                             # own rounding still fine


def test_sek_amount_is_not_rupees():
    from bse_intel.grounding import foreign_amounts, foreign_as_rupees
    assert foreign_amounts("order worth SEK 120 million")[0][0] == 120.0
    assert foreign_amounts("fee of THB 45 million")[0][0] == 45.0
    assert foreign_as_rupees(["order of ₹120 million"], "order worth SEK 120 million")
    assert gate.numbers_in_quote("SEK 9.7 million order", "order SEK 9.7 million") == []
    assert gate._FOREIGN.search("sek ") and gate._FOREIGN.search("thb ")


def test_a_currency_code_inside_a_word_is_not_a_currency():
    import re
    from bse_intel.currency import TAIL_PATTERN
    tail = re.compile(TAIL_PATTERN)
    for text in ("revenue in the country ", "our brand ", "pipeline details ", "the cop ", "pen "):
        assert (tail.search(text) is not None) == (text.strip() in ("the cop", "pen")), text
    assert tail.search("sek ") and tail.search("thb ") and tail.search("us$")
