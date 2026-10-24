"""A meaning critic in shadow mode: each point on a published live card judged against its own quote (owner, 2026-10-21).

docs/audit/ai-quality-plan-2026-10-21.md, change 3. A card's figures pass the checks, yet reviewers still find a third
of the WRONG cards wrong in meaning: a segment read as the company, a year-ago column, an annual charge read as the
order's size, a cause the filing never gives. After a live card is committed, a model of another family than the card's
writer is given each point (headline, takeaway, what happened, why it matters, call takeaways) with its quote, about
600 characters of filing around that quote and the memory items it cites, and answers per point OK or one named fault,
with a one-line reason and an optional narrower text.

Shadow only: the verdicts go to the object store (``evidence/critic/<news_id>.json``, beside the raw replies in ``evidence/``) and a count to the run's stats. Nothing on
the card, its row or memory changes, and no D1 row is written. The daily audit compares the verdicts with the blind
reviewers' (``critic-export``) before anyone decides to act on them.

Why not ``causes.py`` again (F74, not adopted: it cut 73% of claims and caught 8 of 27): that asked "is this stated?"
over 60 K characters and cut what it could not quote. Here the question is the meaning of one point against a local
window, OK is the default, a fault must be named from a fixed list, and nothing is cut.

Spare free quota only (providers.toml ``routes.critic``): its own route, models no card route uses, each stopped at its
``max_share`` of the day; skipped for the rest of the run once nothing can serve it; at most ``CRITIC_MAX`` cards a run,
inside the run's live time; ``CRITIC=0`` turns it off.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Annotated, Any

from pydantic import BeforeValidator, Field

from .ai.gateway import AllProvidersFailed, model_family
from .models import OptStr, _Lenient
from .timeutil import now_iso

log = logging.getLogger(__name__)

PREFIX = "evidence/critic/"   # under evidence/, which the Worker and sync.py already allow
ROUTE = "critic"
VERDICTS = ("OK", "WRONG_PERIOD", "WRONG_ENTITY_OR_SCOPE", "WRONG_DIRECTION", "UNIT", "UNSUPPORTED_CAUSE", "INVENTED",
            "OVERSTATED")
_ALIASES = {"WRONG_ENTITY": "WRONG_ENTITY_OR_SCOPE", "WRONG_SCOPE": "WRONG_ENTITY_OR_SCOPE", "SCOPE": "WRONG_ENTITY_OR_SCOPE",
            "ENTITY": "WRONG_ENTITY_OR_SCOPE", "PERIOD": "WRONG_PERIOD", "DIRECTION": "WRONG_DIRECTION",
            "WRONG_UNIT": "UNIT", "UNITS": "UNIT", "CAUSE": "UNSUPPORTED_CAUSE", "UNSUPPORTED": "UNSUPPORTED_CAUSE",
            "OVERSTATE": "OVERSTATED", "CORRECT": "OK", "SUPPORTED": "OK", "PASS": "OK"}
MISSING = "MISSING"            # a point the critic's reply left out (stored, never counted as OK)
WINDOW = 600                   # characters of filing either side of a quote
MAX_POINTS = 14
MAX_JOB_CHARS = 12_000         # the points, their windows and memory: Groq's model allows 8 K tokens a minute
MIN_LEFT_S = 45                # no critic call starts with less of the run's time than this
MAX_FAILURES = 2               # calls that went out and failed, before the critic stops for the run

def family(model_label: str | None) -> str:
    """'gemini/gemini-3.6-flash' -> 'gemini' (ai.gateway.model_family): the critic is never of the writer's family."""
    return model_family(model_label)


def _verdict(value: Any) -> str:
    text = re.sub(r"[\s/-]+", "_", str(value or "").strip().upper())
    text = _ALIASES.get(text, text)
    if text not in VERDICTS:
        raise ValueError(f"unknown verdict: {value!r}")
    return text


class PointVerdict(_Lenient):
    id: Annotated[str, BeforeValidator(lambda v: str(v or "").strip())]
    verdict: Annotated[str, BeforeValidator(_verdict)]
    reason: Annotated[str, BeforeValidator(lambda v: " ".join(str(v or "").split())[:300])] = ""
    corrected: OptStr = None


def _points(value: Any) -> list:
    out = []
    for item in value if isinstance(value, list) else []:
        try:
            out.append(PointVerdict.model_validate(item))
        except Exception:   # one unreadable entry is left as MISSING, not a failed reply
            continue
    return out


class CriticReply(_Lenient):
    points: Annotated[list[PointVerdict], BeforeValidator(_points)] = Field(min_length=1)


