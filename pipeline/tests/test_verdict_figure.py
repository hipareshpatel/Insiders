"""CARD_VERDICT_NEEDS_FIGURE: the WRONG guidance and watch verdicts of the 1 Nov 2026 blind audit, each with the switch off (as
stored) and on. The evidence strings are the stored cards' own words."""

from __future__ import annotations

import pytest

from bse_intel import signals
from bse_intel.guidance_dated import why_no_verdict
from bse_intel.models import Filing, Pass2Output
from bse_intel.verdict_figure import why_unjudged

NEWS = "nse-106838016"


def _on(monkeypatch, on: bool) -> None:
    monkeypatch.setenv("CARD_VERDICT_NEEDS_FIGURE", "1" if on else "0")
    monkeypatch.setenv("CARD_GUIDANCE_DATED", "0")
    monkeypatch.setenv("DECK_DISCUSSED_PERIOD", "0")
    monkeypatch.setenv("CARD_WATCH_VERDICT", "1")


def _filing(when: str = "2026-10-31T14:19:31+05:30") -> Filing:
    return Filing(news_id=NEWS, scrip_code="1", company_name="X Limited", headline="h", subject="", filed_at=when,
                  filing_date=when[:10], event_type="CONCALL_PRESENTATION")


def _out(promises=(), watches=()) -> Pass2Output:
    return Pass2Output.model_validate({
        "is_material": True, "event_type": "CONCALL_PRESENTATION", "timeline_entry": "t",
        "card": {"headline": "Company earnings call for Q2FY27", "impact_level": "LOW", "takeaway": "t", "what_happened": ["x"]},
        "dossier_delta": {"promise_updates": [{"guidance_id": g, "status": s, "evidence": e} for g, s, e in promises],
                          "watch_updates": [{"watch_id": w, "status": s, "evidence": e} for w, s, e in watches]}})


def _watch(wid, text, target, check_in="Q2FY27", check_by="2026-09-30") -> dict:
    return {"id": wid, "kind": "KPI", "text": text, "target": target, "check_in": check_in, "check_by": check_by,
            "created_on": "2026-05-07T10:00:00+05:30"}


def _guide(gid, statement, target, metric="x", due="Q2FY27", due_date="2026-09-30") -> dict:
    return {"id": gid, "statement": statement, "target": target, "metric": metric, "due": due, "due_date": due_date,
            "given_on": "2026-07-21T10:00:00+05:30", "source_news_id": "nse-old", "status": "OPEN", "status_history": []}


def _run(before: dict, out: Pass2Output) -> list[tuple[str, str, str]]:
    found = signals._promises(before, {"financial_metrics": [], "guidance": [], "watchlist": []}, out, _filing())
    return [(s.type, s.severity, s.text) for s in found]


# --- (a) a verdict with no figure for the target -------------------------------------------------------------------------
HERIT = ("PROMISE", _guide("g_2d148653", "Add 5,000 farmers in Q2FY27 (added 5,000 in Q1)", None, metric="farmers_added"),
         "DELIVERED", "Procurement volumes increased 7% YoY to 1.73 MLPD.")
EMUD = ("WATCH", _watch("w_3a807c0b", "International revenue growth", "25%"), "MET",
        "International business now contributes 62% of total revenue, with North America at 38-40%")
# --- the target's own figure only ----------------------------------------------------------------------------------------
CLEAN = ("WATCH", _watch("w_e862f5a0", "Commissioning of 51 MWp solar capacity", None), "MISSED",
         "1.4 GW RE Power Sales capacity commissioned in FY26, including 51 MWp solar.")
OLA = ("PROMISE", _guide("g_f14bb261", "Ola Electric expects Q1 FY27 orders to double Q-o-Q to nearly 45,000 units.",
                         "45,000 units"), "DELIVERED", "Q1 FY27 orders expected at 40,000 to 45,000 units.")
# --- (b) / (c) a miss its own words contradict ---------------------------------------------------------------------------
SURY = ("WATCH", _watch("w_4e856d5c", "Net NPA ratio", "<3%"), "MISSED", "NNPA ratio 4.2% at Mar-26, within the <=4.21 target.")
# CANBK's watch named FY27, which watch_code (live since 27 Oct) already holds as not due; the same words on a quarter's watch:
CANBK = ("WATCH", _watch("w_52868646", "GNPA ratio", "1.50%"), "MISSED", "GNPA reached 1.33% in Q2FY27, surpassing the guidance.")
WRONG = [HERIT, EMUD, CLEAN, OLA, SURY, CANBK]


def _case(case):
    kind, item, status, evidence = case
    if kind == "PROMISE":
        return {"guidance": [item]}, _out(promises=[(item["id"], status, evidence)])
    return {"watchlist": [item]}, _out(watches=[(item["id"], status, evidence)])


