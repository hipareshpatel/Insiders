"""No EPS on a card (owner rule 26 Oct 2026: "No EPS numbers on card or on stock pages").

Memory keeps every EPS figure (xbrl reading, the dossier, eps_adjust, the cross-checks); what a reader sees does not
carry it. The model is not given an EPS line (xbrl.table, dossier.metric_lines) and the results table has no EPS row, and
this is the guard behind them: any line, bullet, key number or change of a card that states earnings per share is dropped
before the card is published. A dividend per share is not EPS and stays.
"""

from __future__ import annotations

import re

from .models import Fact, Pass2Output

# "EPS", "E.P.S.", "basic EPS", "earnings per share", "earnings/share", "earnings ₹5 per share", "earnings of ₹ 5 / share",
# "earnings per ₹10 share", "earnings per equity share of ₹10 each", "profit per share", "profit/share", "profit after tax per
# share", "PAT per share", "PAT/share", "per-share earnings". A dividend, DPS, book value, NAV or price per share is not EPS
# and is not matched. Digits are Unicode on both sides (\d here, \p{Nd} in the web twin cardText.ts).
_AMT = r"(?:(?:rs\.?|inr|₹)\s*)?\d[\d.,]*\s*(?:/-)?"
_PER = r"(?:\s+(?:per|a|each)\s+|\s*/\s*)"
_SHARE = (r"(?:(?:rs\.?|inr|₹)\s*\d[\d.,]*\s*(?:/-)?\s+)?(?:(?:equity|ordinary|diluted|basic)\s+)*share"
          r"(?:\s+of\s+(?:rs\.?|inr|₹)\s*\d[\d.,]*(?:\s*/-)?(?:\s+each)?)?")
_QUAL = r"(?:\s*\([^)]{0,40}\))?"
EPS_SOURCE = (r"\b(?:eps|e\.p\.s\.?|"
              r"(?:diluted\s+|basic\s+)?earnings?" + _QUAL + _PER + _SHARE + r"|"
              r"earnings?\s+(?:of\s+)?" + _AMT + r"(?:\s+(?:per|a|each)\s+|\s*/\s*)" + _SHARE + r"|"
              r"(?:profit|pat)\s+(?:of\s+)?" + _AMT + r"(?:\s+(?:per|a|each)\s+|\s*/\s*)" + _SHARE + r"|"
              r"(?:net\s+)?(?:profit(?:\s+after\s+tax)?|income|pat)" + _QUAL + _PER + _SHARE + r"|"
              r"per[\s-]share\s+(?:earnings|profit|income))(?!\w)")
EPS_WORDS = re.compile(EPS_SOURCE, re.I)
_PERIOD = re.compile(r"\b(?:Q[1-4]|H[12]|9M)?\s*FY\s*'?\d{2,4}(?:-\d{2})?\b|\b(?:Q[1-4]|H[12]|9M)\b|\b20\d{2}(?:-\d{2})?\b", re.I)
# the separators a trailing EPS clause may follow: ", " "; " " — " " | "
_SEP = re.compile(r",\s|;\s|\s[—–|]\s")
_LEAD_WORDS = re.compile(r"(?:\s*\b(?:basic|diluted|and|net|adjusted|reported|with|plus)\b|\s*&)*\s*", re.I)
_DANGLE = re.compile(r"(?:[\s,;:\-—–|(]+|\s+(?:basic|diluted|and|net)$)$", re.I)
# the only words a trailing EPS clause may carry after the EPS words: its figure, its change and its comparison
_CLAUSE_WORDS = frozenset(
    "rs re inr cr crore crores lakh lakhs mn million bn billion bps pp x per share shares a an each of vs versus from to up down "
    "rose fell yoy qoq yr yrs year years ago earlier prior previous last compared with at was were is in the quarter quarters "
    "q fy h m basic diluted and or grew growth growing increase increased decrease decreased decline declined declining "
    "dropped higher lower rise rising falling on by".split())


def mentions_eps(text: str | None) -> bool:
    return bool(text) and EPS_WORDS.search(text) is not None


def _balanced(text: str) -> bool:
    depth = 0
    for c in text:
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _trailing_cut(text: str) -> str | None:
    """The text without a TRAILING EPS clause: the EPS words start after the last ", " / "; " / " — " / " | " (outside
    brackets) and nothing but the clause follows (its figure, a bracketed change, "vs ₹x", "a year ago"). The separator
    and dangling "basic" / "diluted" / "and" / "net" go too. None when the EPS is anywhere else: nothing after the EPS
    words may survive, so no figure can be given to the wrong metric."""
    m = EPS_WORDS.search(text)
    if not m:
        return text
    depth, depths = 0, []
    for c in text:
        if c in ")]":
            depth = max(0, depth - 1)
        depths.append(depth)
        if c in "([":
            depth += 1
    last = None
    for sm in _SEP.finditer(text):
        if depths[sm.start()] == 0:
            last = sm
    if last is None or last.end() > m.start() or depths[m.start()] != 0:
        return None
    if not _LEAD_WORDS.fullmatch(text[last.end():m.start()]):
        return None
    rest = text[m.end():]
    if mentions_eps(rest) or not _balanced(rest):
        return None
    words = re.findall(r"[^\W\d_]+", _PERIOD.sub(" ", rest))
    if any(w.lower() not in _CLAUSE_WORDS for w in words):
        return None
    prefix = text[:last.start()]
    while True:
        cut = _DANGLE.sub("", prefix)
        if cut == prefix:
            break
        prefix = cut
    prefix = prefix.rstrip()
    return prefix if prefix and _balanced(prefix) and not mentions_eps(prefix) else None


