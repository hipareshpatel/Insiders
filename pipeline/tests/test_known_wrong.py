"""The known-wrong list (F223, 28 Oct 2026): figures where the exchange's own file differs from the company's own results
statement are named in code, every memory writer skips them, and `memory-drop-known-wrong` takes the stored ones out with a
backup first. Run on the local sink (SQLite + a directory standing in for R2).

Also the classes a re-read of the file fixes, shown through the seed on stale memory (the plan in
docs/audit/known-wrong-2026-10-28.md leaves them to `seed-memory --scrips`): an EPS sign flipped by the code before 26 Oct,
an EPS stored as 0 while another tag held the real one, a unit slip written before the neighbour rule (Dolphin Offshore)."""

import copy
import json
import re
from pathlib import Path
from types import SimpleNamespace

from test_todo90 import CONT, EPS, NCI, OWN, PAT
from test_xbrl import HEAD, _ctx, _fact

from bse_intel import bse_gap_fill as bf
from bse_intel import known_wrong as kw
from bse_intel import memory_drop, restore
from bse_intel.bse import XbrlLink
from bse_intel.cli import cmd_memory_drop_known_wrong
from bse_intel.dossier import _metric_entry
from bse_intel.seed import SeedStats, seed_results
from bse_intel.sinks.local import LocalSink

FIXTURES = Path(__file__).parent / "fixtures"
WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
ECO, VADILAL, PRADEEP, VELJAN, KOVAI = "530643", "519152", "513532", "505232", "523323"


def _source(scrip, period, value, basis, unit="INR_CR", news_id=None, as_of=None):
    return {"news_id": news_id or f"xbrl:res:{scrip}:{period}", "as_of": as_of or "2025-05-20T18:00:00+05:30", "value": value,
            "unit": unit, "basis": basis, "lab": {"by": "file", "doc": "results", "basis": basis}}


def _entry(scrip, metric, period, value, basis="CONSOLIDATED", **kw_):
    unit = "INR" if metric.startswith("eps") else "INR_CR"
    return _metric_entry(metric, period, [_source(scrip, period, value, basis, unit, **kw_)])


def _dossier(scrip, *entries, **more):
    return {"schema_version": 3, "scrip_code": scrip, "company_name": "Demo", "financial_metrics": list(entries),
            "balance_sheet": [], "timeline": [], "updated_at": "2026-10-27T10:00:00+05:30", **more}


def _sink(settings, dossiers):
    sink = LocalSink(settings)
    for scrip, dossier in dossiers.items():
        sink.put_dossier(scrip, dossier)
    return sink


def _stored(sink, scrip, metric, period):
    return [e for e in sink.get_dossier(scrip)["financial_metrics"] if e["metric"] == metric and e["period"] == period]


def _figures(sink, scrip):
    return {(e["metric"], e["period"]): e["value"] for e in sink.get_dossier(scrip)["financial_metrics"]}


def _memory(settings):
    """Four of the listed companies as the BSE fill left them, with what must stay beside each wrong figure."""
    return {
        ECO: _dossier(ECO, _metric_entry("pat", "Q4FY25", [   # the same value on the other basis is another figure
            _source(ECO, "Q4FY25", 3.42, "CONSOLIDATED"),
            _source(ECO, "Q4FY25", 3.42, "STANDALONE", news_id="xbrl:res-sa:530643:Q4FY25")]),
                      _entry(ECO, "revenue", "Q4FY25", 41.5),
                      _entry(ECO, "pat", "Q3FY25", 3.42)),   # the same value in another period is another figure
        VELJAN: _dossier(VELJAN, _entry(VELJAN, "eps", "Q3FY26", 11.24), _entry(VELJAN, "pat", "Q3FY26", 5.06)),   # right already
        PRADEEP: _dossier(PRADEEP, _metric_entry("pat", "Q4FY26", [
            _source(PRADEEP, "Q4FY26", 15.83, "CONSOLIDATED"),
            _source(PRADEEP, "Q4FY26", 10.32, "CONSOLIDATED", news_id="n-later", as_of="2026-10-01T10:00:00+05:30")])),
        VADILAL: _dossier(
            VADILAL, _entry(VADILAL, "pat", "Q3FY25", -42.94, basis="CONSOLIDATED", news_id="xbrl:res:519152:cons"),
            _entry(VADILAL, "pat_discontinued", "Q3FY25", -24.63, basis="STANDALONE"),   # the line the file added to the profit
            standalone={"metrics": [{"metric": "pat", "period": "Q3FY25", "value": -42.94, "unit": "INR_CR", "as_of": "x",
                                     "source_news_id": "xbrl:res-sa:519152:Q3FY25", "lab": {"basis": "STANDALONE"}},
                                    {"metric": "pat", "period": "Q4FY25", "value": -42.94, "unit": "INR_CR", "as_of": "x",
                                     "source_news_id": "xbrl:res-sa:519152:Q4FY25", "lab": {"basis": "STANDALONE"}}],
                        "balance_sheet": []}),
    }


