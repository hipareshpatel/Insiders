"""bse-verify-kept: the classification of BSE's answers and the summary, against a fake session. No network."""
from __future__ import annotations

import json
from datetime import date

from bse_intel import bse_verify_kept as v
from bse_intel.adapters import bse


class Answer:
    def __init__(self, status, body):
        self.status_code, self.content, self.headers = status, body if isinstance(body, bytes) else json.dumps(body).encode(), {}


class Fake:
    """Answers by path and scrip."""

    def __init__(self, header, ann, refuse_at=None):
        self.headers, self.header, self.ann, self.refuse_at = {}, header, ann, refuse_at

    def get(self, url, params=None, timeout=None):
        scrip = params.get("scripcode") or params.get("strScrip")
        if scrip == self.refuse_at:
            return Answer(403, b"<html>Just a moment... cf-chl challenge</html>" + b"x" * 400)
        if "getScripHeaderData" in url:
            return Answer(200, self.header[scrip][0])
        if "StockTrading" in url:
            return Answer(200, self.header[scrip][1])
        return Answer(200, {"Table": self.ann[scrip]})

    def close(self):
        pass


def _client(fake):
    rec = v.RecordingSession(fake)
    return bse.BSEClient(session=rec, sleep=lambda s: None), rec


KEPT = [{"scrip_code": s, "company_name": f"Co {s}", "isin": f"INE{s}", "market_cap_cr": 900.0} for s in ("1", "2", "3")]
TODAY = date(2026, 10, 26)
HEADER = {"1": ({"Header": {"Category": "Listed", "DisplayText": ""}, "CurrRate": {"LTP": "10.5"}}, {"MktCapFull": "1,234.5"}),
          "2": ({"Header": {"Category": "Listed", "DisplayText": "Suspended"}}, {"MktCapFull": "300"}),
          "3": ({"Header": {"Category": "Listed"}, "Cmpname": {"Category": "Listed"}}, {"MktCapFull": "800"})}
ANN = {"1": [{"DissemDT": "2026-10-20T10:00:00"}, {"DissemDT": "2026-10-01T10:00:00"}], "2": [],
       "3": [{"NEWS_DT": "2026-10-10T09:00:00"}]}


def test_status_and_market_cap_are_read_from_the_header():
    assert v.parse_status({"Header": {"Category": "Listed"}}) == "active"
    assert v.parse_status({"Header": {"Category": "Listed", "DisplayText": "Suspended"}}) == "suspended"
    assert v.parse_status({"Header": {"Category": "Delisted"}}) == "delisted"
    assert v.parse_status({"Other": "x"}) == "unknown"
    assert v.parse_mcap_cr({"MktCapFull": "9,14,652.52", "MktCapFF": "10"}) == 914652.52
    assert v.parse_mcap_cr({"MktCapFull": "-"}) is None and v.parse_mcap_cr({}) is None


def test_verify_and_summary():
    client, rec = _client(Fake(HEADER, ANN))
    result = v.verify(client, KEPT, TODAY, 500)
    by = {r["scrip_code"]: r for r in result["companies"]}
    assert by["1"]["scrip_status"] == "active" and by["1"]["market_cap_cr"] == 1234.5
    assert by["1"]["latest_announcement"] == "2026-10-20" and by["1"]["announcement_in_90d"] is True
    assert by["2"]["scrip_status"] == "suspended" and by["2"]["latest_announcement"] is None
    assert by["3"]["announcement_in_90d"] is True
    s = result["summary"]
    assert (s["asked"], s["calls_made"], s["status_200"], s["status_403"], s["status_other"]) == (3, 9, 9, 0, 0)
    assert (s["active"], s["suspended"], s["still_at_or_over_min_mcap"], s["announcement_in_90d"]) == (2, 1, 2, 2)
    assert s["active_and_over_min_and_announced"] == 2   # 1 (1,234 Cr) and 3 (800 Cr)
    assert result["blocked"] is None
    assert "active 2, suspended 1" in v.render(result) and v.to_csv(result).count("\n") == 4
    # the announcement call is filtered by the scrip
    ann_call = [c for c in rec.log if c["path"].startswith("AnnSubCategoryGetData")][0]
    assert ann_call["scrip"] == "1"


def test_a_refusal_stops_the_run_and_keeps_the_body_head():
    client, rec = _client(Fake(HEADER, ANN, refuse_at="2"))
    result = v.verify(client, KEPT, TODAY, 500)
    assert [r["scrip_code"] for r in result["companies"]] == ["1"]
    assert result["not_asked"] == ["2", "3"]
    b = result["blocked"]
    assert b["scrip_code"] == "2" and b["status"] == 403 and len(b["body_head"]) == v.BODY_CHARS
    assert b["body_head"].startswith("<html>Just a moment")
    s = result["summary"]
    assert s["status_403"] == 1 and s["status_200"] == 3
    assert "REFUSED at 2" in v.render(result)
