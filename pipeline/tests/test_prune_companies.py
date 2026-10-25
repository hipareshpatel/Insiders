import json

import pytest

from bse_intel import prune_companies as pc
from bse_intel.nse import Equity, parse_sme_list
from bse_intel.sinks.local import LocalSink


def _equities():
    rows = [Equity("TCS", "Tata Consultancy Services Limited", "INE467B01029"),
            Equity("SPELS", "SPEL Semiconductor Limited", "INE0KOP01011"),
            Equity("NOISIN", "No Isin Limited", "INE000N01011")]
    return rows + [Equity(f"S{i}", f"Filler {i}", f"INE9{i:07d}") for i in range(pc.MIN_NSE_ROWS)]


SME = [Equity("RAVITA", "Ravita Engineering", "INE1UEL01023")] + [Equity(f"M{i}", f"Sme {i}", f"INE8{i:07d}") for i in range(pc.MIN_SME_ROWS)]

ROWS = [
    {"scrip_code": "532540", "symbol": "TCS", "company_name": "Tata Consultancy Services Limited", "isin": "INE467B01029"},
    {"scrip_code": "SPELS", "symbol": "SPELS", "company_name": "SPEL Semiconductor Limited", "isin": "INE0KOP01011"},
    {"scrip_code": "540956", "symbol": "BHATIA", "company_name": "Bhatia Communications", "isin": "INE0AAA01010"},
    {"scrip_code": "590115", "symbol": "MOM50", "company_name": "Motilal Oswal Nifty 50 ETF", "isin": "INF247L01AB1"},
    {"scrip_code": "544900", "symbol": "FOOREIT", "company_name": "Foo REIT", "isin": "INE0BBB23010"},
    {"scrip_code": "544901", "symbol": "RAVITA", "company_name": "Ravita Engineering", "isin": "INE1UEL01023"},
    {"scrip_code": "531847", "symbol": "ASIANSTR", "company_name": "Asian Star Co", "isin": "INE0CCC01011"},   # has a card
    {"scrip_code": "519397", "symbol": "SHARAT", "company_name": "Sharat Industries", "isin": "INE0DDD01012"},   # starred
    {"scrip_code": "500999", "symbol": "TCS", "company_name": "Other Co Same Symbol", "isin": "INE0EEE01013"},   # symbol clash
]


def _sink(settings):
    sink = LocalSink(settings)
    sink.execute("companies_upsert", [dict(r, updated_at="x") for r in ROWS])
    sink._db.execute("UPDATE companies SET watchlist = 1 WHERE scrip_code = '519397'")
    sink._db.execute(
        "INSERT INTO cards (news_id, scrip_code, filing_date, filed_at, event_category, impact_level, headline, card_json)"
        " VALUES ('n1', '531847', '2026-10-01', '2026-10-01T10:00:00+05:30', 'X', 'LOW', 'h', '{}')")
    sink._db.commit()
    sink.execute("catalysts_upsert", [{"id": "c1", "scrip_code": "540956", "event_type": "AGM", "event_date": "2026-12-01"}])
    for scrip in ("540956", "590115", "531847", "532540", "SPELS"):
        sink.put_dossier(scrip, {"scrip_code": scrip, "financial_metrics": [{"metric": "revenue"}], "ownership": [{}, {}]})
    return sink


def _ids(rows):
    return {r["scrip_code"] for r in rows}


def test_classify():
    nse = {"INE467B01029"}
    f = lambda c: pc.classify(c, nse, {"TCS"}, {"INE1UEL01023"}, {"RAVITA"})  # noqa: E731
    assert f({"scrip_code": "1", "isin": "INE467B01029"}) == "nse"
    assert f({"scrip_code": "1", "isin": "INF1", "symbol": "X"}) == pc.FUND
    assert f({"scrip_code": "1", "isin": "INE1UEL01023"}) == pc.SME
    assert f({"scrip_code": "1", "isin": "INE5", "company_name": "Foo InvIT"}) == pc.REIT
    assert f({"scrip_code": "1", "isin": "INE5", "company_name": "Foo Ltd"}) == pc.BSE_ONLY
    assert f({"scrip_code": "1", "isin": "INE5", "symbol": "TCS"}) == "isin_mismatch"      # kept, reported
    assert f({"scrip_code": "TCS", "isin": None}) == "nse"                                  # symbol-keyed new listing


