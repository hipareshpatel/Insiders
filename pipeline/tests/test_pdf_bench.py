"""The hard-PDF answer key: loading, pairs, scoring (F199)."""
from __future__ import annotations

from pathlib import Path

from bse_intel import pdf_bench as pb
from bse_intel import pdf_readers as prd

KEY = """symbol,scrip,period_end,period,basis,metric,expected_cr,unit_printed,pdf_url,tags
AAA,,2024-03-31,Q4FY24,consolidated,revenue,100.5,crore,https://x/a.pdf,lakh|bank
AAA,,2024-03-31,FY24,STANDALONE,pat,12.34,crore,https://x/a.pdf,lakh
BBB,,2024-03-31,Q4FY24,STANDALONE,revenue,7,crore,https://x/b.pdf,bank
BBB,,2024-03-31,Q4FY24,STANDALONE,pat,,crore,https://x/b.pdf,bank
CCC,,2024-03-31,Q4FY24,STANDALONE,pat,3,crore,,bank
"""


def rec(expected, readers, verdict, tags=("bank",)):
    return {"symbol": "S", "period": "Q4FY24", "metric": "revenue", "basis": "STANDALONE", "pdf_url": "u",
            "expected": expected, "tags": list(tags), "readers": readers, "verdict": verdict}


def test_the_committed_key_loads_and_names_only_askable_figures():
    text = (Path(__file__).resolve().parents[2] / "docs/bench/hardpdf/key.csv").read_text(encoding="utf-8")
    key = pb.load_key(text)
    assert len(key) == 340 and len({r["pdf_url"] for r in key}) == 21
    assert {r["metric"] for r in key} == {"revenue", "pat"} and {r["basis"] for r in key} == {"STANDALONE", "CONSOLIDATED"}
    assert all(r["period"].startswith(("Q", "FY")) and "H" not in r["period"][:2] for r in key)


def test_key_rows_without_a_figure_or_a_pdf_are_skipped_and_the_basis_is_upper():
    key = pb.load_key(KEY)
    assert [(r["symbol"], r["period"], r["basis"]) for r in key] == \
        [("AAA", "Q4FY24", "CONSOLIDATED"), ("AAA", "FY24", "STANDALONE"), ("BBB", "Q4FY24", "STANDALONE")]
    assert key[0]["expected_cr"] == 100.5 and key[0]["tags"] == ["lakh", "bank"]


def test_pairs_follow_the_referee_names_and_group_by_pdf():
    pairs = pb.pairs_of(pb.load_key(KEY))
    assert [p["pdf_url"] for p in pairs] == ["https://x/a.pdf", "https://x/a.pdf", "https://x/b.pdf"]
    assert pairs[0]["metric"] == "revenue" and pairs[1]["metric"] == "pat" and pairs[0]["expected"] == 100.5
    assert [p["symbol"] for p in pb.pairs_of(pb.load_key(KEY), limit=1)] == ["AAA", "AAA"]


def test_outcome_is_right_within_half_a_printed_decimal():
    assert pb.outcome("ok", 100.504, 100.5, 0.005) == "right"
    assert pb.outcome("ok", 100.52, 100.5, 0.005) == "wrong"
    assert pb.outcome("ok", 100.52, 100.5, 0.05) == "right"       # a coarser printed figure
    assert pb.outcome("none", None, 100.5, 0.005) == "abstain"
    assert pb.outcome("ok", None, 100.5, 0.005) == "abstain"


def test_score_counts_readers_tags_and_lists_false_settlements():
    ok = lambda v: {"status": "ok", "value": v, "tol": 0.005}   # noqa: E731
    none = {"status": "none", "value": None, "tol": 0.005}
    records = [
        rec(10.0, {"a": ok(10.0), "b": ok(10.0), "c": none},
            {"status": "settled", "value": 10.0, "tol": 0.005, "agreed": ["a", "b"], "disagreed": [], "reason": ""}),
        rec(20.0, {"a": ok(21.0), "b": ok(21.0), "c": none},
            {"status": "settled", "value": 21.0, "tol": 0.005, "agreed": ["a", "b"], "disagreed": [], "reason": ""}, ("scan",)),
        rec(30.0, {"a": ok(30.0), "b": ok(31.0), "c": none},
            {"status": "disagree", "value": 30.0, "tol": 0.005, "agreed": ["a"], "disagreed": ["b"], "reason": "x"}),
        rec(40.0, {"a": ok(40.0), "b": none, "c": none},
            {"status": "scanned_lead", "value": 40.0, "tol": 0.005, "agreed": ["a"], "disagreed": [], "reason": ""}),
    ]
    s = pb.score(records)
    assert s["readers"]["a"] == {"right": 3, "wrong": 1, "abstain": 0}
    assert s["readers"]["b"] == {"right": 1, "wrong": 2, "abstain": 1}
    assert s["readers"]["c"] == {"right": 0, "wrong": 0, "abstain": 4}
    assert s["ensemble"]["right"] == 1 and s["ensemble"]["wrong"] == 1 and s["ensemble"]["abstain"] == 2
    assert s["ensemble"]["lead_right"] == 1 and s["ensemble"]["lead_wrong"] == 0
    assert [(f["settled"], f["expected"], f["agreed"]) for f in s["false_settlements"]] == [(21.0, 20.0, ["a", "b"])]
    assert s["by_tag"]["scan"]["ENSEMBLE"]["wrong"] == 1 and s["by_tag"]["bank"]["a"]["right"] == 3
    assert "false settlements (1)" in pb.to_markdown(s) and "settled 21" in pb.to_markdown(s)


