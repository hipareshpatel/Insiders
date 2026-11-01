"""CARD_RESULTS_FACE_REBUILD (off; STATUS 17c, 1 Nov 2026): a stored results card made before CARD_EBITDA_PROFIT_V2 went on
(30 Oct 2026, ~00:40 IST) gets the face today's code writes: the headline, the key numbers and the takeaway, from memory's file
figures for its quarter, through `results_card.build`. No AI and no PDF.

Release check 41318733817 (adjusted_profit, 2,260 PDF results cards): 757 cards carry two profit key lines ("Net profit" and
"Net profit to shareholders"), the last nse-106834799; none of the 151 after it does. On most both figures are right, but the
face states two profits; on some the old code's lines disagree with each other (RELIANCE Q4FY26: the key "to shareholders"
₹20,589 Cr, the headline's owners' ₹16,971 Cr). The live V2 path writes one profit line.

Only what code wrote is replaced: a headline in code's "<name> <period>: ..." form, a takeaway code wrote (the profit bridge or
the period's figures), key numbers whose quote is a file line. What the model wrote (its facts, points, other keys) is kept."""

from __future__ import annotations

import copy
import re

from .settings import card_results_face_rebuild

V2_SINCE = "2026-10-29T19:10:00+00:00"   # CARD_EBITDA_PROFIT_V2 on, 30 Oct 2026 ~00:40 IST
_CODE_HEADLINE = re.compile(r"^.+? (?:Q[1-4]|H[12]|9M)?FY\d{2}: ")
_CODE_KEY = re.compile(r"^-\s+[a-z_]+\s+\S+:\s")   # a file line, as results_card._line writes it
_CODE_TAKEAWAY = re.compile(r"\bthe largest move was\b|^(?:Q[1-4]|H[12]|9M)?FY\d{2}:\s", re.I)
_PROFIT_KEY = re.compile(r"^Net (?:profit|loss)\b", re.I)


def _utc(when: str | None) -> str:
    """An ISO time as UTC text, comparable by string ("2026-10-30T00:40:00+05:30" -> "2026-10-29T19:10:00+00:00")."""
    from datetime import datetime, timezone

    try:
        t = datetime.fromisoformat(str(when or "").replace("Z", "+00:00"))
    except ValueError:
        return ""
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


def two_profit_keys(card_json: dict) -> bool:
    """The card's key numbers state two profit lines (the whole and the shareholders')."""
    labels = [str(k.get("label") or "") for k in card_json.get("key_numbers") or [] if isinstance(k, dict)]
    profits = [x for x in labels if _PROFIT_KEY.match(x)]
    return any("to shareholders" in x for x in profits) and any("to shareholders" not in x for x in profits)


def predates_v2(card_json: dict, filed_at: str | None) -> bool:
    """A face V2 never wrote: two profit key lines, or a card of a filing before V2 went on."""
    when = _utc(filed_at)
    return two_profit_keys(card_json) or bool(when and when < V2_SINCE)


def _from_file(entry: dict) -> bool:
    """A memory row the exchange's file gave (labelled file or calc, or under a synthetic ``xbrl:`` id)."""
    from .watch_code import _sources_of

    sources = _sources_of(entry)
    labs = [entry.get("lab"), *(s.get("lab") for s in sources)]
    return any(isinstance(lab, dict) and lab.get("by") in ("file", "calc") for lab in labs) \
        or any(str(s.get("news_id") or "").startswith("xbrl:") for s in sources) \
        or str(entry.get("source_news_id") or "").startswith("xbrl:")


