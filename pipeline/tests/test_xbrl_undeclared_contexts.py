"""NSE banking files of March 2023 that tag figures to contexts they never declare (OneD, FourD, OneI)."""
from datetime import date
from pathlib import Path

from bse_intel import xbrl, xbrl_facts

FIXTURE = Path(__file__).parent / "fixtures" / "nse_mahabank_q4fy23_cons_undeclared.xml"


def test_undeclared_legacy_contexts_are_dated_from_the_file():
    data = FIXTURE.read_bytes()
    doc = xbrl_facts.parse_facts(data, "532525", "u")
    assert doc["period"] == "Q4FY23" and doc["n_facts"] > 200          # was 64: the segment rows alone
    facts = xbrl_facts.Facts(doc)
    end = date(2023, 3, 31)
    assert facts.cr("InterestEarned", end=end, months=3) == 4495.46
    assert facts.cr("InterestEarned", end=end, months=12) == 15898.6
    assert facts.cr("ProfitLossForThePeriod", end=end, months=12) == 2602.79
    result = xbrl.parse(data)
    assert result.period == "Q4FY23" and result.basis == "CONSOLIDATED"


def test_declared_contexts_are_left_alone():
    data = FIXTURE.read_bytes().replace(b'contextRef="OneD"', b'contextRef="Nowhere"')
    doc = xbrl_facts.parse_facts(data, "532525", "u")
    assert "Nowhere" not in doc["contexts"]
