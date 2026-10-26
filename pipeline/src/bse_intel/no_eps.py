"""No EPS on a card (owner rule 26 Oct 2026: "No EPS numbers on card or on stock pages").

Memory keeps every EPS figure (xbrl reading, the dossier, eps_adjust, the cross-checks); what a reader sees does not
carry it. The model is not given an EPS line (xbrl.table, dossier.metric_lines) and the results table has no EPS row, and
this is the guard behind them: any line, bullet, key number or change of a card that states earnings per share is dropped
before the card is published. A dividend per share is not EPS and stays.
"""

from __future__ import annotations

import re
import unicodedata

from .models import Fact, Pass2Output

# EPS is stated when text, after normalising (NFKC, soft hyphen and zero-width characters removed, non-breaking hyphen to
# "-", "_" to a space, matched case-insensitively), has EITHER
#   A. an explicit token: EPS / E.P.S. / E P S / LPS not followed by a letter (EPSILON, Repsol, deposits, steps stay), or
#   C. earnings wording: "earnings per share", "loss per share", "profit/(loss) per share", "earnings-per-share",
#      "earnings ₹5 per share", "PAT/share", "per-share earnings" (profit, loss, income, PAT, earnings), or
#   B. a per-share figure: an amount within 6 words of a per-share phrase ("Earnings were ₹5.2 per share", "each share
#      earned ₹5", "profit worked out to ₹5 per share") unless its clause (piece between ", " "; " " — " " | ") names a non-EPS per-share item (_NOT_EPS).
_AMT = r"(?:(?:rs\.?|inr|₹)\s*)?\d[\d.,]*\s*(?:/-)?"
_PER = r"(?:[\s\-]+(?:per|a|each)[\s\-]+|\s*/\s*)"
_SHARE = (r"(?:(?:rs\.?|inr|₹)\s*\d[\d.,]*\s*(?:/-)?\s+)?(?:(?:equity|ordinary|diluted|basic)\s+)*share"
          r"(?:\s+of\s+(?:rs\.?|inr|₹)\s*\d[\d.,]*(?:\s*/-)?(?:\s+each)?)?(?![^\W_])(?!\s+(?:capital|premium)\b)")
_QUAL = r"(?:\s*\([^)]{0,40}\))?"
_WORD = (r"(?<![^\W\d_])(?:(?:net|basic|diluted|adjusted|reported|total)\s+)*"
         r"(?:profit|loss|income|pat|earnings?)(?:\s+(?:after|before)\s+tax)?")
_TOKEN = re.compile(r"(?<![^\W\d_])(?:e[\s.\-]*p[\s.\-]*s|lps)(?![^\W\d_])", re.I)
_WORDING = re.compile(
    _WORD + r"(?:\s*/\s*\(?\s*(?:loss|profit)\s*\)?)?" + _QUAL + _PER + _SHARE + "|"
    + _WORD + r"\s+(?:of\s+)?" + _AMT + _PER + _SHARE + "|"
    r"per[\s\-]share\s+(?:earnings|profit|loss|income)(?![^\W_])", re.I)
_PS = (r"(?:(?<![^\W\d_])per\s*(?:equity\s+|ordinary\s+)?(?:share|sh)|(?<![^\W\d_])(?:a|each)\s+(?:equity\s+)?share"
       r"|/\s*(?:equity\s+)?(?:share|sh))(?![^\W\d_])(?!\s+(?:of|capital)\b)")
