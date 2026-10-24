"""The deterministic memory seed, and the NSE sources that fill what BSE's archive will not serve."""
from bse_intel import seed as seed_mod
from bse_intel.bse import XbrlLink
from bse_intel.nse import ResultsFiling
from bse_intel.seed import SeedStats, seed_results

from test_xbrl import _cap, _insurance_xml


class Sink:
    def __init__(self):
        self.dossiers = {}

    def get_dossier(self, scrip):
        return self.dossiers.get(scrip)

    def put_dossier(self, scrip, dossier):
        self.dossiers[scrip] = dossier


class Bse:
    """BSE's archive: it lists a quarter but serves nothing for it, and knows nothing of the newer one."""

    def __init__(self, links):
        self.links = links

    def results_xbrl(self, scrip):
        return self.links

    def download(self, url, max_bytes=0):
        return None


class Nse:
    def __init__(self, rows, files):
        self.rows, self.files, self.listed = rows, files, 0

    def financial_results(self, symbol, quarterly=True):
        self.listed += 1
        return self.rows

    def download(self, url, max_bytes=0):
        return self.files.get(url)


GI_XML = _insurance_xml("GI", _cap("PremiumEarned", 66_518_700_000) + _cap("ProfitOrLossBeforeTax", 12_474_100_000)
                        + _cap("ProvisionForTax", 3_010_100_000) + _cap("ProfitLossAfterTax", 9_464_000_000))


def _row(url, period_end, filed_at, taxonomy="GI"):
    return ResultsFiling(period="Quarterly", consolidated=False, audited="Audited", filed_at=filed_at,
                         xbrl_url=url, is_bank=False, period_end=period_end, taxonomy=taxonomy)


def test_a_quarter_bse_never_listed_is_seeded_from_nse():
    """The older fallback only fired for a file BSE named. Since the integrated format arrived BSE often
    names none, so the quarter was simply absent from memory and no counter moved."""
    seed_mod._nse_rows.cache_clear()
    sink, stats = Sink(), SeedStats()
    url = "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_GI_1_14102026103636_WEB.xml"
    nse = Nse([_row(url, "2026-09-30", "2026-10-14")], {url: GI_XML})
    seed_results(sink, Bse([]), "540716", "ICICI Lombard", "2025-01-01", None, stats,
                 company={}, nse=nse, symbol="ICICIGI")

    assert stats.results_periods == 1 and stats.results_from_nse == 1
    metrics = {m["metric"]: m for m in sink.dossiers["540716"]["financial_metrics"]}
    assert metrics["revenue"]["period"] == "Q2FY27" and metrics["revenue"]["value"] == 6651.87
    assert metrics["pat"]["value"] == 946.4


def test_without_a_bse_client_the_seed_reads_nse_alone():
    """Owner, 2026-10-19: everything on NSE. The seed runs online with no BSE client at all."""
    seed_mod._nse_rows.cache_clear()
    sink, stats = Sink(), SeedStats()
    url = "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_GI_1_14102026103636_WEB.xml"
    nse = Nse([_row(url, "2026-09-30", "2026-10-14")], {url: GI_XML})
    seed_results(sink, None, "NEWCO", "New Co", "2025-01-01", None, stats, company={}, nse=nse, symbol="NEWCO")
    assert stats.results_periods == 1 and stats.skipped == 0
    assert sink.dossiers["NEWCO"]["financial_metrics"]