# --- the list ---------------------------------------------------------------------------------------------------------

def test_the_list_carries_each_figure_with_its_evidence():
    assert len(kw.KNOWN_WRONG_FIGURES) == len({(e.scrip, e.basis, e.period, e.metric) for e in kw.KNOWN_WRONG_FIGURES})
    for e in kw.KNOWN_WRONG_FIGURES:
        assert e.evidence and re.fullmatch(r"\d{4}-\d{2}-\d{2}", e.proven) and e.wrong != e.right
        assert e.basis in ("CONSOLIDATED", "STANDALONE", "") and kw.norm_metric(e.metric) == e.metric
    by = {(e.scrip, e.period, e.metric): (e.wrong, e.right) for e in kw.KNOWN_WRONG_FIGURES}
    assert by[(ECO, "Q4FY25", "pat")] == (3.42, 2.20) and by[(VADILAL, "Q3FY25", "pat")] == (-42.94, -18.31)
    assert by[(PRADEEP, "Q4FY26", "pat")] == (15.83, 10.32) and by[(VELJAN, "Q3FY26", "eps")] == (10.31, 11.24)
    assert by[(ECO, "Q4FY25", "tax_expense")] == (2.85, 4.07) and by[(PRADEEP, "Q4FY26", "tax_expense")] == (-2.76, 2.76)
    assert by[(VADILAL, "Q3FY25", "pat_discontinued")] == (-24.63, None)


def test_a_figure_matches_only_on_company_metric_period_basis_and_value():
    assert kw.listed(ECO, "pat", "Q4FY25", 3.42, "CONSOLIDATED")
    assert kw.listed(ECO, "PAT", "Q4FY25", 3.4200001, None), "a basis the writer does not state could be either"
    assert not kw.listed(ECO, "pat", "Q4FY25", 2.20, "CONSOLIDATED"), "the right figure for the same key is never held back"
    assert not kw.listed(ECO, "pat", "Q4FY25", 3.42, "STANDALONE"), "the other basis is another figure"
    assert not kw.listed(ECO, "pat", "Q3FY25", 3.42, "CONSOLIDATED") and not kw.listed(ECO, "revenue", "Q4FY25", 3.42)
    assert not kw.listed("500001", "pat", "Q4FY25", 3.42) and not kw.listed(None, "pat", "Q4FY25", 3.42)


# --- the drop ---------------------------------------------------------------------------------------------------------

