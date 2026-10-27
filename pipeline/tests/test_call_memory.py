"""Call memory v2 (TODO 83, F180, docs/design/call-memory.md): the checks of section 3 on small texts modelled on the audit
cases, the memory write, the merge guard, the switch, the command and the pipeline hook."""
from __future__ import annotations

import gzip
import json
from types import SimpleNamespace

import pytest

from bse_intel import call_memory as cm
from bse_intel import call_queue
from bse_intel import cli
from bse_intel.dossier import merge, new_dossier
from bse_intel.models import CallMemoryOutput, CallPoint, Filing, Pass2Output
from bse_intel.pipeline import text_key
from bse_intel.prompts.engine import PromptEngine

PAGE_1 = """--- Page 1 of 3 ---
Good afternoon. We expect pre-sales growth of much higher than 15% for the whole of FY27 and towards 20% from FY28.
Our operational cash flow, collections less construction and land spend, was Rs 755 crore in the first half.
We will add 10 lakh tonnes of capacity by FY28 at the new plant.
"""
PAGE_2 = """--- Page 2 of 3 ---
Question: Is the 15% for the whole of FY27? Management: To clarify, the 15% plus growth is for the second half of FY27,
not the whole year. Onward only has U.S. and Europe customers today.
"""
PAGE_3 = """--- Page 3 of 3 ---
Capex of Rs 500 crore is planned. The weather was fine in the city and the plant is near the river bank.
We will add 10 lakh tonnes of capacity by FY28 at the new plant.
"""
TEXT = "\n".join((PAGE_1, PAGE_2, PAGE_3))


def _point(**kw) -> CallPoint:
    base = {"type": "guidance", "statement": "Pre-sales growth of 15% in FY27", "metric": "presales_growth",
            "topic": "fy27_presales_growth", "value": 15, "unit": "PERCENT", "period": "FY27", "section": "PREPARED",
            "speaker": "MANAGEMENT", "page": 1, "quote": "much higher than 15% for the whole of FY27"}
    return CallPoint.model_validate({**base, **kw})


def _check(*points, text=TEXT, blocks=""):
    return cm.check_points(list(points), text, blocks, scope="123:n1")


def _reasons(dropped):
    return [d["reason"] for d in dropped]


# ---------------------------------------------------------------- the model's reply is lenient
def test_a_bad_enum_or_entry_never_costs_the_other_points():
    out = CallMemoryOutput.model_validate({"points": [
        {"type": "GUIDANCE", "value": "10", "unit": "LAKH_TONNES", "direction": "sideways", "section": "Q&A", "page": "3"},
        "not a point", {"type": "weather"}]})
    assert [p.type for p in out.points] == ["guidance", None]
    assert out.points[0].value == 10.0 and out.points[0].direction is None and out.points[0].section == "QA"
    assert out.points[0].page == 3


# ---------------------------------------------------------------- 3.1 quote, 3.2 figures
def test_a_quote_not_in_the_text_drops_the_point_with_its_reason():
    kept, dropped = _check(_point(quote="much higher than 25% for the whole of FY27"))
    assert kept == [] and _reasons(dropped) == ["quote"]
    assert dropped[0]["point"]["quote"].startswith("much higher than 25%")


def test_a_quote_found_only_in_the_block_reading_counts():
    kept, dropped = _check(_point(quote="much higher than 15% for the whole of FY27"), text="--- Page 1 of 1 ---\nunrelated words",
                           blocks="much higher than 15% for the whole of FY27")
    assert len(kept) == 1 and dropped == []


def test_a_figure_not_in_the_quote_drops_the_point():
    # the statement borrows a figure (500) the sentence it quotes does not carry
    kept, dropped = _check(_point(statement="Capex of 900 crore", type="capex_capacity", value=None, unit=None, period=None,
                                  quote="the plant is near the river bank"))   # 900 is nowhere near the quote
    assert kept == [] and _reasons(dropped) == ["figure"]
    assert "900" in dropped[0]["detail"]
    # a figure in the next sentence on the page is kept, and the point says so (third measured run: 99 of 107 such drops true)
    kept, dropped = _check(_point(statement="Capex of 500 crore", type="capex_capacity", value=None, unit=None, period=None,
                                  quote="the plant is near the river bank"))
    assert len(kept) == 1 and kept[0].figure_beside_quote and dropped == []
    kept, dropped = _check(_point(value=18))   # the value is not in the quote either
    assert _reasons(dropped) == ["figure"]


def test_period_labels_and_dates_are_not_figures_of_the_statement():
    kept, dropped = _check(_point(statement="Growth of 15% for H2FY27 and Q4FY27, said on 12.11.2026"))
    assert len(kept) == 1


# ---------------------------------------------------------------- 3.3 unit (APL Apollo's 10 lakh tonnes)
def test_ten_lakh_tonnes_is_kept_with_its_base_value():
    kept, dropped = _check(_point(type="capex_capacity", statement="Adds 10 lakh tonnes of capacity by FY28", value=10,
                                  unit="LAKH_TONNES", period="FY28", quote="We will add 10 lakh tonnes of capacity by FY28"))
    assert dropped == [] and len(kept) == 1
    assert kept[0].value_base == 1_000_000 and kept[0].base_unit == "TONNES"


def test_a_unit_that_loses_the_scale_word_is_dropped():
    q = "We will add 10 lakh tonnes of capacity by FY28"
    for unit in ("TONNES", "MILLION_TONNES", "INR_CR"):
        kept, dropped = _check(_point(type="capex_capacity", statement="Adds 10 lakh tonnes", value=10, unit=unit, period="FY28", quote=q))
        assert kept == [] and _reasons(dropped) == ["unit"], unit


def test_a_model_base_value_that_is_wrong_is_put_right_by_code():
    # third measured run: Sobha's "12 million square feet" was dropped for a model value_base of 1e6
    kept, dropped = _check(_point(type="capex_capacity", statement="Adds 10 lakh tonnes", value=10, unit="LAKH_TONNES", value_base=100_000,
                                  base_unit="TONNES", period="FY28", quote="We will add 10 lakh tonnes of capacity by FY28"))
    assert dropped == [] and kept[0].value_base == 1_000_000 and not kept[0].figure_beside_quote


def test_crore_and_percent_units_follow_the_quote():
    ok, bad = _check(_point(type="capex_capacity", statement="Capex of Rs 500 crore", value=500, unit="INR_CR", period=None,
                            quote="Capex of Rs 500 crore is planned."))
    assert len(ok) == 1 and ok[0].value_base == 5_000_000_000 and ok[0].base_unit == "INR"
    kept, dropped = _check(_point(type="capex_capacity", statement="Capex of Rs 500 crore", value=500, unit="INR_LAKH", period=None,
                                  quote="Capex of Rs 500 crore is planned."))
    assert _reasons(dropped) == ["unit"]
    kept, dropped = _check(_point(unit="INR_CR"))   # 15% typed as crore
    assert _reasons(dropped) == ["unit"]


# ---------------------------------------------------------------- 3.4 period, 3.5 page
def test_a_period_the_text_never_names_is_set_to_null():
    # "FY28" is not within 600 characters of this sentence, and not in it
    point = _point(type="capex_capacity", statement="Capex of Rs 500 crore", value=500, unit="INR_CR", period="FY29",
                   quote="Capex of Rs 500 crore is planned.", page=3)
    kept, dropped = _check(point)
    assert dropped == [] and kept[0].period is None and kept[0].period_stated is False


def test_a_period_named_near_the_quote_on_its_page_is_kept():
    kept, _ = _check(_point(statement="Capex of Rs 500 crore", type="capex_capacity", value=500, unit="INR_CR", period="FY28",
                            quote="Capex of Rs 500 crore is planned.", page=3))
    assert kept[0].period == "FY28" and kept[0].period_stated is True   # "by FY28" stands in the next sentence of the page