@pytest.mark.parametrize("case", WRONG, ids=[c[1]["id"] for c in WRONG])
def test_the_audit_lines_off_keep_the_verdict_on_say_not_judged(monkeypatch, case):
    before, out = _case(case)
    _on(monkeypatch, False)
    off = _run(before, out)
    assert len(off) == 1 and off[0][1] in ("POSITIVE", "WARNING")   # as stored: a verdict
    _on(monkeypatch, True)
    on = _run(before, out)
    assert len(on) == 1 and on[0][:2] == ("WATCH_RESOLVED", "INFO") and "Not judged against this filing" in on[0][2]


RIGHT = [
    # a met figure inside a ceiling, a miss outside a floor, a delivered count above the target: all stand
    ("WATCH", _watch("w_a", "Net NPA ratio", "<=4.21%"), "MET", "NNPA ratio 3.9% at Sep-26."),
    ("WATCH", _watch("w_b", "EBITDA margin", "at least 19%"), "MISSED", "EBITDA margin was 17.2% in Q2FY27."),
    ("PROMISE", _guide("g_c", "Add 5,000 farmers in Q2FY27", "5,000 farmers"), "DELIVERED", "Added 5,400 farmers in Q2FY27."),
    ("PROMISE", _guide("g_d", "Commission 51 MWp in Q2FY27", "51 MWp"), "DELIVERED", "Commissioned 51 MWp of solar capacity in Q2FY27."),
    ("WATCH", _watch("w_e", "International revenue growth", "25%"), "MET", "International revenue grew 31% YoY."),
    # a target with no figure (an event) is outside the rule
    ("PROMISE", _guide("g_f", "Launch the new plant in Q2FY27", None), "DELIVERED", "The plant was launched in August."),
]


@pytest.mark.parametrize("case", RIGHT, ids=[c[1]["id"] for c in RIGHT])
def test_verdicts_with_their_figure_stand_both_ways(monkeypatch, case):
    before, out = _case(case)
    for on in (False, True):
        _on(monkeypatch, on)
        got = _run(before, out)
        assert len(got) == 1 and got[0][1] in ("POSITIVE", "WARNING"), (on, got)


def test_canbk_as_stored_is_already_not_due_under_the_watch_verdict(monkeypatch):
    before, out = _case(("WATCH", _watch("w_52868646", "GNPA trending to FY27 guidance", "1.50%", check_in="FY27", check_by="2027-03-31"),
                         "MISSED", "GNPA reached 1.33% in Q2FY27, surpassing the FY27 guidance."))
    for on in (False, True):
        _on(monkeypatch, on)
        assert _run(before, out) == []


def test_off_gives_nothing(monkeypatch):
    _on(monkeypatch, False)
    assert why_unjudged("MISSED", "1.50%", "GNPA reached 1.33%", "GNPA") is None


def test_a_bare_figure_without_a_lower_is_better_topic_gives_no_bound(monkeypatch):
    _on(monkeypatch, True)
    # revenue 1,400 Cr against a bare 1,500 Cr: the miss is right, and a bare figure is no ceiling for revenue
    assert why_unjudged("MISSED", "₹1,500 Cr", "Revenue was ₹1,400 Cr.", "FY27 revenue") is None


# --- (d) a target due before the filing's period is not "not due" --------------------------------------------------------
SHAKTI = {"id": "g_9b4e3b9d", "statement": "0.5 GW module plant to be commissioned by end-Q1FY27.", "target": "0.5 GW",
          "metric": "module_capacity", "due": "Q1FY27", "due_date": "2026-06-30", "given_on": "2026-01-15T10:00:00+05:30"}
METRICS = [{"metric": "revenue", "period": "Q2FY27", "value": 100.0, "source_news_id": NEWS, "as_of": "2026-10-31T14:19:31+05:30"}]


def test_shaktipump_a_past_target_is_not_called_not_due(monkeypatch):
    _on(monkeypatch, False)
    assert why_no_verdict(SHAKTI, METRICS, NEWS) == "the target is not due for the period this filing reports"
    _on(monkeypatch, True)
    assert why_no_verdict(SHAKTI, METRICS, NEWS) == "it was due Q1FY27, which has passed; this filing reports Q2FY27 and does not settle it"


def test_a_year_target_on_its_last_quarter_keeps_the_old_wording(monkeypatch):
    _on(monkeypatch, True)
    eiel = {**SHAKTI, "due": "FY26", "due_date": "2026-03-31"}
    q4 = [{**METRICS[0], "period": "Q4FY26"}]
    assert why_no_verdict(eiel, q4, NEWS) == "the target is not due for the period this filing reports"
    later = {**SHAKTI, "due": "Q3FY27", "due_date": "2026-12-31"}
    assert why_no_verdict(later, METRICS, NEWS) == "the target is not due for the period this filing reports"


@pytest.mark.parametrize("evidence", ["Revenue growth strong at 18 per cent.", "Revenue growth strong at 18 pct.",
                                      "Revenue growth strong at 18 percent."])
def test_per_cent_and_pct_are_percent(monkeypatch, evidence):
    _on(monkeypatch, True)
    assert why_unjudged("MET", "15%", evidence, "Revenue growth") is None
    assert why_unjudged("MET", "15 per cent", evidence, "Revenue growth") is None
    assert why_unjudged("MET", "15 pct", "Revenue grew 18%.", "Revenue growth") is None
