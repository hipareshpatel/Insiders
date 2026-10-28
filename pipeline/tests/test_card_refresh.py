"""refresh-card-blocks: a stored card's code blocks rebuilt from memory by today's code, no AI (design audit,
2026-10-20: 14 of 849 live cards carried the blocks of the 19 Oct redesign)."""

import json
from types import SimpleNamespace

from backup_objects import BackupObjects
from bse_intel import card_refresh
from bse_intel.dossier import new_dossier
from bse_intel.models import Filing

FILED = "2026-09-10T18:00:00+05:30"


def _card():
    return {"event_type": "ORDER_WIN", "impact_level": "MODERATE", "headline": "Demo Rail wins ₹120 Cr signalling order",
            "what_happened": [{"text": "Order of ₹120 Cr from Northern Railway", "quote": "order of Rs. 120 crore"}],
            "deal_value": {"amount_cr": 120.0, "counterparty": "Northern Railway", "stage": "AWARDED"},
            "signals": [{"type": "METRIC_SHIFT", "severity": "WARNING", "text": "EPS down 177%"},
                        {"type": "ORDER_FLOW", "severity": "INFO", "text": "3rd order since July"}],
            "timeline_entry": "Won a ₹120 Cr order"}


def _dossier():
    d = new_dossier(Filing(news_id="n0", scrip_code="500001", company_name="Demo Rail Ltd", headline="h", subject="",
                           filed_at="2026-05-01T10:00:00+05:30", filing_date="2026-05-01"))
    d["financial_metrics"] = [{"metric": "revenue", "period": "FY26", "value": 1200.0, "unit": "INR_CR",
                               "as_of": "2026-05-01T10:00:00+05:30", "news_id": "n0",
                               "sources": [{"news_id": "n0", "value": 1200.0, "as_of": "2026-05-01T10:00:00+05:30"}]}]
    return d


def test_an_old_card_gets_todays_blocks_and_loses_signals_now_off():
    filing = Filing(news_id="n1", scrip_code="500001", company_name="Demo Rail Ltd", headline="h", subject="",
                    filed_at=FILED, filing_date=FILED[:10])
    company = {"scrip_code": "500001", "market_cap_cr": 2400.0, "last_price": 240.0, "price_date": FILED[:10]}
    new, changed = card_refresh.refresh(_card(), _dossier(), filing, company)
    assert [s["type"] for s in new["signals"]] == ["ORDER_FLOW"]
    assert "signals" in changed and new["headline"] == _card()["headline"]   # what the model wrote is kept
    assert new["scale"] and "scale" in changed
    assert set(card_refresh.BLOCKS) <= set(new)


def test_run_writes_back_only_cards_that_changed():
    stored = [{"news_id": "n1", "scrip_code": "500001", "symbol": "DEMO", "company_name": "Demo Rail Ltd",
               "filing_date": FILED[:10], "filed_at": FILED, "headline": "h", "card_json": json.dumps(_card()), "held": 0}]

    class Sink(BackupObjects):
        written: list = []

        def query(self, name, params):
            assert name == "export_cards"
            return [r for r in stored if (r["filed_at"], r["news_id"]) > (params[0], params[1])]

        def get_dossier(self, scrip):
            return _dossier()

        def company(self, scrip):
            return {"scrip_code": scrip, "market_cap_cr": 2400.0, "last_price": 240.0, "price_date": FILED[:10]}

        def execute(self, statement, rows):
            assert statement == "cards_upsert"
            self.written += rows
            return len(rows)

    sink = Sink()
    pipeline = SimpleNamespace(sink=sink, prompts=SimpleNamespace(sector_for=lambda industry: SimpleNamespace(footer=())),
                               _prices=None, _buckets=None)
    report = card_refresh.run(pipeline)
    assert report["changed"] == 1 and report["failed"] == 0
    (row,) = sink.written
    assert "card_json" not in row and [s["type"] for s in row["card"]["signals"]] == ["ORDER_FLOW"]
    stored[0]["card_json"] = json.dumps(row["card"])
    sink.written = []
    assert card_refresh.run(pipeline)["changed"] == 0   # a second run finds nothing to change