def test_period_named_forms():
    assert cm.period_named("H2FY27", "the second half of FY27")
    assert not cm.period_named("H2FY27", "the first half of FY27")
    assert cm.period_named("FY27", "for 2026-27 we expect")
    assert cm.period_named("Q2FY27", "Q2 FY27 volumes")
    assert cm.period_named("by March 2028", "capacity ready by Mar-28 or 2028")
    assert not cm.period_named("FY27", "FY28 and beyond")


def test_the_page_is_the_one_the_quote_stands_on():
    kept, _ = _check(_point(quote="Onward only has U.S. and Europe customers today", type="dependence",
                            statement="Only U.S. and Europe customers", value=None, unit=None, period=None, page=1))
    assert kept[0].page == 2 and kept[0].pages == [2]


# ---------------------------------------------------------------- 3.6 Q&A wins (Sobha), 3.7 once, 3.8 definitions
def test_a_qa_clarification_supersedes_the_prepared_remark():
    prepared = _point()
    answer = _point(section="QA", period="H2FY27", statement="Pre-sales growth of 15% plus in H2FY27", page=2,
                    quote="the 15% plus growth is for the second half of FY27")
    kept, dropped = _check(prepared, answer)
    assert dropped == [] and len(kept) == 2
    first, second = kept
    assert first.superseded_by == second.id and second.superseded_by is None
    assert first.period == "FY27" and second.period == "H2FY27"


def test_an_analysts_question_does_not_supersede_management():
    claim = _point(section="QA", speaker="ANALYST", period="H2FY27", page=2, quote="the 15% plus growth is for the second half of FY27")
    kept, _ = _check(_point(), claim)
    assert kept[0].superseded_by is None


def test_the_same_fact_on_two_pages_is_one_point_with_both_pages():
    twice = dict(type="capex_capacity", statement="Adds 10 lakh tonnes", value=10, unit="LAKH_TONNES", period="FY28", topic="new_plant_capacity",
                 quote="We will add 10 lakh tonnes of capacity by FY28 at the new plant")
    kept, _ = _check(_point(**twice, page=1), _point(**twice, page=3))
    assert len(kept) == 1 and kept[0].pages == [1, 3]


def test_a_company_defined_measure_is_flagged():
    kept, _ = _check(_point(type="kpi", statement="Operational cash flow of Rs 755 crore", metric="operating_cash_flow", topic="ocf",
                            value=755, unit="INR_CR", period=None, page=1,
                            definition="collections less construction and land spend", quote="was Rs 755 crore in the first half"))
    assert kept[0].company_defined is True
    assert _check(_point())[0][0].company_defined is False


# ---------------------------------------------------------------- Onward: dependence with no figure
def test_a_dependence_point_without_a_figure_is_kept():
    kept, dropped = _check(_point(type="dependence", statement="Onward only has U.S. and Europe customers", metric="geography",
                                  topic="customer_geography", value=None, unit=None, period=None,
                                  quote="Onward only has U.S. and Europe customers today", page=2))
    assert dropped == [] and kept[0].value is None and kept[0].period_stated is False


# ---------------------------------------------------------------- memory
def test_remember_replaces_the_filings_points_on_a_rerun_newest_first():
    dossier = {"scrip_code": "123", "call_memory": []}
    old = cm.check_points([_point()], TEXT, "", scope="123:call-old")[0]
    cm.remember(dossier, "call-old", "2026-05-20T19:00:00+05:30", old, now="2026-05-21T00:00:00")
    first = cm.check_points([_point(), _point(type="dependence", statement="Only U.S. and Europe customers", topic="geo", value=None,
                                              unit=None, period=None, quote="Onward only has U.S. and Europe customers today")],
                            TEXT, "", scope="123:call-new")[0]
    cm.remember(dossier, "call-new", "2026-08-14T19:00:00+05:30", first, now="2026-08-15T00:00:00")
    assert [e["news_id"] for e in dossier["call_memory"]] == ["call-new", "call-new", "call-old"]
    cm.remember(dossier, "call-new", "2026-08-14T19:00:00+05:30", first[:1], now="2026-08-16T00:00:00")   # the re-run keeps one
    assert [e["news_id"] for e in dossier["call_memory"]] == ["call-new", "call-old"]
    entry = dossier["call_memory"][0]
    assert entry["id"].startswith("cm_") and entry["quarter"] == "Q1FY27" and entry["date"] == "2026-08-14"
    assert entry["lab"]["by"] == "ai" and entry["lab"]["doc"] == "call" and entry["lab"]["ok"] is True
    assert entry["lab"]["page"] == 1 and entry["lab"]["quote"].startswith("much higher than 15%")
    assert "value_high" not in entry   # empty fields are not stored


def test_remember_keeps_at_most_600_points():
    dossier = {"scrip_code": "123", "call_memory": [{"id": f"cm_{i}", "news_id": f"old{i}", "date": f"2025-01-{i % 28 + 1:02d}"}
                                                    for i in range(600)]}
    cm.remember(dossier, "new", "2026-08-14T19:00:00+05:30", cm.check_points([_point()], TEXT, "", scope="123:new")[0])
    assert len(dossier["call_memory"]) == 600 and dossier["call_memory"][0]["news_id"] == "new"


def test_prior_points_are_the_latest_earlier_calls_current_ones():
    dossier = {"call_memory": [
        {"id": "cm_a", "news_id": "c2", "date": "2026-05-20", "type": "guidance", "topic": "t1", "statement": "s1", "period": "FY27",
         "superseded_by": "cm_b"},
        {"id": "cm_b", "news_id": "c2", "date": "2026-05-20", "type": "guidance", "topic": "t1", "statement": "s2", "period": "H2FY27"},
        {"id": "cm_c", "news_id": "c1", "date": "2026-02-05", "type": "risk", "topic": "t2", "statement": "s3"},
        {"id": "cm_d", "news_id": "c3", "date": "2026-08-14", "type": "risk", "topic": "t4", "statement": "this filing"}]}
    prior = cm.prior_points(dossier, "c3", "2026-08-14T19:00:00+05:30")
    assert [p["id"] for p in prior] == ["cm_b", "cm_a"]
    assert cm.prior_points(dossier, "c1", "2026-02-05T19:00:00+05:30") == []
    assert len(cm.prior_points({"call_memory": [{"id": str(i), "news_id": "c", "date": "2026-01-01"} for i in range(90)]}, "x", "2026-09-01")) == 40


# ---------------------------------------------------------------- the merge guard
def _delta(metric, period, value, by=None, unit="INR_CR"):
    row = {"metric": metric, "period": period, "value": value, "unit": unit}
    if by:
        row["by"] = by
    return Pass2Output.model_validate({"is_material": True, "event_type": "RESULTS", "timeline_entry": "t",
                                       "card": {"headline": "Sobha figures stated", "impact_level": "LOW", "takeaway": "t", "what_happened": ["x"]},
                                       "dossier_delta": {"financial_metrics": [row]}})


def _filing(news_id, when, event_type, headline="h"):
    return Filing(news_id=news_id, scrip_code="123", company_name="Sobha Ltd", headline=headline, subject="", filed_at=when,
                  filing_date=when[:10], event_type=event_type)


