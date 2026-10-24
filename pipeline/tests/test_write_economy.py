"""D1 row writes (owner, 2026-10-21: the free 100,000 a day was reached on 20 Oct). Every statement over the real
migrations: the same rows sent again write nothing, a changed row still writes. LocalSink.execute returns SQLite's
total_changes delta, which counts trigger writes too."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from test_pipeline import FakeBse, _filing, build, rows

from bse_intel.sinks.local import LocalSink
from bse_intel.timeutil import now_ist


@pytest.fixture
def sink(settings):
    return LocalSink(settings)


def _ledger(news_id="n1", pdf="https://www.bseindia.com/xml-data/corpfiling/AttachLive/abc.pdf", **extra):
    return {"news_id": news_id, "scrip_code": "500001", "company_name": "Demo Ltd", "symbol": "DEMO",
            "headline": "Outcome of board meeting", "subject": "", "category": "Result", "subcategory": "",
            "filed_at": "2026-10-20T18:00:00+05:30", "filing_date": "2026-10-20", "pdf_url": pdf, "xbrl_url": None,
            "status": "PENDING", "route": "PASS1", "event_type": "RESULTS", "reason": "results",
            "updated_at": "2026-10-20T18:01:00+05:30", **extra}


def _card(news_id="n1", **extra):
    card = {"news_id": news_id, "headline": "Demo Q2 revenue up 12%", "review": {"status": "OK"}}
    return {"news_id": news_id, "scrip_code": "500001", "symbol": "DEMO", "company_name": "Demo Ltd",
            "filing_date": "2026-10-20", "filed_at": "2026-10-20T18:00:00+05:30", "sector": "cement",
            "event_category": "RESULTS", "impact_level": "MODERATE", "headline": card["headline"],
            "grounding_score": 0.97, "needs_review": 0, "memory_complete": 1, "card": card,
            "pdf_url": "https://x/abc.pdf", "model": "writer-a", "created_at": "2026-10-20T18:05:00+05:30",
            "market_session": "AFTER_MARKET", "actionability_score": 40, "is_actionable_signal": 0, "held": 0, **extra}


def _company(**extra):
    return {"scrip_code": "500001", "symbol": "DEMO", "company_name": "Demo Ltd", "isin": "INE000A01010",
            "industry": "Cement", "sector": "cement", "market_cap_cr": 1234.5, "size_category": "SMALL",
            "last_price": 101.25, "price_date": "2026-10-20", "ret_1w": 1.5, "ret_1m": -2.25, "ret_1y": 10.0,
            "technicals_json": json.dumps({"rs": 61}), "updated_at": "2026-10-20T06:00:00+05:30", **extra}


def test_filings_update_writes_only_a_change(sink):
    sink.execute("filings_discover", [_ledger()])
    update = {"news_id": "n1", "status": "PENDING", "attempts": 0, "updated_at": "2026-10-20T19:00:00+05:30"}
    assert sink.execute("filings_update", [update]) == 0              # same status, attempts and error: no write
    assert sink.execute("filings_update", [dict(update, updated_at="2026-10-21T00:00:00+05:30")]) == 0
    done = {"news_id": "n1", "status": "ANALYZED", "event_type": "RESULTS", "reason": None, "last_error": None,
            "updated_at": "2026-10-20T19:05:00+05:30"}
    assert sink.execute("filings_update", [done]) == 1
    assert sink.execute("filings_update", [dict(done, updated_at="2026-10-20T19:20:00+05:30")]) == 0   # a retried request
    assert sink.execute("filings_update", [dict(done, status="FAILED", attempts=1, last_error="x")]) == 1
    (row,) = rows(sink, "select status, attempts, last_error, updated_at from filings")
    assert row == {"status": "FAILED", "attempts": 1, "last_error": "x", "updated_at": "2026-10-20T19:05:00+05:30"}


def test_filings_discover_queues_a_known_filing_again_only_for_another_attachment(sink):
    assert sink.execute("filings_discover", [_ledger()]) == 1
    sink.execute("filings_update", [{"news_id": "n1", "status": "ANALYZED", "attempts": 1, "updated_at": "t"}])
    assert sink.execute("filings_discover", [_ledger()]) == 0
    # BSE moves an attachment from AttachLive/ to AttachHis/ under the same name: no change
    assert sink.execute("filings_discover", [_ledger(pdf="https://www.bseindia.com/xml-data/corpfiling/AttachHis/abc.pdf")]) == 0
    assert sink.execute("filings_discover", [_ledger(pdf=None)]) == 0
    assert sink.execute("filings_discover", [_ledger(pdf="https://www.bseindia.com/xml-data/corpfiling/AttachLive/abd.pdf")]) == 1
    (row,) = rows(sink, "select status, attempts, pdf_url, last_error from filings")
    assert row["status"] == "PENDING" and row["attempts"] == 0 and row["pdf_url"].endswith("/abd.pdf")
    assert row["last_error"].startswith("attachment changed: ") and row["last_error"].endswith("/abc.pdf")


def test_filings_import_writes_only_a_change(sink):
    row = dict(_ledger(), attempts=1, last_error=None, status="ANALYZED")
    assert sink.execute("filings_import", [row]) == 1
    assert sink.execute("filings_import", [dict(row, updated_at="later")]) == 0
    assert sink.execute("filings_import", [dict(row, reason="another reason")]) == 1


def test_cards_upsert_writes_only_a_change_and_the_search_index_only_for_a_headline(sink):
    sink.execute("companies_upsert", [_company()])
    first = sink.execute("cards_upsert", [_card()])
    assert first == 4          # the card, its search row (two in SQLite's count), the company's card count
    assert sink.execute("cards_upsert", [_card()]) == 0
    assert sink.execute("cards_upsert", [_card(created_at="2026-10-21T09:00:00+05:30")]) == 0   # created_at alone
    assert sink.execute("cards_upsert", [_card(held=1)]) == 1        # the row only: no search-index rewrite
    changed = _card(headline="Demo Q2 revenue up 13%")
    changed["card"] = dict(changed["card"], headline="Demo Q2 revenue up 13%")
    assert sink.execute("cards_upsert", [changed]) == 5              # row + search delete + search insert
    (row,) = rows(sink, "select held, headline, created_at from cards")
    assert row == {"held": 0, "headline": "Demo Q2 revenue up 13%", "created_at": "2026-10-20T18:05:00+05:30"}


def test_cards_upsert_keeps_a_measured_reaction_without_a_write(sink):
    sink.execute("cards_upsert", [_card()])
    sink.execute("cards_reaction", [{"news_id": "n1", "reaction": {"t1": 1.2}}])
    assert sink.execute("cards_reaction", [{"news_id": "n1", "reaction": {"t1": 1.2}}]) == 0
    assert sink.execute("cards_upsert", [_card()]) == 0             # a re-run without the reaction keeps it
    assert json.loads(rows(sink, "select post_event_return_json p from cards")[0]["p"]) == {"t1": 1.2}


def test_companies_upsert_writes_only_a_change(sink):
    assert sink.execute("companies_upsert", [_company()]) == 3       # the row and its search row (two)
    assert sink.execute("companies_upsert", [_company(updated_at="2026-10-20T12:00:00+05:30")]) == 0
    # market-data's second run of a day: the same closes
    price = {"scrip_code": "500001", "company_name": "500001", "last_price": 101.25, "price_date": "2026-10-20",
             "ret_1w": 1.5, "ret_1m": -2.25, "ret_1y": 10.0, "technicals_json": json.dumps({"rs": 61}),
             "updated_at": "2026-10-20T13:00:00+05:30"}
    assert sink.execute("companies_upsert", [price]) == 0
    assert sink.execute("companies_upsert", [dict(price, last_price=102.0, price_date="2026-10-21")]) == 1
    # a card's company row: the summary as stored is no change; a new summary is
    summary = {"scrip_code": "500001", "company_name": "Demo Ltd", "updated_at": "x",
               "memory_summary_json": json.dumps({"open": 1}), "earliest_open_due": "2027-03-31",
               "inflection_last_at": None, "former_names_json": "[]"}
    assert sink.execute("companies_upsert", [summary]) == 1
    assert sink.execute("companies_upsert", [dict(summary, updated_at="y")]) == 0
    assert sink.execute("companies_upsert", [dict(summary, former_names_json='["Old Demo Ltd"]')]) == 5   # + search rewrite
    (row,) = rows(sink, "select last_price, price_date, company_name, isin, former_names_json from companies")
    assert row == {"last_price": 102.0, "price_date": "2026-10-21", "company_name": "Demo Ltd", "isin": "INE000A01010",
                   "former_names_json": '["Old Demo Ltd"]'}


def test_runs_kv_catalysts_and_seen_companies_write_once(sink):
    run = {"run_id": "r1", "mode": "live", "started_at": "a", "status": "RUNNING"}
    assert sink.execute("runs_upsert", [run]) == 1
    assert sink.execute("runs_upsert", [run]) == 0
    done = dict(run, finished_at="b", status="OK", stats={"analyzed": 1})
    assert sink.execute("runs_upsert", [done]) == 1
    assert sink.execute("runs_upsert", [done]) == 0
    assert sink.kv_set("k", "1", "a") == 1 and sink.kv_set("k", "1", "b") == 0 and sink.kv_set("k", "2", "c") == 1
    cat = {"id": "c1", "scrip_code": "500001", "event_type": "AGM", "event_date": "2027-01-01", "description": "AGM",
           "source_news_id": "n1", "created_at": "a"}
    assert sink.execute("catalysts_upsert", [cat]) == 1
    assert sink.execute("catalysts_upsert", [dict(cat, created_at="b")]) == 0
    seen = {"scrip_code": "500002", "company_name": "Other Ltd", "symbol": "OTH", "updated_at": "a"}
    assert sink.execute("companies_seen", [seen]) == 3
    assert sink.execute("companies_seen", [dict(seen, updated_at="b")]) == 0


def test_discovery_again_writes_nothing_and_requeues_a_filing_with_another_attachment(settings, monkeypatch):
    """A day read again (the live runs read today every 15 minutes; a resumed backfill reads its cursor's day again)
    costs no row write; a known filing the exchange now serves with another file is queued again with every attempt."""
    when = now_ist() - timedelta(days=3)
    filings = [_filing("n-res", "Unaudited Financial Results for the quarter ended September 30, 2026", when, "Result")]
    pipeline, sink, _ = build(settings, filings, {}, {})
    day = when.date()
    assert pipeline.discover(day) == 1
    sink.execute("filings_update", [{"news_id": "n-res", "status": "ANALYZED", "attempts": 1, "updated_at": "t"}])
    before = pipeline.stats.d1_rows_written
    assert pipeline.discover(day) == 0 and pipeline.stats.d1_rows_written == before
    assert pipeline.stats.attachment_changed == 0
    # the same file under another folder: no change
    pipeline.bse = FakeBse([f.model_copy(update={"pdf_url": "https://bse.invalid/AttachHis/n-res.pdf"}) for f in filings], {})
    pipeline.discover(day)
    assert pipeline.stats.d1_rows_written == before and rows(sink, "select status from filings")[0]["status"] == "ANALYZED"
    revised = FakeBse([f.model_copy(update={"pdf_url": "https://bse.invalid/n-res-revised.pdf"}) for f in filings], {})
    # counted only, until a day's count shows the exchange keeps an unchanged filing's link
    pipeline.bse = revised
    pipeline.discover(day)
    assert pipeline.stats.attachment_changed == 1 and rows(sink, "select status from filings")[0]["status"] == "ANALYZED"
    monkeypatch.setenv("ATTACHMENT_REQUEUE", "1")
    pipeline.stats.attachment_changed = 0
    pipeline.bse = FakeBse([f.model_copy(update={"pdf_url": "https://bse.invalid/n-res-revised.pdf"}) for f in filings], {})
    pipeline.discover(day)
    assert pipeline.stats.attachment_changed == 1
    (row,) = rows(sink, "select status, attempts, pdf_url from filings")
    assert row == {"status": "PENDING", "attempts": 0, "pdf_url": "https://bse.invalid/n-res-revised.pdf"}
    after = pipeline.stats.d1_rows_written
    pipeline.discover(day)                                           # the new file is now the stored one
    assert pipeline.stats.d1_rows_written == after and pipeline.stats.attachment_changed == 1


def test_the_universe_seed_saves_its_resume_point_every_ten_companies_and_at_the_end(settings, monkeypatch):
    import argparse

    from bse_intel import nse as nse_mod
    from bse_intel import seed as seed_mod
    from bse_intel import universe
    from bse_intel.cli import cmd_seed_memory

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    stop_at = {"500023"}

    def results(sink, bse, scrip, *a, **k):
        if scrip in stop_at:
            raise nse_mod.SourceBlockedError("HTTP 403")

    monkeypatch.setattr(nse_mod, "NseClient", Client)
    monkeypatch.setattr(seed_mod, "seed_results", results)
    monkeypatch.setattr(seed_mod, "seed_shareholding", lambda *a, **k: None)
    sink = LocalSink(settings)
    sink.put_object(universe.UNIVERSE_KEY, json.dumps(
        {"source": "nse", "included": [str(500001 + i) for i in range(25)]}).encode())
    saved: list[str] = []
    real = sink.kv_set
    monkeypatch.setattr(sink, "kv_set", lambda key, value, at: (key == "seed:universe_last" and saved.append(value),
                                                                real(key, value, at))[1])
    args = argparse.Namespace(scrips=None, universe=True, restart=False, source="nse", since="2024-01-01",
                              results_only=False, shareholding_only=False)
    assert cmd_seed_memory(args, settings, sink) == 2   # stopped by a refusal
    assert saved == ["500010", "500020", "500022"]                 # every ten, then the last one done before the stop
    stop_at.clear()
    assert cmd_seed_memory(args, settings, sink) == 0
    assert saved[3:] == ["500025"]                                  # 500023-500025: three companies, saved once
