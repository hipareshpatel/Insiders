"""The one-time BSE fill of memory gaps for companies NSE lists no results for (F201): the market-cap filter, NSE read at run
time, nothing overwritten, the BSE label, and a dry run that writes nothing."""
import json
from datetime import date
from types import SimpleNamespace

from bse_intel import bse_gap_fill as bf
from bse_intel import memory_gaps as mg
from bse_intel.bse import XbrlLink
from bse_intel.dossier import label

from test_seed import GI_XML

TODAY = date(2026, 10, 25)   # the newest quarter past its deadline is Q1FY27
Q1FY27_XML = GI_XML.replace(b"2026-07-01", b"2026-04-01").replace(b"2026-09-30", b"2026-06-30")
URL = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/q1fy27.xml"
SETTINGS = SimpleNamespace(universe_min_mcap_cr=500.0, text_cache_dir=None)


class Sink:
    def __init__(self, companies, dossiers=None):
        self.companies, self.dossiers, self.kv, self.writes = companies, dict(dossiers or {}), {}, 0

    def company(self, scrip):
        return self.companies.get(scrip)

    def get_dossier(self, scrip):
        d = self.dossiers.get(scrip)
        return json.loads(json.dumps(d)) if d is not None else None

    def put_dossier(self, scrip, dossier):
        self.writes += 1
        self.dossiers[scrip] = dossier

    def kv_get(self, key):
        return self.kv.get(key)

    def kv_set(self, key, value, at=None):
        self.kv[key] = value


class Nse:
    def __init__(self, rows=None, failed=()):
        self.rows, self.integrated_failed, self.asked = rows or {}, set(failed), []

    def financial_results(self, symbol, quarterly=True):
        self.asked.append(symbol)
        return self.rows.get(symbol, [])


class Bse:
    def __init__(self, links=None, files=None):
        self.links, self.files, self.listed, self.downloaded = links or {}, files or {}, [], []

    def results_xbrl(self, scrip):
        self.listed.append(scrip)
        return self.links.get(scrip, [])

    def download(self, url, max_bytes=0):
        self.downloaded.append(url)
        return self.files.get(url)


def company(symbol, cap):
    return {"symbol": symbol, "company_name": symbol.title(), "market_cap_cr": cap}


def setup(companies, nse=None, bse=None, dossiers=None):
    sink = Sink(companies, dossiers)
    report = mg.survey(sink, sorted(companies), TODAY)
    symbols = {s: c["symbol"] for s, c in companies.items()}
    link = XbrlLink("Q1FY27", "STANDALONE", URL, "2026-08-10T18:00:00")
    return sink, report, symbols, nse or Nse(), bse or Bse({s: [link] for s in companies}, {URL: Q1FY27_XML})


def test_a_class_b_company_above_the_cut_off_is_filled_and_labelled_bse():
    sink, report, symbols, nse, bse = setup({"1": company("NIRLON", 900.0)})
    out = bf.run(sink, report, symbols, nse, bse, SETTINGS, apply=True)
    assert out["companies_class_b"] == 1 and out["companies_filled"] == 1 and out["quarters_filled"] == 1
    entries = {e["metric"]: e for e in sink.dossiers["1"]["financial_metrics"]}
    assert entries["revenue"]["period"] == "Q1FY27" and entries["revenue"]["value"] == 6651.87
    for entry in entries.values():
        assert entry["exchange"] == "BSE" and entry["source_url"] == URL and entry["lab"]["exchange"] == "BSE"
        assert all(s["exchange"] == "BSE" for s in entry.get("sources", [])) and entry["source_news_id"].startswith("xbrl:res:1:")
    assert {r["source"] for r in out["rows"]} == {"BSE"}
    assert "Q1FY27" not in mg.check(sink.dossiers["1"], TODAY)["missing"]


