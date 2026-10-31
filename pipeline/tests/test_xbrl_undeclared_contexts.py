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


def test_reread_legacy_replaces_a_stored_document_that_lost_the_undeclared_contexts(monkeypatch):
    from bse_intel import xbrl_store
    from backup_objects import BackupObjects

    data = FIXTURE.read_bytes()
    url = "https://nsearchives.nseindia.com/corporate/xbrl/BANKING_90815_832437_25042023120056.xml"
    old = xbrl_facts.parse_facts(data, "532525", url)
    for ctx in ("OneD", "FourD", "OneI"):           # as stored before the fix: the facts on the undeclared contexts were dropped
        old["contexts"].pop(ctx, None)
    old["facts"] = [f for f in old["facts"] if f[1] in old["contexts"]]
    old["n_facts"], old["period"] = len(old["facts"]), "Q4FY23"
    sink = BackupObjects()
    k = xbrl_facts.key("532525", "Q4FY23", "CONSOLIDATED")
    sink.put_object(k, xbrl_facts.dumps(old))
    monkeypatch.setattr(xbrl_store, "get", lambda s, u: data if u == url else None)
    dry = xbrl_facts.reread_legacy(sink, ["532525"], dry_run=True)
    assert dry["reread"] == 1 and xbrl_facts.loads(sink.get_object(k))["n_facts"] == old["n_facts"]
    got = xbrl_facts.reread_legacy(sink, ["532525"])
    doc = xbrl_facts.loads(sink.get_object(k))
    assert got["reread"] == 1 and doc["n_facts"] > 200 and doc["period"] == "Q4FY23"
    assert xbrl_facts.reread_legacy(sink, ["532525"])["reread"] == 0       # a second pass finds nothing to do