_FIG = r"(?<![^\W_])(?<![.,])(?:(?:rs\.?|inr|₹)\s*)?[(+\-−]?\d[\d.,]*"
_FIGURE = re.compile(_FIG + r"(?:\s+\S+){0,6}?\s*" + _PS + "|" + _PS + r"(?:\s+\S+){0,6}?[\s:=]*" + _FIG, re.I)
# per-share items that are NOT EPS: a figure with one of these beside it keeps its per-share figure (rule B only)
_NOT_EPS = re.compile(
    r"(?<![^\W\d_])(?:dividends?|dps|payout|book\s+value|bvps|nav|net\s+asset\s+value|prices?|cmp|market\s+price|face\s+value|"
    r"par\s+value|buy-?\s*back|offers?|issue[ds]?|rights|premium|allot\w*|conversion|warrants?|targets?|valuation|ebitda|"
    r"revenue|sales|cash\s+flow|preferential|subscription|exercise|esop|options?|tender|acquir\w*|acquisition|consideration|"
    r"swap|split|bonus|sub-?division|stake|qip|placement|ofs|floor|sold|sell\w*|bought|buy|purchase[ds]?|repurchas\w*|trade[ds]?|transfer\w*|"
    r"fair\s+value|market\s+cap\w*|valuer)(?![^\W\d_])", re.I)
# a share-price move ("shares closed at ₹250, up ₹5 a share") is not EPS, unless an earnings word is beside the figure
# ("Earnings rose to ₹5 per share")
_MOVE = re.compile(r"(?<![^\W\d_])(?:clos\w*|gain\w*|fell|falls?|rose|rises?|up|down|stock|shares?\s+(?:closed|traded))(?![^\W\d_])", re.I)
_EARN = re.compile(r"(?<![^\W\d_])(?:earn\w*|profits?|loss(?:es)?|pat|income)(?![^\W\d_])", re.I)
_CLAUSE = re.compile(r",\s|;\s|\s[—–|]\s|\n")   # the pieces of a line (a comma inside "₹1,200" is no break)
_INVISIBLE = re.compile("[­​-‏⁠﻿]")
_PERIOD = re.compile(r"\b(?:Q[1-4]|H[12]|9M)?\s*FY\s*'?\d{2,4}(?:-\d{2})?\b|\b(?:Q[1-4]|H[12]|9M)\b|\b20\d{2}(?:-\d{2})?\b", re.I)
# the separators a trailing EPS clause may follow: ", " "; " " — " " | "
_SEP = re.compile(r",\s|;\s|\s[—–|]\s")
_LEAD_WORDS = re.compile(r"(?:\s*\b(?:basic|diluted|and|net|adjusted|reported|with|plus|earnings?|profit|loss|income|pat|"
                         r"after|tax|was|were|is|of)\b|\s*[&:])*\s*", re.I)
_DANGLE = re.compile(r"(?:[\s,;:\-—–|(]+|\s+(?:basic|diluted|and|net)$)$", re.I)
# the only words a trailing EPS clause may carry after the EPS words: its figure, its change and its comparison
_CLAUSE_WORDS = frozenset(
    "rs re inr cr crore crores lakh lakhs mn million bn billion bps pp x per share shares a an each of vs versus from to up down "
    "rose fell yoy qoq yr yrs year years ago earlier prior previous last compared with at was were is in the quarter quarters "
    "q fy h m basic diluted and or grew growth growing increase increased decrease decreased decline declined declining "
    "dropped higher lower rise rising falling on by".split())


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE.sub("", text).replace("‐", "-").replace("‑", "-")
    return text.replace("_", " ")


def _find(text: str):
    """The first place a normalised text states EPS (a match), or None."""
    found = [m for m in (_TOKEN.search(text), _WORDING.search(text)) if m]
    pos = 0
    while (m := _FIGURE.search(text, pos)):   # rule B holds unless the clause around the figure names a non-EPS per-share item
        pos = m.start() + 1
        if _CLAUSE.search(m.group()):   # a figure and a per-share phrase in two different clauses are not one statement
            continue
        start = max([0] + [x.end() for x in _CLAUSE.finditer(text) if x.end() <= m.start()])
        end = min([len(text)] + [x.start() for x in _CLAUSE.finditer(text) if x.start() >= m.end()])
        # the non-EPS word must sit beside the figure (up to 6 words before it, 1 after): "Earnings were ₹5 per share
        # and dividend ₹2 per share" states EPS though its clause names a dividend (review of F190)
        before = text[start:m.start()].split()[-6:]
        after = text[m.end():end].split()[:1]
        near = " ".join(before + [m.group()] + after)
        if not (_NOT_EPS.search(near) or (_MOVE.search(near) and not _EARN.search(near))):
            found.append(m)
            break
    return min(found, key=lambda m: (m.start(), -m.end())) if found else None


