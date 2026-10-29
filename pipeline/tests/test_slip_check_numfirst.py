"""Step 1 (owner, 29 Oct 2026): the unit-slip check asks the numbers-first reader first (SLIP_CHECK_NUMFIRST=1); where it has no
answer the text-layer reader decides as before, from the same download."""
from types import SimpleNamespace

import pytest

from bse_intel import pdf_numbers_first as nf
from bse_intel.slip_check import PdfCheck

from test_pdf_numbers_first import crore, pl, statement

URL = "https://nsearchives.nseindia.com/q2.pdf"


class Nse:
    def __init__(self, data: bytes):
        self.data, self.fetches = data, 0

    def fetch(self, url, max_bytes=0):
        self.fetches += 1
        return self.data


def check(data: bytes, metric: str, corrected: float):
    nse = Nse(data)
    got = PdfCheck(nse, "ABC", pdf_url=URL, pdf_period="Q2FY27")(SimpleNamespace(period="Q2FY27", basis="STANDALONE"),
                                                                metric, corrected)
    return got, nse.fetches


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("SLIP_CHECK_NUMFIRST", "1")


def test_the_new_reader_confirms_the_corrected_figure_from_one_download(on):
    rows, want = pl()
    (agrees, why), fetches = check(statement(rows), "pat", crore(want["pat"][0]))
    assert agrees is True and "numbers-first" in why and fetches == 1


def test_the_new_reader_refuses_a_corrected_figure_the_pdf_does_not_print(on):
    rows, want = pl()
    (agrees, why), _ = check(statement(rows), "pat", crore(want["pat"][0]) * 10)
    assert agrees is False and "numbers-first" in why


def test_where_the_new_reader_has_no_answer_the_text_layer_reader_decides_without_a_second_download(on, monkeypatch):
    monkeypatch.setattr(nf, "reading_from_tables", lambda *a, **k: SimpleNamespace(status="none"))
    rows, want = pl()
    (agrees, why), fetches = check(statement(rows), "pat", crore(want["pat"][0]))
    assert "numbers-first" not in why and fetches == 1


def test_switched_off_the_new_reader_is_never_asked(monkeypatch):
    monkeypatch.delenv("SLIP_CHECK_NUMFIRST", raising=False)
    monkeypatch.setattr(nf, "analyse", lambda *a, **k: pytest.fail("numbers-first asked with the switch off"))
    rows, want = pl()
    (agrees, why), fetches = check(statement(rows), "pat", crore(want["pat"][0]))
    assert "numbers-first" not in why and fetches == 1


def test_a_metric_the_new_reader_does_not_read_goes_to_the_text_layer_reader(on, monkeypatch):
    monkeypatch.setattr(nf, "analyse", lambda *a, **k: pytest.fail("numbers-first asked for EPS"))
    rows, _ = pl()
    check(statement(rows), "eps", 1.0)


def test_a_later_candidate_filing_that_proves_the_figure_wins_over_an_earlier_one_that_does_not(on, monkeypatch):
    # review of eb2474a: the first filing with a reading decided, and a False removes stored figures
    rows, want = pl()
    right = crore(want["pat"][0])
    wrong_pdf, good_pdf = b"%PDF first", b"%PDF second"
    monkeypatch.setattr(nf, "analyse", lambda data, **k: data)
    monkeypatch.setattr(nf, "reading_from_tables", lambda data, *a, **k: SimpleNamespace(
        status="ok", value=right * 10 if data == wrong_pdf else right, tol=0.005, page=1, label="Profit"))

    class Two:
        fetches = 0

        def fetch(self, url, max_bytes=0):
            Two.fetches += 1
            return wrong_pdf if url.endswith("1.pdf") else good_pdf
    chk = PdfCheck(Two(), "ABC")
    monkeypatch.setattr(chk, "_urls", lambda period: ["https://x/1.pdf", "https://x/2.pdf"])
    agrees, why = chk(SimpleNamespace(period="Q2FY27", basis="STANDALONE"), "pat", right)
    assert agrees is True


def test_a_failed_download_is_not_asked_again_by_the_text_layer_reader(on):
    class Gone:
        fetches = 0

        def fetch(self, url, max_bytes=0):
            Gone.fetches += 1
            return b""
    got = PdfCheck(Gone(), "ABC", pdf_url=URL, pdf_period="Q2FY27")(SimpleNamespace(period="Q2FY27", basis="STANDALONE"),
                                                                    "pat", 1.0)
    assert got[0] is None and Gone.fetches == 1