def test_a_dry_run_can_list_each_changed_cards_blocks_before_and_after():
    stored = [{"news_id": "n1", "scrip_code": "500001", "symbol": "DEMO", "company_name": "Demo Rail Ltd",
               "filing_date": FILED[:10], "filed_at": FILED, "headline": "h", "card_json": json.dumps(_card()), "held": 0}]

    class Sink(BackupObjects):
        def query(self, name, params):
            return [r for r in stored if (r["filed_at"], r["news_id"]) > (params[0], params[1])]

        def get_dossier(self, scrip):
            return _dossier()

        def company(self, scrip):
            return {"scrip_code": scrip, "market_cap_cr": 2400.0, "last_price": 240.0, "price_date": FILED[:10]}

        def execute(self, statement, rows):
            raise AssertionError("a dry run writes nothing")

    pipeline = SimpleNamespace(sink=Sink(), prompts=SimpleNamespace(sector_for=lambda industry: SimpleNamespace(footer=())),
                               _prices=None, _buckets=None)
    diffs: list = []
    report = card_refresh.run(pipeline, dry_run=True, diffs=diffs)
    (d,) = diffs
    assert report["changed"] == 1 and d["news_id"] == "n1" and "signals" in d["changed"]
    assert set(d["before"]) == set(d["after"]) == set(d["changed"]) - {"impact"}
    assert d["before"]["signals"] == _card()["signals"] and d["after"]["signals"] != d["before"]["signals"]
    assert card_refresh.run(pipeline, dry_run=True)["changed"] == 1   # without the list: counts only, as before


def test_a_refreshed_card_with_a_clear_event_becomes_high():
    card = {**_card(), "event_type": "RESULTS", "deal_value": None, "signals": [],
            "results": {"pat": {"value": 50.0, "prev_year": 30.0, "yoy_pct": 66.7}}, "score": {"vetoes": [], "reasons": []}}
    stored = [{"news_id": "r1", "scrip_code": "500001", "symbol": "DEMO", "company_name": "Demo Rail Ltd", "impact_level": "MODERATE",
               "filing_date": FILED[:10], "filed_at": FILED, "headline": "h", "card_json": json.dumps(card), "held": 0}]

    class Sink(BackupObjects):
        written: list = []

        def query(self, name, params):
            return [r for r in stored if (r["filed_at"], r["news_id"]) > (params[0], params[1])]

        def get_dossier(self, scrip):
            return _dossier()

        def company(self, scrip):
            return None

        def execute(self, statement, rows):
            self.written += rows
            return len(rows)

    sink = Sink()
    pipeline = SimpleNamespace(sink=sink, prompts=SimpleNamespace(sector_for=lambda industry: SimpleNamespace(footer=())),
                               _prices=None, _buckets=None)
    card_refresh.run(pipeline)
    # memory holds no results for this filing: the old table stays, and its PAT +67% makes the card HIGH
    (row,) = sink.written
    assert row["card"]["results"]["pat"]["yoy_pct"] == 66.7 and row["impact_level"] == "HIGH"
    assert row["card"]["score"]["reasons"] == ["Impact: PAT +67% YoY"]


def test_export_held_writes_only_held_cards(tmp_path):
    from bse_intel.cli import cmd_export_held

    rows = [{"news_id": "a", "scrip_code": "1", "filed_at": FILED, "held": 1, "card_json": json.dumps({"headline": "A"})},
            {"news_id": "b", "scrip_code": "1", "filed_at": FILED, "held": 0, "card_json": json.dumps({"headline": "B"})}]

    class Sink(BackupObjects):
        def query(self, name, params):
            return [r for r in rows if (r["filed_at"], r["news_id"]) > (params[0], params[1])]

    out = tmp_path / "held.json"
    assert cmd_export_held(SimpleNamespace(out=str(out)), None, Sink()) == 0
    assert [c["news_id"] for c in json.loads(out.read_text())] == ["a"]