def mentions_eps(text: str | None) -> bool:
    return bool(text) and _find(normalise(text)) is not None


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
    """The text without a TRAILING EPS clause: after the last ", " / "; " / " — " / " | " (outside brackets) the EPS words
    start and nothing but the clause follows (its figure, a bracketed change, "vs ₹x", "a year ago"); the head has no EPS.
    The separator and dangling "basic" / "diluted" / "and" / "net" go too. None when the EPS is anywhere else: nothing
    after the EPS words may survive, so no figure can be given to the wrong metric. `text` is normalised."""
    if _find(text) is None:
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
    if last is None:
        return None
    tail = text[last.end():]
    m = _find(tail)
    if m is None or depths[last.end() + m.start()] != 0 or not _LEAD_WORDS.fullmatch(tail[:m.start()]):
        return None
    rest = tail[m.end():]
    if _find(rest) is not None or not _balanced(rest):
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
    return prefix if prefix and _balanced(prefix) and _find(prefix) is None else None


def cut_text(text: str | None) -> str | None:
    """The text as the card may show it: unchanged without EPS, its trailing EPS clause cut when that is all there is, and
    None when it states EPS anywhere else (the caller drops the whole item: a wrong line is worse than a missing one)."""
    if not text or not mentions_eps(text):
        return text
    cut = _trailing_cut(normalise(text))
    return cut if cut and not mentions_eps(cut) else None


def _clip(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0].rstrip(" ,;:-")


# the words a headline's leading company run never takes: verbs and the words of the result itself
_NOT_NAME = frozenset(
    "reports reported posts posted announces announced delivers delivered records recorded declares declared clocks clocked "
    "logs logged sees saw swings swung turns turned rises rose falls fell jumps jumped surges surged slips slipped gains "
    "gained drops dropped grows grew up down beats beat misses missed lifts lifted cuts cut hikes hiked narrows narrowed "
    "widens widened reaches reached crosses crossed approves approved earnings profit profits loss losses income eps lps "
    "basic diluted net pat revenue sales results result quarter quarterly annual ebitda margin margins".split())
_PERIOD_TOKEN = re.compile(r"\(?(?:(?:Q[1-4]|H[12]|9M)\s*)?(?:FY\s*'?\d{2,4}(?:-\d{2})?)\)?|\(?(?:Q[1-4]|H[12]|9M)\)?|\(?20\d{2}(?:-\d{2})?\)?", re.I)


def _lead_run(headline: str) -> tuple[str, str]:
    """The headline's leading company and period ("Acme Ltd", "Q1FY27", "(FY26)"): capitalised words, then period tokens, and
    never a verb, a figure or a result word. Returns (company, run as written)."""
    run, company, period = [], [], False
    for tok in headline.split():
        bare = tok.strip(":,;-—–|")
        if bare and _PERIOD_TOKEN.fullmatch(bare):
            period = True
        elif period or not bare or not (bare == "&" or (bare[0].isupper() and not any(c.isdigit() for c in bare)
                                                       and bare.lower().strip("()") not in _NOT_NAME and _find(bare) is None)):
            break
        else:
            company.append(bare)
        run.append(bare)
    return " ".join(company), " ".join(run).strip(" :-\u2013\u2014,;(")


def _headline_without_eps(headline: str, facts: list[str]) -> str:
    """A headline that is about EPS and cannot be cut: its leading company and period ("Acme Q1FY27") when it has them, then
    the first line of what happened that is not EPS (alone when it already starts with the company), or "results"."""
    company, prefix = _lead_run(normalise(headline))
    fact = next((f.strip().rstrip(".") for f in facts if f.strip() and not mentions_eps(f)), "")
    if fact and company and fact.lower().startswith(company.lower()):
        prefix = ""
    line = f"{prefix}: {fact}" if prefix and fact else fact or (f"{prefix}: results" if prefix else "Quarterly results announced")
    return _clip(line, 220) if len(line) >= 8 else "Quarterly results announced"


