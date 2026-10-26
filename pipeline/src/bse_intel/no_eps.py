"""No EPS on a card (owner rule 26 Oct 2026: "No EPS numbers on card or on stock pages").

Memory keeps every EPS figure (xbrl reading, the dossier, eps_adjust, the cross-checks); what a reader sees does not
carry it. The model is not given an EPS line (xbrl.table, dossier.metric_lines) and the results table has no EPS row, and
this is the guard behind them: any line, bullet, key number or change of a card that states earnings per share is dropped
before the card is published. A dividend per share is not EPS and stays.
"""

from __future__ import annotations

import re

from .models import Pass2Output

# "EPS", "basic EPS", "diluted EPS", "earnings per share", "earnings a share", "profit per share", "per-share earnings"
EPS_WORDS = re.compile(
    r"\b(?:eps|earnings?\s+(?:per|a|each)\s+(?:equity\s+)?share|(?:net\s+)?(?:profit|income)\s+per\s+(?:equity\s+)?share|"
    r"per[\s-]share\s+(?:earnings|profit|income))\b", re.I)
# a clause of a headline or one line that opens on EPS: "..., EPS ₹5.20 (+12% YoY)" up to the next ; or , or end
_CLAUSE = re.compile(r"\s*[,;]\s*(?:basic\s+|diluted\s+)?(?:eps|earnings\s+per\s+share)\b(?:[^;,.]|,(?=\d)|\.(?=\d))*", re.I)


def mentions_eps(text: str | None) -> bool:
    return bool(text) and EPS_WORDS.search(text) is not None


def _scrub(text: str | None) -> str | None:
    """A sentence with its EPS clause taken out ("revenue ₹10 Cr, EPS ₹2.1" -> "revenue ₹10 Cr"); unchanged when the
    text is about nothing else (the caller then drops the whole item or keeps the field as the card cannot lose it)."""
    if not text or not mentions_eps(text):
        return text
    cleaned = _CLAUSE.sub("", text).strip()
    return cleaned if cleaned and not mentions_eps(cleaned) else text


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
        # a line with an EPS clause beside other figures loses only that clause ("PAT ₹50 Cr, EPS ₹2" keeps the PAT)
        out_items = []
        for item in items:
            text = _scrub(item.text)
            if text != item.text and not mentions_eps(item.quote or ""):
                dropped.append(f"EPS clause: {item.text[:60]}")
                item = item.model_copy(update={"text": text})
            out_items.append(item)
        return out_items

    for field in ("what_happened", "why_it_matters"):
        items = cut(getattr(card, field))
        kept = keep(items, lambda i: [i.text, i.quote or ""], field)
        if not kept and field == "what_happened" and items:
            # a card keeps at least one line of what happened: the first, with its EPS clause cut where it can be
            kept = [items[0].model_copy(update={"text": _scrub(items[0].text) or items[0].text})]
        setattr(card, field, kept)
    card.key_numbers = keep(card.key_numbers, lambda k: [k.label, k.value, k.change or ""], "key_numbers")
    card.notable_changes = keep(card.notable_changes, lambda c: [c.metric, c.why, c.change or ""], "notable_changes")
    card.quantified_impact = keep(card.quantified_impact, lambda q: [q.label, q.interpretation, q.formula], "quantified_impact")
    card.missing_disclosures = [t for t in card.missing_disclosures if not mentions_eps(t)]
    track = card.track_next
    for name in ("pending_approvals", "catalysts", "risks"):
        setattr(track, name, [t for t in getattr(track, name) if not mentions_eps(t)])
    track.kpis_to_verify = keep(track.kpis_to_verify, lambda k: [k.kpi, k.metric or "", k.check_in or ""], "kpis_to_verify")
    track.milestones = keep(track.milestones, lambda m: [m.what], "milestones")
    card.call_takeaways = keep(cut(card.call_takeaways), lambda t: [t.text, t.quote or ""], "call_takeaways")
    for field in ("headline", "takeaway", "core_catalyst"):
        before = getattr(card, field)
        after = _scrub(before)
        if after != before:
            setattr(card, field, after)
            dropped.append(f"{field}: EPS clause")
    after = _scrub(out.timeline_entry)
    if after != out.timeline_entry:
        out.timeline_entry = after or ""
        dropped.append("timeline_entry: EPS clause")
    return dropped
