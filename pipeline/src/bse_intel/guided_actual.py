"""CARD_GUIDED_NOT_ACTUAL (settings.card_guided_not_actual; off by default, then nothing here runs). Blind audit 1 Nov 2026,
BIRLACORPN nse-106838226: a fundraise card said "Net debt was ₹4,000 Cr at the end of FY26" where 4,000 is management's expected
peak net debt for FY27, said on the May call ("FY27 capex guided at ₹900 Cr, with peak net debt expected around ₹4,000 Cr").

How it got there: the call card's reading wrote the guided figure into the balance-sheet snapshot (`dossier_delta.balance_sheet.
net_debt_cr`, no period, doc "call"), memory kept it as a fact, and every later card was shown "balance_sheet: net debt 4000"
and the quarterly call summary printed "Balance sheet: net debt ₹4,000 Cr", both without a word of "expected". No checker compared
a card's "was" figure with what memory only holds as guidance.

Three parts, each behind the switch:

1. ``guided_balance_fields``: at memory write, a balance-sheet figure of a call or deck that the same reading words as guided
   (expect / guide / peak / target / by FY..) is not stored as a balance.
2. ``view_balance`` / ``summary_marker``: a balance-sheet figure memory holds from a call with no period is shown to the AI and on
   the call summary as "stated on a call, period not given; may be guided, not an actual".
3. ``apply_card_json``: a card point that states, without a guided word, a figure that only memory's guidance (or an unperiod-
   ised call balance figure) holds, with no actual of that line in memory and no such figure in its own quote, is dropped (list
   items) or noted (headline, takeaway). Every change is returned as a note."""

from __future__ import annotations

import re

from .settings import card_guided_not_actual

GUIDED = re.compile(r"\b(?:expect\w*|guid\w*|peak\w*|target\w*|aim\w*|plan(?:s|ned|ning)?|project\w*|estimat\w*|anticipat\w*|"
                    r"forecast\w*|will|would|should|likely|by\s+(?:FY|Q[1-4]|March|end of|the end of)\w*)\b", re.I)
_AMOUNT = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)")
_SENTENCE = re.compile(r"(?<=[.;])\s+")
# line words the guided entry and the card sentence must share, and the balance-sheet field a line is
_LINES = (("net debt", r"net[- ]debt"), ("gross debt", r"gross debt|total debt|borrowings"), ("cash", r"cash"),
          ("net worth", r"net worth|shareholders'? (?:funds|equity)"), ("capex", r"capex|capital expenditure"),
          ("revenue", r"revenue|sales"), ("ebitda", r"ebitda"), ("order book", r"order[- ]?book"),
          ("volume", r"volumes?"), ("capacity", r"capacity"))
_FIELD = {"net debt": "net_debt_cr", "gross debt": "gross_debt_cr", "cash": "cash_cr", "net worth": "net_worth_cr"}
_CALL_DOCS = ("call", "slides")
_LISTS = ("what_happened", "why_it_matters", "notable_changes")
_RUPEES = re.compile(r"(?:₹|Rs\.?)\s*(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s*(?:Cr\b|crore)", re.I)


def _rupee_amounts(text: str) -> list[float]:
    """Amounts written as money (₹, Rs, Cr, crore): a percentage, a year or a capacity in tonnes is not one."""
    out = []
    for a, b in _RUPEES.findall(text or ""):
        try:
            out.append(float(((a or b)).replace(",", "")))
        except ValueError:
            pass
    return out


def _amounts(text: str) -> list[float]:
    out = []
    for raw in _AMOUNT.findall(text or ""):
        try:
            out.append(float(raw.replace(",", "")))
        except ValueError:
            pass
    return out


def _lines(text: str) -> set[str]:
    return {name for name, rx in _LINES if re.search(rf"\b(?:{rx})", text or "", re.I)}


def _same(a: float, b: float, tol: float = 0.005) -> bool:
    return a == b or (a != 0 and abs(a - b) <= tol * abs(a))


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE.split(text or "") if s]


