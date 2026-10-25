"""Memory labels, step 2 (docs/design/memory-labels.md, F150): the one-off job that labels what is already in memory.
No AI, no card change: readers see the same memory."""
from __future__ import annotations

import copy
import datetime
import json
from types import SimpleNamespace

from bse_intel import cli, memory_labels as ml, xbrl
from bse_intel.dossier import view_as_of
from test_xbrl import results_xml

CUT = "2027-01-01T00:00:00+05:30"
KEPT = {"by": "ai", "doc": "results", "at": "2026-10-01T10:00:00+05:30", "ok": True}


def _fig(metric, period, value, news_id, **extra):
    return {"metric": metric, "period": period, "value": value, "unit": "INR_CR", "yoy_pct": None, "qoq_pct": None,
            "as_of": "2026-10-20T17:00:00+05:30", "source_news_id": news_id, **extra}


def old_memory() -> dict:
    """What memory looked like before step 1: not one label (but one that step 1 already wrote)."""
    both = _fig("revenue", "Q1FY27", 100.0, "xbrl:res:1:Q1FY27", basis="CONSOLIDATED")
    both.update(sources=[{"news_id": "xbrl:res:1:Q1FY27", "as_of": "2026-07-20T17:00:00+05:30", "value": 100.0, "unit": "INR_CR",
                          "basis": "CONSOLIDATED"},
                         {"news_id": "nse-90", "as_of": "2026-07-21T17:00:00+05:30", "value": 99.0, "unit": "INR_CR",
                          "basis": "CONSOLIDATED"}])
    return {
        "schema_version": 3, "scrip_code": "1", "company_name": "Demo Ltd", "updated_at": "x", "last_filed_at": "x",
        "business_summary": {"text": "Makes cement", "as_of": "2026-07-20T17:00:00+05:30", "source_news_id": "nse-90"},
        "financial_metrics": [
            _fig("revenue", "Q2FY27", 120.0, "xbrl:res:1:Q2FY27", basis="CONSOLIDATED"),
            _fig("pbt", "Q2FY27", 20.0, "xbrl:res:1:Q2FY27", basis="CONSOLIDATED"),
            _fig("finance_cost", "Q2FY27", 2.0, "xbrl:res:1:Q2FY27"),
            _fig("depreciation", "Q2FY27", 3.0, "xbrl:res:1:Q2FY27"),
            _fig("ebitda", "Q2FY27", 25.0, "xbrl:res:1:Q2FY27"),
            _fig("ebitda_margin", "Q2FY27", 20.83, "xbrl:res:1:Q2FY27", unit="PCT"),
            _fig("pat", "Q3FY27", 15.5, "nse-100", basis="CONSOLIDATED"),       # the card's XBRL table has 15.5
            _fig("eps", "Q3FY27", 4.0, "nse-100"),                              # the card's table has 4.2
            _fig("order_book", "Q3FY27", 5000.0, "nse-100"),                    # not a line of the table
            _fig("ebitda", "Q3FY27", 30.0, "nse-100"),                          # derived line, same value in the table
            _fig("order_book", "Q2FY27", 4000.0, "nse-200"),                    # said on a call
            _fig("roa_pct", "Q2FY27", 1.2, "nse-300", lab=dict(KEPT)),          # step 1's label stays
            both,
        ],
        "balance_sheet": [{"period": "Q2FY27", "cash_cr": 41.0, "as_of": "2026-10-20T17:00:00+05:30",
                           "source_news_id": "xbrl:res:1:Q2FY27"}],
        "standalone": {"metrics": [_fig("revenue", "Q2FY27", 80.0, "xbrl:res-sa:1:Q2FY27")], "balance_sheet": []},
        "guidance": [{"id": "g_1", "statement": "Capex 500 Cr", "given_on": "2026-10-21T10:00:00+05:30",
                      "source_news_id": "nse-201", "status": "OPEN", "status_history": []}],
        "operating_notes": [{"text": "n", "as_of": "2026-10-20T17:00:00+05:30", "source_news_id": "nse-100"}],
        "call_points": [{"news_id": "nse-200", "date": "2026-10-22", "category": "Other", "text": "Demand firm"}],
        "timeline": [
            {"id": "t_1", "date": "2026-10-20T17:00:00+05:30", "event_type": "RESULTS", "summary": "r", "news_id": "nse-100"},
            {"id": "t_2", "date": "2026-10-22T10:00:00+05:30", "event_type": "CONCALL_PRESENTATION", "summary": "c", "news_id": "nse-200"}],
        "ownership": [{"period": "SEP-2026", "promoter_pct": 50.0, "as_of": "2026-10-18T10:00:00+05:30",
                       "source_news_id": "xbrl:shp:1:SEP-2026"}],
        "governance": {"auditor": {"name": "A & Co", "as_of": "2026-09-01T10:00:00+05:30", "source_news_id": "nse-100"},
                       "auditor_history": [{"name": "A & Co", "as_of": "2026-09-01T10:00:00+05:30", "source_news_id": "nse-100"}],
                       "quarters": [{"quarter_end": "2026-09-30", "as_of": "2026-10-10T10:00:00+05:30", "source": "u"}]},
        "identity": {"former_names": ["Old Name Ltd"], "entities": []},
        "corporate_actions": [{"ex_date": "2026-09-01", "subject": "Dividend Rs 2", "kind": "DIVIDEND"}],
        "pledges": {"events": [{"as_of": "2026-10-01T10:00:00+05:30", "x": 1}]},
    }