# ------------------------------------------------------------------ the blind vote (plan change 6)
# A second answer to the card's enumerated fields from a model that sees only the filing's opening, never the card
# (deal stage was 4 of live review 3's 7 WRONG cards, impact_level too high on 14 of 32 in review 5). Shadow: stored
# beside the verdicts with the conservative value where the two differ; nothing on the card changes.
OPENING = 3000                  # characters of the filing the vote reads
IMPACT_ORDER = ("LOW", "MODERATE", "HIGH")
# least to most advanced: where the votes differ the less advanced stage is the conservative one
STAGE_ORDER = ("PROPOSED", "MOU", "L1_BIDDER", "LOI", "BOARD_APPROVED", "TERMS_FINALISED", "SHAREHOLDER_APPROVED", "LOA",
               "WORK_ORDER", "DEVELOPMENT_ORDER", "CONTRACT", "IN_PROGRESS", "PARTIALLY_COMPLETED", "COMPLETED")


def _upper(value: Any) -> str | None:
    text = re.sub(r"[\s/-]+", "_", str(value or "").strip().upper())
    return text or None


class VoteReply(_Lenient):
    event_type: Annotated[OptStr, BeforeValidator(_upper)] = None
    impact_level: Annotated[OptStr, BeforeValidator(_upper)] = None
    tone: Annotated[OptStr, BeforeValidator(_upper)] = None
    deal_stage: Annotated[OptStr, BeforeValidator(_upper)] = None


def card_enums(card: dict) -> dict:
    """The card's own values for the fields the vote answers (a deal's stage only when the card has a deal)."""
    deal = card.get("deal_value") if isinstance(card.get("deal_value"), dict) else {}
    out = {"event_type": card.get("event_type"), "impact_level": card.get("impact_level"), "tone": card.get("tone")}
    if deal.get("stage"):
        out["deal_stage"] = deal["stage"]
    return {k: str(v).upper() for k, v in out.items() if v}


def _conservative(field: str, a: str, b: str) -> str | None:
    """The value to use when the two votes differ; None when there is no safer side (event type: flagged only)."""
    order = IMPACT_ORDER if field == "impact_level" else STAGE_ORDER if field == "deal_stage" else None
    if order and a in order and b in order:
        return order[min(order.index(a), order.index(b))]
    if field == "tone":
        return "NEUTRAL"
    return None


def compare_votes(card: dict, vote: VoteReply) -> dict:
    """{field: {card, vote, agree, conservative}} for each field both sides answered."""
    out = {}
    for field, mine in card.items():
        theirs = getattr(vote, field, None)
        if not theirs:
            continue
        agree = theirs == mine
        out[field] = {"card": mine, "vote": theirs, "agree": agree,
                      "conservative": mine if agree else _conservative(field, mine, theirs)}
    return out


def render_vote(job: dict) -> str:
    fields = ", ".join(job.get("card_enums", {}))
    return f"FILING OPENING:\n{job.get('opening') or ''}\n\nAnswer only these fields: {fields}."


# ------------------------------------------------------------------ the job: what the critic is shown


def card_points(card: dict) -> list[dict]:
    """The points on the card's face, each {"id", "field", "text", "quote", "memory_refs"}."""
    points: list[dict] = []

    def add(pid: str, field: str, text: Any, quote: Any = None, refs: Any = None) -> None:
        text = " ".join(str(text or "").split())
        if text:
            points.append({"id": pid, "field": field, "text": text, "quote": (str(quote).strip() or None) if quote else None,
                           "memory_refs": [str(r) for r in (refs or []) if r]})

    add("headline", "headline", card.get("headline"))
    takeaway = " ".join(str(card.get("takeaway") or "").split())
    if takeaway and takeaway != " ".join(str(card.get("headline") or "").split()):
        add("takeaway", "takeaway", takeaway)
    for i, fact in enumerate(card.get("what_happened") or []):
        fact = fact if isinstance(fact, dict) else {"text": fact}
        add(f"what_happened.{i}", "what_happened", fact.get("text"), fact.get("quote"))
    for i, item in enumerate(card.get("why_it_matters") or []):
        item = item if isinstance(item, dict) else {"text": item}
        add(f"why_it_matters.{i}", "why_it_matters", item.get("text"), item.get("quote"), item.get("memory_refs"))
    for i, item in enumerate(card.get("call_takeaways") or []):
        if isinstance(item, dict) and item.get("verified"):   # only a verified takeaway is on the face
            add(f"call_takeaways.{i}", "call_takeaways", item.get("text"), item.get("quote"), item.get("memory_refs"))
    return points[:MAX_POINTS]


_FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def excerpt(text: str, quote: str | None, width: int = WINDOW) -> str | None:
    """The filing around the quote, ``width`` characters either side; None when the quote cannot be placed."""
    if not text or not quote:
        return None
    words = quote.split()[:30]
    match = re.search(r"\s+".join(re.escape(w) for w in words), text, re.I) if words else None
    if match is None:   # a paraphrased quote: its longest figure, if that is in the filing
        figures = sorted(_FIGURE.findall(quote), key=len, reverse=True)
        figure = next((f for f in figures if len(f) >= 4), None)
        match = re.search(r"(?<![\d,.])" + re.escape(figure) + r"(?![\d,]|\.\d)", text) if figure else None
    if match is None:
        return None
    start, end = max(0, match.start() - width), min(len(text), match.end() + width)
    return ("…" if start else "") + " ".join(text[start:end].split()) + ("…" if end < len(text) else "")


def memory_items(view: dict | None, refs: list[str]) -> list[dict]:
    """The memory items a point cites, as the writer was shown them (each trimmed to 400 characters)."""
    if not view or not refs:
        return []
    index = {}
    for key in ("guidance", "recent_timeline", "watchlist", "deals", "previous_calls"):
        for item in view.get(key) or []:
            if isinstance(item, dict) and item.get("id"):
                index[item["id"]] = (key, item)
    out = []
    for ref in refs:
        if ref in index:
            kind, item = index[ref]
            out.append({"id": ref, "kind": kind, "item": json.dumps(item, ensure_ascii=False, default=str)[:400]})
    return out