def test_a_listed_entry_is_removed_and_a_different_value_for_the_same_key_is_kept(settings):
    sink = _sink(settings, _memory(settings))
    out = memory_drop.run(sink, apply=True)
    assert out["error"] is None and out["dossiers_written"] == 3 and out["backup"]["dossiers"] == 3   # Veljan's is right: not written

    eco = _figures(sink, ECO)
    (pat,) = _stored(sink, ECO, "pat", "Q4FY25")
    assert pat["basis"] == "STANDALONE" and pat["source_news_id"] == "xbrl:res-sa:530643:Q4FY25" and "sources" not in pat, \
        "the consolidated source (the listed figure) is gone, the standalone one of the same value is not it"
    assert eco[("revenue", "Q4FY25")] == 41.5 and eco[("pat", "Q3FY25")] == 3.42   # nothing else of the company is touched

    assert _figures(sink, VELJAN) == {("eps", "Q3FY26"): 11.24, ("pat", "Q3FY26"): 5.06}   # a different value, same key: kept
    # a figure with two sources keeps the later one and is rebuilt from it
    (pradeep,) = _stored(sink, PRADEEP, "pat", "Q4FY26")
    assert pradeep["value"] == 10.32 and pradeep["source_news_id"] == "n-later" and "sources" not in pradeep
    # Vadilal: the listed figure is the STANDALONE one, in the standalone block; the consolidated entry of the same value stays
    vadilal = sink.get_dossier(VADILAL)
    assert [m["period"] for m in vadilal["standalone"]["metrics"]] == ["Q4FY25"]
    assert _figures(sink, VADILAL) == {("pat", "Q3FY25"): -42.94}
    rows = {(r["scrip"], r["metric"]): r["status"] for r in out["rows"]}
    assert rows[(PRADEEP, "pat")] == "dropped" and rows[(VELJAN, "eps")] == "other value kept"
    assert rows[(KOVAI, "pat")] == "no dossier"
    assert "dropped" in memory_drop.render(out) and "restore --backup" in memory_drop.render(out)


def test_a_second_run_finds_nothing_more_to_drop(settings):
    sink = _sink(settings, _memory(settings))
    memory_drop.run(sink, apply=True)
    after = {s: sink.get_dossier(s) for s in (ECO, VELJAN, PRADEEP, VADILAL)}
    again = memory_drop.run(sink, apply=True)
    assert again["dossiers_written"] == 0 and again["backup"] is None
    assert {s: sink.get_dossier(s) for s in after} == after


def test_the_dry_run_writes_nothing(settings):
    sink = _sink(settings, _memory(settings))
    before = {s: copy.deepcopy(sink.get_dossier(s)) for s in (ECO, VELJAN, PRADEEP, VADILAL)}
    out = memory_drop.run(sink)
    assert out["apply"] is False and out["backup"] is None and out["dossiers_written"] == 0
    assert {r["status"] for r in out["rows"] if r["scrip"] == PRADEEP and r["metric"] == "pat"} == {"would drop"}
    assert {s: sink.get_dossier(s) for s in before} == before
    assert sink.list_objects("backup/") == []


def test_restore_undoes_the_drop_and_keeps_what_was_written_since(settings):
    sink = _sink(settings, _memory(settings))
    before = {s: copy.deepcopy(sink.get_dossier(s)) for s in (ECO, PRADEEP, VADILAL)}
    out = memory_drop.run(sink, apply=True, scrips=[ECO, PRADEEP, VADILAL])
    prefix = out["backup"]["prefix"]
    assert prefix.startswith("backup/memory-drop-known-wrong-")
    # the backup holds the dossier as it was and as the job wrote it, before the write
    assert json.loads(sink.get_object(f"{prefix}memory/{PRADEEP}.json")) == before[PRADEEP]
    assert json.loads(sink.get_object(f"{prefix}after/memory/{PRADEEP}.json")) == sink.get_dossier(PRADEEP)
    # a later writer adds a quarter to the Eco dossier
    later = sink.get_dossier(ECO)
    later["financial_metrics"].append(_entry(ECO, "revenue", "Q1FY26", 9.9))
    sink.put_dossier(ECO, later)

    preview = restore.plan(sink, prefix, everything=True)
    assert "will restore" in restore.render(preview)
    restore.apply(sink, preview)
    assert sink.get_dossier(PRADEEP) == before[PRADEEP] and sink.get_dossier(VADILAL) == before[VADILAL]
    eco = _figures(sink, ECO)
    assert eco[("revenue", "Q1FY26")] == 9.9   # what a later writer stored stays
    assert sink.get_dossier(ECO)["financial_metrics"][0] == before[ECO]["financial_metrics"][0]   # the wrong figure is back