def card_rows():
    results = {"period": "Q3FY27", "pat": {"value": 15.5}, "eps": {"value": 4.2}, "ebitda": {"value": 30.0}}

    def row(news_id, headline, card):
        return {"news_id": news_id, "scrip_code": "1", "filed_at": "2026-10-20", "headline": headline,
                "card_json": json.dumps(card)}
    return [row("nse-100", "Financial Results", {"event_type": "RESULTS", "xbrl": {"period": "Q3FY27"}, "results": results}),
            row("nse-200", "Transcript of earnings call", {"event_type": "CONCALL_PRESENTATION"}),
            row("nse-201", "Investor Presentation", {"event_type": "CONCALL_PRESENTATION"})]


def labelled(d=None):
    d = copy.deepcopy(d or old_memory())
    changed, new, had = ml.Labeller(ml.card_facts(card_rows())).run(d)
    return d, changed, new, had


def fig(d, metric, period, news_id=None):
    return next(m for m in d["financial_metrics"] if m["metric"] == metric and m["period"] == period
                and (news_id is None or m.get("source_news_id") == news_id))


def test_exchange_files_are_file_and_derived_lines_under_them_are_calc_with_their_inputs():
    d, *_ = labelled()
    assert fig(d, "revenue", "Q2FY27")["lab"] == {"by": "file", "doc": "results", "basis": "CONSOLIDATED", "unit": "INR_CR",
                                                  "at": "2026-10-20T17:00:00+05:30"}
    ebitda = fig(d, "ebitda", "Q2FY27", "xbrl:res:1:Q2FY27")["lab"]
    assert ebitda["by"] == "calc" and ebitda["from"] == ["pbt:Q2FY27", "finance_cost:Q2FY27", "depreciation:Q2FY27"]
    assert fig(d, "ebitda_margin", "Q2FY27")["lab"]["from"] == ["ebitda:Q2FY27", "revenue:Q2FY27"]
    assert d["balance_sheet"][0]["lab"]["by"] == "file" and d["standalone"]["metrics"][0]["lab"]["basis"] == "STANDALONE"
    assert d["ownership"][0]["lab"]["by"] == "file"


def test_a_figure_under_a_plain_id_is_file_only_when_the_cards_xbrl_table_has_the_value():
    d, *_ = labelled()
    assert fig(d, "pat", "Q3FY27")["lab"]["by"] == "file" and fig(d, "pat", "Q3FY27")["lab"]["doc"] == "results"
    assert fig(d, "eps", "Q3FY27")["lab"]["by"] == "unknown"            # 4.0 here, 4.2 in the table
    assert fig(d, "order_book", "Q3FY27")["lab"]["by"] == "unknown"     # no such line
    assert fig(d, "ebitda", "Q3FY27")["lab"]["by"] == "calc"
    d2 = old_memory()   # no card at all: unknown
    ml.Labeller({}).run(d2)
    assert fig(d2, "pat", "Q3FY27")["lab"]["by"] == "unknown"
    rows = card_rows()   # a card made without its XBRL file: unknown
    rows[0]["card_json"] = json.dumps({"event_type": "RESULTS", "results": {"period": "Q3FY27", "pat": {"value": 15.5}}})
    d3 = old_memory()
    ml.Labeller(ml.card_facts(rows)).run(d3)
    assert fig(d3, "pat", "Q3FY27")["lab"]["by"] == "unknown"
    rows = card_rows()   # another quarter than the table's: unknown
    d4 = old_memory()
    d4["financial_metrics"][6]["period"] = "Q2FY27"
    ml.Labeller(ml.card_facts(rows)).run(d4)
    assert fig(d4, "pat", "Q2FY27")["lab"]["by"] == "unknown"