def _held(monkeypatch, on, metric, period, file_value, call_value, unit="INR_CR"):
    if on:
        monkeypatch.setenv("MEMORY_CALL_V2", "1")
    else:
        monkeypatch.delenv("MEMORY_CALL_V2", raising=False)
    d = new_dossier(_filing("xbrl:res:123:" + period, "2026-11-05T18:00:00+05:30", "RESULTS"))
    d = merge(d, _delta(metric, period, file_value, by="file", unit=unit),
              _filing("xbrl:res:123:" + period, "2026-11-05T18:00:00+05:30", "RESULTS"), None, "now")
    call = _filing("call-1", "2026-11-10T19:00:00+05:30", "CONCALL_PRESENTATION", "Q2FY27 earnings call transcript")
    out = _delta(metric, period, call_value, unit=unit)
    out.event_type = "CONCALL_PRESENTATION"
    d = merge(d, out, call, None, "now")
    return next(m for m in d["financial_metrics"] if m["metric"] == metric and m["period"] == period)


@pytest.mark.parametrize("metric,period,file_value,call_value,unit", [
    ("operating_cash_flow", "H1FY27", -342.12, 755.0, "INR_CR"),     # Sobha: statutory against its own "operational cash flow"
    ("ebitda_margin", "Q2FY27", 12.12, 7.7, "PERCENT")])             # Vishal Mega Mart: file against operating EBITDA margin
def test_a_calls_figure_far_from_the_files_is_not_a_source(monkeypatch, metric, period, file_value, call_value, unit):
    got = _held(monkeypatch, True, metric, period, file_value, call_value, unit)
    assert [s["value"] for s in got.get("sources", [got])] == [file_value]
    assert got["value"] == file_value
    off = _held(monkeypatch, False, metric, period, file_value, call_value, unit)
    assert sorted(s["value"] for s in off.get("sources", [off])) == sorted([file_value, call_value])   # switch off: as before


def test_a_calls_figure_within_five_percent_of_the_files_stays_a_source(monkeypatch):
    got = _held(monkeypatch, True, "operating_cash_flow", "H1FY27", 1000.0, 1030.0)
    assert sorted(s["value"] for s in got["sources"]) == [1000.0, 1030.0]


# ---------------------------------------------------------------- the reading, the command and the pipeline hook
class FakeGateway:
    def __init__(self, points, fail=False):
        self.points, self.fail, self.calls = points, fail, []

    def has_route(self, route):
        return route == "pass2_long"

    def complete_json(self, route, system, user, schema, bulk=False, allow=None, **kw):
        self.calls.append({"route": route, "system": system, "user": user, "bulk": bulk, "allow": allow})
        if self.fail:
            raise RuntimeError(self.fail if isinstance(self.fail, str) else "every provider failed")
        return SimpleNamespace(value=CallMemoryOutput.model_validate({"points": self.points}), model_label="fake/model")


def _raw(point: CallPoint) -> dict:
    return point.model_dump(exclude_none=True)


def test_read_asks_one_free_bulk_call_with_the_prior_points(settings):
    gateway = FakeGateway([_raw(_point())])
    prompts = PromptEngine(settings)
    filing = _filing("c3", "2026-11-10T19:00:00+05:30", "CONCALL_PRESENTATION", "Earnings call transcript")
    paid = cm.paid_providers(settings)
    assert "deepseek" in paid
    out = cm.read(gateway, prompts, filing, "transcript", "Realty", TEXT, "", [{"id": "cm_b", "type": "guidance", "topic": "t",
                                                                               "statement": "s", "period": "FY27"}], paid)
    call = gateway.calls[0]
    assert call["route"] == "pass2_long" and call["bulk"] is True
    assert call["allow"](SimpleNamespace(provider="deepseek")) is False and call["allow"](SimpleNamespace(provider="gemini")) is True
    assert "cm_b" in call["user"] and "--- Page 2 of 3 ---" in call["user"] and "Sobha" in call["user"]
    assert "at most 60 points" in call["system"] and "$" not in call["system"].replace("$schema", "")
    assert out.served_by == "fake/model" and len(out.points) == 1 and out.prompt_chars > 1000


class FakeSink:
    def __init__(self, texts, dossier, filings):
        self.texts, self.dossier, self.filings, self.puts = texts, dossier, filings, []

    def query(self, name, params):
        assert name == "export_filings"
        return sorted((f for f in self.filings if f["news_id"] > params[1]), key=lambda f: f["news_id"])[:params[2]]

    def get_object(self, key):
        return self.texts.get(key)

    def get_dossier(self, scrip):
        return json.loads(json.dumps(self.dossier)) if self.dossier is not None else None

    def put_dossier(self, scrip, dossier):
        self.puts.append(dossier)
        self.dossier = dossier

    def company(self, scrip):
        return {"industry": "Real Estate"}


def _world(settings):
    moderator = "Moderator: welcome to the call. Moderator: the first question. Moderator: the last question, participant.\n"
    entry = {"v": 1, "digital": [moderator + PAGE_1.split("\n", 1)[1], PAGE_2.split("\n", 1)[1], PAGE_3.split("\n", 1)[1]],
             "has_image": [False] * 3, "ocr": {}}
    row = {"news_id": "call-2", "scrip_code": "123", "company_name": "Sobha Ltd", "symbol": "SOBHA", "headline": "Earnings call transcript",
           "subject": "", "category": "", "subcategory": "", "filed_at": "2026-11-10T19:00:00+05:30", "filing_date": "2026-11-10",
           "pdf_url": None, "xbrl_url": None, "status": "ANALYZED", "route": "NONE", "event_type": "CONCALL_PRESENTATION"}
    other = {**row, "news_id": "call-20"}
    return FakeSink({text_key("call-2"): gzip.compress(json.dumps(entry).encode())}, {"scrip_code": "123", "call_memory": []},
                    [other, row, {**row, "news_id": "call-1"}])


def test_the_command_writes_points_and_reasons_and_leaves_memory_alone(monkeypatch, settings, tmp_path, capsys):
    sink = _world(settings)
    good = _raw(_point())
    bad = _raw(_point(quote="a quote that is nowhere in the document"))
    gateway = FakeGateway([good, bad])
    monkeypatch.setattr(cli, "_pipeline", lambda s, k: SimpleNamespace(gateway=gateway, prompts=PromptEngine(s)))
    args = SimpleNamespace(ids="call-2,call-missing", out=str(tmp_path / "o"), apply=False)
    assert cli.cmd_call_memory(args, settings, sink) == 0
    detail = json.loads((tmp_path / "o" / "call-2.json").read_text())
    assert detail["kept"] == 1 and detail["dropped"] == 1 and detail["model"] == "fake/model" and detail["applied"] is False
    assert detail["points_dropped"][0]["reason"] == "quote" and detail["counts_by_type"] == {"guidance": 1}
    assert detail["points_kept"][0]["page"] == 1 and detail["kind"] == "transcript"
    summary = json.loads((tmp_path / "o" / "summary.json").read_text())
    assert summary["documents"] == 2 and summary["read"] == 1 and summary["failed"] == 1 and summary["dropped_by_reason"] == {"quote": 1}
    assert [r.get("error") for r in summary["rows"]] == [None, "PermanentSkip: not in the filings ledger"]
    assert sink.puts == [] and sink.dossier["call_memory"] == []   # nothing written to memory


def test_the_command_with_apply_merges_the_points_into_memory(monkeypatch, settings, tmp_path):
    sink = _world(settings)
    gateway = FakeGateway([_raw(_point())])
    monkeypatch.setattr(cli, "_pipeline", lambda s, k: SimpleNamespace(gateway=gateway, prompts=PromptEngine(s)))
    args = SimpleNamespace(ids="call-2", out=str(tmp_path / "o"), apply=True)
    assert cli.cmd_call_memory(args, settings, sink) == 0
    assert len(sink.puts) == 1 and [e["news_id"] for e in sink.dossier["call_memory"]] == ["call-2"]
    assert json.loads((tmp_path / "o" / "call-2.json").read_text())["applied"] is True


