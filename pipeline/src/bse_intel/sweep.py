"""The end-of-day sweep (ai-quality plan change 7; owner list B1, 2026-10-21): before Gemini's daily reset, the held
cards of the live window whose hold is a writer's error are read again, so the free quota left at the reset writes
them better rather than lapsing.

Only true classes: a figure the filing does not hold (ungrounded), a sum or change that does not add up, a figure out
of scale with the company, a claim the filing does not support. A card held only for how it quoted the filing (152 of
223 held on 21 Oct) is not swept: that is the check's problem, and 30 of 31 sent back for wording came back held again.
Each filing is swept once, at most MAX_A_DAY a day. The re-run goes through every check as any card does; nothing is
released by the sweep itself. No AI here: the filings are set PENDING (requeue.requeue_ids) and the live run that
follows reads them with the live writer."""

from __future__ import annotations

import json
import logging
from datetime import timedelta

from . import requeue
from .timeutil import now_ist

log = logging.getLogger(__name__)

WINDOW = ((11, 30), (12, 25))   # IST, before Gemini's daily quota resets (midnight Pacific = 12:30 IST)
MAX_A_DAY = 40
DAY_KEY, DONE_KEY = "sweep:day", "sweep:done"
DONE_KEPT = 2000
# grounding keys that mean the writer got something wrong; quote and change fixes alone are not among them
TRUE_CLASSES = {"ungrounded": "figure not in the filing", "math_mismatches": "arithmetic", "out_of_fit": "out of scale",
                "unsupported_claims": "unsupported claim", "call_figure_conflicts": "contradicts the XBRL"}


def hold_class(card: dict) -> str | None:
    """Why a held card was held, when it is a writer's error; None for a hold on wording alone."""
    grounding = card.get("grounding") or {}
    for key, name in TRUE_CLASSES.items():
        if grounding.get(key):
            return name
    return None


def due(sink, now=None) -> bool:
    now = now or now_ist()
    return WINDOW[0] <= (now.hour, now.minute) < WINDOW[1] and sink.kv_get(DAY_KEY) != now.date().isoformat()


def run(sink, live_days: int, max_attempts: int, now=None, limit: int = MAX_A_DAY) -> dict:
    """Set up to ``limit`` held live-window filings with a true-class hold PENDING; returns a summary."""
    now = now or now_ist()
    done = set(json.loads(sink.kv_get(DONE_KEY) or "[]"))
    since = (now.date() - timedelta(days=live_days)).isoformat()
    picked, classes = [], {}
    for row in sink.query("cards_held_recent", [since, 500]):
        if row["news_id"] in done:
            continue
        try:
            card = json.loads(row["card_json"] or "{}")
        except ValueError:
            continue
        name = hold_class(card)
        if not name:
            continue
        picked.append(row["news_id"])
        classes[name] = classes.get(name, 0) + 1
        if len(picked) >= limit:
            break
    result = requeue.requeue_ids(sink, picked, max_attempts) if picked else {"requeued": 0, "filings": []}
    stamp = now.isoformat(timespec="seconds")
    sink.kv_set(DAY_KEY, now.date().isoformat(), stamp)
    if picked:
        sink.kv_set(DONE_KEY, json.dumps(sorted(done | set(picked))[-DONE_KEPT:]), stamp)
    log.info("end-of-day sweep: %d held cards read again (%s)", len(picked), classes)
    return {"requeued": result["requeued"], "classes": classes, "filings": picked}
