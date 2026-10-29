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
