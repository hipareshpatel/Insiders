"""METRIC_BUSINESS_LINE (owner, 1 Nov 2026: "fix at root cause, must be applicable to other companies also"): EICHERMOT files two
monthly updates on the 1st, Royal Enfield (~100,000 units) and VECV (~10,000). Memory kept one "volumes" figure a month, so the
VECV card for October showed Royal Enfield's April and May as its history. Operating figures now carry a business line."""

import json

from bse_intel import business_line, memory_split_lines
from bse_intel.dossier import merge, new_dossier
from bse_intel.models import Filing, Pass2Output
from bse_intel.signals import volume_strip
from bse_intel.sinks.local import LocalSink

RE, VECV = "Royal Enfield", "VECV"
ENTITIES = {"identity": {"former_names": [], "entities": [
    {"name": "VECV", "type": "subsidiary", "source_news_id": "x"}, {"name": "Royal Enfield", "type": "brand", "source_news_id": "x"},
    {"name": "Volvo Financial Services (India) Private Limited", "type": "Joint Venture (50%)", "source_news_id": "x"}]}}


def _filing(news_id, when, headline):
    return Filing(news_id=news_id, scrip_code="505200", company_name="Eicher Motors Limited", headline=headline, subject="",
                  filed_at=when, filing_date=when[:10], event_type="MONTHLY_BUSINESS_UPDATE")


def _out(rows):
    return Pass2Output.model_validate({
        "is_material": True, "event_type": "MONTHLY_BUSINESS_UPDATE", "timeline_entry": "t",
        "card": {"headline": "Monthly update", "impact_level": "LOW", "takeaway": "t", "what_happened": ["Sales reported."]},
        "dossier_delta": {"financial_metrics": rows}})


def _row(period, value, line=None):
    return {"metric": "volumes", "period": period, "value": value, "unit": "UNITS", **({"line": line} if line else {})}


MONTHS = (("APR-2026", "2026-05-01T12:09:00+05:30", 113164.0, 7318.0), ("MAY-2026", "2026-06-01T12:09:00+05:30", 103231.0, 7978.0),
          ("JUN-2026", "2026-07-01T12:09:00+05:30", 99000.0, 8200.0))


def _run(monkeypatch, on, by_headline=False):
    """Both lines' monthly updates for three months, in the order they were filed (RE first, VECV a minute after)."""
    monkeypatch.setenv("METRIC_BUSINESS_LINE", "1" if on else "0")
    d = {**new_dossier(_filing("seed", "2026-04-01T09:00:00+05:30", "h")), **ENTITIES}
    for i, (period, when, re_units, vecv_units) in enumerate(MONTHS):
        for name, units, news in ((RE, re_units, f"re-{i}"), (VECV, vecv_units, f"vecv-{i}")):
            headline = f"Eicher Motors: {name} sales for {period}" if by_headline else "Monthly business update"
            filing = _filing(news, when, headline)
            rows = [_row(period, units, None if by_headline else name)]
            remembered = _out(rows)
            business_line.assign(remembered.dossier_delta.financial_metrics, filing, d)
            d = merge(d, remembered, filing, None, "now")
    return d


def _series(d, line):
    return {e["period"]: e["value"] for e in d["financial_metrics"] if e["metric"] == "volumes" and e.get("line") == line}


def test_off_two_lines_overwrite_each_other_as_before(monkeypatch):
    d = _run(monkeypatch, on=False)
    rows = [e for e in d["financial_metrics"] if e["metric"] == "volumes"]
    assert len(rows) == 3 and not any("line" in e for e in rows)
    assert all(len(e["sources"]) == 2 for e in rows)   # the fault: one figure a month, the other line only in sources


def test_on_two_lines_in_one_month_stay_apart(monkeypatch):
    d = _run(monkeypatch, on=True)
    assert _series(d, RE) == {"APR-2026": 113164.0, "MAY-2026": 103231.0, "JUN-2026": 99000.0}
    assert _series(d, VECV) == {"APR-2026": 7318.0, "MAY-2026": 7978.0, "JUN-2026": 8200.0}
    assert not any("sources" in e for e in d["financial_metrics"] if e["metric"] == "volumes")   # one filing each


def test_code_names_the_line_from_the_headline_whatever_the_model_said(monkeypatch):
    d = _run(monkeypatch, on=True, by_headline=True)   # the model gave no line; the headline names it
    assert set(_series(d, RE)) == {"APR-2026", "MAY-2026", "JUN-2026"} and set(_series(d, VECV)) == set(_series(d, RE))
    monkeypatch.setenv("METRIC_BUSINESS_LINE", "1")
    rows = _out([_row("JUL-2026", 1.0, "Royal Enfield (RE)"), {**_row("JUL-2026", 2.0, "Company"), "metric": "revenue"}])
    business_line.assign(rows.dossier_delta.financial_metrics, _filing("n", "2026-08-01T10:00:00+05:30", "Monthly update"), d)
    assert [m.line for m in rows.dossier_delta.financial_metrics] == [RE, None]   # the model's word in memory's spelling; no line on a statement
    both = _out([_row("JUL-2026", 1.0, "Something Else")])
    business_line.assign(both.dossier_delta.financial_metrics, _filing("n", "2026-08-01T10:00:00+05:30", "Royal Enfield and VECV"), d)
    assert both.dossier_delta.financial_metrics[0].line == "Something Else"   # two lines named: the code does not choose