def test_the_nse_list_is_fetched_once_for_a_company_not_once_a_quarter():
    """NSE paces itself by several seconds a call and the list is read for every quarter BSE fails on."""
    seed_mod._nse_rows.cache_clear()
    sink, stats = Sink(), SeedStats()
    url = "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_GI_1_14102026103636_WEB.xml"
    nse = Nse([_row(url, "2026-09-30", "2026-10-14")], {url: GI_XML})
    links = [XbrlLink(url=f"https://bse/dead-{n}.xml", period=p, basis="STANDALONE", filed_at=f"{d}T18:00:00+05:30")
             for n, (p, d) in enumerate((("Q1FY27", "2026-07-20"), ("Q4FY26", "2026-04-20")))]
    seed_results(sink, Bse(links), "540716", "ICICI Lombard", "2025-01-01", None, stats,
                 company={}, nse=nse, symbol="ICICIGI")

    assert nse.listed == 1, "one list for the company, however many quarters ask for it"
    assert stats.skipped == 2, "the two quarters BSE listed and served nothing for are still reported"
    assert stats.results_periods == 1


def test_a_quarter_tagged_in_the_wrong_unit_reaches_memory_put_right(monkeypatch):
    """Every quarter is read before any is written, so the company's other quarters can show that one file
    is tagged at a tenth of its value (Jubilant Pharmova Q4FY24) before it reaches memory."""
    from test_xbrl import _quarter

    files = {"q1": _quarter("Q1FY24", 1586.9, 60.0, 3.77), "q2": _quarter("Q2FY24", 1680.3, 62.1, 3.90),
             "q3": _quarter("Q3FY24", 1677.1, 66.4, 4.17), "q4": _quarter("Q4FY24", 1758.6, -61.8, -3.69, scale=0.1)}
    links = [XbrlLink(period=f.period, basis="CONSOLIDATED", url=url, filed_at="2024-06-01T18:00:00")
             for url, f in files.items()]

    class Served(Bse):
        def download(self, url, max_bytes=0):
            return url.encode()

    monkeypatch.setattr(seed_mod.xbrl_fast_path, "parse", lambda data: files[data.decode()])
    sink, stats = Sink(), SeedStats()
    seed_results(sink, Served(links), "530019", "Jubilant Pharmova", "2024-01-01", None, stats, company={})

    memory = {(m["metric"], m["period"]): m["value"] for m in sink.dossiers["530019"]["financial_metrics"]}
    assert memory[("revenue", "Q4FY24")] == 1758.6 and memory[("pat", "Q4FY24")] == -61.8
    assert memory[("revenue", "Q3FY24")] == 1677.1 and stats.rescaled == 1 and stats.results_periods == 4
    assert "1 files in the wrong unit put right" in stats.line()


def test_a_later_standalone_file_does_not_replace_the_consolidated_quarter():
    """Max Financial (round 5): standalone files filed in July replaced the consolidated quarter of May, so memory held
    the holding company's ₹17 Cr quarter beside a ₹39,473 Cr twelve-month revenue."""
    from dataclasses import replace

    seed_mod._nse_rows.cache_clear()
    cons = replace(_row("https://x/cons.xml", "2026-03-31", "2026-05-13 18:00"), consolidated=True)
    later_standalone = _row("https://x/std.xml", "2026-03-31", "2026-07-13 18:00")

    class Nse:
        def financial_results(self, symbol):
            return [later_standalone, cons]

    best = seed_mod._nse_quarters(Nse(), "MFSL", "2025-01-01", "500271")
    assert [r.xbrl_url for r in best.values()] == ["https://x/cons.xml"]


