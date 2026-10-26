"""F162 (TODO 49): a quarter NSE lists no consolidated file for stays on the standalone basis, behind MEMORY_STANDALONE_ONLY."""

from types import SimpleNamespace

from bse_intel import seed
from bse_intel.models import FinancialMetric


def _parsed(period, basis):
    return SimpleNamespace(basis=basis, kind="RESULTS", period=None, fy_end_month=3, balance_sheet=None, template="",
                           metrics=[FinancialMetric(metric="revenue", period=period, value=100.0, unit="INR_CR"),
                                    FinancialMetric(metric="pat", period=period, value=10.0, unit="INR_CR")])


class _Row:
    def __init__(self, end, consolidated):
        self.period_end, self.consolidated, self.filed_at = end, consolidated, "2026-01-28T10:00:00"
        self.xbrl_url, self.taxonomy = f"u:{end}:{consolidated}", ""


class _Sink:
    def __init__(self):
        self.dossiers = {}

    def get_dossier(self, scrip):
        return self.dossiers.get(scrip)

    def put_dossier(self, scrip, dossier):
        self.dossiers[scrip] = dossier


def test_seed_keeps_a_standalone_only_quarter_with_the_switch(monkeypatch):
    files = {"u:2025-03-31:True": _parsed("Q4FY25", "CONSOLIDATED"), "u:2025-06-30:False": _parsed("Q1FY26", "STANDALONE")}
    monkeypatch.setattr(seed, "_nse_quarters", lambda *a, **k: {"Q4FY25": _Row("2025-03-31", True), "Q1FY26": _Row("2025-06-30", False)})
    monkeypatch.setattr(seed, "_fetch", lambda client, url, root: url.encode())
    monkeypatch.setattr(seed, "_parse_results", lambda data, stats: files[data.decode()])
    monkeypatch.setattr(seed, "_seed_standalone", lambda *a, **k: None)
    for switch in ("0", "1"):
        monkeypatch.setenv("MEMORY_STANDALONE_ONLY", switch)
        sink = _Sink()
        seed.seed_results(sink, None, "1", "Demo", "2025-01-01", None, seed.SeedStats(), nse=object(), symbol="DEMO")
        d = sink.get_dossier("1")
        periods = {(m["period"], m.get("basis")) for m in d["financial_metrics"]}
        assert ("Q4FY25", "CONSOLIDATED") in periods
        if switch == "0":
            assert ("Q1FY26", "STANDALONE") not in periods and "standalone_only" not in d
        else:
            assert ("Q1FY26", "STANDALONE") in periods
            assert d["standalone_only"] == ["Q1FY26"]