def test_a_backup_that_does_not_read_back_stops_the_drop_before_that_company_is_written(settings):
    class Garbled(LocalSink):
        def get_object(self, key):
            body = super().get_object(key)
            return b"garbled" if key.startswith("backup/") and body and not key.endswith("meta.json") else body

    sink = Garbled(settings)
    memory = _memory(settings)
    for scrip, dossier in memory.items():
        sink.put_dossier(scrip, dossier)
    out = memory_drop.run(sink, apply=True)
    assert out["error"] and out["dossiers_written"] == 0
    assert {s: sink.get_dossier(s) for s in memory} == memory


def test_the_command_is_a_dry_run_by_default_and_names_a_company_not_on_the_list(settings, capsys):
    sink = _sink(settings, _memory(settings))
    assert cmd_memory_drop_known_wrong(SimpleNamespace(scrips=None, apply=False, json=None), settings, sink) == 0
    out = capsys.readouterr().out
    assert "dry run, nothing written" in out and "would drop" in out and sink.list_objects("backup/") == []
    assert cmd_memory_drop_known_wrong(SimpleNamespace(scrips="999999", apply=True, json=None), settings, sink) == 2
    assert "not on the list: 999999" in capsys.readouterr().err and sink.list_objects("backup/") == []
    assert cmd_memory_drop_known_wrong(SimpleNamespace(scrips=PRADEEP, apply=True, json=None), settings, sink) == 0
    assert _stored(sink, PRADEEP, "pat", "Q4FY26")[0]["value"] == 10.32 and _figures(sink, ECO)[("pat", "Q4FY25")] == 3.42


# --- every writer honours the list --------------------------------------------------------------------------------------

def _quarter_file(start, end, facts, nature="Consolidated"):
    body = HEAD + _ctx("Q", start, end)
    body += (f'<in-bse-fin:NatureOfReportStandaloneConsolidated contextRef="Q">{nature}'
             "</in-bse-fin:NatureOfReportStandaloneConsolidated>")
    for name, value in facts.items():
        body += _fact(name, "Q", value, "INRPerShare") if name.startswith("Basic") else _fact(name, "Q", round(value * 1e7), "INR")
    return (body + "</xbrli:xbrl>").encode()


class _Exchange:
    """An archive with one file per quarter, as the seed reads it."""

    def __init__(self, *files):   # (period, basis, filed on, bytes)
        self.files = {f"https://x/{p}-{b}.xml": data for p, b, _, data in files}
        self.links = [XbrlLink(url=f"https://x/{p}-{b}.xml", period=p, basis=b, filed_at=f"{d}T18:00:00+05:30") for p, b, d, _ in files]

    def results_xbrl(self, scrip):
        return self.links

    def download(self, url, max_bytes=0):
        return self.files[url]


def _seed(sink, scrip, exchange, since="2023-01-01"):
    stats = SeedStats()
    seed_results(sink, exchange, scrip, "Demo", since, None, stats, company={})
    return stats


def test_the_seed_skips_a_listed_figure_and_writes_the_right_one(settings):
    wrong_file = _quarter_file("2025-01-01", "2025-03-31", {"RevenueFromOperations": 41.5, PAT: 3.42, EPS: "1.19"})
    sink = _sink(settings, {})
    _seed(sink, ECO, _Exchange(("Q4FY25", "CONSOLIDATED", "2025-05-20", wrong_file)))
    got = _figures(sink, ECO)
    assert ("pat", "Q4FY25") not in got and got[("revenue", "Q4FY25")] == 41.5 and got[("eps", "Q4FY25")] == 1.19

    # a corrected file (or any other figure for the same key) is written as always
    right_file = _quarter_file("2025-01-01", "2025-03-31", {"RevenueFromOperations": 41.5, PAT: 2.20, EPS: "1.19"})
    _seed(sink, ECO, _Exchange(("Q4FY25", "CONSOLIDATED", "2025-06-20", right_file)))
    assert _figures(sink, ECO)[("pat", "Q4FY25")] == 2.20

    # the same wrong value on the other basis is not the listed figure
    other = _sink(settings, {})
    _seed(other, ECO, _Exchange(("Q4FY25", "STANDALONE", "2025-05-20", _quarter_file("2025-01-01", "2025-03-31", {
        "RevenueFromOperations": 41.5, PAT: 3.42}, nature="Standalone"))))
    assert _figures(other, ECO)[("pat", "Q4FY25")] == 3.42