def test_the_universe_seed_resumes_after_the_last_company_and_stops_on_a_refusal(settings, monkeypatch):
    """Go-live history (PLAN G6): `seed-memory --universe` walks every universe company in key order, records each one
    finished, and a second run continues after it. An NSE refusal stops the run before that company is recorded."""
    import argparse
    import json

    from bse_intel import nse as nse_mod
    from bse_intel import universe
    from bse_intel.cli import cmd_seed_memory
    from bse_intel.sinks.local import LocalSink

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    seen: list[str] = []
    refuse = {"500003"}

    def results(sink, bse, scrip, *a, **k):
        if scrip in refuse:
            raise nse_mod.SourceBlockedError("HTTP 403")
        seen.append(scrip)

    monkeypatch.setattr(nse_mod, "NseClient", Client)
    monkeypatch.setattr(seed_mod, "seed_results", results)
    monkeypatch.setattr(seed_mod, "seed_shareholding", lambda *a, **k: None)
    sink = LocalSink(settings)
    args = argparse.Namespace(scrips=None, universe=True, restart=False, source="nse", since="2024-01-01",
                              results_only=False, shareholding_only=False)
    assert cmd_seed_memory(args, settings, sink) == 2          # no NSE universe file yet: nothing to walk
    sink.put_object(universe.UNIVERSE_KEY, json.dumps(
        {"source": "nse", "included": ["500004", "500001", "500003", "500002"]}).encode())

    assert cmd_seed_memory(args, settings, sink) == 75         # refused (cli.REFUSED), as the other NSE syncs
    assert seen == ["500001", "500002"]                         # key order; stopped at the refusal
    refuse.clear()
    assert cmd_seed_memory(args, settings, sink) == 0
    assert seen == ["500001", "500002", "500003", "500004"]     # resumed at the refused company
    assert cmd_seed_memory(args, settings, sink) == 0 and len(seen) == 4
    args.restart = True
    assert cmd_seed_memory(args, settings, sink) == 0 and len(seen) == 8


def test_the_universe_seed_takes_companies_reporting_now_first(settings, monkeypatch):
    """E2E (owner, 2026-10-21): its results card had no earlier quarter, as the seed walks scrip codes in order and had
    not reached 544783. A company with results due (a board meeting soon) is seeded first, once, and the resume point
    keeps following the scrip order."""
    import argparse
    import json
    from datetime import date, timedelta

    from bse_intel import nse as nse_mod
    from bse_intel import universe
    from bse_intel.cli import cmd_seed_memory
    from bse_intel.sinks.local import LocalSink

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    seen: list[str] = []
    monkeypatch.setattr(nse_mod, "NseClient", Client)
    monkeypatch.setattr(seed_mod, "seed_results", lambda sink, bse, scrip, *a, **k: seen.append(scrip))
    monkeypatch.setattr(seed_mod, "seed_shareholding", lambda *a, **k: None)
    sink = LocalSink(settings)
    sink.put_object(universe.UNIVERSE_KEY, json.dumps(
        {"source": "nse", "included": ["500001", "500002", "544783"]}).encode())
    soon = (date.today() + timedelta(days=3)).isoformat()
    sink._db.execute("INSERT INTO catalysts (id, scrip_code, company_name, event_type, event_date, description, created_at) "
                     "VALUES ('c1', '544783', 'E2E', 'BOARD_MEETING', ?, 'results', ?)", (soon, soon))
    args = argparse.Namespace(scrips=None, universe=True, restart=False, source="nse", since="2024-01-01",
                              results_only=False, shareholding_only=False)
    assert cmd_seed_memory(args, settings, sink) == 0
    assert seen == ["544783", "500001", "500002"]
    assert sink.kv_get("seed:universe_last") == "500002"
    assert cmd_seed_memory(args, settings, sink) == 0 and len(seen) == 3   # nothing seeded twice


def test_nse_pacing_is_three_to_five_seconds_unless_a_bulk_load_sets_a_range(monkeypatch):
    from bse_intel.nse import pause_from_env

    monkeypatch.delenv("NSE_PAUSE_SECONDS", raising=False)
    assert pause_from_env() == (3.0, 5.0)
    monkeypatch.setenv("NSE_PAUSE_SECONDS", "1.5,2.5")
    assert pause_from_env() == (1.5, 2.5)
    for bad in ("0.1,0.2", "2", "fast", "3,1"):       # never faster than a second, never malformed
        monkeypatch.setenv("NSE_PAUSE_SECONDS", bad)
        assert pause_from_env() == (3.0, 5.0)


