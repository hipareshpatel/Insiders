"""Call memory v2 (TODO 83, F180, docs/design/call-memory.md): the checks of section 3 on small texts modelled on the audit
cases, the memory write, the merge guard, the switch, the command and the pipeline hook."""
from __future__ import annotations

import gzip
import json
from types import SimpleNamespace

import pytest

from bse_intel import call_memory as cm
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
    kept, dropped = _check(_point(statement="Capex of 500 crore", type="capex_capacity", value=None, unit=None, period=None,
                                  quote="the plant is near the river bank"))
    assert kept == [] and _reasons(dropped) == ["figure"]
    assert "500" in dropped[0]["detail"]
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


def test_a_model_base_value_that_is_wrong_drops_the_point():
    kept, dropped = _check(_point(type="capex_capacity", statement="Adds 10 lakh tonnes", value=10, unit="LAKH_TONNES", value_base=100_000,
                                  base_unit="TONNES", period="FY28", quote="We will add 10 lakh tonnes of capacity by FY28"))
    assert _reasons(dropped) == ["unit"]


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
            raise RuntimeError("every provider failed")
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
    assert [r.get("error") for r in summary["rows"]] == [None, "LookupError: no stored text"]
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


def test_the_step_writes_points_with_the_switch_on_and_a_failure_is_swallowed(monkeypatch, settings):
    monkeypatch.setenv("MEMORY_CALL_V2", "1")
    filing = _filing("c", "2026-11-10T19:00:00+05:30", "CONCALL_PRESENTATION", "Earnings call transcript")
    merged = {"scrip_code": "123"}
    Hook(settings, FakeGateway([_raw(_point())]))._call_memory_step(filing, "Real Estate", merged, TEXT, "")
    assert [e["news_id"] for e in merged["call_memory"]] == ["c"]
    failing = {"scrip_code": "123", "call_memory": [{"id": "cm_x", "news_id": "old", "date": "2026-05-01"}]}
    Hook(settings, FakeGateway([], fail=True))._call_memory_step(filing, "Real Estate", failing, TEXT, "")   # logged, nothing raised
    assert [e["id"] for e in failing["call_memory"]] == ["cm_x"]


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