def test_a_drop_is_not_undone_by_a_re_read(settings):
    wrong_file = _quarter_file("2026-01-01", "2026-03-31", {"RevenueFromOperations": 120.0, PAT: 15.83, EPS: "5.98"})
    sink = _sink(settings, {PRADEEP: _memory(settings)[PRADEEP]})
    memory_drop.run(sink, apply=True, scrips=[PRADEEP])
    _seed(sink, PRADEEP, _Exchange(("Q4FY26", "CONSOLIDATED", "2026-05-20", wrong_file)))   # the seed or the live run reads the same file
    assert all(e["value"] != 15.83 for e in _stored(sink, PRADEEP, "pat", "Q4FY26"))
    assert _figures(sink, PRADEEP)[("revenue", "Q4FY26")] == 120.0   # the rest of the file is written as always


def test_the_standalone_block_skips_a_listed_figure_too():
    from bse_intel.dossier import put_standalone
    from bse_intel.models import FinancialMetric

    dossier = _dossier(VADILAL)
    metrics = [FinancialMetric(metric="pat", period="Q3FY25", value=-42.94), FinancialMetric(metric="pat", period="Q4FY25", value=-42.94),
               FinancialMetric(metric="revenue", period="Q3FY25", value=60.1)]
    put_standalone(dossier, metrics, None, "2025-02-14T18:00:00+05:30", "xbrl:res-sa:519152:Q3FY25")
    assert {(m["metric"], m["period"]) for m in dossier["standalone"]["metrics"]} == {("pat", "Q4FY25"), ("revenue", "Q3FY25")}


def test_the_bse_fill_skips_a_listed_figure(settings):
    def seeded(entry_value):
        return {"financial_metrics": [
            {**_entry(ECO, "pat", "Q4FY25", entry_value), "sources": [_source(ECO, "Q4FY25", entry_value, "CONSOLIDATED")]},
            _entry(ECO, "revenue", "Q4FY25", 41.5)]}

    fresh, why = bf.new_figures({"financial_metrics": []}, seeded(3.42), ECO, {"Q4FY25"}, {"Q4FY25": "https://x/f.xml"})
    assert [e["metric"] for e in fresh] == ["revenue"] and why == {"known wrong figure": 1}
    fresh, why = bf.new_figures({"financial_metrics": []}, seeded(2.20), ECO, {"Q4FY25"}, {})
    assert sorted(e["metric"] for e in fresh) == ["pat", "revenue"] and why == {}
    assert "known wrong figure" in bf.REASONS

    # and the write itself, in case an entry reaches it another way
    sink = _sink(settings, {ECO: _dossier(ECO)})
    entries = [_entry(ECO, "pat", "Q4FY25", 3.42), _entry(ECO, "revenue", "Q4FY25", 41.5)]
    assert bf._write(sink, ECO, entries) == 1
    assert _figures(sink, ECO) == {("revenue", "Q4FY25"): 41.5}
    # the quarter-level skip (Kovai) stays as it was
    assert (KOVAI, "Q4FY26") in bf.KNOWN_WRONG


# --- what a re-read of the file fixes (the plan's seed-memory runs) -------------------------------------------------------

def test_a_re_read_puts_a_flipped_eps_sign_right(settings):
    """Alembic Q4FY26: the file's profit 67.13, owners' -33.87, EPS 2.61 (screener 2.61); memory held -2.61 from before the
    26 Oct fix. The seed replaces the file's own entry, so the stale figure goes."""
    scrip = "500710"
    stale = _dossier(scrip, _entry(scrip, "eps", "Q4FY26", -2.61), _entry(scrip, "pat", "Q4FY26", 67.13))
    sink = _sink(settings, {scrip: stale})
    file = _quarter_file("2026-01-01", "2026-03-31", {"RevenueFromOperations": 950.0, PAT: 67.13, OWN: -33.87, NCI: 0, EPS: "2.61"})
    _seed(sink, scrip, _Exchange(("Q4FY26", "CONSOLIDATED", "2026-05-20", file)), since="2025-01-01")
    got = _figures(sink, scrip)
    assert got[("eps", "Q4FY26")] == 2.61 and got[("pat", "Q4FY26")] == 67.13
    assert len(_stored(sink, scrip, "eps", "Q4FY26")) == 1