def test_a_refresh_without_the_text_never_brings_back_a_comparative():
    """Review 6 (2026-10-20): a refresh rebuilt Kanoria's table with the year-ago column the pipeline had taken off as
    restated. With no text to judge it, a comparative the stored table lacks stays out; with the cached text it is
    judged as when the card was written."""
    d = _dossier()
    src = lambda news_id, value: {"news_id": news_id, "value": value, "as_of": "2026-05-01T10:00:00+05:30"}
    d["financial_metrics"] = [
        {"metric": metric, "period": period, "value": value, "sources": [src(n, value) for n in ids]}
        for metric, period, value, ids in (
            ("revenue", "Q1FY27", 304.39, ("r1",)), ("revenue", "Q1FY26", 431.42, ("n0", "r1")),
            ("revenue", "Q4FY26", 265.82, ("n0", "r1")),
            ("pat", "Q1FY27", 31.62, ("r1",)), ("pat", "Q1FY26", -40.11, ("n0", "r1")), ("pat", "Q4FY26", 3.55, ("n0",)))]
    stored = {"period": "Q1FY27", "prev_year_period": "Q1FY26", "prev_quarter_period": "Q4FY26",
              "revenue": {"value": 304.39, "prev_quarter": 265.82, "qoq_pct": 14.5},
              "pat": {"value": 31.62, "prev_quarter": 3.55, "qoq_pct": 790.7}}
    card = {**_card(), "event_type": "RESULTS", "deal_value": None, "results": stored}
    filing = Filing(news_id="r1", scrip_code="500001", company_name="Demo Rail Ltd", headline="h", subject="",
                    filed_at=FILED, filing_date=FILED[:10])
    new, _ = card_refresh.refresh(card, d, filing, None)
    assert "prev_year" not in new["results"]["revenue"] and "prev_year" not in new["results"]["pat"]
    assert new["results"]["revenue"]["prev_quarter"] == 265.82
    # the text prints memory's year-ago figures: judged, they come back
    text = "(Rs. in lakh) Revenue 30,439 26,582 43,142\nProfit for the period 3,162 355 (4,011)"
    new, _ = card_refresh.refresh(card, d, filing, None, printed=text)
    assert new["results"]["revenue"]["prev_year"] == 431.42


def test_the_refresh_reads_the_cached_text_when_there_is_one():
    seen = []
    pipeline = SimpleNamespace(_cached_text=lambda news_id: seen.append(news_id) or None)
    assert card_refresh.filed_text(pipeline, "r1") is None and seen == ["r1"]
    assert card_refresh.filed_text(SimpleNamespace(), "r1") is None   # GitHub's maintenance: no cache


def test_a_stored_call_card_gives_memory_its_checked_takeaways():
    """Cards written before the takeaways went into memory (2026-10-21): the refresh puts their verified ones there,
    once, for the company page's quarterly summary."""
    card = {**_card(), "event_type": "CONCALL_PRESENTATION", "call_takeaways": [
        {"category": "Guidance", "text": "Deposit growth guided at 11-12% for FY27", "verified": True, "versus_prior": "raised from 9-11%"},
        {"category": "Risks", "text": "Credit cost guided below 0.5%", "verified": False}]}
    stored = [{"news_id": "n1", "scrip_code": "500001", "symbol": "DEMO", "company_name": "Demo Rail Ltd",
               "filing_date": FILED[:10], "filed_at": FILED, "headline": "h", "card_json": json.dumps(card), "held": 0}]
    memory = _dossier()
    saved: dict = {}

    class Sink(BackupObjects):
        def query(self, name, params):
            return [r for r in stored if (r["filed_at"], r["news_id"]) > (params[0], params[1])]

        def get_dossier(self, scrip):
            return memory

        def company(self, scrip):
            return {"scrip_code": scrip}

        def execute(self, statement, rows):
            return len(rows)

        def put_dossier(self, scrip, dossier):
            saved[scrip] = json.loads(json.dumps(dossier))

    pipeline = SimpleNamespace(sink=Sink(), prompts=SimpleNamespace(sector_for=lambda industry: SimpleNamespace(footer=())),
                               _prices=None, _buckets=None)
    report = card_refresh.run(pipeline)
    assert report["memories_with_call_points"] == 1
    assert [p["text"] for p in saved["500001"]["call_points"]] == ["Deposit growth guided at 11-12% for FY27"]
    saved.clear()
    assert card_refresh.run(pipeline)["memories_with_call_points"] == 0 and not saved   # nothing new the second time