def guided_balance_fields(snapshot: dict, doc: str, texts: list[str]) -> list[str]:
    """The fields of a balance-sheet snapshot a call or deck reading states only as guidance: its value is in a sentence of
    ``texts`` (the reading's takeaways and guidance) that names the line and carries a guided word."""
    if not card_guided_not_actual() or doc not in _CALL_DOCS:
        return []
    found = []
    for line, field in _FIELD.items():
        value = snapshot.get(field)
        if not isinstance(value, (int, float)):
            continue
        for sentence in (s for t in texts for s in _sentences(t)):
            if line in _lines(sentence) and _guided_beside(sentence, value):
                found.append(field)
                break
    return found


# the words that make a figure guidance when they sit beside it; a bare will/plan/aim/project does not (a verb elsewhere in the sentence)
_NEAR = re.compile(r"\b(?:expect\w*|guid\w*|peak\w*|target\w*|anticipat\w*|forecast\w*|estimat\w*|by\s+(?:FY|the end of FY)\w*)\b", re.I)
_ACTUAL_BEFORE = re.compile(r"\b(?:as\s+(?:of|at|on)|stood\s+at|was|were|at\s+the\s+end\s+of|closed\s+at|ended\s+at)\b", re.I)
WINDOW = 6   # words either side of the figure


def _guided_beside(sentence: str, value: float) -> bool:
    """A guided word within WINDOW words of an amount equal to ``value``, the amount not dated as an actual ("stood at", "as of")."""
    tokens = sentence.split()
    for i, tok in enumerate(tokens):
        if not any(_same(value, a) for a in _amounts(tok)):
            continue
        if _ACTUAL_BEFORE.search(" ".join(tokens[max(0, i - 4):i + 4])):
            continue
        if _NEAR.search(" ".join(tokens[max(0, i - WINDOW):i + WINDOW + 1])):
            return True
    return False


def unstated_period(snap: dict) -> bool:
    """A balance figure a model read from a call or deck with no period: what it is the balance of is not known."""
    lab = snap.get("lab") or {}
    return not snap.get("period") and lab.get("by") == "ai" and lab.get("doc") in _CALL_DOCS


NOTE = "stated on a call, period not given: may be guided or expected by management, not an actual; never state it as an actual"


def view_balance(snap: dict | None, shown: dict | None) -> dict | None:
    """The balance snapshot the AI is shown (``shown``, built from ``snap``), marked when it is a call's with no period."""
    if shown and snap and card_guided_not_actual() and unstated_period(snap):
        return {**shown, "note": NOTE}
    return shown


def summary_marker(snap: dict) -> str:
    return " (stated on a call, period not given; may be guided, not an actual)" if card_guided_not_actual() and unstated_period(snap) else ""


def guided_label() -> str:
    return "Management guided (expected, not an actual)" if card_guided_not_actual() else "Management said"


def _guided_figures(dossier: dict) -> list[dict]:
    """What memory holds as guidance: {text, value, lines, why}. Guidance entries, call-memory points of type guidance, outlook
    or commitment, guidance call points, watch targets, and balance figures a call gave with no period."""
    out: list[dict] = []

    def add(text, why, values=None):
        text = " ".join(str(text or "").split())
        values = values if values is not None else _amounts(text)
        lines = _lines(text)
        for v in values:
            if lines:
                out.append({"text": text, "value": v, "lines": lines, "why": why})

    for g in dossier.get("guidance") or []:
        add(f"{g.get('statement') or ''} {g.get('metric') or ''} {g.get('target') or ''}", "guidance")
    for p in dossier.get("call_memory") or []:
        if p.get("type") in ("guidance", "outlook", "commitment"):
            vals = [x for x in (p.get("value"), p.get("value_high")) if isinstance(x, (int, float))]
            add(f"{p.get('statement') or ''} {p.get('metric') or ''}", "call memory " + str(p.get("type")), vals or None)
    for p in dossier.get("call_points") or []:
        if str(p.get("category") or "").lower() == "guidance":
            add(p.get("text"), "call guidance point")
    for w in dossier.get("watchlist") or []:
        if w.get("target"):
            add(f"{w.get('text') or ''} {w.get('metric') or ''} {w.get('target')}", "watch target")
    for b in dossier.get("balance_sheet") or []:
        if unstated_period(b):
            for line, field in _FIELD.items():
                if isinstance(b.get(field), (int, float)):
                    out.append({"text": f"{line} {b[field]:g} Cr (call, no period)", "value": float(b[field]), "lines": {line},
                                "why": "call balance figure with no period"})
    return out