def test_the_command_survives_a_failed_reading(monkeypatch, settings, tmp_path):
    sink = _world(settings)
    monkeypatch.setattr(cli, "_pipeline", lambda s, k: SimpleNamespace(gateway=FakeGateway([], fail=True), prompts=PromptEngine(s)))
    args = SimpleNamespace(ids="call-2", out=str(tmp_path / "o"), apply=True)
    assert cli.cmd_call_memory(args, settings, sink) == 1
    assert "every provider failed" in json.loads((tmp_path / "o" / "summary.json").read_text())["rows"][0]["error"]
    assert sink.puts == []


def test_the_parser_knows_the_command():
    from bse_intel.cli import main

    with pytest.raises(SystemExit) as exit_info:
        main(["call-memory", "--help"])
    assert exit_info.value.code == 0


class Hook:
    """Just the parts of the pipeline the call-memory step touches."""

    _call_memory_step = __import__("bse_intel.pipeline", fromlist=["Pipeline"]).Pipeline._call_memory_step

    def __init__(self, settings, gateway):
        self.gateway, self.prompts, self.settings = gateway, PromptEngine(settings), settings


def test_the_step_does_nothing_with_the_switch_off(monkeypatch, settings):
    monkeypatch.delenv("MEMORY_CALL_V2", raising=False)
    gateway = FakeGateway([_raw(_point())])
    merged = {"scrip_code": "123"}
    Hook(settings, gateway)._call_memory_step(_filing("c", "2026-11-10T19:00:00+05:30", "CONCALL_PRESENTATION", "call transcript"), "Real Estate",
                                              merged, TEXT, "")
    assert gateway.calls == [] and "call_memory" not in merged


def test_the_step_only_queues_the_filing_with_the_switch_on_and_a_failure_is_swallowed(monkeypatch, settings):
    monkeypatch.setenv("MEMORY_CALL_V2", "1")
    filing = _filing("c", "2026-11-10T19:00:00+05:30", "CONCALL_PRESENTATION", "Earnings call transcript")
    gateway, sink = FakeGateway([_raw(_point())]), KvSink()
    merged = {"scrip_code": "123"}
    hook = Hook(settings, gateway)
    hook.sink = sink
    hook._call_memory_step(filing, "Real Estate", merged, TEXT, "")
    assert gateway.calls == [] and "call_memory" not in merged   # no AI call, memory untouched
    assert [i["news_id"] for i in call_queue.pending(sink)] == ["c"]
    item = call_queue.pending(sink)[0]
    assert item["scrip"] == "123" and item["filed_at"] == "2026-11-10T19:00:00+05:30"
    hook._call_memory_step(filing, "Real Estate", merged, TEXT, "")   # queued twice is one entry
    assert len(call_queue.pending(sink)) == 1
    hook.sink = SimpleNamespace(kv_get=lambda k: (_ for _ in ()).throw(RuntimeError("D1 down")))
    hook._call_memory_step(filing, "Real Estate", merged, TEXT, "")   # logged, nothing raised


class KvSink(FakeSink):
    def __init__(self, texts=None, dossier=None, filings=None):
        super().__init__(texts or {}, dossier, filings or [])
        self.kv = {}

    def kv_get(self, key):
        return self.kv.get(key)

    def kv_set(self, key, value, updated_at):
        self.kv[key] = value


def _queued_world(settings):
    world = _world(settings)
    sink = KvSink(world.texts, world.dossier, world.filings)
    return sink


def _pending_args(tmp_path, **kw):
    return SimpleNamespace(ids=None, out=str(tmp_path / "o"), apply=True, pending=True, time_budget=1500, limit=0, **kw)


def test_pending_reads_the_queue_writes_points_and_clears_the_filing(monkeypatch, settings, tmp_path):
    monkeypatch.setenv("MEMORY_CALL_V2", "1")
    sink = _queued_world(settings)
    call_queue.enqueue(sink, "call-2", "123", "2026-11-10T19:00:00+05:30")
    gateway = FakeGateway([_raw(_point())])
    monkeypatch.setattr(cli, "_pipeline", lambda s, k: SimpleNamespace(gateway=gateway, prompts=PromptEngine(s)))
    assert cli.cmd_call_memory(_pending_args(tmp_path), settings, sink) == 0
    assert [e["news_id"] for e in sink.dossier["call_memory"]] == ["call-2"] and len(gateway.calls) == 1
    assert call_queue.pending(sink) == []
    assert cli.cmd_call_memory(_pending_args(tmp_path), settings, sink) == 0 and len(gateway.calls) == 1   # nothing left to read


def test_pending_does_nothing_with_the_switch_off_or_an_empty_queue(monkeypatch, settings, tmp_path):
    sink = _queued_world(settings)
    call_queue.enqueue(sink, "call-2", "123", "x")
    called = []
    monkeypatch.setattr(cli, "_pipeline", lambda s, k: called.append(1))
    monkeypatch.delenv("MEMORY_CALL_V2", raising=False)
    assert cli.cmd_call_memory(_pending_args(tmp_path), settings, sink) == 0
    monkeypatch.setenv("MEMORY_CALL_V2", "1")
    assert cli.cmd_call_memory(_pending_args(tmp_path), settings, _queued_world(settings)) == 0
    assert called == [] and len(call_queue.pending(sink)) == 1


def test_a_transient_failure_stays_queued_and_is_given_up_after_three_attempts(monkeypatch, settings, tmp_path):
    monkeypatch.setenv("MEMORY_CALL_V2", "1")
    sink = _queued_world(settings)
    call_queue.enqueue(sink, "call-2", "123", "x")
    monkeypatch.setattr(cm.time, "sleep", lambda s: None)   # the waits between the asks and the documents
    busy = "route: no provider could serve the request (a: InternalServerError; b: rate limited (429); paced)"
    monkeypatch.setattr(cli, "_pipeline", lambda s, k: SimpleNamespace(gateway=FakeGateway([], fail=busy), prompts=PromptEngine(s)))
    for attempt in (1, 2):
        assert cli.cmd_call_memory(_pending_args(tmp_path), settings, sink) == 124   # left in the queue
        assert [i["attempts"] for i in call_queue.pending(sink)] == [attempt]
    assert cli.cmd_call_memory(_pending_args(tmp_path), settings, sink) == 0   # third failure: given up, nothing left
    assert call_queue.pending(sink) == [] and sink.puts == []
    states = json.loads(next(v for k, v in sink.kv.items() if k.startswith("callmem:s:")))
    assert states["call-2"]["state"] == "gave_up" and states["call-2"]["attempts"] == 3 and "rate limited (429)" in states["call-2"]["reason"]


def test_no_stored_text_yet_stays_queued(monkeypatch, settings, tmp_path):
    # the pipeline queues the filing before it writes the text (best effort), so a missing text is retried, not given up
    monkeypatch.setenv("MEMORY_CALL_V2", "1")
    sink = _queued_world(settings)
    sink.texts.clear()   # in the ledger, text not written yet
    call_queue.enqueue(sink, "call-2", "123", "x")
    monkeypatch.setattr(cli, "_pipeline", lambda s, k: SimpleNamespace(gateway=FakeGateway([]), prompts=PromptEngine(s)))
    assert cli.cmd_call_memory(_pending_args(tmp_path), settings, sink) == 124
    states = json.loads(next(v for k, v in sink.kv.items() if k.startswith("callmem:s:")))
    assert states["call-2"] == {**states["call-2"], "state": "retry", "attempts": 1, "reason": "RuntimeError: no stored text yet"}
    assert [i["news_id"] for i in call_queue.pending(sink)] == ["call-2"]


