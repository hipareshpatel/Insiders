"""F200: a unit-slip correction needs the filing's own PDF text layer to print the corrected figure (owner, 27 Oct 2026)."""
from datetime import date
from types import SimpleNamespace

from bse_intel import pdf_referee, seed as seed_mod
from bse_intel.bse import XbrlLink
from bse_intel.pdf_referee import Row
from bse_intel.seed import SeedStats, seed_results

from test_seed import Bse, Sink
from test_xbrl import _quarter

Q4 = date(2024, 3, 31)


class Nse:
    """NSE as the check sees it: an announcement list and a PDF download, counted."""

    def __init__(self):
        self.lists = self.pdfs = 0

    def announcements(self, day_from, day_to=None, symbol=None, scrip_for=None):
        self.lists += 1
        return [SimpleNamespace(pdf_url="https://nsearchives.nseindia.com/a.pdf", subject="Financial Results",
                                headline="Outcome of Board Meeting", filed_at="2024-05-10")]

    def fetch(self, url, max_bytes=0):
        self.pdfs += 1
        return b"%PDF fake"

    def financial_results(self, symbol, quarterly=True):
        return []


def _setup(monkeypatch, revenue_in_pdf, ocr_seen):
    files = {"q1": _quarter("Q1FY24", 1586.9, 60.0, 3.77), "q2": _quarter("Q2FY24", 1680.3, 62.1, 3.90),
             "q3": _quarter("Q3FY24", 1677.1, 66.4, 4.17), "q4": _quarter("Q4FY24", 1758.6, -61.8, -3.69, scale=0.1)}
    links = [XbrlLink(period=f.period, basis="CONSOLIDATED", url=url, filed_at="2024-06-01T18:00:00")
             for url, f in files.items()]

    class Served(Bse):
        def download(self, url, max_bytes=0):
            return url.encode()

    monkeypatch.setattr(seed_mod.xbrl_fast_path, "parse", lambda data: files[data.decode()])

    def read(payload, ocr=True, max_ocr_pages=6):
        ocr_seen.append(ocr)
        if revenue_in_pdf is None:
            return None, "no pages"
        return [Row("revenue", "Revenue from operations", "CONSOLIDATED", 10.0, [revenue_in_pdf * 10], [("quarter", Q4)],
                    [Q4], set(), 3)], ""
    monkeypatch.setattr(pdf_referee, "read_document", read)
    return Served(links)


def _seed(bse, nse):
    sink, stats = Sink(), SeedStats()
    seed_results(sink, bse, "530019", "Jubilant Pharmova", "2024-01-01", None, stats, company={}, nse=nse, symbol="JUBLPHARMA")
    return sink, stats


def _memory(sink):
    return {(m["metric"], m["period"]): m["value"] for m in sink.dossiers["530019"]["financial_metrics"]}


def test_pdf_agrees_the_slip_is_corrected(monkeypatch):
    ocr = []
    nse = Nse()
    sink, stats = _seed(_setup(monkeypatch, 1758.6, ocr), nse)   # millions in the PDF: 17,586
    assert _memory(sink)[("revenue", "Q4FY24")] == 1758.6 and stats.rescaled == 1 and not stats.slip_held
    assert ocr == [False], "the text layer only, never OCR"
    assert (nse.lists, nse.pdfs) == (1, 1)


def test_pdf_shows_the_uncorrected_figure_so_the_quarter_is_held_and_flagged(monkeypatch):
    nse = Nse()
    sink, stats = _seed(_setup(monkeypatch, 175.86, []), nse)
    assert ("revenue", "Q4FY24") not in _memory(sink) and ("revenue", "Q3FY24") in _memory(sink)
    assert stats.rescaled == 0 and len(stats.slip_held) == 1 and "Q4FY24" in stats.slip_held[0]
    assert sink.dossiers["530019"]["scale_held"] == ["Q4FY24"]
    assert "1 quarters held for an unconfirmed unit slip" in stats.line()


def test_pdf_unreadable_or_missing_holds_and_flags(monkeypatch):
    sink, stats = _seed(_setup(monkeypatch, None, []), Nse())
    assert ("revenue", "Q4FY24") not in _memory(sink) and len(stats.slip_held) == 1
    # no NSE client at all (a BSE-only seed): nothing to read the PDF with, so nothing is corrected
    sink, stats = _seed(_setup(monkeypatch, 1758.6, []), None)
    assert ("revenue", "Q4FY24") not in _memory(sink) and "no NSE client" in stats.slip_held[0]


def test_a_later_clean_seed_clears_the_flag(monkeypatch):
    sink, stats = _seed(_setup(monkeypatch, 175.86, []), Nse())
    assert sink.dossiers["530019"]["scale_held"] == ["Q4FY24"]
    _seed_again = _setup(monkeypatch, 1758.6, [])
    stats = SeedStats()
    seed_results(sink, _seed_again, "530019", "Jubilant Pharmova", "2024-01-01", None, stats, company={}, nse=Nse(),
                 symbol="JUBLPHARMA")
    assert "scale_held" not in sink.dossiers["530019"] and _memory(sink)[("revenue", "Q4FY24")] == 1758.6


def test_no_slip_no_pdf_fetched(monkeypatch):
    ocr = []
    bse = _setup(monkeypatch, 1758.6, ocr)
    seed_mod.xbrl_fast_path.parse = lambda data: {  # the same quarters, all in the right unit
        "q1": _quarter("Q1FY24", 1586.9, 60.0, 3.77), "q2": _quarter("Q2FY24", 1680.3, 62.1, 3.90),
        "q3": _quarter("Q3FY24", 1677.1, 66.4, 4.17), "q4": _quarter("Q4FY24", 1758.6, -61.8, -3.69)}[data.decode()]
    nse = Nse()
    sink, stats = _seed(bse, nse)
    assert (nse.lists, nse.pdfs, ocr) == (0, 0, []) and stats.results_periods == 4 and not stats.slip_held


def _reseed(sink, bse):
    stats = SeedStats()
    seed_results(sink, bse, "530019", "Jubilant Pharmova", "2024-01-01", None, stats, company={}, nse=Nse(),
                 symbol="JUBLPHARMA")
    return stats


def test_a_pdf_that_cannot_be_read_never_deletes_what_memory_holds(monkeypatch):
    """Review of #168: an NSE hiccup (no PDF read) holds the quarter but leaves the earlier seed's figures; only a PDF
    that prints another figure removes them."""
    sink, _ = _seed(_setup(monkeypatch, 1758.6, []), Nse())
    assert _memory(sink)[("revenue", "Q4FY24")] == 1758.6
    stats = _reseed(sink, _setup(monkeypatch, None, []))
    assert len(stats.slip_held) == 1 and _memory(sink)[("revenue", "Q4FY24")] == 1758.6
    assert sink.dossiers["530019"]["scale_held"] == ["Q4FY24"]
    _reseed(sink, _setup(monkeypatch, 175.86, []))
    assert ("revenue", "Q4FY24") not in _memory(sink)
