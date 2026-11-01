"""The business line an operating figure is about (METRIC_BUSINESS_LINE, owner 1 Nov 2026: "fix at root cause, must be
applicable to other companies also").

Memory keyed an operating figure (monthly volumes, a sector KPI) by (metric, period) alone. EICHERMOT files two monthly updates
on the 1st, Royal Enfield motorcycles (~100,000 units) and VECV trucks (~10,000): memory kept RE's April and May under
"volumes", VECV's only in ``sources``, and the VECV card for October showed RE's months as its history. Any company with two
lines reporting one metric (Tata Motors CV/PV/JLR, M&M auto/farm, Bajaj, cement and power groups, a bank beside its
subsidiaries) has the same fault.

The fix has four parts, all behind the switch:
1. ``FinancialMetric.line`` names the business ("Royal Enfield", "VECV"); None is the whole company.
2. ``assign`` sets it: code first (the filing's own headline or subject names exactly one line memory knows: a line already
   stored, a segment, a subsidiary, JV or brand of the identity), the model's own word as the fallback; never a guess.
3. ``dossier.merge`` keys operating rows by (metric, period, line); statement lines never carry a line.
4. Readers take ``view(dossier, line)``: the rows of the filing's own line (a row with no line is the whole company), so one
   line's figure never enters another's series.
``repair`` / ``split_entry`` split what memory already holds (cli ``memory-split-lines``).

A name is a line only when it is learned from repeated reporting (LINE_MIN_FILINGS): at least two different filings of the
company state the same metric's figures with that name as subject. An entity mentioned in a headline (a subsidiary, a JV, a
shareholder, a project, an EV brand) is not a line by that alone: dry run of 1 Nov 2026 over 1,902 companies tagged Hero's
volumes "VIDA", Tata Steel's EBITDA per tonne "Tata Steel Netherlands", IDFC First's bank KPIs "FIH Private Investments Ltd".
A row is split only when its sources come from two or more qualified lines; one reporting line is never tagged.
"""

from __future__ import annotations

import json
import logging
import re

from .settings import metric_business_line

log = logging.getLogger(__name__)

# names that say "the company", never a line
GENERIC = frozenset({"company", "total", "group", "consolidated", "standalone", "overall", "others", "other", "unallocated",
                     "domestic", "india", "exports", "export", "all", "combined", "whole company", "none", "null", "na", "n a"})
MIN_NAME = 4
LINE_MIN_FILINGS = 2   # filings of the same metric that must name a line before it counts as one
# an identity entity that holds or invests in the company, or is named like one, reports nothing of its own
_OWNER_TYPE = re.compile(r"shareholder|promoter|investor|investment|stakeholder|holding", re.I)
_OWNER_NAME = re.compile(r"\b(?:investments?|holdings?|trust|funds?|mauritius|b\.?\s?v\.?|capital partners|nominees?)\b", re.I)


def enabled() -> bool:
    return metric_business_line()