def test_market_cap_filter_skips_small_and_unknown_without_asking_anyone():
    companies = {"1": company("SMALL", 120.0), "2": company("UNKNOWN", None), "3": company("EDGE", 500.0)}
    sink, report, symbols, nse, bse = setup(companies)
    out = bf.run(sink, report, symbols, nse, bse, SETTINGS, apply=True)
    assert out["skipped"]["mcap below cut-off"] == 1 and out["skipped"]["mcap unknown"] == 1
    assert nse.asked == ["EDGE"] and bse.listed == ["3"] and out["companies_filled"] == 1 and "1" not in sink.dossiers


def test_a_company_nse_lists_results_for_is_left_alone_and_a_failed_nse_list_is_not_empty():
    companies = {"1": company("HASNSE", 900.0), "2": company("FLAKY", 900.0)}
    sink, report, symbols, _, bse = setup(companies)
    nse = Nse({"HASNSE": [object()]}, failed={"FLAKY"})
    out = bf.run(sink, report, symbols, nse, bse, SETTINGS, apply=True)
    assert out["skipped"] == {"nse has results": 1, "nse list unavailable": 1}
    assert out["companies_class_b"] == 0 and bse.listed == [] and sink.writes == 0


def test_never_overwrites_a_figure_memory_holds():
    held = {"financial_metrics": [{"metric": "revenue", "period": "Q1FY27", "value": 1.0, "basis": "STANDALONE",
                                   "source_news_id": "xbrl:res:1:Q1FY27", "unit": "INR_CR",
                                   "lab": label("file", "results", "2026-08-01")}]}
    sink, report, symbols, nse, bse = setup({"1": company("PARTIAL", 900.0)}, dossiers={"1": held})
    # the quarter is partial (revenue held, pat missing), so it is no gap quarter: the file adds nothing and revenue stays
    out = bf.run(sink, report, symbols, nse, bse, SETTINGS, apply=True)
    assert [e["value"] for e in sink.dossiers["1"]["financial_metrics"] if e["metric"] == "revenue"] == [1.0]
    assert out["quarters_filled"] == 0
    # a quarter that is a gap for one metric only: the figure the file also holds for the other is skipped
    before = {"financial_metrics": [dict(held["financial_metrics"][0])]}
    after = {"financial_metrics": [
        {"metric": "revenue", "period": "Q1FY27", "value": 6651.87, "basis": "STANDALONE", "sources": [{"news_id": "xbrl:res:1:Q1FY27"}]},
        {"metric": "pat", "period": "Q1FY27", "value": 946.4, "basis": "STANDALONE", "sources": [{"news_id": "xbrl:res:1:Q1FY27"}]}]}
    fresh, why = bf.new_figures(before, after, "1", {"Q1FY27"}, {"Q1FY27": URL})
    assert [e["metric"] for e in fresh] == ["pat"] and why == {"quarter held": 1}


def test_a_figure_on_another_basis_than_memory_main_basis_is_not_added():
    before = {"financial_metrics": [{"metric": "revenue", "period": "Q4FY26", "value": 5.0, "basis": "CONSOLIDATED",
                                     "source_news_id": "xbrl:res:1:Q4FY26", "lab": label("file", "results", None)}]}
    after = {"financial_metrics": [{"metric": "pat", "period": "Q1FY27", "value": 9.0, "basis": "STANDALONE",
                                    "sources": [{"news_id": "xbrl:res:1:Q1FY27"}]}]}
    fresh, why = bf.new_figures(before, after, "1", {"Q1FY27"}, {})
    assert fresh == [] and why == {"basis differs": 1}


def test_a_dry_run_writes_nothing_and_keeps_no_state():
    sink, report, symbols, nse, bse = setup({"1": company("NIRLON", 900.0)})
    out = bf.run(sink, report, symbols, nse, bse, SETTINGS, apply=False)
    assert out["companies_filled"] == 1 and out["figures_filled"] >= 2 and out["figures_written"] == 0
    assert sink.writes == 0 and sink.dossiers == {} and sink.kv == {}
    again = bf.run(sink, report, symbols, nse, bse, SETTINGS, apply=False)
    assert again["companies_filled"] == 1 and "dry run" in bf.render(out)