def test_statement_lines_never_take_a_line(monkeypatch):
    monkeypatch.setenv("METRIC_BUSINESS_LINE", "1")
    d = new_dossier(_filing("seed", "2026-04-01T09:00:00+05:30", "h"))
    out = _out([{"metric": "pat", "period": "Q1FY27", "value": 5.0, "line": "VECV"}])
    business_line.assign(out.dossier_delta.financial_metrics, _filing("a", "2026-08-01T10:00:00+05:30", "h"), d)
    d = merge(d, out, _filing("a", "2026-08-01T10:00:00+05:30", "h"), None, "now")
    assert [e.get("line") for e in d["financial_metrics"] if e["metric"] == "pat"] == [None]


def test_each_strip_shows_only_its_own_line(monkeypatch):
    d = _run(monkeypatch, on=True)
    vecv = volume_strip(d, "vecv-2")
    assert [m["period"] for m in vecv["months"]] == ["APR-2026", "MAY-2026", "JUN-2026"]
    assert [m["value"] for m in vecv["months"]] == [7318.0, 7978.0, 8200.0]
    re_strip = volume_strip(d, "re-2")
    assert [m["value"] for m in re_strip["months"]] == [113164.0, 103231.0, 99000.0]


def test_off_the_strip_is_the_old_one(monkeypatch):
    d = _run(monkeypatch, on=False)
    monkeypatch.setenv("METRIC_BUSINESS_LINE", "0")
    assert volume_strip(d, "vecv-2")["months"][-1]["value"] == 8200.0   # the latest source's figure, one series, nothing split


def test_the_memory_a_card_reads_holds_its_line_only(monkeypatch):
    from bse_intel.dossier import view_as_of

    d = _run(monkeypatch, on=True)
    def seen(line):
        view = view_as_of(d, "2026-09-01T00:00:00+05:30", line=line)
        return json.dumps(view)
    assert "113164" in seen(RE) and "7318" not in seen(RE)
    assert "7318" in seen(VECV) and "113164" not in seen(VECV)
    assert "113164" not in seen(None) and "7318" not in seen(None)   # the whole company: neither line's figure


def test_footer_kpi_is_the_filings_own_lines_series(monkeypatch):
    from bse_intel.dossier import results_snapshot

    d = _run(monkeypatch, on=True)
    d["financial_metrics"] += [{"metric": "revenue", "period": "Q1FY27", "value": 100.0, "unit": "INR_CR", "as_of": "2026-08-01T10:00:00+05:30",
                                "source_news_id": "res"}]
    assert business_line.of_filing(d, "vecv-0") == VECV and business_line.of_filing(d, "res") is None
    assert business_line.view(d, None)["financial_metrics"] == [e for e in d["financial_metrics"] if e["metric"] != "volumes"]


# ---- the repair of what memory already holds -------------------------------------------------------------------------------------

def _legacy():
    """Memory as it stands today: one figure a month (the latest source's), the other line only under sources[]; October is VECV's alone."""
    def src(news, value, when):
        return {"news_id": news, "as_of": when, "value": value, "unit": "UNITS"}
    rows = []
    for period, ids in (("APR-2026", (("nse-106606818", 113164.0), ("nse-106606779", 7318.0))),
                        ("MAY-2026", (("nse-106650962", 103231.0), ("nse-106650810", 7978.0)))):
        srcs = [src(n, v, "2026-05-01T12:09:00+05:30") for n, v in ids]
        rows.append({"metric": "volumes", "period": period, "value": ids[0][1], "unit": "UNITS", "as_of": srcs[0]["as_of"],
                     "source_news_id": ids[0][0], "sources": srcs, "value_news_id": ids[0][0]})
    rows.append({"metric": "volumes", "period": "OCT-2026", "value": 10861.0, "unit": "UNITS", "as_of": "2026-11-01T12:00:00+05:30",
                 "source_news_id": "nse-106838761"})
    rows.append({"metric": "pat", "period": "Q1FY27", "value": 5.0, "unit": "INR_CR", "as_of": "2026-08-01T10:00:00+05:30", "source_news_id": "res"})
    return {**ENTITIES, "scrip_code": "505200", "financial_metrics": rows}


CARDS = [{"scrip_code": "505200", "news_id": n, "filed_at": "2026-05-01T12:09:00+05:30", "headline": h, "card_json": json.dumps({"headline": h})}
         for n, h in (("nse-106606818", "Royal Enfield sells 113,164 motorcycles in April"), ("nse-106606779", "VECV sells 7,318 vehicles in April"),
                      ("nse-106650962", "Royal Enfield May 2026 sales"), ("nse-106650810", "VECV May 2026 sales"),
                      ("nse-106838761", "VECV October 2026: 10,861 vehicles"))]


