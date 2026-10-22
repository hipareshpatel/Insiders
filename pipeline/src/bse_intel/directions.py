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
    # a profit or loss turn says which side of zero the period's PAT is (Sapphire Foods Q2FY27, 22 Oct 2026: "PAT turns
    # positive" on a ₹1.51 Cr loss); a turn at another line (EBITDA, operating) is not this one, see _OTHER_LINE
    ("return to profit", re.compile(
        r"\b(?:return\w*|swung|swings?|turn\w*|came|comes?|bounced|got|is|was)\s+(?:back\s+)?(?:to|into|in)\s+(?:the\s+|a\s+)?"
        r"(?:net\s+)?(?:profit(?:ability)?|black)\b|\bturn\w*\s+profitable\b|\b(?:back|swung)\s+in(?:to)?\s+(?:the\s+)?black\b"
        r"|\b(?:pat|net profit|profit after tax|bottom[- ]line|net income)\s+(?:\w+\s+){0,2}?turn\w*\s+positive\b", re.I),
     "pat", "positive"),
    ("swing to loss", re.compile(
        r"\b(?:swung|swings?|turn\w*|slipp\w*|slid|fell|plunged|pushed)\s+(?:back\s+)?(?:to|into)\s+(?:the\s+|a\s+)?(?:net\s+)?"
        r"(?:loss|red)\b|\bturn\w*\s+loss[- ]making\b"
        r"|\b(?:pat|net profit|profit after tax|bottom[- ]line|net income)\s+(?:\w+\s+){0,2}?turn\w*\s+negative\b", re.I),
     "pat", "negative"),
)
# A period named before the claim or just after it: a turn in another period ("full-year FY26 swung to a net loss" on a
# Q4 card, Kabra Extrusion) says nothing about this period's PAT
_PERIOD = re.compile(r"\b(?:Q[1-4]\s?FY\s?'?\d{2,4}|[HQ][1-4]|FY\s?'?\d{2,4}|9M\w*|nine months|full[- ]year|annual|year[- ]ago|"
                     r"last year|previous (?:year|quarter)|preceding quarter|half[- ]year)\b", re.I)


def _other_period(window: str, period: str | None) -> bool:
    """Whether `window` names a period other than `period` (a bare "Q2" is the same as "Q2FY27")."""
    own = re.sub(r"[\s']", "", period or "").upper()
    for m in _PERIOD.finditer(window):
        token = re.sub(r"[\s']", "", m.group(0)).upper()
        if not own or not (token == own or (re.fullmatch(r"[HQ][1-4]", token) and own.startswith(token))):
            return True
    return False


_OTHER_LINE = re.compile(r"\b(?:ebitda|ebit|operating|gross|segment|cash|pbt|pre-tax|before tax)\b", re.I)
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
            if metric == "pat" and _OTHER_LINE.search(text[max(hit.start() - 40, 0):hit.end() + 25]):
                continue   # "EBITDA returned to profit", "swung to an operating loss": another line's turn
            if metric == "pat" and _other_period(text[_start(text, hit.start()):hit.end() + 30],
                                                 getattr(m_fig, "period", None)):
                continue
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

    headline = (clean(card.headline, "headline") or "").rstrip(" ;,")
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

    # a key number's change tag reads the same way: "Turnaround YoY" on a PAT that is still a loss
    pat = figures.get("pat")
    if pat is not None and pat.value is not None and pat.value < 0:
        for k in getattr(card, "key_numbers", None) or []:
            if re.search(r"\b(?:pat|profit|net income|earnings)\b", str(k.label or ""), re.I) \
                    and not _OTHER_LINE.search(str(k.label or "")) \
                    and re.search(r"turnaround|turn\w* positive|return\w* to profit|profitable", str(k.change or ""), re.I):
                notes.append(f"key number {k.label}: change \"{k.change}\" cut (the period's PAT is a loss)")
                k.change = None

    kept_changes = [c for c in card.notable_changes if not wrong_change(c)]
    if len(kept_changes) != len(card.notable_changes):
        notes.append(f"notable changes: {len(card.notable_changes) - len(kept_changes)} cut (contradicted by the file's figures)")
    card.notable_changes = kept_changes
    out.timeline_entry = clean(out.timeline_entry, "timeline") or out.timeline_entry
    return notes