def test_an_apply_run_remembers_handled_companies_and_restart_forgets():
    sink, report, symbols, nse, bse = setup({"1": company("NIRLON", 900.0)})
    bf.run(sink, report, symbols, nse, bse, SETTINGS, apply=True)
    second = bf.run(sink, report, symbols, nse, bse, SETTINGS, apply=True)
    assert second["companies_skipped_tried"] == 1 and second["companies_filled"] == 0
    assert bf.run(sink, report, symbols, nse, bse, SETTINGS, apply=True, restart=True)["companies_skipped_tried"] == 0


def test_bse_listing_nothing_is_counted_and_the_time_budget_leaves_more():
    sink, report, symbols, nse, _ = setup({"1": company("A", 900.0), "2": company("B", 900.0)})
    out = bf.run(sink, report, symbols, nse, Bse(), SETTINGS, apply=True)
    assert out["skipped"]["bse lists nothing"] == 2
    ticks = iter([0, 0, 99, 99])
    late = bf.run(sink, report, symbols, nse, Bse(), SETTINGS, apply=True, restart=True, time_budget=10,
                  clock=lambda: next(ticks))
    assert late["more"] is True


# F214, TODO 108: quarters older than a company's first NSE results row
Q4FY26_XML = GI_XML.replace(b"2026-07-01", b"2026-01-01").replace(b"2026-09-30", b"2026-03-31")
URL_Q4 = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/q4fy26.xml"


def nse_row(period_end):
    return SimpleNamespace(period_end=period_end)


def pre_setup(nse_rows):
    companies = {"1": company("LATE", 900.0)}
    sink = Sink(companies)
    report = mg.survey(sink, ["1"], TODAY)
    links = [XbrlLink("Q1FY27", "STANDALONE", URL, "2026-08-10T18:00:00"),
             XbrlLink("Q4FY26", "STANDALONE", URL_Q4, "2026-05-10T18:00:00")]
    return sink, report, {"1": "LATE"}, Nse({"LATE": nse_rows}), Bse({"1": links}, {URL: Q1FY27_XML, URL_Q4: Q4FY26_XML})


def test_a_late_listed_company_gets_only_the_quarters_older_than_its_first_nse_row():
    sink, report, symbols, nse, bse = pre_setup([nse_row("2026-06-30")])   # NSE's first row is Q1FY27
    out = bf.run(sink, report, symbols, nse, bse, SETTINGS, apply=True, pre_nse=True)
    periods = {e["period"] for e in sink.dossiers["1"]["financial_metrics"]}
    assert periods == {"Q4FY26"} and out["companies_pre_nse"] == 1 and out["companies_class_b"] == 0
    assert out["quarters_filled"] == 1 and {r["source"] for r in out["rows"]} == {"BSE"}
    assert all(e["exchange"] == "BSE" for e in sink.dossiers["1"]["financial_metrics"])


def test_a_gap_inside_nses_range_is_not_filled_from_bse():
    # NSE holds Q3FY26 and Q1FY27; Q4FY26 is a hole inside that range and BSE has it, but it is not older than NSE's first row
    sink, report, symbols, nse, bse = pre_setup([nse_row("2025-12-31"), nse_row("2026-06-30")])
    out = bf.run(sink, report, symbols, nse, bse, SETTINGS, apply=True, pre_nse=True)
    # the quarters older than Q3FY26 stay candidates (BSE is asked) but the file's Q4FY26 and Q1FY27 are not written
    assert out["companies_pre_nse"] == 1 and out["companies_filled"] == 0 and out["rows"] == []
    # and the file holding only those quarters is not even downloaded (F218: only the quarters needed)
    assert sink.writes == 0 and sink.dossiers == {} and out["skipped"].get("bse lists no needed quarter")