def test_a_standalone_only_quarter_is_not_seeded_beside_consolidated_ones_and_leaves_memory():
    """Heritage (T5, 2026-10-20): NSE listed only a standalone re-filing for Q4FY25 and Q2FY26; the seed put its PAT
    (20.51) beside five consolidated sources (38.17), and a card said PAT +16.7% YoY where it fell 37%."""
    seed_mod._nse_rows.cache_clear()

    def xml(basis, start, end, pat):
        return (GI_XML.decode().replace(">Standalone<", f">{basis}<").replace("2026-07-01", start).replace("2026-09-30", end)
                .replace("9464000000", str(pat))).encode()

    cons, alone = "https://nse/cons.xml", "https://nse/alone.xml"
    rows = [ResultsFiling(period="Quarterly", consolidated=True, audited="Audited", filed_at="2026-10-14", xbrl_url=cons,
                          is_bank=False, period_end="2026-09-30", taxonomy="GI"),
            ResultsFiling(period="Quarterly", consolidated=False, audited="Audited", filed_at="2026-07-14", xbrl_url=alone,
                          is_bank=False, period_end="2026-06-30", taxonomy="GI")]
    nse = Nse(rows, {cons: xml("Consolidated", "2026-07-01", "2026-09-30", 9_464_000_000),
                     alone: xml("Standalone", "2026-04-01", "2026-06-30", 2_051_000_000)})
    sink, stats = Sink(), SeedStats()
    # an earlier seed had put the standalone quarter in
    sink.dossiers["519552"] = {"financial_metrics": [{"metric": "pat", "period": "Q1FY27", "value": 205.1, "unit": "INR_CR",
                                                      "as_of": "2026-07-14T18:00:00+05:30",
                                                      "source_news_id": "xbrl:res:519552:Q1FY27"}]}
    seed_results(sink, None, "519552", "Heritage Foods", "2025-01-01", None, stats, company={}, nse=nse, symbol="HERITGFOOD")
    periods = {m["period"] for m in sink.dossiers["519552"]["financial_metrics"]}
    assert "Q2FY27" in periods and "Q1FY27" not in periods
    pat = next(m for m in sink.dossiers["519552"]["financial_metrics"] if m["metric"] == "pat")
    assert pat.get("basis") == "CONSOLIDATED"


def test_shards_split_the_universe_and_keep_their_own_resume_points(settings, monkeypatch):
    """Owner (2026-10-21): fill the history today; eight runners each take every eighth company."""
    import argparse
    import json

    from bse_intel import nse as nse_mod
    from bse_intel import universe
    from bse_intel.cli import cmd_seed_memory
    from bse_intel.sinks.local import LocalSink

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    seen: list[str] = []
    monkeypatch.setattr(nse_mod, "NseClient", Client)
    monkeypatch.setattr(seed_mod, "seed_results", lambda sink, bse, scrip, *a, **k: seen.append(scrip))
    monkeypatch.setattr(seed_mod, "seed_shareholding", lambda *a, **k: None)
    sink = LocalSink(settings)
    sink.put_object(universe.UNIVERSE_KEY, json.dumps(
        {"source": "nse", "included": ["500001", "500002", "500003", "500004", "500005"]}).encode())
    args = argparse.Namespace(scrips=None, universe=True, restart=False, source="nse", since="2020-04-01",
                              results_only=True, shareholding_only=False, shard="1/2")
    assert cmd_seed_memory(args, settings, sink) == 0
    assert seen == ["500002", "500004"]
    assert sink.kv_get("seed:universe_last:1of2") == "500004" and sink.kv_get("seed:universe_last") is None
    args.shard = "0/2"
    assert cmd_seed_memory(args, settings, sink) == 0
    assert seen[2:] == ["500001", "500003", "500005"]
    args.shard = "2/2"
    assert cmd_seed_memory(args, settings, sink) == 2          # malformed: nothing walked


