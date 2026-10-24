"""Several filings' pass-2 requests in one call (ai/packer.py)."""

from __future__ import annotations

import re
import threading

from bse_intel.ai.gateway import AIResult
from bse_intel.ai.packer import Packer, PackedItem, PackedReply
from bse_intel.models import Pass1Result


class FakeGateway:
    def __init__(self, skip: set[str] = frozenset()):
        self.calls, self.skip, self.bulk = [], skip, []

    def complete_json(self, route, system, user, schema, **kw):
        self.calls.append((route, user))
        self.bulk.append(kw.get("bulk", False))
        if schema is PackedReply:
            ids = re.findall(r'<task id="(t\d+)">', user)
            items = [PackedItem(task_id=t, answer={"is_material": True, "event_type": "ORDER_WIN", "reason": f"from {t}"})
                     for t in ids if t not in self.skip]
            return AIResult(PackedReply(results=items), "gemini", "gemini-3.6-flash", 1.0)
        return AIResult(schema(is_material=False, event_type="OTHER", reason="own route"), "nvidia", "nemotron", 1.0)


def _run(packer, n):
    out = [None] * n

    def work(i):
        out[i] = packer.complete("pass2", f"instructions {i}", f"filing {i}", Pass1Result)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(n)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    return out


def test_three_workers_share_one_call_and_each_gets_its_own_answer():
    gw = FakeGateway()
    results = _run(Packer(gw, size=3, wait_s=5), 3)
    packed = [c for c in gw.calls if c[0] == "pass2_packed"]
    assert len(packed) == 1 and all(f"filing {i}" in packed[0][1] for i in range(3))
    assert sorted(r.value.reason for r in results) == ["from t1", "from t2", "from t3"]
    assert all(r.model_label == "gemini/gemini-3.6-flash" for r in results)


def test_a_missing_answer_goes_to_its_own_route_and_a_lone_request_is_sent_after_the_wait():
    gw = FakeGateway(skip={"t2"})
    results = _run(Packer(gw, size=2, wait_s=5), 2)
    assert sorted(r.model_label for r in results) == ["gemini/gemini-3.6-flash", "nvidia/nemotron"]
    gw = FakeGateway()
    (lone,) = _run(Packer(gw, size=5, wait_s=0.2), 1)
    assert lone.model_label == "gemini/gemini-3.6-flash" and len(gw.calls) == 1


def test_a_pack_is_sent_before_the_runs_deadline_and_records_its_members():
    """Online, a run with one or two new filings must send its pack before its time budget ends (owner, 2026-10-19)."""
    import time

    gw = FakeGateway()
    gw.deadline = time.monotonic() + 120.5          # the packer keeps 120 s for the call itself
    packer = Packer(gw, size=6, wait_s=600)
    started = time.monotonic()
    (lone,) = [packer.complete("pass2", "instructions", "filing", Pass1Result, "nse-1")]
    assert time.monotonic() - started < 5 and lone.model_label == "gemini/gemini-3.6-flash"
    assert lone.pack["members"] == ["nse-1"] and len(lone.pack["id"]) == 12


def test_a_pack_out_of_quota_goes_to_its_own_route_and_a_quota_failure_there_reaches_the_caller():
    """With Nemotron 3 Super off the card routes, a packed filing whose Gemini models are all out of quota goes to the
    regular writers; if they are out of quota too, the gateway's failure reaches the pipeline, which leaves the filing
    queued with no attempt spent (test_pipeline.test_packed_filings_stay_queued_when_every_writer_is_out_of_quota)."""
    import pytest

    from bse_intel.ai.gateway import CEILING, AllProvidersFailed

    class OutOfQuota(FakeGateway):
        def __init__(self, own_route_too):
            super().__init__()
            self.own_route_too = own_route_too

        def complete_json(self, route, system, user, schema, **kw):
            self.calls.append((route, user))
            if route == "pass2_packed" or self.own_route_too:
                raise AllProvidersFailed(route, [("gemini:gemini-3.7-flash", CEILING, "daily quota")])
            return AIResult(schema(is_material=False, event_type="OTHER", reason="own route"), "zai", "glm-4.5-flash", 1.0)

    (r,) = _run(Packer(OutOfQuota(False), size=1, wait_s=1), 1)
    assert r.model_label == "zai/glm-4.5-flash"
    with pytest.raises(AllProvidersFailed) as info:
        Packer(OutOfQuota(True), size=1, wait_s=1).complete("pass2", "i", "f", Pass1Result)
    assert info.value.quota_exhausted


def test_a_backfill_packer_marks_its_requests_bulk_and_a_live_one_does_not():
    """So the gateway keeps the best writers' live reserve out of backfill packs (ai-quality plan item 1)."""
    gw = FakeGateway(skip={"t1"})
    Packer(gw, size=1, wait_s=1, bulk=True).complete("pass2_bulk", "i", "f", Pass1Result)
    assert gw.calls[0][0] == "pass2_packed" and gw.calls[1][0] == "pass2_bulk" and gw.bulk == [True, True]
    gw = FakeGateway()
    Packer(gw, size=1, wait_s=1).complete("pass2", "i", "f", Pass1Result)
    assert gw.bulk == [False]