def test_first_answer_takes_readers_in_order_and_every_wrong_reading_is_listed():
    ok = lambda v: {"status": "ok", "value": v, "tol": 0.005, "page": 3}   # noqa: E731
    none = {"status": "none", "value": None, "tol": 0.005}
    settled = {"status": "none", "value": None, "tol": 0.005, "agreed": [], "disagreed": [], "reason": ""}
    records = [
        rec(10.0, {"native": ok(10.0), "numfirst": ok(11.0)}, settled),   # native first: right, numfirst's 11 not used
        rec(20.0, {"native": none, "numfirst": ok(20.0)}, settled),       # native none: numfirst's figure
        rec(30.0, {"native": none, "numfirst": none}, settled),
        {**rec(40.0, {"native": ok(41.0), "numfirst": none}, settled), "metric": "pat"},
    ]
    s = pb.score(records)
    assert s["first"] == {"right": 2, "wrong": 1, "abstain": 1}
    assert s["by_metric"]["revenue"][pb.FIRST] == {"right": 2, "wrong": 0, "abstain": 1}
    assert s["by_metric"]["pat"]["native"] == {"right": 0, "wrong": 1, "abstain": 0}
    assert [(w["reader"], w["read"], w["expected"]) for w in s["wrong_readings"]] == [("numfirst", 11.0, 10.0), ("native", 41.0, 40.0)]
    assert s["by_filing"]["S u"]["numfirst"] == {"right": 1, "wrong": 1, "abstain": 2}
    md = pb.to_markdown(s)
    assert "| FIRST ANSWER (in reader order) | 2 | 1 | 1 |" in md and "Every wrong reading (2)" in md
    assert "native: S Q4FY24 STANDALONE pat: read 41, printed 40 (page 3)" in md


def test_answer_pair_applies_the_unchanged_settle_rule():
    def reading(name, family, value, verbatim=True):
        return prd.Reading(name, family, "ok", value, verbatim, True, "textlayer", "Revenue", 1)

    class FakeEnsemble:
        names = ["native", "camelot", "tatr"]

        def readings(self, key, payload, period, metric, basis):
            assert (period, metric, basis, payload) == ("Q4FY24", "revenue", "STANDALONE", b"%PDF")
            return [reading("native", "pymupdf", 10.0), reading("camelot", "lattice", 10.0),
                    prd.Reading("tatr", "tatr", "none", note="no row")]

    pair = pb.pairs_of(pb.load_key(KEY))[2]
    got = pb.answer_pair(FakeEnsemble(), b"%PDF", pair)
    assert got["verdict"]["status"] == "settled" and got["verdict"]["agreed"] == ["native", "camelot"]
    assert got["readers"]["tatr"]["status"] == "none" and got["expected"] == 7.0
    # the settled 10.0 against the printed 7: a false settlement
    assert pb.score([got])["false_settlements"][0]["settled"] == 10.0
    down = pb.answer_pair(FakeEnsemble(), None, pair)
    assert down["verdict"]["status"] == "none" and {r["status"] for r in down["readers"].values()} == {"unavailable"}


# --- the out-of-sample key and its per-batch table -----------------------------------------------------------------

def xrow(symbol, n, status="found_unique", metric="revenue", value="100.5", pdf="x", period="Q2FY27"):
    return {"symbol": symbol, "filing_period": period, "period": period, "basis": "standalone", "metric": metric, "xbrl_value": value,
            "status": status, "pdf_url": f"https://x/{symbol}{n}.pdf" if pdf == "x" else pdf, "printed_unit": "crore"}


