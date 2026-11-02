"""CARD_RESULTS_FACE_REBUILD (off; STATUS 17c, 1 Nov 2026): a stored results card made before CARD_EBITDA_PROFIT_V2 went on
(30 Oct 2026, ~00:40 IST) gets the face today's code writes: the headline, the key numbers and the takeaway, from memory's file
figures for its quarter, through `results_card.build`. No AI and no PDF.

Release check 41318733817 (adjusted_profit, 2,260 PDF results cards): 757 cards carry two profit key lines ("Net profit" and
"Net profit to shareholders"), the last nse-106834799; none of the 151 after it does. On most both figures are right, but the
face states two profits; on some the old code's lines disagree with each other (RELIANCE Q4FY26: the key "to shareholders"
₹20,589 Cr, the headline's owners' ₹16,971 Cr). The live V2 path writes one profit line.

Only what the old code wrote is replaced (lead's review of #358): the headline or takeaway only when it is exactly what the
old path writes from the same figures, and never by a line with fewer figures; of the key numbers only the old profit lines
(and an EPS key, never on a card: owner rule 26 Oct 2026), by V2's one profit line in place. Every other key, the model's
facts and points stay. A card of unknown basis, or memory without the quarter's year-ago profit and top line, is left."""

from __future__ import annotations

import copy
import re

from .settings import card_results_face_rebuild

V2_SINCE = "2026-10-29T19:10:00+00:00"   # CARD_EBITDA_PROFIT_V2 on, 30 Oct 2026 ~00:40 IST
_PROFIT_KEY = re.compile(r"^Net (?:profit|loss)\b", re.I)
_PROFIT_QUOTE = re.compile(r"^-\s+pat(?:_owners)?\s")   # results_card._line of a profit metric
_EPS_KEY = re.compile(r"\bEPS\b|earnings per share", re.I)
_FIGURE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _old_profit_key(key: dict) -> bool:
    """A profit key the old code wrote: "Net profit" or "Net profit to shareholders" (a loss too) quoting a file line."""
    return bool(_PROFIT_KEY.match(str(key.get("label") or "")) and _PROFIT_QUOTE.match(str(key.get("quote") or "")))


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


def _file_source(src: dict) -> bool:
    """A source the exchange's file gave (labelled file or calc, or under a synthetic ``xbrl:`` id)."""
    lab = src.get("lab")
    return (isinstance(lab, dict) and lab.get("by") in ("file", "calc")) or str(src.get("news_id") or "").startswith("xbrl:")


def _from_file(entry: dict) -> bool:
    """A memory row the exchange's file gave (labelled file or calc, or under a synthetic ``xbrl:`` id)."""
    from .watch_code import _sources_of

    sources = _sources_of(entry)
    labs = [entry.get("lab"), *(s.get("lab") for s in sources)]
    return any(isinstance(lab, dict) and lab.get("by") in ("file", "calc") for lab in labs) \
        or any(str(s.get("news_id") or "").startswith("xbrl:") for s in sources) \
        or str(entry.get("source_news_id") or "").startswith("xbrl:")


