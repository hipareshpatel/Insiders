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