def test_the_switch_off_and_rows_without_a_quarter_leave_a_company_nse_lists_alone():
    sink, report, symbols, nse, bse = pre_setup([nse_row("2026-06-30")])
    out = bf.run(sink, report, symbols, nse, bse, SETTINGS, apply=True, pre_nse=False)
    assert out["skipped"] == {"nse has results": 1} and bse.listed == [] and sink.writes == 0
    sink, report, symbols, nse, bse = pre_setup([object()])   # no quarter end on the row: nothing is "older than NSE"
    out = bf.run(sink, report, symbols, nse, bse, SETTINGS, apply=True, pre_nse=True)
    assert out["skipped"] == {"nse has results": 1} and bse.listed == [] and sink.writes == 0


def test_the_pre_nse_switch_is_read_from_the_environment_and_a_dry_run_writes_nothing(monkeypatch):
    monkeypatch.delenv("BSE_FILL_PRE_NSE", raising=False)
    sink, report, symbols, nse, bse = pre_setup([nse_row("2026-06-30")])
    assert bf.run(sink, report, symbols, nse, bse, SETTINGS)["companies_pre_nse"] == 0   # default off
    monkeypatch.setenv("BSE_FILL_PRE_NSE", "1")
    out = bf.run(sink, report, symbols, nse, bse, SETTINGS, apply=False)
    assert out["companies_pre_nse"] == 1 and out["quarters_filled"] == 1 and out["figures_written"] == 0
    assert sink.writes == 0 and sink.dossiers == {} and sink.kv == {}


# F218: the fill reads BSE through the ported adapter (BSE's own page headers), and a refusal prints its summary


class _Adapter:
    """Stands in for adapters.bse.BSEClient: answers by path or URL, or raises what it is given."""

    def __init__(self, answers):
        self.answers, self.calls, self.closed = answers, [], False

    def _answer(self, key):
        self.calls.append(key)
        got = self.answers[key]
        if isinstance(got, Exception):
            raise got
        return got

    def get(self, path, params, dataset, covers=None):
        return self._answer(path)

    def fetch_url(self, url, params, dataset, covers=None, file=False):
        assert file   # a filing's file: counted toward the file cap, a 404 is Missing
        return self._answer(url)

    def close(self):
        self.closed = True


_ARCHIVE = json.dumps({"Table": [
    {"Quarter": "Consolidated-Dec-24;DQ2024-2025;124.00;c", "Fld_QuarterName": "Quarter", "stand_xbrl_link": None,
     "conso_xbrl_link": "/XBRLFILES/FourOneUploadDocument/a.xml", "Filing_Date_Time": "2025-02-12T15:53:53",
     "Revised_Date_Time": None}]}).encode()


def test_the_ported_client_lists_the_archive_and_fetches_files_through_the_adapter():
    from bse_intel.adapters import bse as ported
    from bse_intel.bse import AttachmentError

    url = "https://www.bseindia.com/XBRLFILES/FourOneUploadDocument/a.xml"
    saved = []
    fake = _Adapter({"Result_Arch_ng/w": _ARCHIVE, url: b"<xbrl/>", "gone": ported.Missing("HTTP 404"),
                     "dead": ported.Failed("HTTP 503 after 3 retries"),
                     "removed": ported.Blocked("HTTP 410 from removed (requests)"),
                     "bad": ported.Blocked("HTTP 400 from bad (requests)")})
    with bf.PortedBse(fake) as bse:
        bse.raw = SimpleNamespace(save=lambda *a: saved.append(a))
        bse.warm_up()
        links = bse.results_xbrl("532811")
        assert [(link.period, link.basis, link.url) for link in links] == [("Q3FY25", "CONSOLIDATED", url)]
        assert saved and saved[0][1] == {"scrip_cd": "532811"}   # the archive's JSON as received
        assert bse.download(url) == b"<xbrl/>"
        assert bse.download("gone") is None   # that quarter's gap, not a refusal
        assert bse.download("removed") is None   # a 410 too, as the old path had it
        try:
            bse.download("bad")
            raise AssertionError("a 400 must fail the company, not stop the run")
        except AttachmentError:
            pass
        try:
            bse.download("dead")
            raise AssertionError("a dead file must raise")
        except AttachmentError:
            pass
    assert fake.closed


