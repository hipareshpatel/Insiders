"""tijori-referee: which Tijori cross-check pairs go to NSE's file (owner, 26 Oct 2026)."""

from bse_intel.cli import tijori_referee_rows


def _row(metric, cls, lead, screener=None, tijori=10.0):
    return {"scrip": "s", "symbol": "S", "basis": "consolidated", "period": "Q1FY27", "metric": metric, "class": cls,
            "memory_value": 12.0, "tijori_value": tijori, "screener_value": screener, "lead": lead}


def test_revenue_and_profit_leads_and_every_sign_difference_go_to_the_referee():
    rows = [_row("revenue", "mismatch", True, 10.0), _row("pat", "lender_definition", True, 10.0),
            _row("eps", "mismatch", True, 10.0),          # EPS leads stay out: off the cards, memory-only
            _row("revenue", "mismatch", False),           # Tijori alone: not a lead
            _row("pat", "naming", True, 10.0), _row("revenue", "match", True, 12.0),
            _row("eps", "sign", False, None, -12.0)]
    picked = tijori_referee_rows(rows)
    assert [(r["metric"], r["class"]) for r in picked] == [("revenue", "mismatch"), ("pat", "lender_definition"), ("eps", "sign")]
    assert picked[-1]["screener_value"] == -12.0      # Tijori's figure stands in where screener has none
    assert picked[0]["screener_value"] == 10.0


def test_every_wrong_quarter_pair_goes_to_the_referee_lead_or_not():
    picked = tijori_referee_rows([_row("pat", "wrong_quarter", False), _row("eps", "mismatch", False)])
    assert [(r["metric"], r["class"]) for r in picked] == [("pat", "wrong_quarter")]
