

def test_price_chart_series_is_written_once_a_day():
    """market-data writes a year of closes per company to R2 (chart/<scrip>.json) for the company page; a second run
    the same day writes nothing, and a short or missing series none at all."""
    import json

    import pytest

    pd = pytest.importorskip("pandas")   # the [market] extra; CI installs [dev] only

    from bse_intel.market import chart_series, write_chart

    days = pd.bdate_range("2025-09-01", periods=300)
    frame = pd.DataFrame({"Close": [100.0 + i for i in range(300)]}, index=days)
    series = chart_series(frame)
    assert len(series["d"]) == 260 and series["c"][-1] == 399.0 and series["d"][-1] == days[-1].date().isoformat()
    assert chart_series(frame.head(3)) is None and chart_series(None) is None

    class Sink:
        def __init__(self):
            self.objects = {}

        def put_object(self, key, body, content_type="application/json"):
            self.objects[key] = json.loads(body)

    sink, last = Sink(), days[-1].date().isoformat()
    assert write_chart(sink, "500001", frame, last, "2026-01-01") == 1
    assert sink.objects["chart/500001.json"]["as_of"] == last
    assert write_chart(sink, "500001", frame, last, last) == 0          # already written for this price date
    assert write_chart(sink, "500002", frame, None, None) == 0          # no price date: nothing

    class Broken(Sink):
        def put_object(self, *a, **k):
            raise RuntimeError("R2 down")

    assert write_chart(Broken(), "500001", frame, last, None) == 0      # logged, never stops the prices