def drop_eps(out: Pass2Output) -> list[str]:
    """Take EPS out of the card in place. Returns what was dropped, for the log ("<field>: dropped" / "<field>: EPS clause cut", never the text).
    An item whose text states EPS is dropped whole; the one exception is a trailing EPS clause, which is cut."""
    card = out.card
    if card is None:
        return []
    dropped: list[str] = []

    def keep(items, texts, where: str):
        kept = []
        for item in items:
            if mentions_eps(" ".join(t for t in texts(item) if t)):   # one line: "Dividend | ₹2 per share" is a dividend
                dropped.append(f"{where}: dropped")
            else:
                kept.append(item)
        return kept

    def refine(items, where: str):
        """Items with one text: a trailing EPS clause is cut, any other EPS drops the item (its quote is left as it is)."""
        kept = []
        for item in items:
            text = cut_text(item.text)
            if text is None:
                dropped.append(f"{where}: dropped")
                continue
            if text != item.text:
                dropped.append(f"{where}: EPS clause cut")
                item = item.model_copy(update={"text": text})
            kept.append(item)
        return kept

    def refine_strings(items, where: str):
        kept = []
        for t in items:
            text = cut_text(t)
            if text is None:
                dropped.append(f"{where}: dropped")
            else:
                if text != t:
                    dropped.append(f"{where}: EPS clause cut")
                kept.append(text)
        return kept

    card.what_happened = refine(card.what_happened, "what_happened")   # may be empty until the headline is set
    card.why_it_matters = refine(card.why_it_matters, "why_it_matters")
    card.key_numbers = keep(card.key_numbers, lambda k: [k.label, k.value, k.change or ""], "key_numbers")
    card.notable_changes = keep(card.notable_changes, lambda c: [c.metric, c.why, c.change or "", c.previous or "", c.current or ""], "notable_changes")
    card.quantified_impact = keep(card.quantified_impact, lambda q: [q.label, q.interpretation, q.formula], "quantified_impact")
    card.missing_disclosures = refine_strings(card.missing_disclosures, "missing_disclosures")
    track = card.track_next
    for name in ("pending_approvals", "catalysts", "risks"):
        setattr(track, name, refine_strings(getattr(track, name), f"track_next.{name}"))
    track.kpis_to_verify = keep(track.kpis_to_verify, lambda k: [k.kpi, k.metric or "", k.check_in or "", k.target or ""], "kpis_to_verify")
    track.milestones = keep(track.milestones, lambda m: [m.what], "milestones")
    card.call_takeaways = refine(card.call_takeaways, "call_takeaways")
    after = cut_text(card.headline)
    if after is None:
        after = _headline_without_eps(card.headline, [f.text for f in card.what_happened])
    if after != card.headline:
        card.headline = after
        dropped.append("headline: EPS clause cut")
    if not card.what_happened:
        # a card keeps at least one line of what happened: the headline, now without EPS
        card.what_happened = [Fact(text=card.headline)]
        dropped.append("what_happened: rebuilt")
    for field, empty in (("takeaway", ""), ("core_catalyst", None)):   # a line that cannot be cut is left off, never swapped
        before = getattr(card, field)
        if not before:
            continue
        after = cut_text(before)
        if after is None:
            after = empty
        if after != before:
            setattr(card, field, after)
            dropped.append(f"{field}: EPS clause cut" if after else f"{field}: dropped")
    if out.timeline_entry:
        after = cut_text(out.timeline_entry)
        if after is None:
            after = card.headline
        if after != out.timeline_entry:
            out.timeline_entry = after
            dropped.append("timeline_entry: EPS clause cut")
    return dropped