def build_job(news_id: str, card_json: dict, writer: str, text: str, view: dict | None, filed_at: str = "",
              event_type: str = "") -> dict | None:
    """A self-contained copy of what the critic needs: nothing in it points back at the card."""
    points = card_points(json.loads(json.dumps(card_json, default=str)))
    if not points:
        return None
    for width in (WINDOW, WINDOW // 2, WINDOW // 4):
        for p in points:
            p["excerpt"] = excerpt(text, p["quote"], width)
            p["memory"] = memory_items(view, p["memory_refs"])
        if _size(points) <= MAX_JOB_CHARS:
            break
    while _size(points) > MAX_JOB_CHARS and any(p.get("excerpt") for p in points):
        last = max((p for p in points if p.get("excerpt")), key=lambda p: points.index(p))
        last["excerpt"], last["excerpt_note"] = None, "left out for length"
    card = json.loads(json.dumps(card_json, default=str))
    return {"news_id": news_id, "writer": writer, "filed_at": filed_at, "event_type": event_type, "points": points,
            "opening": " ".join((text or "")[:OPENING].split()), "card_enums": card_enums(card)}


def _size(points: list[dict]) -> int:
    return sum(len(p["text"]) + len(p.get("quote") or "") + len(p.get("excerpt") or "")
               + sum(len(m["item"]) for m in p.get("memory", [])) for p in points)


def render(job: dict) -> str:
    """The user message: one block per point."""
    lines = [f"EVENT TYPE: {job.get('event_type') or 'unknown'}", ""]
    for p in job["points"]:
        lines.append(f"POINT {p['id']} ({p['field']}): {p['text']}")
        if p["field"] not in ("headline", "takeaway"):
            lines.append(f"QUOTE: {p['quote'] or '(none given)'}")
            lines.append(f"EXCERPT: {p.get('excerpt') or '(quote not found in the filing text' + (', left out for length' if p.get('excerpt_note') else '') + ')'}")
        for m in p.get("memory", []):
            lines.append(f"MEMORY {m['id']} ({m['kind']}): {m['item']}")
        lines.append("")
    lines.append("Answer for every POINT id above.")
    return "\n".join(lines)


# ------------------------------------------------------------------ the run


def key(news_id: str) -> str:
    """evidence/critic/{news_id}.json, the id cut to safe characters as for the raw replies (pipeline.evidence_key)."""
    safe = "".join(ch for ch in news_id if ch.isalnum() or ch in "-_")[:120] or "unknown"
    return f"{PREFIX}{safe}.json"


def record(job: dict, reply: CriticReply, critic_model: str, latency_s: float) -> dict:
    """The stored verdicts: each point of the job with its verdict; a point the reply left out is MISSING."""
    said = {}
    for v in reply.points:
        said.setdefault(v.id, v)
    points = []
    for p in job["points"]:
        v = said.get(p["id"])
        points.append({"id": p["id"], "field": p["field"], "text": p["text"], "quote": p["quote"],
                       "excerpt_found": bool(p.get("excerpt")), "memory_refs": p["memory_refs"],
                       "verdict": v.verdict if v else MISSING, "reason": v.reason if v else "",
                       "corrected": (v.corrected or None) if v and v.verdict != "OK" else None})
    counts: dict[str, int] = {}
    for p in points:
        counts[p["verdict"]] = counts.get(p["verdict"], 0) + 1
    return {"news_id": job["news_id"], "filed_at": job.get("filed_at"), "event_type": job.get("event_type"),
            "writer": job["writer"], "critic": critic_model, "critiqued_at": now_iso(), "latency_s": round(latency_s, 1),
            "mode": "shadow", "counts": counts, "points": points}


def new_counts() -> dict:
    return {"queued": 0, "cards": 0, "points": 0, "flagged_points": 0, "flagged_cards": 0, "by_verdict": {},
            "by_critic": {}, "not_reached": 0, "failed": 0, "store_failed": 0, "stopped": None,
            "votes": 0, "vote_failed": 0, "vote_disagree": {}}


def _vote(job: dict, gateway, vote_system: str, writer: str, counts: dict) -> dict | None:
    """The blind vote for one job, or None (no opening, nothing to vote on, or the call failed: never raises)."""
    if not vote_system or not job.get("opening") or not job.get("card_enums"):
        return None
    try:
        result = gateway.complete_json(ROUTE, vote_system, render_vote(job), VoteReply,
                                       allow=lambda t, w=writer: family(f"{t.provider}/{t.model}") != w)
    except Exception as exc:
        log.info("vote for %s not taken: %s", job["news_id"], type(exc).__name__)
        counts["vote_failed"] += 1
        return None
    votes = compare_votes(job["card_enums"], result.value)
    counts["votes"] += 1
    for field, v in votes.items():
        if not v["agree"]:
            counts["vote_disagree"][field] = counts["vote_disagree"].get(field, 0) + 1
    return {"model": result.model_label, "fields": votes}


def run(jobs: list[dict], gateway, sink, system: str, deadline: float | None, max_cards: int,
        counts: dict | None = None, clock=time.monotonic, vote_system: str = "") -> dict:
    """Judge up to ``max_cards`` jobs; store each verdict; return the counts for the run's stats. Never raises."""
    counts = counts if counts is not None else new_counts()
    counts["queued"] += len(jobs)
    failures = 0
    for i, job in enumerate(jobs):
        if counts["cards"] >= max_cards:
            counts["stopped"] = counts["stopped"] or "CRITIC_MAX reached"
        elif deadline is not None and clock() >= deadline - MIN_LEFT_S:
            counts["stopped"] = counts["stopped"] or "run time used"
        if counts["stopped"]:
            counts["not_reached"] += len(jobs) - i
            break
        writer = family(job["writer"])
        try:
            result = gateway.complete_json(ROUTE, system, render(job), CriticReply,
                                           allow=lambda t, w=writer: family(f"{t.provider}/{t.model}") != w)
        except AllProvidersFailed as exc:
            if exc.attempted:
                counts["failed"] += 1
                failures += 1
                if failures >= MAX_FAILURES:
                    counts["stopped"] = "critic calls failing"
                continue
            # nothing could be asked: quota at the route's share, no key, cooling down - the run's other cards too
            counts["stopped"] = ("quota used" if exc.quota_exhausted else "no critic model available")
            counts["not_reached"] += len(jobs) - i
            break
        except Exception as exc:   # the critic never stops a run
            log.warning("critic for %s failed: %s", job["news_id"], type(exc).__name__)
            counts["failed"] += 1
            failures += 1
            if failures >= MAX_FAILURES:
                counts["stopped"] = "critic calls failing"
            continue
        body = record(job, result.value, result.model_label, result.latency_s)
        if deadline is None or clock() < deadline - MIN_LEFT_S:
            vote = _vote(job, gateway, vote_system, writer, counts)
            if vote:
                body["votes"] = vote
        try:
            sink.put_object(key(job["news_id"]), json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode())
        except Exception as exc:
            log.warning("critic verdict for %s not stored: %s", job["news_id"], exc)
            counts["store_failed"] += 1
            continue
        counts["cards"] += 1
        counts["points"] += len(body["points"])
        flagged = sum(n for v, n in body["counts"].items() if v not in ("OK", MISSING))
        counts["flagged_points"] += flagged
        counts["flagged_cards"] += flagged > 0
        for verdict, n in body["counts"].items():
            counts["by_verdict"][verdict] = counts["by_verdict"].get(verdict, 0) + n
        counts["by_critic"][result.model_label] = counts["by_critic"].get(result.model_label, 0) + 1
    return counts


def export(sink, since: str, until: str | None = None) -> list[dict]:
    """Every stored verdict critiqued on or after ``since`` (YYYY-MM-DD, IST) and before ``until``; read only."""
    out = []
    for name in sorted(sink.list_objects(PREFIX)):
        blob = sink.get_object(name)
        if not blob:
            continue
        try:
            body = json.loads(blob)
        except ValueError:
            continue
        day = str(body.get("critiqued_at") or "")[:10]
        if day >= since and (until is None or day < until):
            out.append(body)
    return sorted(out, key=lambda b: (b.get("critiqued_at") or "", b.get("news_id") or ""))