def test_a_filing_not_in_the_ledger_leaves_the_queue_at_once_with_its_reason(monkeypatch, settings, tmp_path):
    monkeypatch.setenv("MEMORY_CALL_V2", "1")
    sink = _queued_world(settings)
    call_queue.enqueue(sink, "call-missing", "123", "x")
    monkeypatch.setattr(cli, "_pipeline", lambda s, k: SimpleNamespace(gateway=FakeGateway([]), prompts=PromptEngine(s)))
    assert cli.cmd_call_memory(_pending_args(tmp_path), settings, sink) == 0
    states = json.loads(next(v for k, v in sink.kv.items() if k.startswith("callmem:s:")))
    assert states["call-missing"]["state"] == "gave_up" and states["call-missing"]["reason"] == "PermanentSkip: not in the filings ledger"
    assert call_queue.pending(sink) == []


def test_a_rerun_of_a_read_filing_is_queued_again(monkeypatch, settings):
    sink = KvSink()
    call_queue.enqueue(sink, "a", "1", "x")
    call_queue.settle(sink, call_queue.pending(sink)[0], "done")
    assert call_queue.pending(sink) == []
    call_queue.enqueue(sink, "a", "1", "x")
    assert [i["news_id"] for i in call_queue.pending(sink)] == ["a"]


def test_the_time_budget_stops_the_queue_with_exit_124(monkeypatch, settings, tmp_path):
    monkeypatch.setenv("MEMORY_CALL_V2", "1")
    sink = _queued_world(settings)
    for n in ("call-2", "call-1"):
        call_queue.enqueue(sink, n, "123", "x")
    gateway = FakeGateway([_raw(_point())])
    monkeypatch.setattr(cli, "_pipeline", lambda s, k: SimpleNamespace(gateway=gateway, prompts=PromptEngine(s)))
    clock = iter([0.0, 0.0, 5000.0, 5000.0, 5000.0, 5000.0])
    monkeypatch.setattr(cli.time, "monotonic", lambda: next(clock, 5000.0))
    args = _pending_args(tmp_path)
    args.time_budget = 100
    assert cli.cmd_call_memory(args, settings, sink) == 124
    assert len(gateway.calls) == 1 and [i["news_id"] for i in call_queue.pending(sink)] == ["call-1"]


def test_the_limit_caps_the_filings_read(monkeypatch, settings, tmp_path):
    monkeypatch.setenv("MEMORY_CALL_V2", "1")
    sink = _queued_world(settings)
    for n in ("call-2", "call-1"):
        call_queue.enqueue(sink, n, "123", "x")
    gateway = FakeGateway([_raw(_point())])
    monkeypatch.setattr(cli, "_pipeline", lambda s, k: SimpleNamespace(gateway=gateway, prompts=PromptEngine(s)))
    args = _pending_args(tmp_path)
    args.limit = 1
    cli.cmd_call_memory(args, settings, sink)
    assert len(gateway.calls) == 1


def test_gemini_3_serves_call_memory_with_the_cards_key_absent_and_has_no_live_reserve():
    import tomllib
    from pathlib import Path

    from bse_intel.ai.gateway import AIGateway

    config = tomllib.loads((Path(cli.__file__).parents[2] / "config" / "providers.toml").read_text())
    env = {"GEMINI_API_KEY_3": "k3", "NVIDIA_API_KEY": "n"}   # what call-memory.yml passes: no GEMINI_API_KEY
    gateway = AIGateway(config, client_factory=lambda *a, **k: None, env=env)
    entries = gateway.routes["call_memory"]
    assert {t.provider for t in entries} == {"gemini_3", "nvidia"}
    live = [t for t in entries if t.api_key]
    assert {t.provider for t in live} == {"gemini_3", "nvidia"}
    assert not any(t.provider == "gemini" for t in gateway.routes["pass2"] if t.api_key)
    assert not any(gateway.reserved_for_live(t) for t in entries if t.provider == "gemini_3")   # its own quota, not the cards' reserve
    assert all(t.provider != "gemini_3" for r, ts in gateway.routes.items() if r != "call_memory" for t in ts)


# ---------------------------------------------------------------- the independent review's cases (F180)
REVIEW_TEXT = """--- Page 1 of 2 ---
We guide revenue growth of 20% for FY27 and 25% for FY28. Operating cash flow was an outflow of (342.12) crore in H1.
EBITDA margin was up 2 percentage points.
--- Page 2 of 2 ---
Management: For FY28 we now see 22%.
"""


def test_an_answer_clarifies_only_its_own_period():
    fy27 = _point(statement="Revenue growth of 20% for FY27", topic="revenue_growth", value=20, period="FY27",
                  quote="We guide revenue growth of 20% for FY27 and 25% for FY28.")
    fy28 = _point(statement="Revenue growth of 25% for FY28", topic="revenue_growth", value=25, period="FY28",
                  quote="We guide revenue growth of 20% for FY27 and 25% for FY28.")
    answer = _point(statement="Revenue growth of 22% for FY28", topic="revenue_growth", value=22, period="FY28",
                    section="QA", page=2, quote="For FY28 we now see 22%.")
    kept, _ = cm.check_points([fy27, fy28, answer], REVIEW_TEXT)
    by_value = {p.value: p for p in kept}
    assert by_value[20].superseded_by is None and by_value[25].superseded_by == by_value[22].id


def test_a_negative_figure_and_percentage_points_are_kept():
    outflow = _point(type="kpi", statement="Operating cash flow of (342.12) crore in H1", metric="operating_cash_flow",
                     topic="operating_cash_flow", value=-342.12, unit="INR_CR", period=None,
                     quote="Operating cash flow was an outflow of (342.12) crore in H1.")
    points = _point(type="margin_driver", statement="EBITDA margin up 2 percentage points", metric="ebitda_margin",
                    topic="ebitda_margin_change", value=2, unit="PERCENTAGE_POINTS", period=None,
                    quote="EBITDA margin was up 2 percentage points.")
    sign = _point(type="margin_driver", statement="EBITDA margin up 2 percentage points", metric="ebitda_margin",
                  topic="ebitda_margin_change_pct", value=2, unit="%", period=None,
                  quote="EBITDA margin was up 2 percentage points.")
    kept, dropped = cm.check_points([outflow, points, sign], REVIEW_TEXT)
    assert len(kept) == 3, dropped


def test_periods_are_stored_in_one_form():
    p = _point(period="FY 2027", quote="We guide revenue growth of 20% for FY27 and 25% for FY28.", value=20,
               statement="Revenue growth of 20% for FY27")
    (kept,), _ = cm.check_points([p], REVIEW_TEXT)
    assert kept.period == "FY27"


def test_an_empty_reading_keeps_the_filings_earlier_points(monkeypatch, settings):
    monkeypatch.setenv("MEMORY_CALL_V2", "1")
    filing = _filing("c", "2026-11-10T19:00:00+05:30", "CONCALL_PRESENTATION", "Earnings call transcript")
    merged = {"scrip_code": "123", "call_memory": [{"id": "cm_c", "news_id": "c", "date": "2026-11-10"}]}
    Hook(settings, FakeGateway([_raw(_point(quote="words that are not in the document"))]))._call_memory_step(
        filing, "Real Estate", merged, TEXT, "")
    assert [e["id"] for e in merged["call_memory"]] == ["cm_c"]


# ---------------------------------------------------------------- after the first measured run (F180)
def test_a_long_document_is_read_in_parts_of_whole_pages():
    pages = "".join(f"--- Page {i} of 6 ---\n" + ("word " * 1000) + "\n" for i in range(1, 7))
    chunks = cm.parts(pages, limit=12_000)
    assert len(chunks) == 3 and all(c.startswith("--- Page") for c in chunks)
    assert "".join(chunks) == pages