def test_dry_run_report(settings):
    report = pc.plan(_sink(settings), _equities(), SME)
    assert _ids(report["remove"]) == {"540956", "590115", "544900", "544901"}
    types = {r["scrip_code"]: r["type"] for r in report["remove"]}
    assert types == {"540956": pc.BSE_ONLY, "590115": pc.FUND, "544900": pc.REIT, "544901": pc.SME}
    assert _ids(report["has_cards"]) == {"531847", "519397"}      # a card, and a star: reported, never removed
    assert _ids(report["isin_mismatch_kept"]) == {"500999"}
    assert report["nse_kept"] == 2
    removed = {r["scrip_code"]: r for r in report["remove"]}
    assert removed["540956"]["memory"] == {"financial_metrics": 1, "ownership": 2}
    assert removed["544900"]["has_memory"] is False
    assert report["summary"]["to_remove_by_type"][pc.FUND]["with_memory"] == 1
    assert "to remove" in pc.render(report) and pc.to_csv(report).startswith("action,type")


def test_keep_sme(settings):
    report = pc.plan(_sink(settings), _equities(), SME, keep_sme=True)
    assert "544901" not in _ids(report["remove"]) and report["nse_kept"] == 3


def test_refuses_a_broken_nse_list(settings):
    sink = _sink(settings)
    with pytest.raises(ValueError):
        pc.plan(sink, _equities()[:5], SME)
    with pytest.raises(ValueError):
        pc.plan(sink, _equities(), [])


def test_dry_run_changes_nothing(settings):
    sink = _sink(settings)
    pc.plan(sink, _equities(), SME)
    assert len(sink.query("companies_prune_counts", ["", 100])) == len(ROWS)
    assert sink.list_objects("backup/") == [] and sink.get_dossier("540956")


def test_apply_backs_up_then_deletes(settings, monkeypatch):
    sink = _sink(settings)
    report = pc.plan(sink, _equities(), SME)
    order = []
    real_put, real_delete, real_exec = sink.put_object, sink.delete_object, sink.execute
    monkeypatch.setattr(sink, "put_object", lambda *a, **k: (order.append("backup"), real_put(*a, **k))[1])
    monkeypatch.setattr(sink, "delete_object", lambda *a, **k: (order.append("delete_object"), real_delete(*a, **k))[1])
    monkeypatch.setattr(sink, "execute", lambda s, r: (order.append(s), real_exec(s, r))[1])
    done = pc.apply(sink, report, "2026-10-26")
    assert order[0] == "backup" and order.index("backup") < order.index("companies_prune") < order.index("delete_object")
    assert done["removed"] == 4 and done["memory_deleted"] == 2 and done["backup"] == "backup/prune-companies-2026-10-26.json"
    left = _ids(sink.query("companies_prune_counts", ["", 100]))
    assert left == {"532540", "SPELS", "531847", "519397", "500999"}
    assert sink.get_dossier("540956") is None and sink.get_dossier("590115") is None
    assert sink.get_dossier("531847") and sink.get_dossier("532540")     # a company with a card keeps its memory
    assert not sink._db.execute("SELECT 1 FROM catalysts").fetchall()
    backup = json.loads(sink.get_object(done["backup"]))
    assert _ids(backup["companies"]) == {"540956", "590115", "544900", "544901"}
    assert set(backup["memory"]) == {"memory/540956.json", "memory/590115.json"}
    assert backup["memory"]["memory/540956.json"]["ownership"] == [{}, {}]


def test_sql_guard_keeps_a_company_that_gained_a_card(settings):
    sink = _sink(settings)
    report = pc.plan(sink, _equities(), SME)
    sink._db.execute(
        "INSERT INTO cards (news_id, scrip_code, filing_date, filed_at, event_category, impact_level, headline, card_json)"
        " VALUES ('n2', '540956', '2026-10-02', '2026-10-02T10:00:00+05:30', 'X', 'LOW', 'h', '{}')")
    sink._db.commit()
    done = pc.apply(sink, report, "2026-10-26")
    assert done["removed"] == 3 and done["kept_by_sql_guard"] == ["540956"]
    assert sink.get_dossier("540956")                   # still there; the backup has it too
    assert "540956" in _ids(sink.query("companies_prune_counts", ["", 100]))


def test_backup_that_cannot_be_read_back_stops_before_deleting(settings, monkeypatch):
    sink = _sink(settings)
    report = pc.plan(sink, _equities(), SME)
    monkeypatch.setattr(sink, "put_object", lambda *a, **k: None)
    with pytest.raises(RuntimeError):
        pc.apply(sink, report, "2026-10-26")
    assert len(sink.query("companies_prune_counts", ["", 100])) == len(ROWS)


def test_parse_sme_list():
    text = "SYMBOL,NAME_OF_COMPANY,SERIES,DATE_OF_LISTING,PAID_UP_VALUE,ISIN_NUMBER,FACE_VALUE,\nRAVITA,Ravita Engineering Services Limited,ST,22-Oct-26,5,INE1UEL01023,5,\n"
    assert parse_sme_list(text) == [Equity("RAVITA", "Ravita Engineering Services Limited", "INE1UEL01023", "ST")]
