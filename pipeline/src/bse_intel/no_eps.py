"""No EPS on a card (owner rule 26 Oct 2026: "No EPS numbers on card or on stock pages").

Memory keeps every EPS figure (xbrl reading, the dossier, eps_adjust, the cross-checks); what a reader sees does not
carry it. The model is not given an EPS line (xbrl.table, dossier.metric_lines) and the results table has no EPS row, and
this is the guard behind them: any line, bullet, key number or change of a card that states earnings per share is dropped
before the card is published. A dividend per share is not EPS and stays.
"""

from __future__ import annotations

import re

from .models import Fact, Pass2Output

# "EPS", "E.P.S.", "basic EPS", "diluted EPS", "earnings per share", "earnings/share", "earnings a share", "earnings of ₹5 a share",
# "diluted earnings per ordinary share", "profit per share", "PAT per share", "per-share earnings". A dividend, book value,
# NAV or price per share is not EPS and is not matched.
_SHARE = r"(?:(?:equity|ordinary|diluted|basic)\s+)*share"
EPS_WORDS = re.compile(
    r"\b(?:eps\b|e\.p\.s\b\.?|"
    r"(?:diluted\s+|basic\s+)?earnings?(?:\s+(?:per|a|each)\s+|\s*/\s*)" + _SHARE + r"|"
    r"earnings?\s+of\s+(?:rs\.?\s*|inr\s*|₹\s*)?[\d.,]+\s*(?:/-)?\s*(?:per|a|each)\s+" + _SHARE + r"|"
    r"(?:net\s+)?(?:profit|income|pat)\s+per\s+" + _SHARE + r"|"
    r"per[\s-]share\s+(?:earnings|profit|income))(?!\w)", re.I)
# a metric a sentence goes on to state: the EPS clause stops before it
_METRIC = re.compile(r"\b(?:revenue|sales|pat|pbt|profit|ebitda|ebit|margins?|income|turnover|dividend|order|net\s+worth|debt)\b", re.I)
_AND = re.compile(r"\s+and\s+", re.I)
_LEAD = re.compile(r"\s*[,;]\s*(?:(?:basic|diluted)\s+)?(?=\S)", re.I)


def mentions_eps(text: str | None) -> bool:
    return bool(text) and EPS_WORDS.search(text) is not None


def _stop(text: str, j: int) -> bool:
    """True when the text at j ends a clause: ; or , (not inside a number), a full stop (not a decimal point)."""
    c = text[j]
    nxt = text[j + 1] if j + 1 < len(text) else ""
    prev = text[j - 1] if j else ""
    if c == ";":
        return True
    if c == "," and not (nxt.isdigit() and prev.isdigit()):
        return True
    return c == "." and not nxt.isdigit()


def _clause_end(text: str, j: int, with_metric_stop: bool = True) -> int:
    """Where the clause that runs on from j ends: at ; , . outside brackets, at " and ", or before another metric word."""
    depth = 0
    while j < len(text):
        c = text[j]
        if c in "([":
            depth += 1
        elif c in ")]":
            depth = max(0, depth - 1)
        elif depth == 0:
            if _stop(text, j) or _AND.match(text, j):
                return j
            if with_metric_stop and c.isspace() and _METRIC.match(text, j + 1):
                return j
        j += 1
    return j


def _cut_clauses(text: str) -> str:
    """Every ", EPS ₹2.10 (+1.5% YoY)" clause taken out of a sentence, and the bare change that follows it (", up 12%");
    a clause stops before " and ..." or another metric ("Revenue ₹10 Cr, EPS ₹2.10 and PAT ₹5 Cr" keeps the PAT)."""
    pos = 0
    for _ in range(8):
        for m in _LEAD.finditer(text, pos):
            eps = EPS_WORDS.match(text, m.end())
            if not eps:
                continue
            end = _clause_end(text, eps.end())
            while end < len(text) and text[end] == ",":   # a bare change after it: ", up 12%", ", down 3% QoQ"
                nxt = _clause_end(text, end + 1)
                piece = text[end + 1:nxt]
                if not piece.strip() or _METRIC.search(piece) or mentions_eps(piece):
                    break
                end = nxt
            text = text[:m.start()] + text[end:]
            pos = m.start()
            break
        else:
            break
    return text.strip()