def test_figures_in_words_and_an_assembled_slide_quote():
    slide = "--- Page 1 of 1 ---\n39.7%            27.7%\nROCE in H1FY27        ROE in H1FY27\nThree more analogs from Dec-Mar\n"
    roce = _point(type="kpi", statement="ROCE 39.7% in H1FY27", metric="roce", topic="roce", value=39.7, unit="PERCENT",
                  period="H1FY27", section="SLIDE", page=1, quote="39.7% ROCE in H1FY27")
    analogs = _point(type="catalyst", statement="Three more analogs filed Dec-Mar", metric="filings", topic="analog_filings",
                     value=3, unit=None, period=None, section="SLIDE", page=1, quote="Three more analogs from Dec-Mar")
    spoken = roce.model_copy(update={"section": "PREPARED", "topic": "roce_spoken"})
    kept, dropped = cm.check_points([roce, analogs, spoken], slide)
    assert {p.topic for p in kept} == {"roce", "analog_filings"} and [d["reason"] for d in dropped] == ["quote"]
    assert next(p for p in kept if p.topic == "roce").quote_assembled


def test_the_third_gemini_key_serves_call_memory_only():
    from bse_intel.ai.gateway import expand_key_aliases

    config = {"providers": {"gemini": {"api_key_env": "G1", "base_url": "u"},
                            "gemini_2": {"same_as": "gemini", "api_key_env": "G2"},
                            "gemini_3": {"same_as": "gemini", "api_key_env": "G3", "only_routes": ["call_memory"]}},
              "routes": {"pass2": [{"provider": "gemini", "model": "f"}],
                         "call_memory": [{"provider": "gemini", "model": "f"}, {"provider": "nvidia", "model": "d"}]}}
    both = expand_key_aliases(config, {"G1": "a", "G2": "b", "G3": "c"})
    assert [e["provider"] for e in both["routes"]["pass2"]] == ["gemini", "gemini_2"]
    assert [e["provider"] for e in both["routes"]["call_memory"]] == ["gemini_3", "nvidia"]
    unset = expand_key_aliases(config, {"G1": "a", "G2": "b"})
    assert [e["provider"] for e in unset["routes"]["call_memory"]] == ["gemini", "gemini_2", "nvidia"]
    assert "gemini_3" not in unset["providers"]


def test_a_run_killed_mid_reading_still_counts_an_attempt_and_three_give_it_up():
    sink = KvSink()
    call_queue.enqueue(sink, "a", "1", "x")
    for n in (1, 2, 3):   # three runs killed after start, before settle
        item = call_queue.pending(sink)[0]
        assert call_queue.start(sink, item) and item["attempts"] == n
    item = call_queue.pending(sink)[0]
    assert call_queue.start(sink, item) is False and call_queue.pending(sink) == []


def test_a_re_enqueue_while_reading_is_read_again():
    sink = KvSink()
    call_queue.enqueue(sink, "a", "1", "x")
    item = call_queue.pending(sink)[0]
    call_queue.start(sink, item)
    call_queue.enqueue(sink, "a", "1", "x")   # the pipeline re-ran the filing meanwhile
    call_queue.settle(sink, item, "done", count=False)
    assert [i["news_id"] for i in call_queue.pending(sink)] == ["a"]


def test_a_partly_read_document_is_written_and_read_again(monkeypatch, settings, tmp_path):
    monkeypatch.setenv("MEMORY_CALL_V2", "1")
    sink = _queued_world(settings)
    call_queue.enqueue(sink, "call-2", "123", "x")
    monkeypatch.setattr(cli, "_pipeline", lambda s, k: SimpleNamespace(gateway=FakeGateway([_raw(_point())]), prompts=PromptEngine(s)))
    monkeypatch.setattr(cli, "_read_call_document", lambda *a, **k: {"news_id": "call-2", "parts_failed": [2], "parts_failed_capacity": [2]})
    assert cli.cmd_call_memory(_pending_args(tmp_path), settings, sink) == 124
    assert [(i["news_id"], i["attempts"]) for i in call_queue.pending(sink)] == [("call-2", 1)]


def test_a_quote_of_figures_alone_proves_no_label():
    # APL Apollo (third run): "64% housing, 19% commercial" on the quote "64% 19%", where the slide says 64% commercial
    kept, dropped = _check(_point(type="dependence", statement="64% of revenue is housing", value=64, unit="PERCENT",
                                  period=None, quote="15%"))
    assert kept == [] and dropped[0]["detail"] == "the quote has no words, only figures"


def test_a_scale_word_above_the_quoted_row_counts():
    # a table row "Revenue 25,174" under "All figures in Rs lakh" (review of the third run: 31 true rows dropped)
    page = "--- Page 1 of 1 ---\nAll figures in Rs lakh\nRevenue from operations 25,174 for the half year\n"
    p = _point(type="kpi", statement="Revenue from operations Rs 25,174 lakh", value=25174, unit="INR_LAKH", period=None,
               quote="Revenue from operations 25,174", page=1)
    from bse_intel import call_memory as cm
    kept, dropped = cm.check_points([p], page)
    assert dropped == [] and kept[0].value_base == 25174 * 100_000


# ---------------------------------------------------------------- run 5 fixes: pages, columns, retry
# a slide set in two columns, read straight across: each sentence of the left column is cut by the right column's words
TWO_COLUMNS = """--- Page 24 of 40 ---
Our board is evaluating options for deployment of surplus cash.
--- Page 25 of 40 ---
We plan to open 15 exclusive stores
Gold sales were nil in the half year
of which 4 have been launched
against 205.50 Mn in the earlier half
--- Page 26 of 40 ---
Other income rose to 52 Mn.
"""
COLUMN_QUOTE = "We plan to open 15 exclusive stores of which 4 have been launched"


def _column_point(**kw) -> CallPoint:
    base = dict(type="capex_capacity", statement="15 exclusive stores planned, 4 launched", metric="stores", topic="stores",
                value=15, unit=None, period=None, section="SLIDE", page=24, quote=COLUMN_QUOTE)
    return _point(**{**base, **kw})


def test_a_quote_split_by_a_second_column_is_dropped():
    # joined across two columns it is two sentences' words, never one quote (review of F180)
    for page, section in ((24, "SLIDE"), (26, "SLIDE"), (25, "PREPARED")):
        kept, dropped = _check(_column_point(page=page, section=section), text=TWO_COLUMNS)
        assert kept == [] and _reasons(dropped) == ["quote"]
    # on a slide's own cited page the old word-by-word rule still applies (the figures sit in boxes), as before this work
    kept, _ = _check(_column_point(page=25), text=TWO_COLUMNS)
    assert len(kept) == 1


ONE_COLUMN = """--- Page 24 of 40 ---
Our board is evaluating options for deployment of surplus cash.
--- Page 25 of 40 ---
We plan to open 15 exclusive stores of
which 4 have been  launched.
Other income rose to 52 Mn.
--- Page 26 of 40 ---
Nothing here.
"""


def test_a_quote_on_the_page_before_or_after_the_cited_one_is_kept_whole():
    # the model named the slide's printed number 24; the words are on PDF page 25, broken over two lines
    quote = "We plan to open 15 exclusive stores of which 4 have been launched."
    for cited in (24, 25, 26):
        kept, dropped = _check(_column_point(page=cited, quote=quote), text=ONE_COLUMN)
        assert dropped == [] and kept[0].page == 25 and kept[0].pages == [25]
    assert cm._quote_on_near_pages(quote, 24, cm.split_pages(ONE_COLUMN), False)[:1] == (25,)