def tagged_from_memory(dossier: dict, period: str, basis: str, any_source: bool = False):
    """An XbrlResult of memory's exchange-file figures (file or calc, never a model's; ``any_source``: every figure, as the old code
    read memory) for ``period``, its year-ago, previous quarter and the year-to-date periods beside them, on ``basis``; each with
    its YoY and QoQ worked out from memory, none across a change of sign (a loss against a year-ago profit is no -2600%)."""
    from .dossier import _NO_SCALE_UNITS, inr_crore
    from .models import FinancialMetric
    from .periods import prior_quarter_period, prior_year_period
    from .watch_code import _entry_basis, _sources_of, _src_basis
    from .xbrl import PER_SHARE, PERCENT, XbrlResult, _change

    year_ago, prev_q = prior_year_period(period), prior_quarter_period(period)
    wanted = {p for p in (period, year_ago, prev_q, prior_year_period(prev_q or "")) if p}
    to_date = {"Q2": "H1", "Q3": "9M"}.get(period[:2])
    if to_date:
        wanted |= {f"{to_date}{period[2:]}", f"{to_date}{(year_ago or '')[2:]}"}
    rows = [m for m in dossier.get("financial_metrics") or []
            if isinstance(m, dict) and m.get("period") in wanted and isinstance(m.get("value"), (int, float))
            and (any_source or _from_file(m))]
    # the card's basis only: a row labelled another basis never; an unlabelled row only for a period memory labels nowhere
    # (lead's review of #358: a card of unknown basis took STANDALONE rows, ₹263.24 Cr made ₹131.62 Cr)
    labelled = {m["period"] for m in rows if _entry_basis(m)}
    values: dict[tuple[str, str], tuple[float, str | None]] = {}
    for m in rows:
        b = _entry_basis(m)
        if not ((b.upper() == basis.upper()) if b else (m["period"] not in labelled)):
            continue
        if any_source:
            value, unit = m["value"], m.get("unit")
        else:
            # the file's own figure, never the merged one (lead's review of #370: a file source beside an unknown source's 1,238.67
            # put 1,238.67 on the face)
            src = next((s for s in _sources_of(m) if _file_source(s) and isinstance(s.get("value"), (int, float))
                        and (_src_basis(s, m) or basis).upper() == basis.upper()), None)
            if src is None:
                continue
            value, unit = src["value"], src.get("unit") or m.get("unit")
        if m["metric"] in PER_SHARE or m["metric"] in PERCENT or str(unit or "").upper() in _NO_SCALE_UNITS:
            values[(m["metric"], m["period"])] = (float(value), unit)
            continue
        # in crore, whatever rupee unit memory stored it in (lead's review of #370: a lakh row reached the face as crore); a dollar or
        # share count is no rupee figure for the face
        crore = inr_crore(value, unit)
        if crore is not None:
            values[(m["metric"], m["period"])] = (crore, "INR_CR")
    metrics = []
    for (metric, p), (value, unit) in values.items():
        yoy = qoq = None
        if metric not in PERCENT:
            before = values.get((metric, prior_year_period(p) or ""))
            # across a sign change no percentage: results_card writes "against a profit of ₹Y Cr a year earlier" (blind read of
            # 41345924894, c15 nse-106631998: "-2600.1% YoY" on a loss against a year-ago profit)
            yoy = _change(value, before[0]) if before and (value < 0) == (before[0] < 0) else None
            if p.startswith("Q"):
                last = values.get((metric, prior_quarter_period(p) or ""))
                qoq = _change(value, last[0]) if last and (value < 0) == (last[0] < 0) else None
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
    # the face's own period, as code wrote it on the old profit keys or headline: an H1 card's face beside a Q2 table (blind read of
    # 41345924894, COALINDIA nse-106834917: Q2's profit put on a card whose face is H1FY27)
    period = _face_period(card_json) or period
    from .dossier import dossier_as_of
    from .periods import prior_year_period

    basis = card_json.get("basis")
    if not basis:
        return []   # a card of unknown basis: no basis to read memory on (never a mix of the two)
    current = dossier_as_of(dossier, filed_at) if _utc(filed_at) else dossier
    tagged = tagged_from_memory(current, period, basis)
    have = {(m.metric, m.period) for m in tagged.metrics}
    year_ago = prior_year_period(period)
    if not any((p, period) in have and (p, year_ago) in have for p in ("pat", "pat_owners")) \
            or not any((t, period) in have and (t, year_ago) in have for t in ("revenue", "interest_earned", "total_income")):
        return []   # without the year-ago figures the face would carry fewer figures than the stored one (lead's review of #358)
    from pydantic import ValidationError

    try:
        # the old face from every figure memory holds, as the old code read it (ADANIPORTS nse-106605518: its "net profit to
        # shareholders ₹1,238.67 Cr" is an owners' figure no file source backs, a share of other comprehensive income); the new
        # one from the exchange's file only
        v1 = _build(card_json, tagged_from_memory(current, period, basis, any_source=True), company_name, text, v2=False)
        v2 = _build(card_json, tagged, company_name, text, v2=True)
    except ValidationError:
        return []   # a stored card today's model no longer reads is left as it is
    if v1 is None or v2 is None:
        return []
    notes: list[str] = []
    for attr in ("headline", "takeaway"):
        # only text the old code wrote: the stored line must be exactly what v1 makes from these figures; a model's line, or one
        # an older code wrote from other figures, stays (lead's review of #358). Never a line carrying fewer figures
        old, new = str(card_json.get(attr) or ""), str(v2.get(attr) or "")
        if old and new and old != new and old == (v1.get(attr) or "") and len(_FIGURE.findall(new)) >= len(_FIGURE.findall(old)):
            card_json[attr] = new
            notes.append(f"{attr}: {old} -> {new}")
    keys = card_json.get("key_numbers") or []
    profit = next((k for k in v2.get("key_numbers") or [] if _PROFIT_QUOTE.match(str(k.get("quote") or ""))), None)
    old_keys = [k for k in keys if isinstance(k, dict) and (_old_profit_key(k) or _EPS_KEY.search(str(k.get("label") or "")))]
    if profit is not None and old_keys and (len(old_keys) > 1 or _EPS_KEY.search(str(old_keys[0].get("label") or ""))
                                            or (old_keys[0].get("label"), old_keys[0].get("value")) != (profit.get("label"), profit.get("value"))):
        # the old profit lines (and an EPS key: never on a card, owner rule 26 Oct 2026) become V2's one profit line, at the first
        # one's place; every other key stays where it is, nothing is added
        first = keys.index(old_keys[0])
        kept_profit = any(isinstance(k, dict) and k not in old_keys and _PROFIT_QUOTE.match(str(k.get("quote") or "")) for k in keys)
        card_json["key_numbers"] = [k for k in keys[:first] if k not in old_keys] + ([] if kept_profit else [profit]) + \
            [k for k in keys[first:] if k not in old_keys]   # a profit key in the company's own words stays the one
        notes.append("key_numbers: " + "; ".join(f"{k.get('label')} {k.get('value')}" for k in old_keys)
                     + f" -> {profit.get('label')} {profit.get('value')}")
    return notes