def _scrub(text: str | None) -> str | None:
    """A sentence with its EPS clause taken out ("revenue ₹10 Cr, EPS ₹2.1" -> "revenue ₹10 Cr"); unchanged when the
    text is about nothing else (the caller then drops the whole item or keeps the field as the card cannot lose it)."""
    if not text or not mentions_eps(text):
        return text
    cleaned = _cut_clauses(text)
    return cleaned if cleaned and not mentions_eps(cleaned) else text


def _clip(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0].rstrip(" ,;:-")


def _headline_without_eps(headline: str, facts: list[str]) -> str:
    """A headline that is still about EPS after the clause cut: its company and period ("Acme Q1FY27") before the EPS
    words, then the first line of what happened that is not EPS, or "results"."""
    m = EPS_WORDS.search(headline)
    prefix = headline[:m.start()].strip(" :-\u2013\u2014,;(") if m else ""
    fact = next((f.strip().rstrip(".") for f in facts if f.strip()), "")
    if fact and prefix and fact.lower().startswith(prefix.lower()):
        prefix = ""
    line = f"{prefix}: {fact}" if prefix and fact else fact or (f"{prefix}: results" if prefix else "Quarterly results announced")
    return _clip(line, 220) if len(line) >= 8 else "Quarterly results announced"


def drop_eps(out: Pass2Output) -> list[str]:
    """Take EPS out of the card in place. Returns what was dropped, for the log ("dropped" strings, never the figure's value)."""
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

    def cut(items):
        # a line with an EPS clause beside other figures loses only that clause ("PAT ₹50 Cr, EPS ₹2" keeps the PAT);
        # the line's own text decides, its quote stays as the filing printed it
        out_items = []
        for item in items:
            text = _scrub(item.text)
            if text != item.text:
                dropped.append(f"EPS clause: {item.text[:60]}")
                item = item.model_copy(update={"text": text})
            out_items.append(item)
        return out_items

    card.what_happened = keep(cut(card.what_happened), lambda i: [i.text], "what_happened")   # may be empty until the headline is set
    card.why_it_matters = keep(cut(card.why_it_matters), lambda i: [i.text], "why_it_matters")
    card.key_numbers = keep(card.key_numbers, lambda k: [k.label, k.value, k.change or ""], "key_numbers")
    card.notable_changes = keep(card.notable_changes, lambda c: [c.metric, c.why, c.change or ""], "notable_changes")
    card.quantified_impact = keep(card.quantified_impact, lambda q: [q.label, q.interpretation, q.formula], "quantified_impact")
    card.missing_disclosures = [t for t in card.missing_disclosures if not mentions_eps(t)]
    track = card.track_next
    for name in ("pending_approvals", "catalysts", "risks"):
        setattr(track, name, [t for t in getattr(track, name) if not mentions_eps(t)])
    track.kpis_to_verify = keep(track.kpis_to_verify, lambda k: [k.kpi, k.metric or "", k.check_in or ""], "kpis_to_verify")
    track.milestones = keep(track.milestones, lambda m: [m.what], "milestones")
    card.call_takeaways = keep(cut(card.call_takeaways), lambda t: [t.text], "call_takeaways")
    after = _scrub(card.headline)
    if mentions_eps(after):
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
        after = _scrub(before)
        if mentions_eps(after):
            after = _clip(insight, 240) or empty
        if after != before:
            setattr(card, field, after)
            dropped.append(f"{field}: EPS clause")
    after = _scrub(out.timeline_entry)
    if mentions_eps(after):
        after = card.headline
    if after != out.timeline_entry:
        out.timeline_entry = after or ""
        dropped.append("timeline_entry: EPS clause")
    return dropped