def test_a_quote_two_pages_from_the_cited_one_is_not_looked_for():
    pages = cm.split_pages(ONE_COLUMN + "--- Page 27 of 40 ---\nnothing")
    assert cm._quote_on_near_pages("We plan to open 15 exclusive stores of", 23, pages, False) is None


def test_a_quote_on_no_page_is_still_dropped():
    kept, dropped = _check(_column_point(quote="We plan to open 15 exclusive stores of which 9 have been shut"), text=ONE_COLUMN)
    assert kept == [] and _reasons(dropped) == ["quote"]


class FlakyGateway(FakeGateway):
    """Fails with the given errors in turn, then answers."""

    def __init__(self, errors, points):
        super().__init__(points)
        self.errors = list(errors)

    def complete_json(self, *a, **kw):
        if self.errors:
            self.calls.append({})
            err = self.errors.pop(0)
            raise err if isinstance(err, BaseException) else RuntimeError(err)
        return super().complete_json(*a, **kw)


def _read(gateway, settings):
    filing = _filing("c3", "2026-11-10T19:00:00+05:30", "CONCALL_PRESENTATION", "Earnings call transcript")
    return cm.read(gateway, PromptEngine(settings), filing, "transcript", "Realty", TEXT, "", None, frozenset())


def test_a_server_error_on_every_model_is_retried_once_and_the_attempts_are_counted(monkeypatch, settings):
    waits = []
    monkeypatch.setattr(cm.time, "sleep", waits.append)
    gateway = FlakyGateway(["route: no provider could serve the request (a: InternalServerError 503; b: circuit open)"],
                           [_raw(_point())])
    out = _read(gateway, settings)
    assert out.attempts == 2 and len(out.points) == 1 and out.parts_failed == [] and waits == [cm.RETRY_WAITS[0]]
    assert len(gateway.calls) == 2


def test_capacity_errors_are_asked_again_up_to_the_bound_and_the_reading_then_fails(monkeypatch, settings):
    waits = []
    monkeypatch.setattr(cm.time, "sleep", waits.append)
    gateway = FlakyGateway(["503 InternalServerError", "request timed out", "rate limited (429)", "paced"], [])
    with pytest.raises(cm.CallReadFailed, match=f"{cm.MAX_PART_ATTEMPTS} attempts") as caught:
        _read(gateway, settings)
    assert caught.value.capacity is True
    assert len(gateway.calls) == cm.MAX_PART_ATTEMPTS and waits == list(cm.RETRY_WAITS)


def test_a_429_then_success_waits_out_the_gateways_pause(monkeypatch, settings):
    waits = []
    monkeypatch.setattr(cm.time, "sleep", waits.append)
    gateway = FlakyGateway([_failed("rate limited (429)", "paced")], [_raw(_point())])
    out = _read(gateway, settings)
    assert out.attempts == 2 and len(out.points) == 1 and waits == [65.0] and out.parts_failed_capacity == []


def test_a_day_quota_stops_the_reading_without_a_retry(monkeypatch, settings):
    from bse_intel.ai.gateway import AllProvidersFailed
    monkeypatch.setattr(cm.time, "sleep", lambda s: pytest.fail("no wait on a spent day"))
    spent = AllProvidersFailed("call_memory", [("g", "ceiling", "rpd 19/20 (95% safety limit)")])
    assert spent.quota_exhausted
    gateway = FlakyGateway([spent], [])
    with pytest.raises(cm.DayQuotaExhausted):
        _read(gateway, settings)
    assert len(gateway.calls) == 1


def test_part_one_failing_for_capacity_is_asked_again_while_part_two_is_kept(monkeypatch, settings):
    waits = []
    monkeypatch.setattr(cm.time, "sleep", waits.append)
    monkeypatch.setattr(cm, "PART_CHARS", 100)
    text = "--- Page 1 of 2 ---\n" + "a" * 150 + "\n--- Page 2 of 2 ---\n" + "b" * 150 + "\n"
    asked = []

    class PartGateway(FakeGateway):
        def complete_json(self, route, system, user, schema, **kw):
            asked.append(user)
            if len(asked) == 1:   # part 1, first ask
                raise _failed("InternalServerError", "paced")
            return super().complete_json(route, system, user, schema, **kw)

    filing = _filing("c3", "2026-11-10T19:00:00+05:30", "CONCALL_PRESENTATION", "Earnings call transcript")
    out = cm.read(PartGateway([_raw(_point())]), PromptEngine(settings), filing, "transcript", "Realty", text, "", None, frozenset(),
                  gap_s=12.0)
    assert out.parts == 2 and out.parts_failed == [] and out.attempts == 2
    assert len(asked) == 3 and "aaaa" in asked[2] and "bbbb" not in asked[2]   # the ask repeated is part 1 alone
    assert waits == [12.0, 65.0]   # the gap between the parts, then the wait before the retry


def test_a_content_failure_is_not_asked_again(monkeypatch, settings):
    monkeypatch.setattr(cm.time, "sleep", lambda s: pytest.fail("no wait for a content failure"))
    gateway = FlakyGateway([_failed("ValidationError: reply is not JSON")], [])
    with pytest.raises(cm.CallReadFailed) as caught:
        _read(gateway, settings)
    assert caught.value.capacity is False and len(gateway.calls) == 1


def test_capacity_error_kinds():
    assert cm.capacity_error(_failed("InternalServerError", "rate limited (429)", "paced"))
    assert cm.capacity_error(_failed("busy: concurrency limit", "circuit open"))
    assert not cm.capacity_error(_failed("rate limited (429)", "ValidationError: points: field required"))
    assert not cm.capacity_error(_failed("HTTP 403 forbidden", "paced"))
    assert not cm.capacity_error(SimpleNamespace(capped=True))
    # review of #168: a number in a content failure is not a 5xx, nor a "connection" in its text a network failure
    assert not cm.capacity_error(_failed("ValidationError: value 500 not in the quote"))
    assert not cm.capacity_error(_failed("no JSON: the connection between revenue and margin"))
    assert cm.capacity_error(_failed("HTTP 502 bad gateway", "503 UNAVAILABLE", "connection reset by peer"))
    assert cm.capacity_error(_failed("APIConnectionError", "APITimeoutError"))   # the gateway's bare class names


def test_the_gap_is_a_minute_over_the_routes_lowest_requests_per_minute(settings):
    assert cm.pace_gap_s(settings) == 12.0   # providers.toml: rpm 5 on the call_memory route's Gemini models
    assert cm.pace_gap_s(SimpleNamespace(load_toml=lambda name: {})) == cm.DEFAULT_GAP_S


def test_a_day_quota_stops_the_queue_job_and_leaves_every_filing_queued_without_losing_an_attempt(monkeypatch, settings, tmp_path):
    from bse_intel.ai.gateway import AllProvidersFailed
    monkeypatch.setenv("MEMORY_CALL_V2", "1")
    monkeypatch.setattr(cm.time, "sleep", lambda s: None)
    sink = _queued_world(settings)
    call_queue.enqueue(sink, "call-2", "123", "x")
    call_queue.enqueue(sink, "call-3", "123", "x")
    spent = AllProvidersFailed("call_memory", [("g", "ceiling", "rpd 19/20 (95% safety limit)")])
    gateway = FakeGateway([], fail=False)
    gateway.complete_json = lambda *a, **k: (_ for _ in ()).throw(spent)
    monkeypatch.setattr(cli, "_pipeline", lambda s, k: SimpleNamespace(gateway=gateway, prompts=PromptEngine(s)))
    assert cli.cmd_call_memory(_pending_args(tmp_path), settings, sink) == 124
    assert sorted(i["news_id"] for i in call_queue.pending(sink)) == ["call-2", "call-3"]
    assert [i["attempts"] for i in call_queue.pending(sink)] == [0, 0]
    states = json.loads(next(v for k, v in sink.kv.items() if k.startswith("callmem:s:")))
    assert states["call-2"]["state"] == "retry" and "day quota" in states["call-2"]["reason"] and "call-3" not in states


