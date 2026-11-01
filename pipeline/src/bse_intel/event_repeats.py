"""CARD_EVENT_REPEAT: a second card on the same non-results event (settings.card_event_repeat; off by default, then nothing here
runs). STATUS S2, measured 1 Nov 2026 on the live feed: 47 pairs of published cards in 30 days repeat one event from two
documents (82 of 1,955 non-results cards). ARIS filed one ₹250 Cr Transcon order as an exchange intimation and, five minutes
later, a press release, and both became cards. The AI repeat check before pass 2 points at a timeline entry and missed them.

Deterministic and narrow, for the two kinds whose event is named by an amount and a counterparty (ORDER_WIN, M_AND_A; a
results presentation and its call are left to the owner): a new card repeats a memory timeline entry of the same company when
the entry is of the same kind, dated up to 3 days before it, states the same rupee crore amount (within 0.5%) and shares a
distinctive name with it (a customer, a target, a project: a capitalised word that is not the company's own name, a month or a
common word). The later card is held with the earlier one named; its facts stay on the stored card and nothing is deleted."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .settings import card_event_repeat

KINDS = ("ORDER_WIN", "M_AND_A")
WINDOW = timedelta(days=3)
_AMOUNT = re.compile(r"₹\s?([\d,]+(?:\.\d+)?)\s*(?:cr|crore)\b", re.I)
_NAME = re.compile(r"\b[A-Z][A-Za-z&'\-]{3,}\b")
_COMMON = {w.lower() for w in """January February March April May June July August September October November December Order Orders
    Limited Private Company Subsidiary Board Approves Approved Wins Secures Secured Receives Received Bags Contract Contracts Project
    Projects Mandate Service Services Supply Acquisition Acquire Acquires Stake Share Shares Agreement Deal Value India Indian Crore
    Rupees Worth From With Under Phase Group Holdings Industries Solutions Infra Infrastructure Engineering Technologies Systems Power
    Energy Letter Intent Award Awarded Announces Announced Signs Signed Definitive Completion Completes Tender Offer Public""".split()}


# an order book, backlog or running total is no order's own amount (lead's review of #329: two orders whose cards both cite
# "order book now ₹12,400 Cr" would match on it)
_TOTAL = re.compile(r"\b(?:order\s*book|backlog|pipeline|total|cumulative|aggregat\w*|year[- ]to[- ]date|YTD)\b[^₹]{0,30}$", re.I)


def _amounts(text: str) -> set[float]:
    text = text or ""
    return {float(m.group(1).replace(",", "")) for m in _AMOUNT.finditer(text) if not _TOTAL.search(text[max(0, m.start() - 60):m.start()])}


def _names(text: str, own: set[str]) -> set[str]:
    return {w.lower() for w in _NAME.findall(text or "")} - _COMMON - own


def _when(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def match(event_type: str | None, filed_at: str | None, text: str, company_name: str | None, timeline: list[dict] | None,
          news_id: str | None = None) -> tuple[str, str] | None:
    """(the earlier entry's news_id, why) when this card repeats an event memory already has, else None."""
    if not card_event_repeat() or event_type not in KINDS:
        return None
    now = _when(filed_at)
    amounts = _amounts(text)
    if now is None or not amounts:
        return None
    own = {w.lower() for w in re.findall(r"[A-Za-z&'\-]{4,}", company_name or "")}
    names = _names(text, own)
    for entry in reversed(timeline or []):
        if entry.get("event_type") != event_type or not entry.get("news_id") or entry.get("news_id") == news_id:
            continue
        then = _when(entry.get("date"))
        if then is None or not (timedelta(0) <= now - then <= WINDOW):
            continue
        summary = str(entry.get("summary") or entry.get("text") or "")
        same = [a for a in amounts for b in _amounts(summary) if abs(a - b) <= 0.005 * max(a, b)]
        shared = sorted(names & _names(summary, own))
        if same and shared:
            return entry["news_id"], f"same {event_type} of ₹{same[0]:,g} Cr with {', '.join(shared[:3])}"
    return None
