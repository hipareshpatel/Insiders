"""Annual-report PDFs kept in R2 once (owner, 29 Oct 2026: "Save those 10 PDFs to R2 now")."""

import gzip

from bse_intel import annual_pdfs as ap
from test_screener_download import Sink

URL = "https://nsearchives.nseindia.com/annual_reports/AR_29312_AMBUJACEM_2025_2026_A_14411072_30052026181544.pdf"
OLD = "https://nsearchives.nseindia.com/annual_reports/AR_26477_AMBUJACEM_2024_2025_A_31052025201542.pdf"


class Answer:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class Client:
    def __init__(self):
        self.fetched = []

    def _get(self, url, params):
        assert url == ap.LIST and params == {"index": "equities", "symbol": "AMBUJACEM"}
        return Answer({"data": [{"toYr": "2026", "fileName": URL}, {"toYr": "2026", "fileName": URL}, {"toYr": "2025", "fileName": OLD}]})

    def fetch(self, url, max_bytes=0):
        assert max_bytes == ap.MAX_BYTES
        self.fetched.append(url)
        return b"%PDF-1.7 report"


def test_the_years_pdf_is_kept_once_and_never_fetched_again():
    sink, client = Sink(), Client()
    out = ap.run(sink, client, ["ambujacem"], "2026")
    assert client.fetched == [URL] and out["downloaded"] == 1
    assert gzip.decompress(sink.get_object(ap.key("AMBUJACEM", URL))) == b"%PDF-1.7 report"
    again = Client()
    second = ap.run(sink, again, ["AMBUJACEM"], "2026")
    assert again.fetched == [] and second["stored_before"] == 1


def test_the_newest_n_years_are_the_distinct_report_years_newest_first():
    rows = [{"toYr": "2026", "fileName": "a.pdf"}, {"toYr": "2024", "fileName": "c.pdf"}, {"toYr": "2025", "fileName": "b.pdf"},
            {"toYr": "2026", "fileName": "a2.pdf"}, {"toYr": ""}]
    assert ap.newest_years(rows, 3) == ["2026", "2025", "2024"] and ap.newest_years(rows, 1) == ["2026"]


def test_the_file_cap_is_a_planned_stop_that_keeps_what_came():
    from bse_intel.nse import FileCapReached
    from backup_objects import BackupObjects

    class Reply:
        def json(self):
            return {"data": [{"toYr": "2026", "fileName": "https://x/a.pdf"}, {"toYr": "2025", "fileName": "https://x/b.pdf"}]}

    class Client:
        calls = 0

        def _get(self, url, params):
            return Reply()

        def fetch(self, url, max_bytes=None):
            Client.calls += 1
            if Client.calls > 1:
                raise FileCapReached("file cap reached (1 of 1 files)")
            return b"%PDF-1"

    sink = BackupObjects()
    out = ap.run(sink, Client(), ["ABC"], years=2)
    assert out["capped"] is True and out["downloaded"] == 1 and ap.key("ABC", "https://x/a.pdf") in sink.objects