def _actual_values(dossier: dict, line: str) -> list[float]:
    """Figures of this line memory holds as actuals: a balance snapshot with a period or from a file, a metric row."""
    vals = []
    field = _FIELD.get(line)
    for b in dossier.get("balance_sheet") or []:
        if field and isinstance(b.get(field), (int, float)) and not unstated_period(b):
            vals.append(float(b[field]))
    word = line.replace(" ", "_")
    for m in dossier.get("financial_metrics") or []:
        if isinstance(m.get("value"), (int, float)) and (m.get("metric") or "").lower().replace(" ", "_").startswith(word):
            vals.append(float(m["value"]))
    if line in ("capex", "order book"):   # what was spent or won is a deal's amount, not only a metric row
        vals += [float(d["amount_cr"]) for d in dossier.get("deals") or [] if isinstance(d.get("amount_cr"), (int, float))
                 and (line == "order book" or str(d.get("kind") or "").upper() == "CAPEX")]
    return vals


def _guided_misread(text: str, quote: str | None, guided: list[dict], dossier: dict) -> str | None:
    """Why this text states a guided figure as an actual, or None."""
    for sentence in _sentences(text):
        if GUIDED.search(sentence):
            continue
        sentence_lines = _lines(sentence)
        for value in _rupee_amounts(sentence):
            if value < 10:   # a small count: not a rupee line
                continue
            hits = [g for g in guided if sentence_lines & g["lines"] and _same(value, g["value"])]
            if not hits:
                continue
            if quote and any(_same(value, a, 0.02) for a in _amounts(quote)):
                continue   # the filing itself prints it
            if any(_same(value, a) for line in sentence_lines & hits[0]["lines"] for a in _actual_values(dossier, line)):
                continue
            return f"{value:g} is only memory's {hits[0]['why']} ({hits[0]['text'][:80]}), not an actual"
    return None


def apply_card_json(card_json: dict, dossier: dict | None) -> list[str]:
    """A stored or new card's points checked against memory's guidance; returns the notes (what was dropped or left)."""
    if not card_guided_not_actual() or not dossier:
        return []
    guided = _guided_figures(dossier)
    if not guided:
        return []
    notes: list[str] = []
    for attr in ("headline", "takeaway"):
        text = card_json.get(attr)
        if isinstance(text, str) and (why := _guided_misread(text, None, guided, dossier)):
            notes.append(f"{attr}: '{text[:80]}' states a guided figure as an actual ({why}); left for review")
    for name in _LISTS:
        items = card_json.get(name)
        if not isinstance(items, list):
            continue
        kept = []
        for item in items:
            text = item.get("text") if isinstance(item, dict) else item if isinstance(item, str) else None
            quote = item.get("quote") if isinstance(item, dict) else None
            why = _guided_misread(text, quote, guided, dossier) if isinstance(text, str) else None
            if why and not quote and not (isinstance(item, dict) and item.get("basis") in ("MEMORY", "BALANCE_SHEET")):
                # a filing point with no quote: the reader cannot tell it from the filing's own figure, so it is noted, not dropped
                notes.append(f"{name}: '{text[:80]}' may state a guided figure as an actual ({why}); left for review")
                why = None
            if why:
                notes.append(f"{name}: dropped '{text[:80]}', it states a guided figure as an actual ({why})")
                continue
            kept.append(item)
        card_json[name] = kept
    return notes
