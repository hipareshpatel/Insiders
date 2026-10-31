"""Two live classes found by the blind check of 20 fact-sheet cards (31 Oct 2026)."""
from types import SimpleNamespace

from bse_intel import xbrl
from bse_intel.pipeline import Pipeline


def test_a_continuing_profit_that_is_only_the_profit_before_the_associates_share_is_not_kept():
    """IGL Q2FY27: profit = continuing + share; the card called the share "from discontinued operations"."""
    values = {("pat", "Q2FY27"): 600.0, ("pat_continuing", "Q2FY27"): 520.0, ("share_associates", "Q2FY27"): 80.0}
    assert xbrl.continuing_before_share(values) == 1 and ("pat_continuing", "Q2FY27") not in values
    # a real discontinued operation keeps its continuing profit
    real = {("pat", "Q2FY27"): 600.0, ("pat_continuing", "Q2FY27"): 450.0, ("share_associates", "Q2FY27"): 80.0,
            ("pat_discontinued", "Q2FY27"): 70.0}
    assert xbrl.continuing_before_share(real) == 0 and ("pat_continuing", "Q2FY27") in real
    # no share: nothing to do
    plain = {("pat", "Q2FY27"): 600.0, ("pat_continuing", "Q2FY27"): 600.0}
    assert xbrl.continuing_before_share(plain) == 0


def _link(period, filed_at, basis="CONSOLIDATED"):
    return SimpleNamespace(period=period, basis=basis, filed_at=filed_at, url=f"https://x/{period}-{filed_at}.xml")


def test_a_file_filed_months_before_the_pdf_is_never_its_results_file(monkeypatch):
    """QUESS Q2FY27 (30 Oct 2026) took its Q1FY27 file of 29 Jul: the whole card was the earlier quarter's."""
    import bse_intel.pipeline as pl

    filing = SimpleNamespace(filed_at="2026-10-30T18:00:00+05:30", news_id="n", scrip_code="539978", symbol="QUESS")
    me = SimpleNamespace(_results_links=lambda f: [_link("Q1FY27", "2026-07-29T12:00:00+05:30")])
    monkeypatch.setattr(pl, "statement_quarter", lambda text, at: "Q1FY27")
    assert Pipeline._results_xbrl_link(me, filing, "") is None
    # the quarter's own file filed with the PDF is still taken, and a late one (over 45 days after) too
    me = SimpleNamespace(_results_links=lambda f: [_link("Q2FY27", "2026-10-30T18:30:00+05:30")])
    monkeypatch.setattr(pl, "statement_quarter", lambda text, at: "Q2FY27")
    assert Pipeline._results_xbrl_link(me, filing, "").period == "Q2FY27"
    me = SimpleNamespace(_results_links=lambda f: [_link("Q2FY27", "2026-12-20T10:00:00+05:30")])
    assert Pipeline._results_xbrl_link(me, filing, "").filed_at.startswith("2026-12-20")
