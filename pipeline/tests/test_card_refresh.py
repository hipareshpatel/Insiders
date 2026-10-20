"""refresh-card-blocks: a stored card's code blocks rebuilt from memory by today's code, no AI (design audit,
2026-10-20: 14 of 849 live cards carried the blocks of the 19 Oct redesign)."""

import json
from types import SimpleNamespace

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

    class Sink:
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


def test_a_refreshed_card_with_a_clear_event_becomes_high():
    card = {**_card(), "event_type": "RESULTS", "deal_value": None, "signals": [],
            "results": {"pat": {"value": 50.0, "prev_year": 30.0, "yoy_pct": 66.7}}, "score": {"vetoes": [], "reasons": []}}
    stored = [{"news_id": "r1", "scrip_code": "500001", "symbol": "DEMO", "company_name": "Demo Rail Ltd", "impact_level": "MODERATE",
               "filing_date": FILED[:10], "filed_at": FILED, "headline": "h", "card_json": json.dumps(card), "held": 0}]

    class Sink:
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

    class Sink:
        def query(self, name, params):
            return [r for r in rows if (r["filed_at"], r["news_id"]) > (params[0], params[1])]

    out = tmp_path / "held.json"
    assert cmd_export_held(SimpleNamespace(out=str(out)), None, Sink()) == 0
    assert [c["news_id"] for c in json.loads(out.read_text())] == ["a"]