def test_a_long_filing_that_would_overfill_the_pack_goes_in_the_next_one():
    """Two long documents never make one request too large for Gemini's minute; each still gets its own answer."""
    gw = FakeGateway()
    packer = Packer(gw, size=3, wait_s=0.3, max_chars=1000)
    out = [None, None]

    def work(i):
        out[i] = packer.complete("pass2_long", "i" * 10, f"filing {i} " + "x" * 600, Pass1Result)

    import time

    first = threading.Thread(target=work, args=(0,))
    first.start()
    time.sleep(0.05)
    work(1)
    first.join()
    packed = [c for c in gw.calls if c[0] == "pass2_packed"]
    assert len(packed) == 2 and all(r.model_label == "gemini/gemini-3.6-flash" for r in out)
    assert "filing 0" in packed[0][1] and "filing 1" not in packed[0][1]


def test_nothing_on_the_packed_route_can_serve_so_no_wait_and_no_pack():
    """22 Oct: 84 packs failed in two runs with every Gemini model at its day's quota, each after a wait."""
    import time

    gw = FakeGateway()
    gw.can_serve = lambda route, bulk=False: False
    started = time.monotonic()
    (result,) = _run(Packer(gw, size=5, wait_s=5), 1)
    assert time.monotonic() - started < 1 and result.model_label == "nvidia/nemotron"
    assert [c[0] for c in gw.calls] == ["pass2"]


class _ScriptedGateway:
    """Answers a pack with the items given, whatever the tasks were."""

    def __init__(self, items):
        self.items, self.calls = items, []

    def complete_json(self, route, system, user, schema, **kw):
        self.calls.append(route)
        if schema is PackedReply:
            return AIResult(PackedReply(results=self.items), "gemini", "gemini-3.6-flash", 1.0)
        return AIResult(schema(is_material=False, event_type="OTHER", reason="own route"), "nvidia", "nemotron", 1.0)


ALPHA = "Alpha Ltd has received an order worth Rs 120 crore from the Railways for signalling works."
BETA = "Beta Ltd board approved the acquisition of a 51% stake in Gamma Pvt Ltd for Rs 45 crore."


def _answer(reason, quote):
    return {"is_material": True, "event_type": "ORDER_WIN", "reason": reason, "card": {"what_happened": [{"quote": quote}]}}


def _send(items):
    from bse_intel.ai.packer import _Job

    jobs = [_Job("instructions", f"FILING TEXT:\n{ALPHA}", Pass1Result), _Job("instructions", f"FILING TEXT:\n{BETA}", Pass1Result)]
    Packer(_ScriptedGateway(items), size=2)._send(jobs)
    return [j.result.value.reason if j.result else None for j in jobs]


def test_swapped_answers_are_not_put_on_the_other_companys_filing():
    """The model answered t1 with t2's card and t2 with t1's: matched by id alone, Alpha's filing got Beta's card."""
    swapped = [PackedItem(task_id="t1", answer=_answer("beta card", BETA)),
               PackedItem(task_id="t2", answer=_answer("alpha card", ALPHA))]
    assert _send(swapped) == [None, None]          # both go to their own route
    right = [PackedItem(task_id="t1", answer=_answer("alpha card", ALPHA)),
             PackedItem(task_id="t2", answer=_answer("beta card", BETA))]
    assert _send(right) == ["alpha card", "beta card"]
    no_quotes = [PackedItem(task_id="t1", answer={"is_material": True, "event_type": "ORDER_WIN", "reason": "a"})]
    assert _send(no_quotes) == ["a", None]          # nothing to judge by: kept


def test_an_id_answered_twice_is_no_answer():
    twice = [PackedItem(task_id="t1", answer=_answer("first", ALPHA)),
             PackedItem(task_id="t1", answer=_answer("second", ALPHA)),
             PackedItem(task_id="t2", answer=_answer("beta card", BETA))]
    assert _send(twice) == [None, "beta card"]


def test_a_generic_quote_shared_by_filings_does_not_send_a_paraphrased_answer_away():
    """An answer that paraphrased its own quotes and also quoted a line common to both filings was sent to the slower
    route: only a quote found in exactly one task's input decides."""
    from bse_intel.ai.packer import misplaced

    common = "Outcome of the Board Meeting held on 23 October 2026"
    own, other = f"{common}. {ALPHA}", f"{common}. {BETA}"
    answer = {"card": {"what_happened": [{"quote": common}, {"quote": "Alpha won a large railway signalling order today"}]}}
    assert not misplaced(answer, own, [other])
    assert misplaced({"card": {"what_happened": [{"quote": common}, {"quote": BETA}]}}, own, [other])