def test_call_and_slide_items_are_ai_without_a_quote():
    d, *_ = labelled()
    assert fig(d, "order_book", "Q2FY27")["lab"]["by"] == "ai" and fig(d, "order_book", "Q2FY27")["lab"]["doc"] == "call"
    assert d["call_points"][0]["lab"] == {"by": "ai", "doc": "call", "at": "2026-10-22"}
    assert d["guidance"][0]["lab"]["by"] == "ai" and d["guidance"][0]["lab"]["doc"] == "slides"
    assert d["timeline"][1]["lab"]["by"] == "ai" and d["timeline"][0]["lab"]["by"] == "unknown"
    assert all("quote" not in lab and "page" not in lab for lab in (d["call_points"][0]["lab"], d["guidance"][0]["lab"]))


def test_an_existing_label_is_never_overwritten_and_a_multi_source_figure_is_labelled_per_source():
    d, _, new, had = labelled()
    assert fig(d, "roa_pct", "Q2FY27")["lab"] == KEPT and had["financial_metrics"] == {"ai": 1}
    both = fig(d, "revenue", "Q1FY27")
    assert "lab" not in both and [s["lab"]["by"] for s in both["sources"]] == ["file", "unknown"]
    again, changed, new2, had2 = labelled(d)
    assert changed is False and again == d and new2 == {}   # a second run changes nothing


def test_sections_only_an_exchange_feed_writes_get_one_file_label_and_governance_twins_agree():
    d, *_ = labelled()
    for section in ("corporate_actions", "pledges", "governance_quarters", "former_names"):
        assert d["section_lab"][section]["by"] == "file"
    assert d["section_lab"]["pledges"]["at"] == "2026-10-01T10:00:00+05:30"
    assert "insider_trades" not in d["section_lab"] and "lab" not in d["corporate_actions"][0]
    assert d["governance"]["auditor"]["lab"] == d["governance"]["auditor_history"][0]["lab"]
    assert d["governance"]["auditor"]["lab"]["by"] == "unknown"


def test_counts_per_section_and_label():
    _, changed, new, had = labelled()
    assert changed
    assert new["financial_metrics"] == {"file": 6, "calc": 3, "unknown": 3, "ai": 1}
    assert new["call_points"] == {"ai": 1} and new["timeline"] == {"unknown": 1, "ai": 1}
    assert new["corporate_actions"] == {"file": 1} and new["balance_sheet"] == {"file": 1}
    assert had == {"financial_metrics": {"ai": 1}}


def test_readers_see_the_same_memory_with_and_without_labels():
    old = old_memory()
    d, *_ = labelled(old)
    assert "lab" in json.dumps(d)
    for cutoff in (CUT, "2026-10-21T00:00:00+05:30", "2026-08-01T00:00:00+05:30"):
        assert view_as_of(d, cutoff) == view_as_of(copy.deepcopy(old), cutoff)


class Sink:
    def __init__(self, dossiers, rows=()):
        self.dossiers, self.rows, self.kv, self.puts = dossiers, list(rows), {}, []
        self.reads: dict[str, int] = {}
        self.concurrent: dict[str, dict] = {}   # a copy another job stored after the job's first read

    def list_dossiers(self):
        return sorted(self.dossiers)

    def get_dossier(self, scrip):
        self.reads[scrip] = self.reads.get(scrip, 0) + 1
        if self.reads[scrip] == 2 and scrip in self.concurrent:
            self.dossiers[scrip] = self.concurrent.pop(scrip)
        d = self.dossiers.get(scrip)
        return json.loads(json.dumps(d)) if d is not None else None

    def put_dossier(self, scrip, dossier):
        self.puts.append(scrip)
        self.dossiers[scrip] = json.loads(json.dumps(dossier))

    def kv_get(self, key):
        return self.kv.get(key)

    def kv_set(self, key, value, now):
        self.kv[key] = value

    def query(self, name, params):
        assert name == "export_cards"
        after = (params[0], params[1])
        return [r for r in self.rows if (r["filed_at"], r["news_id"]) > after][:params[2]]


def sink_of(n=3):
    dossiers = {}
    for i in range(1, n + 1):
        d = old_memory()
        d["scrip_code"] = str(i)
        dossiers[str(i)] = d
    return Sink(dossiers, card_rows())


def test_dry_run_counts_and_writes_nothing():
    sink = sink_of()
    before = copy.deepcopy(sink.dossiers)
    report = ml.label_all(sink, sink.list_dossiers(), True, ml.load_cards(sink))
    assert sink.puts == [] and sink.kv == {} and sink.dossiers == before
    assert report["companies"] == 3 and report["companies_changed"] == 3
    assert report["new"]["financial_metrics"]["calc"] == 9 and report["new"]["corporate_actions"] == {"file": 3}
    text = ml.render(report)
    assert "dry run, nothing written" in text and "financial_metrics" in text and "all newly labelled" in text


