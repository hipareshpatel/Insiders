"""Claims about which way a statement line moved, checked against the filing's own XBRL (round 4, 2026-10-19).

Round 4's blind review found the figures on results cards mostly right and the words around them wrong: profit "on
lower tax" when tax rose (AGI Infra, RSWM, Sterling Tools), a deferred-tax "credit" that was a charge (RSWM), an
inventory "build-up" that was a drawdown and the reverse (Nestle, RSWM, Foseco), EPS "declined" when it rose 48%
(Nestle), "lower credit costs" when provisions rose 53% (RBL). Each is a direction the file states exactly, so code
decides it: a claim the file contradicts is cut out of the card (the clause it sits in, or the sentence, or the fact),
and what is left stands. Only with the file's figures in hand: without XBRL nothing here fires.

A change in inventories is an expense line: positive when stock fell (a drawdown), negative when it rose (a build-up).
"""

from __future__ import annotations

import re

# A tax rate is not the tax bill: the rate can fall while the bill rises with profit ("PAT up on a lower effective tax
# rate" is often true when tax expense grew), so a rate claim is never checked against tax expense
_TAXWORDS = r"(?:tax|taxes|tax expense|tax outgo|tax provision|tax charge|tax burden)(?!\s+rates?\b)"
_LOWER = r"(?:lower|reduced|declin\w*|fall\w*|fell|lighter|softer|smaller|decreas\w*|moderat\w*)"
_HIGHER = r"(?:higher|increased|rising|rose|heavier|elevated|bigger|larger)"
_NEAR = r"\s+(?:\w+\s+){0,2}?"

# (name, pattern, metric, what the claim says): "fell"/"rose" compare the change; "negative"/"positive" the value
RULES = (
    ("lower tax", re.compile(rf"\b{_LOWER}{_NEAR}{_TAXWORDS}\b|\b(?<!deferred ){_TAXWORDS}\s+(?:benefit|savings?)\b", re.I),
     "tax_expense", "fell"),
    ("higher tax", re.compile(rf"\b{_HIGHER}{_NEAR}{_TAXWORDS}\b", re.I), "tax_expense", "rose"),
    ("deferred tax credit", re.compile(r"\bdeferred tax\s+(?:credit|write-?back|reversal|benefit|gain)\b"
                                       r"|\b(?:reversal|write-?back|credit|release)\s+(?:of|in)\s+deferred tax\b", re.I),
     "deferred_tax", "negative"),
    ("deferred tax charge", re.compile(r"\bdeferred tax\s+(?:charge|expense|provision)\b", re.I), "deferred_tax", "positive"),
    ("inventory build-up", re.compile(
        r"\binventor(?:y|ies)\s+(?:build|build-?up|buildup|pile|accumulat\w*|rose|increased|went up|grew)\b"
        r"|\b(?:build-?up|buildup|accumulation|increase|rise)\s+(?:in|of)\s+inventor", re.I), "inventory_change", "negative"),
    ("inventory drawdown", re.compile(
        r"\binventor(?:y|ies)\s+(?:draw-?down|reduction|liquidation|destock\w*|fell|declined|decreased|released|unwound)\b"
        r"|\b(?:draw-?down|reduction|liquidation|decline|release|fall)\s+(?:in|of)\s+inventor|\bdestock", re.I),
     "inventory_change", "positive"),
    ("EPS fell", re.compile(rf"\b(?:eps|earnings per share){_NEAR}{_LOWER}\b|\b{_LOWER}{_NEAR}(?:eps|earnings per share)\b", re.I),
     "eps", "fell"),
    ("EPS rose", re.compile(rf"\b(?:eps|earnings per share){_NEAR}(?:rose|grew|increas\w*|higher|jump\w*|improv\w*|up)\b", re.I),
     "eps", "rose"),
    ("lower credit costs", re.compile(rf"\b{_LOWER}{_NEAR}(?:credit costs?|provisions?|provisioning|loan loss)\b", re.I),
     "provisions", "fell"),
)
_SEQUENTIAL = re.compile(r"\bqoq\b|sequential|quarter[- ]on[- ]quarter|previous quarter|preceding quarter|from q[1-4]", re.I)
# The words that hang a cause on a result: the clause from here to its end is the claim
_CONNECTOR = re.compile(r"\b(?:on|as|due to|driven by|helped by|aided by|owing to|thanks to|amid|with|while|because of|"
                        r"led by|supported by|reflecting|from)\b", re.I)
_TOLERANCE = 0.5   # % change within this is no direction at all


def _current(tagged) -> dict[str, object]:
    return {m.metric: m for m in getattr(tagged, "metrics", None) or [] if m.period == tagged.period}


