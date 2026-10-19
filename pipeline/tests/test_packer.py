"""Several filings' pass-2 requests in one call (ai/packer.py)."""

from __future__ import annotations

import re
import threading

from bse_intel.ai.gateway import AIResult
from bse_intel.ai.packer import Packer, PackedItem, PackedReply
from bse_intel.models import Pass1Result


class FakeGateway:
    def __init__(self, skip: set[str] = frozenset()):
        self.calls, self.skip = [], skip

    def complete_json(self, route, system, user, schema):
        self.calls.append((route, user))
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