def test_a_refusal_through_the_ported_client_stops_with_bses_own_answer():
    from bse_intel.adapters import bse as ported
    from bse_intel.bse import SourceBlockedError

    bse = bf.PortedBse()
    bse._client = _Adapter({"Result_Arch_ng/w": ported.Blocked("HTTP 403 from x (requests)")})
    bse._session.last = SimpleNamespace(text="<HTML><HEAD><TITLE>Access Denied</TITLE></HEAD>\n<BODY>Reference #18.ab",
                                        headers={"Server": "AkamaiGHost"})
    try:
        bse.results_xbrl("532811")
        raise AssertionError("a refusal must raise")
    except SourceBlockedError as exc:
        assert "HTTP 403" in str(exc) and "Access Denied" in str(exc) and "Reference #18.ab" in str(exc)
    bse._client = _Adapter({"Result_Arch_ng/w": b"<html>maintenance</html>"})
    bse._session.last = None
    try:
        bse.results_xbrl("532811")
        raise AssertionError("a page that is not JSON must raise")
    except SourceBlockedError as exc:
        assert "not JSON" in str(exc)


def test_the_summary_of_a_run_bse_refused_before_any_company_prints():
    """Run 40450783308 (27 Oct 2026): BSE refused, then the summary raised KeyError 'companies_pre_nse'."""
    outcome = {"apply": False, "more": False, "failed": ["refused: x"], "rows": [], "min_mcap_cr": 500.0,
               "companies_with_gaps": 0, "companies_skipped_tried": 0, "companies_class_b": 0, "companies_filled": 0,
               "quarters_filled": 0, "figures_filled": 0, "figures_written": 0, "skipped": {}}
    assert "NSE lists only later quarters  0" in bf.render(outcome)


def test_every_downloaded_file_is_kept_in_our_store_and_read_from_it_next_time(monkeypatch):
    """Owner, 27 Oct 2026: "Don't discard those 100 files": a dry run's downloads go into our XBRL store too."""
    from bse_intel import xbrl_store

    store = {}
    monkeypatch.setattr(xbrl_store, "enabled", lambda sink: sink is not None)
    monkeypatch.setattr(xbrl_store, "put", lambda sink, url, data: store.__setitem__(url, data) or True)
    monkeypatch.setattr(xbrl_store, "get", lambda sink, url: store.get(url) if sink is not None else None)
    fake = _Adapter({"u1": b"<xbrl/>"})
    bse = bf.PortedBse(fake)
    bse.keep = object()
    assert bse.download("u1") == b"<xbrl/>" and store == {"u1": b"<xbrl/>"}
    assert bse.download("u1") == b"<xbrl/>"
    assert fake.calls == ["u1"]   # the second time from our store, not BSE (and not counted toward the cap)
    assert bse.files == {"downloaded": 1, "kept": 1, "from_store": 1}


def test_only_the_missing_quarters_and_what_their_checks_read_are_downloaded():
    """Owner, 27 Oct 2026: "We should download which we need": not every quarter from the oldest gap to today, but enough
    for the unit and long-year checks (the four quarters before a gap and the one after)."""
    assert bf.needed_quarters({"Q4FY23"}) == {"Q4FY22", "Q1FY23", "Q2FY23", "Q3FY23", "Q4FY23", "Q1FY24"}
    assert len(bf.needed_quarters({"Q1FY24", "Q4FY23"})) == 7
    periods = ("Q3FY22", "Q4FY22", "Q1FY23", "Q2FY23", "Q3FY23", "Q4FY23", "Q1FY24", "Q2FY24", "Q3FY24", "Q1FY27")
    links = [XbrlLink(p, "CONSOLIDATED", f"https://x/{p}.xml", "2025-01-01T00:00:00") for p in periods]
    recorder = bf._RecordingBse(SimpleNamespace(results_xbrl=lambda scrip: links), bf.needed_quarters({"Q4FY23"}))
    assert [link.period for link in recorder.results_xbrl("1")] == ["Q4FY22", "Q1FY23", "Q2FY23", "Q3FY23", "Q4FY23",
                                                                    "Q1FY24"]
    assert recorder.listed == len(periods)