def _key(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def clean(line: str | None) -> str | None:
    """The line as stored: trimmed, one space between words, at most 60 characters; None for no name or a generic one."""
    text = re.sub(r"\s+", " ", str(line or "")).strip(" .,:;-")
    if not text or _key(text) in GENERIC or len(text) > 60:
        return None
    return text


# balance-sheet and capital items are the whole company's, never one line's (memory-split-lines dry run 1 Nov 2026: Eternal's
# FY26 net worth, inventories and trade receivables would have been tagged "District" from the filing's headline)
_BALANCE = re.compile(r"^(?:net_?worth|inventor(?:y|ies)|trade_(?:receivables|payables)|receivables|payables|borrowings|"
                      r"(?:total|net|gross)_debt(?:_cr)?|debt|cash(?:_and_(?:cash_)?equivalents|_balance)?(?:_cr)?|total_(?:assets|liabilities)|"
                      r"fixed_assets|net_block|goodwill|intangibles?|capex|cwip|book_value(?:_per_share)?|working_capital|share_capital|"
                      r"equity|reserves|investments|loans_and_advances|deposits|provisions)$", re.I)   # whole names, not parts: debtor_days,
# asset_turnover, cash_conversion, assets_under_management stay operating (review of 018517a2)


def operating(metric: str | None) -> bool:
    """Whether a figure may carry a line: no statement line (dossier.STATEMENT_FIGURES, whole-company from the exchange file) and
    no balance-sheet or capital item."""
    from .dossier import STATEMENT_FIGURES, _norm

    return bool(metric) and _norm(metric) not in STATEMENT_FIGURES and not _BALANCE.match(str(metric))


def _owner(entity: dict) -> bool:
    """An identity entity that is a shareholder, promoter or investor, or whose name reads like one (never a line by mention)."""
    from .dossier import _bare_name

    return bool(_OWNER_TYPE.search(str(entity.get("type") or "")) or _OWNER_NAME.search(_bare_name(entity.get("name") or "")))


def known_lines(dossier: dict | None, segments: bool = True) -> list[str]:
    """The names memory knows for this company: lines already stored on figures first, then its segments and the
    subsidiaries, JVs and brands its identity names. In order, without repeats. ``segments`` False leaves the segment names out:
    a segment can be the whole business ("Cement" for a cement company), so code never reads a line from it (review of #324)."""
    from .dossier import _bare_name

    d = dossier or {}
    names = []
    for e in d.get("financial_metrics", []):
        if isinstance(e, dict):
            names += [e.get("line"), *[s.get("line") for s in e.get("sources", []) if isinstance(s, dict)]]
    if segments:
        names += [e.get("segment") for e in d.get("segment_mix", []) if isinstance(e, dict)]
    names += [_bare_name(e.get("name") or "") for e in (d.get("identity") or {}).get("entities", [])
              if isinstance(e, dict) and not _owner(e)]
    seen, out = set(), []
    for name in names:
        name = clean(name)
        if name and len(name) >= MIN_NAME and _key(name) not in seen:
            seen.add(_key(name))
            out.append(name)
    return out


def _mentions(text: str, name: str) -> bool:
    words = re.escape(_key(name)).replace(r"\ ", " ").split(" ")
    return re.search(r"(?<![a-z0-9])" + r"[^a-z0-9]+".join(words) + r"(?![a-z0-9])", _key(text)) is not None


def qualified_lines(dossier: dict | None, lines: dict[str, str | None] | None = None, metric: str | None = None) -> list[str]:
    """The names that are genuine reporting lines of this company: used as the subject of one metric's figures by at least
    LINE_MIN_FILINGS different filings. A filing's line is the one stored on its source, else ``lines`` (news id -> line read from
    the filing's own text, the repair's way in). ``metric`` limits the count to that metric (None: any one metric will do).
    A name that only appears in identity entities, headlines or one filing is not here."""
    from .dossier import _norm, _sources

    ids: dict[tuple[str, str], set] = {}
    names: dict[str, str] = {}
    for e in (dossier or {}).get("financial_metrics", []):
        if not isinstance(e, dict) or not operating(e.get("metric")):
            continue
        if metric is not None and _norm(e.get("metric")) != _norm(metric):
            continue
        for s in _sources(e):
            name = clean(s.get("line") or e.get("line") or (lines or {}).get(s.get("news_id")))
            if name and len(name) >= MIN_NAME and s.get("news_id"):
                names.setdefault(_key(name), name)
                ids.setdefault((_norm(e.get("metric")), _key(name)), set()).add(s["news_id"])
    out = []
    for (_, key), got in ids.items():
        if len(got) >= LINE_MIN_FILINGS and names[key] not in out:
            out.append(names[key])
    return out


def detect(text: str | None, dossier: dict | None, metric: str | None = None) -> str | None:
    """The one qualified line the text names, else None (nothing named, or two lines named: then the figures decide for
    themselves). Only lines already learned from repeated reporting (``qualified_lines``) are read from text."""
    if not text:
        return None
    return _named(text, qualified_lines(dossier, metric=metric))


def _named(text: str, names: list[str]) -> str | None:
    found = [n for n in names if _mentions(text, n)]
    # one name inside another ("Royal Enfield" and "Royal Enfield Motorcycles"): the longest is the line
    found = [n for n in found if not any(n != m and _key(n) in _key(m) for m in found)]
    return found[0] if len(found) == 1 else None


def canonical(line: str | None, dossier: dict | None) -> str | None:
    """A model's line in the spelling memory already uses ("Royal Enfield (RE)" -> "Royal Enfield"), else cleaned as given."""
    line = clean(line)
    if not line:
        return None
    for name in known_lines(dossier):
        if _key(name) == _key(line) or _mentions(line, name):
            return name
    return line


def assign(metrics: list, filing, dossier: dict | None) -> int:
    """Set ``line`` on the operating figures of this filing's answer (FinancialMetric objects, in place); returns how many
    carry one. The model's own line first, in memory's spelling; else the headline or subject naming exactly one qualified line
    (one already stored on two or more filings of that metric, never a mere entity or a segment name: review of #324). A figure the exchange file built, or a statement line, never takes one."""
    if not enabled():
        return 0
    text = f"{getattr(filing, 'headline', '')} {getattr(filing, 'subject', '')}"
    n = 0
    for m in metrics:
        if getattr(m, "by", None) in ("file", "calc") or not operating(m.metric):
            m.line = None
            continue
        m.line = canonical(getattr(m, "line", None), dossier) or detect(text, dossier, m.metric)
        n += bool(m.line)
    return n


def of_filing(dossier: dict | None, news_id: str) -> str | None:
    """The line this filing's own operating figures carry: the one line they share, None when they carry none or several."""
    from .dossier import reported_by

    lines = {e.get("line") for e in (dossier or {}).get("financial_metrics", [])
             if isinstance(e, dict) and reported_by(e, news_id) and operating(e.get("metric"))}
    return next(iter(lines)) if len(lines) == 1 else None


def view(dossier: dict | None, line: str | None) -> dict | None:
    """The dossier a reader of one line's series should see: only the figures of that line (``line`` None: the whole company's,
    those with no line). Unchanged with the switch off or when no figure carries a line."""
    if not dossier or not enabled():
        return dossier
    if not any(isinstance(e, dict) and e.get("line") for e in dossier.get("financial_metrics", [])):
        return dossier
    return {**dossier, "financial_metrics": [e for e in dossier.get("financial_metrics", [])
                                             if not isinstance(e, dict) or not operating(e.get("metric"))
                                             or e.get("line") == line]}   # statement rows are the whole company's: always kept


def split_entry(entry: dict, lines: dict[str, str | None]) -> list[dict]:
    """One stored figure split by line, from the line each source filing belongs to (``lines``: news id -> line, None when it
    cannot be read). With two or more readable lines among the sources the figure is split, one entry a line. Otherwise
    the entry comes back as it was, never tagged with a single line (a single-source or single-line row). Sources whose line cannot
    be read stay as the whole company's figure, never guessed into a line."""
    from .dossier import _metric_entry, _sources

    groups: dict[str | None, list[dict]] = {}
    for s in _sources(entry):
        groups.setdefault(s.get("line") or lines.get(s.get("news_id")), []).append(s)
    named = [k for k in groups if k]
    if len(named) < 2:
        return [entry]
    out = [_metric_entry(entry["metric"], entry["period"], [{**s, "line": line} for s in group])
           for line, group in groups.items() if line]
    if groups.get(None):
        out.append(_metric_entry(entry["metric"], entry["period"], groups[None]))
    return out


def card_lines(rows: list[dict], dossier: dict | None) -> dict[str, str | None]:
    """news id -> the candidate line each stored card (``export_cards`` rows: news_id, headline, card_json) names among the
    names memory knows (shareholders and investors left out); None when the text names none or several. A candidate is only a
    reading of the text: ``repair`` keeps it when two filings of the same metric share it (``qualified_lines``)."""
    names = known_lines(dossier, segments=False)
    out: dict[str, str | None] = {}
    for row in rows:
        text, body = row.get("headline") or "", ""
        try:
            card = json.loads(row.get("card_json") or "{}")
            text += " " + str(card.get("headline") or "")
            # the headline may name only the company ("Eicher Motors May 2026 motorcycle sales"): its takeaway and points then
            # decide ("Royal Enfield's domestic volumes grew ..."), still only when they name exactly one line
            body = " ".join([str(card.get("takeaway") or "")] + [str(p.get("text") if isinstance(p, dict) else p)
                                                                  for p in card.get("what_happened") or []])
        except ValueError:
            pass
        out[row["news_id"]] = _named(text, names) or (_named(body, names) if body else None)
    return out


def repair(dossier: dict, lines: dict[str, str | None]) -> list[dict]:
    """Split in place the operating figures of ``dossier`` whose sources come from filings of two or more qualified lines
    (``qualified_lines``: a name that two or more filings of the same metric use as subject; ``lines`` holds what each filing's
    own text names); returns one row per figure changed. A row with one source or one line is never tagged, so a company with
    one reporting line is left as it is. Only operating metrics: statement lines are the whole company's and never touched."""
    todo = [e for e in dossier.get("financial_metrics", []) if isinstance(e, dict) and not e.get("line") and operating(e.get("metric"))]
    qualified: dict[str, set] = {}
    rows, out = [], []
    for entry in dossier.get("financial_metrics", []):
        if entry not in todo:
            rows.append(entry)
            continue
        if entry["metric"] not in qualified:
            qualified[entry["metric"]] = {_key(n) for n in qualified_lines(dossier, lines, entry["metric"])}
        usable = {nid: line for nid, line in lines.items() if line and _key(line) in qualified[entry["metric"]]}
        parts = split_entry(entry, usable)
        if parts != [entry]:
            out.append({"metric": entry["metric"], "period": entry["period"], "was": entry.get("value"),
                        "into": [{"line": p.get("line"), "value": p.get("value"), "from": p.get("source_news_id")} for p in parts]})
        rows.extend(parts)
    dossier["financial_metrics"] = rows
    return out