def test_key_from_xbrl_keeps_every_status_but_the_two_failures_and_tags_status_and_batch():
    from bse_intel import xbrl_key as xk
    rows = []
    for i in range(12):                                        # 12 filings: the first ten are batch 1, the last two batch 2
        rows.append(xrow(f"S{i}", i, "found_unique"))
        rows.append(xrow(f"S{i}", i, "not_found", "pat", "12"))
    rows += [xrow("F", 0, "fetch_failed"), xrow("E", 0, "locate_error"), xrow("N", 0, "not_found", value=""),
             xrow("P", 0, "not_found", pdf=""), xrow("Q", 0, "found_unique", "eps", "3.1"),
             xrow("R", 0, "found_unique", "other_income", "4")]       # metrics the readers never answer: no key row
    key = pb.key_from_xbrl(xk.load_csv(xk.to_csv([{**r, "news_id": "n"} for r in rows])))
    assert len(key) == 24 and {r["symbol"] for r in key} == {f"S{i}" for i in range(12)}
    assert key[0]["tags"] == "xbrl:found_unique|batch:1" and key[1]["tags"] == "xbrl:not_found|batch:1"
    assert float(key[1]["expected_cr"]) == 12 and key[0]["period_end"] == "2026-09-30"
    assert {r["tags"].split("|")[1] for r in key if r["symbol"] in ("S9",)} == {"batch:1"}
    assert {r["tags"].split("|")[1] for r in key if r["symbol"] in ("S10", "S11")} == {"batch:2"}
    # the text is a key the bench loads: figures, tags and the pdf per row
    loaded = pb.load_key(pb.key_to_csv(key))
    assert len(loaded) == 24 and loaded[0]["tags"] == ["xbrl:found_unique", "batch:1"] and loaded[0]["expected_cr"] == 100.5


def test_the_score_has_a_per_batch_table_and_running_total_only_for_batch_tagged_keys():
    ok = lambda v: {"status": "ok", "value": v, "tol": 0.005}   # noqa: E731
    none = {"status": "none", "value": None, "tol": 0.005}
    settled = lambda v: {"status": "settled", "value": v, "tol": 0.005, "agreed": ["a"], "disagreed": [], "reason": ""}   # noqa: E731
    records = [
        rec(10.0, {"a": ok(10.0), "b": none}, settled(10.0), ("batch:1",)),
        rec(20.0, {"a": ok(21.0), "b": ok(20.0)}, settled(21.0), ("batch:1", "xbrl:found_unique")),
        rec(30.0, {"a": ok(30.0), "b": none}, settled(30.0), ("batch:2",)),
    ]
    s = pb.score(records)
    first, second = s["by_batch"]["batches"]
    assert first["pairs"] == 2 and first["counts"]["a"] == {"right": 1, "wrong": 1, "abstain": 0}
    assert first["counts"]["ENSEMBLE"] == {"right": 1, "wrong": 1, "abstain": 0}
    assert second["counts"]["b"] == {"right": 0, "wrong": 0, "abstain": 1}
    assert s["by_batch"]["running"][1]["counts"]["a"] == {"right": 2, "wrong": 1, "abstain": 0}
    assert s["by_batch"]["running"][1]["pairs"] == 3
    md = pb.to_markdown(s)
    assert "## Per batch of ten filings" in md and "| 1 | 2 | 1/1/0 | 1/0/1 | 1/1/0 | 1/1/0 |" in md and "| 1-2 | 3 | 2/1/0 |" in md
    plain = pb.score([rec(10.0, {"a": ok(10.0)}, settled(10.0))])
    assert "by_batch" not in plain and "Per batch" not in pb.to_markdown(plain)


def test_key_from_xbrl_keeps_the_exchange_figure_whole_and_numbers_batches_by_filing():
    # review: 234567.89 crore was written as 234568 (a right reading scored wrong); a filing whose rows came from two of its
    # PDFs counted as two filings
    rows = [xrow("BIG", 0, value="234567.89")] + [xrow(f"S{i}", i) for i in range(9)]
    rows.append({**xrow("BIG", 0, metric="pat", value="12345.67"), "pdf_url": "https://x/BIG-second.pdf"})
    rows.append(xrow("LAST", 0))
    key = pb.key_from_xbrl(rows)
    assert key[0]["expected_cr"] == "234567.89" and key[10]["expected_cr"] == "12345.67"
    assert pb.outcome("ok", 234567.89, pb.load_key(pb.key_to_csv(key))[0]["expected_cr"], 0.005) == "right"
    assert key[10]["tags"].endswith("batch:1") and key[11]["tags"].endswith("batch:2")