def test_real_run_writes_changed_dossiers_resumes_and_a_second_run_writes_nothing():
    sink = sink_of()
    report = ml.label_all(sink, sink.list_dossiers(), False, ml.load_cards(sink))
    assert sink.puts == ["1", "2", "3"] and sink.kv[ml.RESUME_KEY] == "3" and report["failed"] == []
    assert fig(sink.dossiers["2"], "pat", "Q3FY27")["lab"]["by"] == "file"
    sink.puts.clear()
    again = ml.label_all(sink, sink.list_dossiers(), False, ml.load_cards(sink), restart=True)
    assert sink.puts == [] and again["companies_changed"] == 0
    sink.kv[ml.RESUME_KEY] = "1"   # a stopped run resumes after its last company
    sink.dossiers["3"] = old_memory() | {"scrip_code": "3"}
    part = ml.label_all(sink, sink.list_dossiers(), False, ml.load_cards(sink))
    assert part["skipped_resumed"] == 1 and part["companies"] == 2 and sink.puts == ["3"]


def test_a_write_by_another_job_between_the_read_and_the_write_is_kept():
    sink = sink_of(1)
    theirs = old_memory()
    theirs["financial_metrics"].append(_fig("order_book", "Q1FY27", 9.0, "nse-777"))
    theirs["pledges"] = {"events": [{"as_of": "2026-10-24T10:00:00+05:30", "x": 2}]}
    sink.concurrent["1"] = theirs   # stored after the job read the company, seen when it re-reads to write
    ml.label_all(sink, ["1"], False, ml.load_cards(sink))
    stored = sink.dossiers["1"]
    assert any(m["metric"] == "order_book" and m["period"] == "Q1FY27" for m in stored["financial_metrics"])   # theirs kept
    assert stored["pledges"]["events"][0]["x"] == 2                                                         # theirs wins
    assert fig(stored, "revenue", "Q2FY27")["lab"]["by"] == "file"                                           # ours too


def test_a_failed_write_is_reported_and_stops_the_resume_point():
    sink = sink_of(3)
    real = sink.put_dossier

    def flaky(scrip, d):
        if scrip == "2":
            raise OSError("boom")
        real(scrip, d)
    sink.put_dossier = flaky
    report = ml.label_all(sink, sink.list_dossiers(), False, {})
    assert len(report["failed"]) == 1 and sink.puts == ["1", "3"] and sink.kv[ml.RESUME_KEY] == "1"


def test_the_time_budget_stops_the_run_with_companies_left():
    sink = sink_of(20)
    ticks = iter(range(100))
    report = ml.label_all(sink, sink.list_dossiers(), True, {}, time_budget=1, clock=lambda: next(ticks) * 1.0)
    assert report["more"] and report["companies"] < 20


def test_command_dry_run_writes_the_json_and_honours_scrips(tmp_path, capsys):
    sink = sink_of()
    out = tmp_path / "labels.json"
    args = SimpleNamespace(scrips="1,2", dry_run=True, json=str(out), restart=False, time_budget=100)
    assert cli.cmd_label_memory(args, None, sink) == 0
    body = json.loads(out.read_text())
    assert body["dry_run"] is True and body["companies"] == 2 and body["new_totals"]["file"] > 0 and sink.puts == []
    assert "dry run, nothing written" in capsys.readouterr().out


def test_the_annualised_roa_is_calc_from_the_quarterly_one_and_net_of_excise_is_calc():
    from bse_intel.results_card import _net_of_excise

    end = datetime.date(2026, 9, 30)
    values = {("roa_pct", "Q2FY27"): 0.45, ("roa_pct", "H1FY27"): 0.91}
    scaled = xbrl._annualise_roa(values, {"Q2FY27": end, "H1FY27": end})
    assert scaled == {("roa_pct", "Q2FY27"): ["roa_pct_quarterly:Q2FY27"], ("roa_pct", "H1FY27"): ["roa_pct_quarterly:Q2FY27"]}
    assert round(values[("roa_pct", "Q2FY27")], 2) == 1.8
    assert xbrl._annualise_roa({("roa_pct", "Q2FY27"): 1.4}, {"Q2FY27": end}) == {}   # left as filed: not calc
    tagged = xbrl.parse(results_xml())
    metric = type(tagged.metrics[0])
    net = _net_of_excise(SimpleNamespace(period=tagged.period,
                                         metrics=[*tagged.metrics, metric(metric="excise_duty", period=tagged.period, value=5.0)]))
    assert net is not None and net.by == "calc" and net.derived_from == [f"revenue:{tagged.period}", f"excise_duty:{tagged.period}"]