def contradicted(text: str, figures: dict) -> list[tuple[str, re.Match]]:
    """The direction claims in `text` that the file's figures contradict, with where they are."""
    out = []
    for name, pattern, metric, says in RULES:
        m_fig = figures.get(metric)
        if m_fig is None or m_fig.value is None:
            continue
        for hit in pattern.finditer(text or ""):
            if re.search(r"\bgrowth\b", (text or "")[hit.start():hit.end() + 10], re.I):
                continue   # "EPS growth moderated" says growth slowed, not that EPS fell
            sentence = _sentence(text, hit.start())
            if says in ("negative", "positive"):
                wrong = m_fig.value > 0 if says == "negative" else m_fig.value < 0
            else:
                change = m_fig.qoq_pct if _SEQUENTIAL.search(sentence) else m_fig.yoy_pct
                if change is None or abs(change) < _TOLERANCE:
                    continue
                wrong = change > 0 if says == "fell" else change < 0
            if wrong:
                out.append((name, hit))
    return out


def _start(text: str, pos: int) -> int:
    """Where the sentence or clause holding `pos` begins."""
    i = max(text.rfind(". ", 0, pos), text.rfind("; ", 0, pos))
    return i + 2 if i >= 0 else 0


def _sentence(text: str, pos: int) -> str:
    start = _start(text, pos)
    end = min([i for i in (text.find(". ", pos), text.find("; ", pos)) if i >= 0] or [len(text)])
    return text[start:end]


def cut(text: str, hit: re.Match) -> str:
    """`text` without the claim: the clause the connector before it opens, else its whole sentence."""
    start = _start(text, hit.start())
    connectors = [m for m in _CONNECTOR.finditer(text, start, hit.start())]
    end_candidates = [i for i in (text.find(",", hit.end()), text.find(";", hit.end()), text.find(". ", hit.end())) if i >= 0]
    end = min(end_candidates) if end_candidates else len(text)
    if connectors:
        begin = connectors[-1].start()
        # the separator before the connector goes too: "PAT rose 20%, on lower tax" -> "PAT rose 20%"
        while begin > start and text[begin - 1] in " ,":
            begin -= 1
        rest = text[end:]
        if not rest and text.rstrip().endswith("."):
            rest = "."   # the sentence keeps its full stop
        return (text[:begin] + rest).strip()
    sentence_end = text.find(". ", hit.end())
    sentence_end = len(text) if sentence_end < 0 else sentence_end + 2
    return (text[:start] + text[sentence_end:]).strip()


def guard(out, tagged) -> list[str]:
    """Cut every direction claim the file contradicts from the card and the timeline line. Returns what was cut."""
    card = getattr(out, "card", None)
    if card is None or tagged is None or getattr(tagged, "kind", None) != "RESULTS":
        return []
    figures = _current(tagged)
    if not figures:
        return []
    notes: list[str] = []

    def clean(text: str | None, where: str) -> str | None:
        if not text:
            return text
        for _ in range(4):   # one claim at a time: each cut moves the rest
            found = contradicted(text, figures)
            if not found:
                break
            name, hit = found[0]
            notes.append(f"{where}: cut \"{hit.group(0)}\" ({name}, contradicted by the file's figures)")
            text = cut(text, hit)
        return text

    headline = clean(card.headline, "headline")
    if headline and len(headline) >= 8:
        card.headline = headline
    card.takeaway = clean(card.takeaway, "takeaway") or ""
    card.core_catalyst = clean(card.core_catalyst, "core_catalyst")
    kept = []
    for fact in card.what_happened:
        fact.text = clean(fact.text, "what_happened") or ""
        if fact.text.strip():
            kept.append(fact)
    if kept:
        card.what_happened = kept
    card.why_it_matters = [i for i in card.why_it_matters if (setattr(i, "text", clean(i.text, "why_it_matters")) or True)
                           and (i.text or "").strip()]
    # a notable change names its metric as memory does ("inventory_change"): read it as words; one about inventory
    # makes its claim anywhere in its words ("inventory_change ... drawdown improving working capital", RSWM)
    def wrong_change(c) -> bool:
        words = " ".join(str(x or "") for x in (c.metric, c.previous, c.current, c.change)).replace("_", " ")
        inventory = figures.get("inventory_change")
        if inventory is not None and inventory.value and re.search(r"inventor", str(c.metric or ""), re.I):
            said = str(c.change or "")
            if re.search(r"build|accumulat|pile|rose|increase", said, re.I) and inventory.value > 0:
                return True
            if re.search(r"draw|destock|liquidat|release|reduc|fell|declin", said, re.I) and inventory.value < 0:
                return True
        return bool(contradicted(words, figures))

    kept_changes = [c for c in card.notable_changes if not wrong_change(c)]
    if len(kept_changes) != len(card.notable_changes):
        notes.append(f"notable changes: {len(card.notable_changes) - len(kept_changes)} cut (contradicted by the file's figures)")
    card.notable_changes = kept_changes
    out.timeline_entry = clean(out.timeline_entry, "timeline") or out.timeline_entry
    return notes
