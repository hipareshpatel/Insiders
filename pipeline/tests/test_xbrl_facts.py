"""Every fact of every results XBRL file kept outside the dossier (xbrl_facts.py, owner 28 Oct 2026): the parse reuses xbrl.py and
loses nothing, the document round-trips, the command reads stored files only (no NSE request without ``--download``), lists the
filings whose file is not stored, and a download goes through the seed's fetch under FILE_CAP."""

from __future__ import annotations

import csv
import gzip
import io
import json
import re
from datetime import date
from pathlib import Path

import httpx
import pytest

from bse_intel import cli, xbrl, xbrl_facts, xbrl_store
from bse_intel.file_cap import files
from bse_intel.nse import NseClient
from bse_intel.sinks.platform import PlatformSink

FIXTURES = Path(__file__).parent / "fixtures"
TITAN = (FIXTURES / "nse_old_titan_q2fy24.xml").read_bytes()      # consolidated Q2FY24; breaks Other expenses into rows (dimensions)
VESUVIUS = (FIXTURES / "nse_vesuvius_halfyearly_dec_h2fy26.xml").read_bytes()   # a December year end: only a half and a full year
SHAREHOLDING = (FIXTURES / "nse_shp_csbbank_q1fy24.xml").read_bytes()
URL = "https://nsearchives.nseindia.com/corporate/xbrl/TITAN_Q2FY24.xml"
URL2 = "https://nsearchives.nseindia.com/corporate/xbrl/TITAN_Q1FY24.xml"
Q2_END = date(2023, 9, 30)


