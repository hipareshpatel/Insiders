"""refresh-summaries: a company's stored summary rebuilt from memory, so a new rule reaches unprocessed companies."""

import json
from types import SimpleNamespace

from bse_intel.cli import cmd_refresh_summaries


def test_refresh_rebuilds_the_overdue_list_without_an_agency_view(capsys):
    dossier = {"scrip_code": "500940", "company_name": "Prism Johnson Ltd", "guidance": [
        {"id": "g1", "statement": "Ind-Ra expects EBITDA margins to improve", "status": "OPEN", "due": "FY26-FY27",
         "due_date": "2026-03-31", "given_on": "2025-06-01T10:00:00+05:30", "status_history": []},
        {"id": "g2", "statement": "Commission the new kiln", "target": "1 MTPA", "status": "OPEN", "due": "FY26",
         "due_date": "2026-03-31", "given_on": "2025-06-01T10:00:00+05:30", "status_history": []}]}

    class Sink:
        rows: list = []

        def list_dossiers(self):
            return ["500940"]

        def get_dossier(self, scrip):
            return dossier

        def execute(self, statement, rows):
            assert statement == "companies_upsert"
            self.rows += rows
            return len(rows)

    sink = Sink()
    assert cmd_refresh_summaries(SimpleNamespace(scrips=None), None, sink) == 0
    assert json.loads(capsys.readouterr().out) == {"companies": 1, "missing": 0, "rows_written": 1}
    (row,) = sink.rows
    summary = row["memory_summary_json"]
    promises = (json.loads(summary) if isinstance(summary, str) else summary)["open_promises"]
    assert [p["statement"] for p in promises] == ["Commission the new kiln"]