def test_old_years_are_read_from_their_march_files_only():
    """Twelve quarters as memory keeps them; before them only the March quarter, whose file carries the year."""
    seed_mod._nse_rows.cache_clear()
    ends = [f"{y}-{m}" for y in range(2021, 2027) for m in ("03-31", "06-30", "09-30", "12-31")][:-1]

    class Nse:
        def financial_results(self, symbol):
            return [_row(f"https://x/{e}.xml", e, f"{e} 18:00") for e in ends]

    best = seed_mod._nse_quarters(Nse(), "X", "2020-04-01", "500001")
    kept = sorted(r.period_end for r in best.values())
    assert kept[-12:] == ends[-12:]
    assert kept[:-12] == [e for e in ends[:-12] if e.endswith("03-31")]


def test_a_consolidated_filers_standalone_quarter_is_kept_apart():
    """Owner (2026-10-21): "we have standalone vs consolidated numbers in financials". Both files of a quarter: the
    consolidated one is memory's, the standalone one goes to dossier["standalone"] for the company page alone."""
    seed_mod._nse_rows.cache_clear()

    def xml(basis, pat):
        return GI_XML.decode().replace(">Standalone<", f">{basis}<").replace("9464000000", str(pat)).encode()

    cons, alone = "https://nse/q2-cons.xml", "https://nse/q2-alone.xml"
    rows = [ResultsFiling(period="Quarterly", consolidated=True, audited="Audited", filed_at="2026-10-14", xbrl_url=cons,
                          is_bank=False, period_end="2026-09-30", taxonomy="GI"),
            ResultsFiling(period="Quarterly", consolidated=False, audited="Audited", filed_at="2026-10-14", xbrl_url=alone,
                          is_bank=False, period_end="2026-09-30", taxonomy="GI")]
    nse = Nse(rows, {cons: xml("Consolidated", 9_464_000_000), alone: xml("Standalone", 2_051_000_000)})
    sink, stats = Sink(), SeedStats()
    seed_results(sink, None, "519552", "Heritage Foods", "2025-01-01", None, stats, company={}, nse=nse, symbol="HERITGFOOD")
    d = sink.dossiers["519552"]
    main = next(m for m in d["financial_metrics"] if m["metric"] == "pat" and m["period"] == "Q2FY27")
    alone_pat = next(m for m in d["standalone"]["metrics"] if m["metric"] == "pat" and m["period"] == "Q2FY27")
    assert main["value"] == 946.4 and alone_pat["value"] == 205.1
    assert stats.standalone_periods == 1


def test_named_companies_may_be_nse_symbols_and_an_unknown_name_fails(settings, monkeypatch):
    """reseed.yml run with SIEMENS, ABB, ... on 22 Oct 2026: none was a company key, and all 14 seeded nothing while
    the job passed. A symbol now resolves through the universe file; a name that is neither fails the command."""
    import argparse
    import json

    from bse_intel import nse as nse_mod
    from bse_intel import universe
    from bse_intel.cli import cmd_seed_memory
    from bse_intel.sinks.local import LocalSink

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(nse_mod, "NseClient", Client)
    monkeypatch.setattr(seed_mod, "seed_results", lambda sink, bse, scrip, *a, **k: seen.append((scrip, k.get("symbol"))))
    monkeypatch.setattr(seed_mod, "seed_shareholding", lambda *a, **k: None)
    sink = LocalSink(settings)
    sink.put_object(universe.UNIVERSE_KEY, json.dumps(
        {"source": "nse", "included": ["500550"], "symbols": {"SIEMENS": "500550"}}).encode())
    args = argparse.Namespace(scrips="siemens", universe=False, restart=False, source="nse", since="2024-01-01",
                              results_only=True, shareholding_only=False)
    assert cmd_seed_memory(args, settings, sink) == 0
    assert seen == [("500550", "SIEMENS")]
    args.scrips = "SIEMENS,NOSUCH"
    assert cmd_seed_memory(args, settings, sink) == 2 and len(seen) == 1