class _Sink(LocalSink):
    def __init__(self, settings, cards):
        super().__init__(settings)
        self._cards = cards

    def query(self, name, params):
        return (self._cards if params[0] == "" else []) if name == "export_cards" else super().query(name, params)


def test_the_repair_splits_the_months_and_tags_the_lone_one(settings):
    sink = _Sink(settings, CARDS)
    sink.put_dossier("505200", _legacy())
    before = sink.get_dossier("505200")
    dry = memory_split_lines.run(sink, ["505200"])
    assert dry["error"] is None and dry["figures"] == 3 and dry["dossiers_written"] == 0 and sink.get_dossier("505200") == before
    assert sorted(dry["lines"]["505200"]) == [RE, VECV]
    text = memory_split_lines.render(dry)
    assert "would split" in text and "Royal Enfield 113164 from nse-106606818" in text and "VECV 7318 from nse-106606779" in text
    done = memory_split_lines.run(sink, ["505200"], apply=True)
    assert done["dossiers_written"] == 1 and done["backup"]["dossiers"] == 1
    d = sink.get_dossier("505200")
    assert _series(d, RE) == {"APR-2026": 113164.0, "MAY-2026": 103231.0}
    assert _series(d, VECV) == {"APR-2026": 7318.0, "MAY-2026": 7978.0, "OCT-2026": 10861.0}
    assert [e.get("line") for e in d["financial_metrics"] if e["metric"] == "pat"] == [None]   # a statement line is left alone
    assert memory_split_lines.run(sink, ["505200"])["figures"] == 0   # a second run finds nothing


def test_the_repair_never_invents_a_line_it_cannot_read(settings):
    cards = [dict(c, headline="Monthly business update", card_json="{}") for c in CARDS]
    sink = _Sink(settings, cards)
    sink.put_dossier("505200", _legacy())
    out = memory_split_lines.run(sink, ["505200"])
    assert out["figures"] == 0   # no headline names a line: nothing to split


def test_a_single_line_company_is_left_alone(settings):
    d = _legacy()
    cards = [dict(c, headline="Royal Enfield sales", card_json="{}") for c in CARDS]   # every filing names the same line
    sink = _Sink(settings, cards)
    sink.put_dossier("505200", d)
    assert memory_split_lines.run(sink, ["505200"])["figures"] == 0


def test_switch_off_the_prompt_and_view_are_unchanged(monkeypatch):
    from bse_intel.prompts.engine import PromptEngine
    from bse_intel.settings import Settings

    monkeypatch.setenv("METRIC_BUSINESS_LINE", "0")
    d = _legacy()
    assert business_line.view({**d, "financial_metrics": [{**e, "line": "X"} for e in d["financial_metrics"]]}, None)["financial_metrics"][0]["line"] == "X"
    flt = _filing("n", "2026-11-01T10:00:00+05:30", "Royal Enfield")
    assert business_line.assign(_out([_row("OCT-2026", 1.0, "VECV")]).dossier_delta.financial_metrics, flt, d) == 0
    engine = PromptEngine(Settings())
    system_off, _ = engine.pass2(flt, "MONTHLY_BUSINESS_UPDATE", None, None, "text")
    monkeypatch.setenv("METRIC_BUSINESS_LINE", "1")
    system_on, _ = engine.pass2(flt, "MONTHLY_BUSINESS_UPDATE", None, None, "text")
    assert system_on == system_off + "\n\n" + engine._business_line and 'set "line"' in system_on


def test_a_line_view_keeps_the_whole_company_statement_rows(monkeypatch):
    """Review of #324: a reader of one line's series must still see revenue and profit (statement rows carry no line)."""
    monkeypatch.setenv("METRIC_BUSINESS_LINE", "1")
    from bse_intel import business_line
    d = {"financial_metrics": [{"metric": "revenue", "period": "Q2FY27", "value": 5000.0},
                               {"metric": "volumes", "period": "OCT-2026", "value": 10861.0, "line": "VECV"},
                               {"metric": "volumes", "period": "OCT-2026", "value": 101000.0, "line": "Royal Enfield"}]}
    got = business_line.view(d, "VECV")["financial_metrics"]
    assert {(e["metric"], e.get("line")) for e in got} == {("revenue", None), ("volumes", "VECV")}


def test_a_segment_name_is_never_read_as_a_line_from_the_headline(monkeypatch):
    """Review of #324: "Cement" for a cement company is its whole business, not a line."""
    monkeypatch.setenv("METRIC_BUSINESS_LINE", "1")
    from bse_intel import business_line
    d = {"segment_mix": [{"segment": "Cement", "period": "Q2FY27"}], "financial_metrics": []}
    assert business_line.detect("Acme: cement production and sales volumes for October", d) is None