def tagged_from_memory(dossier: dict, period: str, basis: str | None):
    """An XbrlResult of memory's exchange-file figures (file or calc, never a model's) for ``period``, its year-ago, previous
    quarter and the year-to-date periods beside them, on ``basis``; each with its YoY and QoQ worked out from memory."""
    from .models import FinancialMetric
    from .periods import prior_quarter_period, prior_year_period
    from .watch_code import _entry_basis
    from .xbrl import PER_SHARE, PERCENT, XbrlResult, _change

    year_ago, prev_q = prior_year_period(period), prior_quarter_period(period)
    wanted = {p for p in (period, year_ago, prev_q, prior_year_period(prev_q or "")) if p}
    to_date = {"Q2": "H1", "Q3": "9M"}.get(period[:2])
    if to_date:
        wanted |= {f"{to_date}{period[2:]}", f"{to_date}{(year_ago or '')[2:]}"}
    values: dict[tuple[str, str], tuple[float, str | None]] = {}
    for m in dossier.get("financial_metrics") or []:
        if not isinstance(m, dict) or m.get("period") not in wanted or not isinstance(m.get("value"), (int, float)):
            continue
        if not _from_file(m):
            continue   # a model's reading of a PDF never makes the face
        b = _entry_basis(m)
        if basis and b and b.upper() != basis.upper():
            continue
        values[(m["metric"], m["period"])] = (float(m["value"]), m.get("unit"))
    metrics = []
    for (metric, p), (value, unit) in values.items():
        yoy = qoq = None
        if metric not in PERCENT:
            before = values.get((metric, prior_year_period(p) or ""))
            yoy = _change(value, before[0] if before else None)
            if p.startswith("Q"):
                last = values.get((metric, prior_quarter_period(p) or ""))
                qoq = _change(value, last[0] if last else None)
        metrics.append(FinancialMetric(metric=metric, period=p, value=round(value, 2), yoy_pct=yoy, qoq_pct=qoq,
                                       unit="INR" if metric in PER_SHARE else "PCT" if metric in PERCENT else unit or "INR_CR",
                                       by="file"))
    kind = (dossier.get("industry") or "").lower()
    template = "NBFC" if any(w in kind for w in ("> banks", "> finance", "insurance")) else ""
    return XbrlResult(kind="RESULTS", basis=basis, period=period, metrics=metrics, template=template)


def apply_card_json(card_json: dict, dossier: dict | None, filed_at: str | None, company_name: str | None,
                    text: str = "") -> list[str]:
    """Rebuild a pre-V2 results card's code-written headline, key numbers and takeaway in place (a dict); the notes of what was
    replaced. Nothing when the switch is off, the card is no results card, its face is V2's, or memory lacks its quarter."""
    if not card_results_face_rebuild() or (card_json.get("event_type") or "RESULTS") != "RESULTS":
        return []
    results = card_json.get("results")
    period = results.get("period") if isinstance(results, dict) else None
    if not period or not dossier or not predates_v2(card_json, filed_at):
        return []
    from . import results_card
    from .dossier import dossier_as_of
    from .models import Card, Pass2Output

    current = dossier_as_of(dossier, filed_at) if filed_at else dossier
    tagged = tagged_from_memory(current, period, card_json.get("basis"))
    now = {m.metric for m in tagged.metrics if m.period == period}
    if not now & {"pat", "pat_owners"}:
        return []
    from pydantic import ValidationError

    try:
        out = Pass2Output.model_validate({"is_material": True, "event_type": "RESULTS",
                                          "timeline_entry": card_json.get("timeline_entry") or "",
                                          "card": {k: copy.deepcopy(card_json[k]) for k in Card.model_fields if k in card_json}})
    except ValidationError:
        return []   # a stored card today's model no longer reads is left as it is
    if not results_card.build(out, tagged, company_name, text=text or "", v2=True):
        return []
    made = out.card.model_dump(mode="json")
    notes: list[str] = []
    headline = str(card_json.get("headline") or "")
    if _CODE_HEADLINE.match(headline) and made.get("headline") and made["headline"] != headline:
        card_json["headline"] = made["headline"]
        notes.append(f"headline: {headline} -> {made['headline']}")
    takeaway = str(card_json.get("takeaway") or "")
    if _CODE_TAKEAWAY.search(takeaway) and made.get("takeaway") and made["takeaway"] != takeaway:
        card_json["takeaway"] = made["takeaway"]
        notes.append(f"takeaway: {takeaway} -> {made['takeaway']}")
    keys = [k for k in card_json.get("key_numbers") or [] if isinstance(k, dict)]
    code_keys = [k for k in keys if _CODE_KEY.match(str(k.get("quote") or ""))]
    if code_keys:
        model_keys = [k for k in keys if k not in code_keys]
        new_keys = [k for k in made.get("key_numbers") or [] if _CODE_KEY.match(str(k.get("quote") or ""))]
        if new_keys and [(k.get("label"), k.get("value")) for k in new_keys] != [(k.get("label"), k.get("value")) for k in code_keys]:
            card_json["key_numbers"] = (new_keys + model_keys)[:max(6, len(new_keys))]
            notes.append("key_numbers: " + "; ".join(f"{k.get('label')} {k.get('value')}" for k in code_keys)
                         + " -> " + "; ".join(f"{k.get('label')} {k.get('value')}" for k in new_keys))
    return notes