class FakeSink(PlatformSink):
    """The platform sink's R2 side in memory (xbrl_store only keeps files for a PlatformSink)."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_object(self, key, body, content_type="application/json"):
        self.objects[key] = body

    def get_object(self, key):
        return self.objects.get(key)

    def list_objects(self, prefix):
        return sorted(k for k in self.objects if k.startswith(prefix))

    def query(self, name, params):
        return []


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for name in ("FILE_CAP", "FILE_CAP_SHARDS", "FILE_CAP_USED", "FILE_CAP_MARKER_DIR", "GITHUB_ENV", "XBRL_STORE_MAX_MB"):
        monkeypatch.delenv(name, raising=False)
    files.reset()
    xbrl_store.reset()
    yield
    files.reset()
    xbrl_store.reset()


def dossier(rows: dict[str, str | None]):
    """A memory with one results source per period; ``rows`` maps a period to the file url the seed stamped (None: never stamped)."""
    metrics = []
    for period, url in rows.items():
        source = {"news_id": f"xbrl:res:1:{period}", "basis": "CONSOLIDATED", "lab": {"file_url": url} if url else {}}
        metrics.append({"metric": "revenue", "period": period, "value": 100.0, "unit": "INR_CR", "basis": "CONSOLIDATED",
                        "source_news_id": f"xbrl:res:1:{period}", "sources": [source], "lab": source["lab"]})
    return {"financial_metrics": metrics}


def sink_with(rows, stored: dict[str, bytes] | None = None):
    sink = FakeSink()
    sink.objects["memory/1.json"] = json.dumps(dossier(rows)).encode()
    for url, data in (stored or {}).items():
        xbrl_store.put(sink, url, data)
    return sink


class CountingNse(NseClient):
    """The real client over a mock transport: its download path, pacing hooks and file counting are the ones a run uses."""

    def __init__(self, body=TITAN, hits=None):
        def handler(request):
            if hits is not None:
                hits.append(str(request.url))
            return httpx.Response(200, content=body)
        super().__init__(transport=httpx.MockTransport(handler), sleep=lambda s: None, retries=1, pause=(0, 0))
        self._warmed = True


# --- the parse ---------------------------------------------------------------------------------------------------

def test_facts_parse_every_fact_with_its_context_unit_and_decimals():
    doc = xbrl_facts.parse_facts(TITAN, "500114", URL)
    assert doc["v"] == 1 and doc["scrip"] == "500114" and doc["url"] == URL
    assert doc["period"] == "Q2FY24" and doc["basis"] == "CONSOLIDATED" and doc["fy_end_month"] == 3
    # one fact per element that has a context and a text: the same rule xbrl.py reads (nothing dropped)
    import xml.etree.ElementTree as ET
    expected = sum(1 for _ in xbrl._fact_elements(ET.fromstring(TITAN)))
    assert doc["n_facts"] == len(doc["facts"]) == expected > 300
    facts = xbrl_facts.Facts(doc)
    # a number where the fact has a unit, as the file spells it; text stays text
    revenue = [row for row in doc["facts"] if row[0] == "RevenueFromOperations" and row[1] == "OneD"]
    assert len(revenue) == 1 and revenue[0][3] == 125290000000.0 and revenue[0][2] == "INR" and revenue[0][4] == -7
    assert doc["units"]["INR"] == "MONEY" and doc["units"]["INRPerShare"] == "PER_SHARE"
    assert all(isinstance(row[3], str) for row in doc["facts"] if row[2] is None)
    # a period or an instant, its length and its label; a dimension where the context has one
    assert doc["contexts"]["OneD"] == {"s": "2023-07-01", "e": "2023-09-30", "m": 3, "l": "Q2FY24"}
    assert doc["contexts"]["OneI"] == {"i": "2023-09-30"}
    assert doc["contexts"]["OneOperatingExpenses01D"]["d"] == {"in-bse-fin:DetailsOfOtherExpensesAxis": "OneOperatingExpenses01Member"}
    # the breakdown of Other expenses is kept beside the total, with its description
    rows = facts.described(("OtherExpenses",), "^Advertising", end=Q2_END, months=3)
    assert rows == [("OtherExpenses", "Advertising", 268.0)]
    # the same revenue xbrl.parse stores, in crore
    stored = next(m.value for m in xbrl.parse(TITAN).metrics if m.metric == "revenue" and m.period == "Q2FY24")
    assert facts.cr("RevenueFromOperations", end=Q2_END, months=3) == pytest.approx(stored)
    assert facts.get("OtherExpenses", end=Q2_END, months=3) == 10560000000   # the undimensioned total, not a row of it


def test_facts_round_trip_through_the_stored_bytes():
    doc = xbrl_facts.parse_facts(TITAN, "500114", URL)
    body = xbrl_facts.dumps(doc)
    assert xbrl_facts.loads(body) == doc
    assert body == xbrl_facts.dumps(xbrl_facts.loads(body))            # the same facts are the same bytes
    assert 1_000 < len(body) < 40_000                                    # the size estimate: a few KB a filing
    sink = FakeSink()
    size = xbrl_facts.save(sink, "500114", "Q2FY24", "CONSOLIDATED", doc)
    key = "raw/xbrl-facts/500114/Q2FY24-consolidated.json.gz"
    assert xbrl_facts.key("500114", "Q2FY24", "CONSOLIDATED") == key and len(sink.objects[key]) == size
    again = xbrl_facts.load(sink, "500114", "Q2FY24", "CONSOLIDATED")
    assert again.doc == doc and len(again) == doc["n_facts"] and xbrl_facts.load(sink, "500114", "Q1FY24", "CONSOLIDATED") is None


def test_the_key_is_under_a_prefix_the_worker_allows():
    worker = (Path(__file__).parents[2] / "web" / "worker" / "internal.ts").read_text(encoding="utf-8")
    allowed = re.search(r"OBJECT_PREFIXES = \[([^\]]*)\]", worker)[1]
    prefixes = re.findall(r'"([^"]+)"', allowed)
    key = xbrl_facts.key("500114", "Q2FY24", None)
    assert any(key.startswith(p) for p in prefixes) and not "xbrl_facts/".startswith(tuple(prefixes))
    assert key.endswith("/Q2FY24-unknown.json.gz")
    assert not key.startswith(xbrl_store.PREFIX)    # not under the 180-day lifecycle rule of raw/xbrl/


def test_a_half_yearly_december_filer_is_kept_though_xbrl_parse_labels_nothing():
    assert xbrl.parse(VESUVIUS) is None                 # a 6- and a 12-month period of a non-March year get no label there
    doc = xbrl_facts.parse_facts(VESUVIUS, "520113")
    assert doc["fy_end_month"] == 12 and doc["period"] == "Q3FY26" and doc["n_facts"] > 20
    facts = xbrl_facts.Facts(doc)
    assert facts.cr("RevenueFromOperations", end=date(2025, 12, 31), months=12) == pytest.approx(2104.33)
    assert facts.cr("RevenueFromOperations", end=date(2025, 12, 31), months=6) == pytest.approx(550.77)
    assert (date(2025, 12, 31), 12) in facts.durations() and facts.get("ScripCode") is None


def test_files_that_are_not_results_give_no_facts():
    assert xbrl_facts.parse_facts(SHAREHOLDING, "1") is None
    assert xbrl_facts.parse_facts(b"not xml", "1") is None
    assert xbrl_facts.parse_facts(b"<xbrl/>", "1") is None


# --- the command: stored files only ------------------------------------------------------------------------------

def test_a_run_reads_stored_files_lists_the_missing_and_never_fetches_without_the_flag():
    sink = sink_with({"Q2FY24": URL, "Q1FY24": URL2, "Q4FY23": None}, stored={URL: TITAN})
    hits: list[str] = []
    out = xbrl_facts.run(sink, [("1", "TITAN")], client=CountingNse(hits=hits))        # a client is there, the flag is not
    assert hits == [] and files.used == 0 and out["downloaded"] == 0 and out["download"] is False
    assert out["files_listed"] == 2 and out["facts_saved"] == 1 and out["missing"] == 1 and out["no_url"] == 1
    assert xbrl_facts.key("1", "Q2FY24", "CONSOLIDATED") in sink.objects                # the stored file's facts are kept
    assert xbrl_facts.key("1", "Q1FY24", "CONSOLIDATED") not in sink.objects
    rows = {r["period"]: r for r in out["missing_rows"]}
    assert rows["Q1FY24"]["url"] == URL2 and rows["Q1FY24"]["reason"] == "file not stored"
    assert rows["Q4FY23"]["url"] == "" and "no file url" in rows["Q4FY23"]["reason"]
    table = list(csv.DictReader(io.StringIO(xbrl_facts.to_csv(out))))
    assert [r["period"] for r in table] == ["Q1FY24", "Q4FY23"] and table[0]["scrip"] == "1" and table[0]["symbol"] == "TITAN"
    assert out["bytes"] > 0 and out["facts"] > 300 and "DescriptionOfOtherExpenses: Advertising" not in out["interesting"]
    text = xbrl_facts.render(out)
    assert "files not stored (to download) 1" in text and "download not asked for" in text and "KB a file" in text


def test_a_second_run_does_not_read_the_files_again_unless_forced():
    sink = sink_with({"Q2FY24": URL}, stored={URL: TITAN})
    xbrl_facts.run(sink, [("1", "TITAN")])
    again = xbrl_facts.run(sink, [("1", "TITAN")])
    assert again["facts_stored_before"] == 1 and again["facts_saved"] == 0
    assert xbrl_facts.run(sink, [("1", "TITAN")], force=True)["facts_saved"] == 1


def test_a_dry_run_counts_and_writes_nothing():
    sink = sink_with({"Q2FY24": URL}, stored={URL: TITAN})
    before = dict(sink.objects)
    out = xbrl_facts.run(sink, [("1", "TITAN")], dry_run=True)
    assert out["facts_saved"] == 1 and sink.objects == before and "dry run" in xbrl_facts.render(out)


def test_download_is_a_separate_opt_in_through_the_seeds_fetch_and_keeps_the_file():
    sink = sink_with({"Q2FY24": URL, "Q1FY24": URL2}, stored={URL: TITAN})
    hits: list[str] = []
    out = xbrl_facts.run(sink, [("1", "TITAN")], download=True, client=CountingNse(hits=hits))
    assert hits == [URL2] and files.used == 1                         # only the file not stored, one file for the cap
    assert out["downloaded"] == 1 and out["facts_saved"] == 2 and out["stopped"] == ""
    assert xbrl_store.key(URL2) in sink.objects                       # the raw file is kept too (F191)
    assert xbrl_facts.key("1", "Q1FY24", "CONSOLIDATED") in sink.objects
    # run again: nothing is missing now, so nothing is fetched
    xbrl_facts.run(sink, [("1", "TITAN")], download=True, client=CountingNse(hits=hits))
    assert hits == [URL2]


def test_download_respects_the_file_cap_and_stops_as_a_planned_stop(monkeypatch):
    monkeypatch.setenv("FILE_CAP", "1")
    urls = [f"https://nsearchives.nseindia.com/corporate/xbrl/T_{i}.xml" for i in range(3)]
    sink = sink_with({f"Q{i + 1}FY24": u for i, u in enumerate(urls)})
    hits: list[str] = []
    out = xbrl_facts.run(sink, [("1", "TITAN")], download=True, client=CountingNse(hits=hits))
    assert len(hits) == 1 and out["downloaded"] == 1 and out["capped"] is True and "file cap reached" in out["stopped"]
    assert out["missing"] == 2          # the first was downloaded (listed missing before it), the second stopped the run
    assert "stopped: file cap reached" in xbrl_facts.render(out)


def test_a_sink_without_an_r2_store_reads_no_file():
    from bse_intel.sinks.local import LocalSink

    class Local(LocalSink):
        def __init__(self):
            self.objects = {}

        def list_objects(self, prefix):
            return []

        def get_dossier(self, scrip):
            return dossier({"Q2FY24": URL})

    out = xbrl_facts.run(Local(), [("1", "TITAN")])
    assert out["store_available"] is False and out["facts_saved"] == 0 and out["missing"] == 1
    assert "no R2 XBRL store" in xbrl_facts.render(out)


def test_the_summary_lists_what_the_files_carry_on_levies_leases_and_treasury_shares():
    extra = (b'<xbrli:context id="X1"><xbrli:entity><xbrli:identifier scheme="s">T</xbrli:identifier></xbrli:entity><xbrli:period>'
             b'<xbrli:startDate>2023-07-01</xbrli:startDate><xbrli:endDate>2023-09-30</xbrli:endDate></xbrli:period><xbrli:scenario>'
             b'<xbrldi:explicitMember dimension="in-bse-fin:DetailsOfOtherExpensesAxis">in-bse-fin:Row9Member</xbrldi:explicitMember>'
             b'</xbrli:scenario></xbrli:context>'
             b'<in-bse-fin:DescriptionOfOtherExpenses contextRef="X1">Excise duty</in-bse-fin:DescriptionOfOtherExpenses>'
             b'<in-bse-fin:OtherExpenses contextRef="X1" unitRef="INR" decimals="-7">150000000.00</in-bse-fin:OtherExpenses>'
             b'<in-bse-fin:LeaseLiabilitiesNoncurrent contextRef="OneI" unitRef="INR" decimals="-7">400000000.00</in-bse-fin:LeaseLiabilitiesNoncurrent>')
    data = TITAN.replace(b"</xbrli:xbrl>", extra + b"</xbrli:xbrl>")
    got = xbrl_facts.interesting(xbrl_facts.Facts(xbrl_facts.parse_facts(data, "1")))
    assert "DescriptionOfOtherExpenses: Excise duty" in got and "LeaseLiabilitiesNoncurrent" in got
    assert "DescriptionOfOtherExpenses: Advertising" not in got
    sink = sink_with({"Q2FY24": URL}, stored={URL: data})
    out = xbrl_facts.run(sink, [("1", "TITAN")])
    assert out["interesting"]["LeaseLiabilitiesNoncurrent"] == 1
    assert "elements and breakdown rows that bear on screener's treatment" in xbrl_facts.render(out)


def test_the_cli_command_is_wired_and_reads_only_without_download(monkeypatch, capsys, tmp_path):
    sink = sink_with({"Q2FY24": URL}, stored={URL: TITAN})
    monkeypatch.setattr(cli, "make_sink", lambda settings: sink, raising=False)
    monkeypatch.setattr(cli, "_universe_companies", lambda s, scrips: [("1", "TITAN")])
    hits: list[str] = []
    monkeypatch.setattr("bse_intel.nse.NseClient", lambda *a, **k: pytest.fail("no NSE client without --download"))
    assert cli.main(["xbrl-facts", "--scrips", "TITAN", "--json", str(tmp_path / "s.json"), "--csv", str(tmp_path / "m.csv")]) == 0
    summary = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert summary["facts_saved"] == 1 and "missing_rows" not in summary and summary["download"] is False and hits == []
    assert (tmp_path / "m.csv").read_text(encoding="utf-8").startswith("scrip,symbol,period,basis,url,reason")
    assert "facts written this run" in capsys.readouterr().out


# --- --dry-run with --download, and the workflow ----------------------------------------------------------------------------

def test_dry_run_with_download_lists_the_files_and_downloads_nothing():
    sink = sink_with({"Q2FY24": URL, "Q1FY24": URL2}, stored={URL: TITAN})
    before = dict(sink.objects)
    hits: list[str] = []
    out = xbrl_facts.run(sink, [("1", "TITAN")], download=True, client=CountingNse(hits=hits), dry_run=True)
    assert hits == [] and files.used == 0 and out["downloaded"] == 0 and out["would_download"] == 1
    assert sink.objects == before                                     # no raw file, no facts written
    assert out["missing_rows"][0]["url"] == URL2 and "dry run" in out["missing_rows"][0]["reason"]
    assert "1 files would be downloaded, none was" in xbrl_facts.render(out)
    # even with no client at all the count is there
    again = xbrl_facts.run(sink, [("1", "TITAN")], download=True, dry_run=True)
    assert again["would_download"] == 1


def test_the_cli_dry_run_with_download_makes_no_nse_client(monkeypatch, tmp_path):
    sink = sink_with({"Q2FY24": URL, "Q1FY24": URL2}, stored={URL: TITAN})
    monkeypatch.setattr(cli, "make_sink", lambda settings: sink, raising=False)
    monkeypatch.setattr(cli, "_universe_companies", lambda s, scrips: [("1", "TITAN")])
    monkeypatch.setattr("bse_intel.nse.NseClient", lambda *a, **k: pytest.fail("a dry run must not build an NSE client"))
    assert cli.main(["xbrl-facts", "--download", "--dry-run", "--json", str(tmp_path / "s.json")]) == 0
    summary = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert summary["would_download"] == 1 and summary["downloaded"] == 0 and xbrl_store.key(URL2) not in sink.objects


def workflow():
    import yaml

    text = (Path(__file__).parents[2] / ".github" / "workflows" / "maintenance.yml").read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def test_workflow_limit_means_the_n_largest_for_both_commands():
    text, doc = workflow()
    assert 'xbrl-facts ${IDS:+--scrips "$IDS"} ${LIMIT:+--top-mcap "$LIMIT"}' in text
    assert 'screener-crosscheck ${IDS:+--scrips "$IDS"} ${LIMIT:+--top-mcap "$LIMIT"}' in text
    assert 'xbrl-facts ${IDS:+--scrips "$IDS"} ${LIMIT:+--limit' not in text
    inputs = (doc.get("on") or doc.get(True))["workflow_dispatch"]["inputs"]
    assert "screener-crosscheck and xbrl-facts - only the N largest companies by market cap" in inputs["limit"]["description"]
    assert len(inputs) <= 25


def test_workflow_refuses_an_xbrl_facts_download_without_a_file_cap_before_installing():
    text, doc = workflow()
    steps = doc["jobs"]["xbrl-facts"]["steps"]
    refuse = next(i for i, st in enumerate(steps) if "Refuse an xbrl-facts download" in st.get("name", ""))
    install = next(i for i, st in enumerate(steps) if st.get("name") == "Install")
    assert refuse < install
    cond = steps[refuse]["if"]
    assert "inputs.apply" in cond and "inputs.file_cap == ''" in cond and "'0'" in cond
    assert "exit 1" in steps[refuse]["run"]
    assert "FILE_CAP: ${{ inputs.file_cap || '0' }}" in text            # the cap the run then holds


def test_workflow_a_downloading_xbrl_facts_run_shares_the_nse_memory_group_and_a_read_only_run_does_not():
    text, doc = workflow()
    group = doc["concurrency"]["group"]
    nse_memory, rest = group.split("|| (inputs.command == 'xbrl-facts' && (inputs.apply || inputs.annual)) && 'maint-nse-memory'")
    assert "seed-memory" in nse_memory and "maint-nse-memory" in nse_memory and "xbrl-facts" not in nse_memory   # the list itself is unchanged
    assert "maint-cards" in rest and "maint-ro-" in rest
    assert '"xbrl-facts"' in rest.split("maint-ro-")[0]              # a read-only run keeps its own group