def test_the_queue_job_leaves_a_gap_between_documents(monkeypatch, settings, tmp_path):
    monkeypatch.setenv("MEMORY_CALL_V2", "1")
    waits = []
    monkeypatch.setattr(cm.time, "sleep", waits.append)
    sink = _queued_world(settings)
    call_queue.enqueue(sink, "call-2", "123", "x")
    call_queue.enqueue(sink, "call-3", "123", "x")
    monkeypatch.setattr(cli, "_pipeline", lambda s, k: SimpleNamespace(gateway=FakeGateway([_raw(_point())]), prompts=PromptEngine(s)))
    monkeypatch.setattr(cli, "_read_call_document", lambda *a, **k: {"parts": 2, "attempts": 1})
    cli.cmd_call_memory(_pending_args(tmp_path), settings, sink)
    assert waits == [24.0]   # one gap of 12 s per request of the first document, none before the first


def test_a_refusal_is_not_retried(monkeypatch, settings):
    monkeypatch.setattr(cm.time, "sleep", lambda s: pytest.fail("no wait for a refusal"))
    gateway = FlakyGateway(["400 Bad Request: invalid argument"], [])
    with pytest.raises(RuntimeError, match="1 attempt"):
        _read(gateway, settings)
    assert len(gateway.calls) == 1


def test_a_valid_empty_answer_is_not_retried(monkeypatch, settings):
    monkeypatch.setattr(cm.time, "sleep", lambda s: pytest.fail("no wait for an empty answer"))
    gateway = FakeGateway([])
    out = _read(gateway, settings)
    assert out.points == [] and out.attempts == 1 and len(gateway.calls) == 1


def test_provider_error_kinds():
    assert cm.provider_error(RuntimeError("openrouter: InternalServerError"))
    assert cm.provider_error(RuntimeError("gemini: 503 UNAVAILABLE overloaded"))
    assert not cm.provider_error(RuntimeError("gemini: 429 quota"))
    assert not cm.provider_error(RuntimeError("403 Forbidden"))
    assert not cm.provider_error(SimpleNamespace(capped=True))


def test_the_ask_covers_the_kinds_of_point_run_5_missed(settings):
    system, _ = PromptEngine(settings).call_memory(
        _filing("c3", "2026-11-10T19:00:00+05:30", "CONCALL_PRESENTATION", "x"), "deck", "Realty", TEXT, None, part=(1, 1))
    for word in ("headwinds", "One-off items", "Dependences", "Dated events", "commissioning date", "discontinued operations"):
        assert word in system


# ---------------------------------------------------------------- review of the run-5 fixes
SPLICE_PAGE = "--- Page 1 of 1 ---\nTotal revenue grew 9% in Q1 on volumes. EBITDA margin rose 14% in Q2 on mix.\n"


def test_two_sentences_of_one_line_are_never_joined_into_one_quote():
    quote = "Total revenue grew 14% in Q2 on mix."
    kept, dropped = _check(_point(statement="Revenue grew 14% in Q2", value=14, period="Q2", quote=quote, page=1), text=SPLICE_PAGE)
    assert kept == [] and _reasons(dropped) == ["quote"]


SPLIT_CALL = """--- Page 1 of 2 ---
Analyst: Will you cut guidance by 30% for the year?
--- Page 2 of 2 ---
Management: we will hold our margin guidance for FY27.
We will not discuss it further.
"""


def test_with_no_page_cited_only_a_whole_quote_counts():
    spliced = "Will you cut guidance by 30% for the year? we will hold our margin guidance for FY27."
    point = _point(type="guidance", statement="Guidance cut by 30%", value=30, period="FY27", section="QA", quote=spliced, page=None)
    kept, dropped = _check(point, text=SPLIT_CALL)
    assert kept == [] and _reasons(dropped) == ["quote"]
    assert cm._quote_on_near_pages(COLUMN_QUOTE, None, cm.split_pages(ONE_COLUMN), True) is None


def test_a_text_without_page_markers_takes_only_whole_quotes():
    flat = "We plan to open 15 exclusive stores\nGold sales were nil\nof which 4 have been launched\n"
    kept, dropped = _check(_column_point(page=None), text=flat)
    assert kept == [] and _reasons(dropped) == ["quote"]


def test_a_slide_bag_of_words_is_for_the_cited_page_only():
    slide = "--- Page 3 of 4 ---\nDebt\n12%\nSafe harbour notice\n--- Page 4 of 4 ---\nEBITDA\n9%\ncrore\n"
    quote = "Debt 12% EBITDA 9% crore"
    assert cm._quote_on_near_pages(quote, 3, cm.split_pages(slide), True) is None
    point = _point(type="kpi", statement="Debt 12%", value=12, unit="PERCENT", period=None, section="SLIDE", quote=quote, page=3)
    kept, dropped = _check(point, text=slide)
    assert kept == [] and _reasons(dropped) == ["quote"]
    box = "--- Page 3 of 4 ---\nDebt\nEBITDA\n12%\n9%\ncrore\n--- Page 4 of 4 ---\nx\n"
    assert cm._quote_on_near_pages(quote, 3, cm.split_pages(box), True)[2] == "slide"


def test_a_quote_loses_its_trailing_punctuation_before_the_page_match():
    quote = "We plan to open 15 exclusive stores of which 4 have been launched,"
    assert cm._quote_on_near_pages(quote, 25, cm.split_pages(ONE_COLUMN), False)[0] == 25


# a question and a later answer, or two sentences on adjacent lines, are never joined
JOINED = """--- Page 1 of 1 ---
Analyst: Will you cut guidance by 30% this year?
Management: Let me think.
We will raise the dividend to Rs 5 per share by FY28.
Total revenue grew 9% in Q1 on volumes.
Other income was small.
Capex plan is 500 crore for FY27
"""


def test_sentences_of_adjacent_lines_are_not_joined():
    for quote, kw in (("Will you cut guidance by 30% this year? We will raise the dividend to Rs 5 per share by FY28.",
                       dict(value=5, unit="INR", period="FY28")),
                      ("Total revenue grew 9% in Q1 on volumes. Capex plan is 500 crore for FY27", dict(value=500, unit="INR_CR", period="FY27"))):
        kept, dropped = _check(_point(type="guidance", statement="a figure " + str(kw["value"]), section="QA", quote=quote, page=1, **kw),
                               text=JOINED)
        assert kept == [] and _reasons(dropped) == ["quote"]


def _failed(*details):
    from bse_intel.ai.gateway import AllProvidersFailed
    return AllProvidersFailed("pass2_long", [(f"m{i}", "failed", d) for i, d in enumerate(details)])


def test_the_retry_reads_the_models_own_outcomes():
    assert cm.provider_error(_failed("InternalServerError", "rate limited (429)"))
    assert cm.provider_error(_failed("HTTP 503 service unavailable", "circuit open"))
    assert not cm.provider_error(_failed("circuit open", "circuit open"))
    assert not cm.provider_error(_failed("rate limited (429)", "max 512 tokens exceeded"))
    assert not cm.provider_error(_failed("InternalServerError", "HTTP 403 forbidden"))
    assert not cm.provider_error(_failed("HTTP 400 bad request"))
    assert not cm.provider_error(_failed("InternalServerError", "model glm-9 not found"))
    assert not cm.provider_error(RuntimeError("model said 512 tokens"))