def cut_text(text: str | None) -> str | None:
    """The text as the card may show it: unchanged without EPS, its trailing EPS clause cut when that is all there is, and
    None when it states EPS anywhere else (the caller drops the whole item: a wrong line is worse than a missing one)."""
    if not text or not mentions_eps(text):
        return text
    cut = _trailing_cut(text)
    return cut if cut and not mentions_eps(cut) else None


def _clip(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0].rstrip(" ,;:-")


def _headline_without_eps(headline: str, facts: list[str]) -> str:
    """A headline that is about EPS and cannot be cut: its company and period ("Acme Q1FY27") before the EPS words when that
    part has no figure, then the first line of what happened that is not EPS, or "results"."""
    m = EPS_WORDS.search(headline)
    prefix = headline[:m.start()].strip(" :-\u2013\u2014,;(") if m else ""
    if prefix and re.search(r"\d", _PERIOD.sub(" ", prefix)):
        p = _PERIOD.search(prefix)
        prefix = prefix[:p.end()].strip(" :-\u2013\u2014,;(") if p else ""
    fact = next((f.strip().rstrip(".") for f in facts if f.strip() and not mentions_eps(f)), "")
    if fact and prefix and fact.lower().startswith(prefix.lower()):
        prefix = ""
    line = f"{prefix}: {fact}" if prefix and fact else fact or (f"{prefix}: results" if prefix else "Quarterly results announced")
    return _clip(line, 220) if len(line) >= 8 else "Quarterly results announced"


def drop_eps(out: Pass2Output) -> list[str]:
    """Take EPS out of the card in place. Returns what was dropped, for the log ("dropped" strings, never the figure's value).
    An item whose text states EPS is dropped whole; the one exception is a trailing EPS clause, which is cut."""
    card = out.card
    if card is None:
        return []
    dropped: list[str] = []

    def keep(items, texts, where: str):
        kept = []
        for item in items:
            if any(mentions_eps(t) for t in texts(item)):
                dropped.append(f"{where}: {texts(item)[0][:60]}")
            else:
                kept.append(item)
        return kept

    def refine(items, where: str):
        """Items with one text: a trailing EPS clause is cut, any other EPS drops the item (its quote is left as it is)."""
        kept = []
        for item in items:
            text = cut_text(item.text)
            if text is None:
                dropped.append(f"{where}: {item.text[:60]}")
                continue
            if text != item.text:
                dropped.append(f"EPS clause: {item.text[:60]}")
                item = item.model_copy(update={"text": text})
            kept.append(item)
        return kept

    def refine_strings(items, where: str):
        kept = []
        for t in items:
            text = cut_text(t)
            if text is None:
                dropped.append(f"{where}: {t[:60]}")
            else:
                if text != t:
                    dropped.append(f"EPS clause: {t[:60]}")
                kept.append(text)
        return kept

    card.what_happened = refine(card.what_happened, "what_happened")   # may be empty until the headline is set
    card.why_it_matters = refine(card.why_it_matters, "why_it_matters")
    card.key_numbers = keep(card.key_numbers, lambda k: [k.label, k.value, k.change or ""], "key_numbers")
    card.notable_changes = keep(card.notable_changes, lambda c: [c.metric, c.why, c.change or ""], "notable_changes")
    card.quantified_impact = keep(card.quantified_impact, lambda q: [q.label, q.interpretation, q.formula], "quantified_impact")
    card.missing_disclosures = refine_strings(card.missing_disclosures, "missing_disclosures")
    track = card.track_next
    for name in ("pending_approvals", "catalysts", "risks"):
        setattr(track, name, refine_strings(getattr(track, name), f"track_next.{name}"))
    track.kpis_to_verify = keep(track.kpis_to_verify, lambda k: [k.kpi, k.metric or "", k.check_in or ""], "kpis_to_verify")
    track.milestones = keep(track.milestones, lambda m: [m.what], "milestones")
    card.call_takeaways = refine(card.call_takeaways, "call_takeaways")
    after = cut_text(card.headline)
    if after is None:
        after = _headline_without_eps(card.headline, [f.text for f in card.what_happened])
    if after != card.headline:
        card.headline = after
        dropped.append("headline: EPS clause")
    if not card.what_happened:
        # a card keeps at least one line of what happened: the headline, now without EPS
        card.what_happened = [Fact(text=card.headline)]
        dropped.append("what_happened: rebuilt from the headline")
    insight = next((i.text for i in card.why_it_matters), None) or next((f.text for f in card.what_happened), "")
    for field, empty in (("takeaway", ""), ("core_catalyst", None)):
        before = getattr(card, field)
        if not before:
            continue
        after = cut_text(before)
        if after is None:
            after = _clip(insight, 240) or empty
        if after != before:
            setattr(card, field, after)
            dropped.append(f"{field}: EPS clause")
    if out.timeline_entry:
        after = cut_text(out.timeline_entry)
        if after is None:
            after = card.headline
        if after != out.timeline_entry:
            out.timeline_entry = after
            dropped.append("timeline_entry: EPS clause")
    return dropped