_FACE_KEY = re.compile(r"^-?\s*pat(?:_owners)?\s+((?:Q[1-4]|H[12]|9M)?FY\d{2}):")
_FACE_HEADLINE = re.compile(r"^.+? ((?:Q[1-4]|H[12]|9M)?FY\d{2}): ")


def _face_period(card_json: dict) -> str | None:
    """The period the old face states: an old profit key's file line ("- pat H1FY27: ..."), else a code headline's ("<name>
    H1FY27: ...")."""
    for k in card_json.get("key_numbers") or []:
        if isinstance(k, dict) and _PROFIT_KEY.match(str(k.get("label") or "")) and (m := _FACE_KEY.match(str(k.get("quote") or ""))):
            return m.group(1)
    m = _FACE_HEADLINE.match(str(card_json.get("headline") or ""))
    return m.group(1) if m else None


def _build(card_json: dict, tagged, company_name: str | None, text: str, v2: bool) -> dict | None:
    """The card as results_card.build writes it from ``tagged`` (V2 or the old path), on a copy; None when it cannot."""
    from . import results_card
    from .models import Card, Pass2Output

    out = Pass2Output.model_validate({"is_material": True, "event_type": "RESULTS",
                                      "timeline_entry": card_json.get("timeline_entry") or "",
                                      "card": {k: copy.deepcopy(card_json[k]) for k in Card.model_fields if k in card_json}})
    if not results_card.build(out, tagged, company_name, text=text or "", v2=v2):
        return None
    return out.card.model_dump(mode="json")