# "More than double" for +74% (LMW's Q2FY27 card, daily audit 21 Oct 2026): a multiple stated in words is checked against
# the two amounts it compares, the sentence's first amount and the first one after the word, both in ₹ crore or both in
# percent. With either amount missing nothing is decided. Applies to every card, with or without XBRL.
_MULTIPLE = re.compile(r"\b(?:(?:more|less)\s+than\s+)?(?:doubl\w*|twice|tripl\w*|three[- ]?fold|halv\w*|half)\b", re.I)
_AMOUNT = re.compile(r"(?:₹\s?([\d,]+(?:\.\d+)?)\s*(?:cr\b|crores?\b))|(\d+(?:\.\d+)?)\s?%", re.I)
_MULTIPLE_TOLERANCE = 0.05


def _multiple_wrong(sentence: str, hit: re.Match) -> bool:
    amounts = [(m.start(), float((m.group(1) or m.group(2)).replace(",", "")), bool(m.group(1)))
               for m in _AMOUNT.finditer(sentence)]
    before = [a for a in amounts if a[0] < hit.start()]
    after = [a for a in amounts if a[0] > hit.end()]
    if not before or not after or before[0][2] != after[0][2] or not before[0][1] or not after[0][1]:
        return False
    # the base follows the word closely, in the same clause ("more than double Q2FY26 (₹40.92 Cr)"); "double its limits to
    # ₹1,000 Cr" names the result, and "provisions tripled ... while the GNPA ratio ... 1.84%" another line (stored cards)
    between = sentence[hit.end():after[0][0]]
    if len(between) > 40 or re.search(r",|;|\bto\b", between):
        return False
    word = hit.group(0).lower()
    ratio = before[0][1] / after[0][1]
    if "half" in word or "halv" in word:
        ratio = 1 / ratio if ratio else 0
        need = 2.0
    else:
        need = 3.0 if ("tripl" in word or "three" in word) else 2.0
    if word.startswith("less than"):
        return ratio >= need * (1 + _MULTIPLE_TOLERANCE)
    return ratio < need * (1 - _MULTIPLE_TOLERANCE)


def wrong_multiples(text: str | None) -> list[re.Match]:
    """The multiples in words ("more than double", "tripled", "halved") the sentence's own amounts contradict."""
    found = []
    for hit in _MULTIPLE.finditer(text or ""):
        start = _start(text, hit.start())
        end = min([i for i in (text.find(". ", hit.end()), text.find("; ", hit.end())) if i >= 0] or [len(text)])
        sentence = text[start:end]
        local = re.compile(re.escape(hit.group(0))).search(sentence, hit.start() - start)
        if local and _multiple_wrong(sentence, local):
            found.append(hit)
    return found


def multiple_guard(out) -> list[str]:
    """Cut from the card each multiple in words its own amounts contradict. Returns what was cut."""
    card = getattr(out, "card", None)
    if card is None:
        return []
    notes: list[str] = []

    def clean(text: str | None, where: str) -> str | None:
        for _ in range(3):
            found = wrong_multiples(text)
            if not found:
                break
            notes.append(f"{where}: cut \"{found[0].group(0)}\" (the amounts it compares do not make that multiple)")
            text = cut(text, found[0])
        return text

    card.takeaway = clean(card.takeaway, "takeaway") or ""
    for fact in card.what_happened:
        fact.text = clean(fact.text, "what_happened") or ""
    card.what_happened = [f for f in card.what_happened if (f.text or "").strip()] or card.what_happened
    card.why_it_matters = [i for i in card.why_it_matters if (setattr(i, "text", clean(i.text, "why_it_matters")) or True)
                           and (i.text or "").strip()]
    return notes