def test_every_block_the_refresh_makes_is_one_it_saves():
    """corporate_action was made by blocks() but missing from BLOCKS, so a card whose only change was that block was
    never written (refresh of 22 Oct 2026, after the corporate-actions history)."""
    filing = Filing(news_id="n1", scrip_code="500001", company_name="Demo Rail Ltd", headline="h", subject="",
                    filed_at=FILED, filing_date=FILED[:10])
    made = card_refresh.blocks(_card(), _dossier(), filing, None)
    assert set(made) == set(card_refresh.BLOCKS)
    card = {**_card(), "event_type": "CORPORATE_ACTION", "headline": "Demo Rail fixes record date for 1:1 bonus"}
    dossier = _dossier()
    dossier["corporate_actions"] = [{"ex_date": "2026-09-25", "subject": "Bonus 1:1", "kind": "BONUS", "factor": 2.0}]
    first, _ = card_refresh.refresh(card, dossier, filing, None)
    again, changed = card_refresh.refresh({**first, "corporate_action": None}, dossier, filing, None)
    assert again["corporate_action"]["factor"] == 2.0 and "corporate_action" in changed


def test_a_call_cards_table_of_another_quarter_is_taken_off():
    """E11 (22 Oct 2026): Nippon Life AMC's Q2FY27 call carried Q1FY27's table. The refresh keeps a table it cannot
    rebuild, except a call card's table of a quarter the call does not discuss."""
    filed = "2026-10-22T14:19:00+05:30"
    filing = Filing(news_id="n9", scrip_code="500001", company_name="Demo Rail Ltd", headline="h", subject="",
                    filed_at=filed, filing_date=filed[:10])
    call = {**_card(), "event_type": "CONCALL_PRESENTATION", "results": {"period": "Q1FY27", "revenue": {"value": 100.0}}}
    new, changed = card_refresh.refresh(call, _dossier(), filing, None)
    assert new["results"] is None and "results" in changed
    kept = {**call, "results": {"period": "Q2FY27", "revenue": {"value": 100.0}}}
    assert card_refresh.refresh(kept, _dossier(), filing, None)[0]["results"]["period"] == "Q2FY27"


def test_a_dry_runs_list_shows_a_call_cards_takeaways_as_stored_before_the_recheck(monkeypatch):
    """The recheck marks takeaways verified in place; the list must still show them as stored."""
    card = {**_card(), "event_type": "CONCALL_PRESENTATION", "takeaway_check": 1,
            "call_takeaways": [{"category": "Guidance", "text": "Margin guided at 18%", "verified": False}]}
    stored = [{"news_id": "n1", "scrip_code": "500001", "symbol": "DEMO", "company_name": "Demo Rail Ltd",
               "filing_date": FILED[:10], "filed_at": FILED, "headline": "h", "card_json": json.dumps(card), "held": 0}]

    from bse_intel.call_summary import TAKEAWAY_CHECK_VERSION

    def recheck(new, text):   # as recheck_calls does: the shared takeaway dicts are marked in place
        for item in new["call_takeaways"]:
            item["verified"] = True
        new["takeaway_check"] = TAKEAWAY_CHECK_VERSION
        return True

    monkeypatch.setattr(card_refresh, "recheck_calls", recheck)
    monkeypatch.setattr(card_refresh, "_call_text", lambda pipeline, row: "the call's text")

    class Sink(BackupObjects):
        def query(self, name, params):
            return [r for r in stored if (r["filed_at"], r["news_id"]) > (params[0], params[1])]

        def get_dossier(self, scrip):
            return _dossier()

        def company(self, scrip):
            return {"scrip_code": scrip}

    pipeline = SimpleNamespace(sink=Sink(), prompts=SimpleNamespace(sector_for=lambda industry: SimpleNamespace(footer=())),
                               _prices=None, _buckets=None)
    diffs: list = []
    card_refresh.run(pipeline, dry_run=True, diffs=diffs)
    (d,) = diffs
    assert "call_takeaways" in d["changed"]
    assert d["before"]["call_takeaways"][0]["verified"] is False and d["after"]["call_takeaways"][0]["verified"] is True