def test_a_re_read_replaces_an_eps_stored_as_zero_with_the_real_one_or_with_nothing(settings):
    """A file that tags 0 EPS first and the real one under another tag was stored as 0 before 26 Oct; a file with only the
    filler beside a profit now stores no EPS, and the stale 0 goes either way."""
    scrip = "532343"
    sink = _sink(settings, {scrip: _dossier(scrip, _entry(scrip, "eps", "Q3FY24", 0.0), _entry(scrip, "eps", "Q4FY24", 0.0),
                                            _entry(scrip, "pat", "Q3FY24", 70.24), _entry(scrip, "pat", "Q4FY24", 80.0))})
    both = _quarter_file("2023-10-01", "2023-12-31", {"RevenueFromOperations": 900.0, PAT: 70.24,
                                                       "BasicEarningsLossPerShareFromContinuingOperations": "0",
                                                       "BasicEarningsPerShare": "10.55"})
    filler = _quarter_file("2024-01-01", "2024-03-31", {"RevenueFromOperations": 950.0, PAT: 80.0,
                                                         "BasicEarningsLossPerShareFromContinuingOperations": "0"})
    _seed(sink, scrip, _Exchange(("Q3FY24", "CONSOLIDATED", "2024-02-10", both), ("Q4FY24", "CONSOLIDATED", "2024-05-10", filler)),
          since="2023-04-01")
    got = _figures(sink, scrip)
    assert got[("eps", "Q3FY24")] == 10.55 and ("eps", "Q4FY24") not in got and got[("pat", "Q4FY24")] == 80.0


def test_a_re_read_puts_a_scale_repair_made_before_the_neighbour_rule_right(settings):
    """Dolphin Offshore Q4FY24 (F196): memory held revenue 19.5 for the file's 1.95 crore; the file is right and the seed no
    longer multiplies it by ten, so the re-read replaces the stale figure (and the year it carries)."""
    scrip = "522261"
    sink = _sink(settings, {scrip: _dossier(scrip, _entry(scrip, "revenue", "Q4FY24", 19.5), _entry(scrip, "pat", "Q4FY24", 14.6))})
    file = (FIXTURES / "nse_dolphin_q4fy24_cons.xml").read_bytes()
    _seed(sink, scrip, _Exchange(("Q4FY24", "CONSOLIDATED", "2024-05-20", file)), since="2024-01-01")
    got = _figures(sink, scrip)
    assert got[("revenue", "Q4FY24")] == 1.95 and got[("pat", "Q4FY24")] != 14.6


# --- the maintenance job --------------------------------------------------------------------------------------------------

def test_the_maintenance_job_is_in_the_memory_group_a_dry_run_unless_apply():
    text = (WORKFLOWS / "maintenance.yml").read_text(encoding="utf-8")
    options = re.search(r"options: \[(refresh-card-blocks.*?)\]", text).group(1)
    assert "memory-drop-known-wrong" in options.split(", ")
    group = re.search(r"\$\{\{ contains\(fromJSON\('(\[[^']*\])'\), inputs\.command\) && 'maint-nse-memory'", text).group(1)
    assert "memory-drop-known-wrong" in json.loads(group)
    step = next(s for s in re.split(r"\n      - (?=name:|uses:)", text) if s.startswith("name: Drop the known-wrong figures"))
    assert "if: inputs.command == 'memory-drop-known-wrong'" in step
    assert '[ "$APPLY" = "true" ] && args+=(--apply)' in step and "APPLY: ${{ inputs.apply }}" in step
    assert "--apply" not in step.replace('args+=(--apply)', "")
