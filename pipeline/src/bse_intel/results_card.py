"""A results card built by code from the filing's XBRL; the model adds a line or two (owner's PLAN 18 part 4: "code
builds the numbers (table, changes, margins); the AI adds 1-2 lines").

Results cards were the weakest card in rounds 3 and 4 (blind agents: 3 of 7 and 7 of 14 published WRONG) against about
one in eight for every other kind: a year-on-year change taken from the previous quarter, a margin "expanded" when it
fell, a stock build read as a drawdown, profit growth put on lower tax when tax rose. Every one is a figure, a change or
a direction the XBRL file states exactly. So when a results card has its file, code writes its headline, the facts (each
quoting its line of the machine-tagged table that leads the filing's text), the key numbers with their changes and the
timeline line; the model's takeaway and at most two points of why it matters are kept (and checked by the direction
guard); its notable changes, core catalyst and computed impacts are left out.
"""

from __future__ import annotations

import re

from .models import Fact, Insight, KeyNumber
from .periods import prior_year_period, quarter_from_index, quarter_index

MAX_WHY = 2
MEMORY_POINTS = 2   # code's own points from memory, ahead of the model's
MIN_QUARTERS = 4    # a rank or a streak needs this many earlier quarters in memory
_LEGAL = re.compile(r"\s+(?:limited|ltd\.?|corporation of india limited)$", re.I)


def _short_name(name: str | None) -> str:
    name = " ".join((name or "").split())
    return _LEGAL.sub("", name).strip() or name


def _cr(value: float) -> str:
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"₹{text} Cr"


def _pct(value: float | None) -> str | None:
    return None if value is None else f"{value:+.1f}%"


def _changes(m) -> str:
    parts = [f"{p} YoY" for p in (_pct(m.yoy_pct),) if p] + [f"{p} QoQ" for p in (_pct(m.qoq_pct),) if p]
    return ", ".join(parts)


def _line(m) -> str:
    """The table line for this metric exactly as `XbrlResult.table()` writes it (the quote a fact carries)."""
    unit = " ₹/share" if m.unit == "INR" else " %" if m.unit == "PCT" else " Cr"
    change = "".join(f", {label} {v:+.1f}%" for label, v in (("YoY", m.yoy_pct), ("QoQ", m.qoq_pct)) if v is not None)
    return f"- {m.metric} {m.period}: {m.value:g}{unit}{change}"


def _year_ago(tagged, m):
    """The same line a year before ("Q1FY26" for "Q1FY27", "FY26" for "FY27"), when the file carries it."""
    match = re.fullmatch(r"(Q[1-4])?FY(\d{2})", m.period or "")
    if not match:
        return None
    label = f"{match.group(1) or ''}FY{int(match.group(2)) - 1:02d}"
    return next((x for x in tagged.metrics if x.metric == m.metric and x.period == label and x.value is not None), None)


def _profit_words(tagged, m) -> tuple[str, str, str]:
    """(label, amount, year-ago note) for the profit line: a loss is written as a loss, never "net profit ₹-12 Cr",
    and a change against a year-ago loss, which no percentage can carry, says what it was."""
    label, amount = ("Net loss", _cr(-m.value)) if m.value < 0 else ("Net profit", _cr(m.value))
    note = ""
    before = _year_ago(tagged, m) if m.yoy_pct is None else None
    if before is not None and (before.value < 0 or m.value < 0):
        was = f"a loss of {_cr(-before.value)}" if before.value < 0 else f"a profit of {_cr(before.value)}"
        note = f"against {was} a year earlier"
    return label, amount, note


_LABELS = (("revenue", "Revenue from operations"), ("interest_earned", "Interest earned"),
           ("pre_provision_operating_profit", "Operating profit before provisions"), ("ebitda", "EBITDA"),
           ("provisions", "Provisions"), ("pat", "Net profit"), ("eps", "EPS"))


_VIEW_LINE = re.compile(r"^\s*(Q[1-4]FY\d{2})\s*:\s*(-?\d[\d,]*(?:\.\d+)?)\s*([A-Z_]*)")


def history_from_view(view: dict | None) -> list[dict]:
    """Memory's quarterly figures as the card's writer was shown them ("Q1FY26: 12.3 INR_CR"): only the figures memory
    keeps after its period checks. The raw store also holds figures left out for not reconciling with their own
    periods, and a rank read from it called Jubilant's quarter "the highest of 6" where memory showed two (round 6)."""
    out = []
    for metric, lines in ((view or {}).get("metrics") or {}).items():
        for line in lines if isinstance(lines, list) else []:
            m = _VIEW_LINE.match(str(line))
            if m:
                out.append({"metric": metric, "period": m.group(1), "value": float(m.group(2).replace(",", "")),
                            "unit": m.group(3) or "INR_CR"})
    return out


def _quarters(history, metric: str) -> dict[int, float]:
    """Memory's quarterly values of one metric, by quarter index."""
    out = {}
    for h in history or ():
        index = quarter_index(str(h.get("period") or ""))
        if h.get("metric") == metric and index is not None and h.get("value") is not None:
            out[index] = float(h["value"])
    return out


def agrees_with_memory(tagged, history) -> bool:
    """Memory and the file agree on the file's own comparative figures: then memory's quarters are the same series. A
    standalone file against consolidated memory (Max Financial's ₹17 Cr holding-company quarter beside ₹39,473 Cr of
    group revenue, round 5) or a restated year gives no point at all."""
    mem = {(h.get("metric"), h.get("period")): h.get("value") for h in history or () if h.get("value") is not None}
    shared = [(m.value, float(mem[(m.metric, m.period)])) for m in tagged.metrics
              if m.period != tagged.period and m.value and (m.metric, m.period) in mem]
    return bool(shared) and all(abs(a - b) <= 0.02 * abs(a) + 0.01 for a, b in shared)


def _value(x: float) -> str:
    return f"{x:,.2f}".rstrip("0").rstrip(".")


def memory_points(tagged, history) -> list[Insight]:
    """What the quarter means against the company's own history, computed in code from memory (owner, 2026-10-19:
    "quarterly results with contextual memory"). The model wrote these from memory and got the periods wrong: Dabur's
    "EBITDA 734.13 against 756.15" was two other quarters, Protean's year-ago margin was Q3's (round 5). Each point uses
    only figures memory holds under the period it names and the file's own figure for this quarter:
    - the highest or lowest quarter memory holds, for revenue and net profit;
    - a run of year-on-year growth or decline, or its end;
    - the EBITDA margin above or below each of the previous four quarters."""
    if tagged is None or not tagged.period or not history:
        return []
    now_index = quarter_index(tagged.period)
    if now_index is None or not agrees_with_memory(tagged, history):
        return []
    now = {m.metric: m for m in tagged.metrics if m.period == tagged.period and m.value is not None}
    points: list[tuple[int, str]] = []    # (priority, text): lower first
    for metric, word in (("pat", "net profit"), ("revenue", "revenue"), ("interest_earned", "interest earned")):
        m = now.get(metric)
        if m is None:
            continue
        past = {i: v for i, v in _quarters(history, metric).items() if i < now_index}
        # the file's own earlier quarters win over memory's (Orient Bell, round 6: memory lacked Q4FY26, the filing showed
        # it higher, and the card called Q1FY27 the highest quarter)
        past.update({i: x.value for x in tagged.metrics if x.metric == metric and x.value is not None
                     for i in [quarter_index(x.period or "")] if i is not None and i < now_index})
        run = []
        for i in range(now_index - 1, now_index - 13, -1):
            if i not in past:
                break
            run.append(past[i])
        if len(run) >= MIN_QUARTERS:
            first = quarter_from_index(now_index - len(run))
            if m.value > max(run):
                points.append((2, f"{tagged.period} {word} of ₹{_value(m.value)} Cr is the highest of the {len(run) + 1} "
                                  f"quarters in a row memory holds since {first}."))
            elif m.value < min(run):
                points.append((2, f"{tagged.period} {word} of ₹{_value(m.value)} Cr is the lowest of the {len(run) + 1} "
                                  f"quarters in a row memory holds since {first}."))
        # year-on-year signs, newest first: this quarter's from the file, earlier ones from memory's own quarters
        series = {**past, now_index: m.value}
        signs = []
        for i in range(now_index, now_index - 12, -1):
            if i not in series or i - 4 not in series or series[i - 4] <= 0 or series[i] < 0:
                break
            signs.append(series[i] > series[i - 4])
        if len(signs) >= 2:
            run = 1
            while run < len(signs) - 1 and signs[run + 1] == signs[1]:
                run += 1
            if signs[0] != signs[1] and run >= 3:
                points.append((1, f"{tagged.period} is the first year-on-year {'rise' if signs[0] else 'fall'} in {word} "
                                  f"after {run} quarters of {'growth' if signs[1] else 'decline'} in memory."))
            elif signs[0] == signs[1]:
                streak = 1
                while streak < len(signs) and signs[streak] == signs[0]:
                    streak += 1
                if streak >= 4:
                    points.append((3, f"{word.capitalize()} has {'grown' if signs[0] else 'fallen'} year on year for "
                                      f"{streak} quarters running, {tagged.period} included."))
    margin = now.get("ebitda_margin")
    if margin is not None:
        past = _quarters(history, "ebitda_margin")
        last4 = [(i, past[i]) for i in range(now_index - 1, now_index - 5, -1) if i in past]
        if len(last4) == 4:
            listed = ", ".join(f"{quarter_from_index(i)} {v:.1f}%" for i, v in last4)
            if all(margin.value > v + 0.5 for _, v in last4):
                points.append((2, f"EBITDA margin of {margin.value:.1f}% is above each of the previous four quarters ({listed})."))
            elif all(margin.value < v - 0.5 for _, v in last4):
                points.append((2, f"EBITDA margin of {margin.value:.1f}% is below each of the previous four quarters ({listed})."))
    points.sort(key=lambda p: p[0])
    return [Insight(text=text, basis="MEMORY") for _, text in points[:MEMORY_POINTS]]


# Each line's pull on net profit when it moves (EBITDA here leaves out other income, as the file tags it)
_BRIDGE = (("ebitda", +1, "EBITDA"), ("other_income", +1, "other income"), ("depreciation", -1, "depreciation"),
           ("finance_cost", -1, "finance cost"), ("exceptional_items", +1, "exceptional items"), ("tax_expense", -1, "tax"))


def profit_driver(tagged) -> str | None:
    """What moved net profit year on year, read from the file: the line whose change pulled profit furthest in the
    direction it went. The model gave causes the statement contradicts - Texmaco's profit up 71% on "cost control" when
    a tax credit did it and EBITDA fell 20%, Ramco's fall on "lower other income" when other income rose (round 5)."""
    if tagged is None or not tagged.period:
        return None
    ago = prior_year_period(tagged.period)
    val = {(m.metric, m.period): m.value for m in tagged.metrics if m.value is not None}
    pat, pat0 = val.get(("pat", tagged.period)), val.get(("pat", ago))
    if pat is None or pat0 is None or abs(pat - pat0) < max(1.0, 0.05 * abs(pat0)):
        return None
    if ("ebitda", tagged.period) not in val or ("ebitda", ago) not in val:
        return None   # a bank or an insurer: provisions and claims move its profit, and the bridge has neither
    pulls = []
    for metric, sign, word in _BRIDGE:
        now, then = val.get((metric, tagged.period)), val.get((metric, ago))
        if now is not None and then is not None:
            pulls.append((sign * (now - then), metric, word, now, then))
    # The bridge's lines must account for the profit change: a discontinued business's gain (Siemens' demerger, round 4)
    # or an associate's share moves profit outside them, and then no line here is "the largest move"
    full = {p[1] for p in pulls} >= {"ebitda", "other_income", "depreciation", "finance_cost", "tax_expense"}
    if full and abs(sum(p[0] for p in pulls) - (pat - pat0)) > 0.25 * abs(pat - pat0) + 1.0:
        return None
    up = pat > pat0
    moving = [p for p in pulls if (p[0] > 0) == up and abs(p[0]) >= 0.25 * abs(pat - pat0)]
    if not moving:
        return None
    pull, metric, word, now, then = max(moving, key=lambda p: abs(p[0]))
    if metric == "tax_expense":
        def tax(x):
            return f"a tax credit of {_cr(-x)}" if x < 0 else f"tax of {_cr(x)}"
        driver = f"{tax(now)} against {tax(then)} a year earlier"
    elif metric == "exceptional_items":
        driver = f"exceptional items of {_cr(now)} against {_cr(then)} a year earlier"
    else:
        driver = f"{word} of {_cr(now)} against {_cr(then)} a year earlier"
    ebitda, ebitda0 = val.get(("ebitda", tagged.period)), val.get(("ebitda", ago))
    contrast = ""
    if metric != "ebitda" and ebitda is not None and ebitda0 and ebitda0 > 0 and (ebitda > ebitda0) != up \
            and abs(ebitda - ebitda0) >= 0.05 * ebitda0:
        contrast = f", while EBITDA {'fell' if up else 'rose'} to {_cr(ebitda)} from {_cr(ebitda0)}"
    loss = lambda x: f"a net loss of {_cr(-x)}" if x < 0 else f"net profit of {_cr(x)}"  # noqa: E731
    return (f"{tagged.period} {loss(pat)} against {loss(pat0)} a year earlier; the largest move was "
            f"{driver}{contrast}.")


def build(out, tagged, company_name: str | None, history=None) -> list[str]:
    """Put the file's figures on a results card. Returns what was replaced (empty when the file cannot carry it)."""
    card = getattr(out, "card", None)
    if card is None or tagged is None or getattr(tagged, "kind", None) != "RESULTS" or not tagged.period:
        return []
    now = {m.metric: m for m in tagged.metrics if m.period == tagged.period and m.value is not None}
    top = now.get("revenue") or now.get("interest_earned") or now.get("total_income")
    profit = now.get("pat")
    if top is None or profit is None:
        return []
    name = _short_name(company_name)
    basis = (tagged.basis or "").lower()
    period = tagged.period
    top_word = "revenue" if top.metric == "revenue" else "interest earned" if top.metric == "interest_earned" else "total income"

    def phrase(m, word: str) -> str:
        if m.metric == "pat":
            label, amount, note = _profit_words(tagged, m)
            change = f" ({_pct(m.yoy_pct)} YoY)" if m.yoy_pct is not None else f" ({note})" if note else ""
            return f"{label.lower()} {amount}{change}"
        change = f" ({_pct(m.yoy_pct)} YoY)" if m.yoy_pct is not None else ""
        return f"{word} {_cr(m.value)}{change}"

    headline = f"{name} {period}: {phrase(top, top_word)}, {phrase(profit, 'net profit')}"
    if len(headline) > 110:
        headline = f"{name} {period}: {phrase(profit, 'net profit')}"
    facts, keys = [], []
    for metric, label in _LABELS:
        m = now.get(metric)
        if m is None or (metric == "provisions" and "interest_earned" not in now):
            continue
        value = f"₹{m.value:,.2f} a share" if metric == "eps" else _cr(m.value)
        changes = _changes(m)
        if metric == "pat":
            label, value, note = _profit_words(tagged, m)
            changes = ", ".join(x for x in (changes, note) if x)
        text = f"{label} {period}: {value}" + (f" ({changes})" if changes else "")
        if metric == "ebitda" and now.get("ebitda_margin") is not None:
            text += f"; margin {now['ebitda_margin'].value:.1f}%"
        facts.append(Fact(text=text + ".", quote=_line(m)))
        keys.append(KeyNumber(label=label, value=value, change=(f"{_pct(m.yoy_pct)} YoY" if m.yoy_pct is not None else None),
                              quote=_line(m)))
    margin = now.get("ebitda_margin")
    if margin is not None:
        keys.append(KeyNumber(label="EBITDA margin", value=f"{margin.value:.1f}%", change=None, quote=_line(margin)))
    replaced = ["headline", "what_happened", "key_numbers", "timeline"]
    card.headline = headline
    card.what_happened = facts[:4] or card.what_happened
    card.key_numbers = keys[:6]
    if basis in ("consolidated", "standalone"):
        card.basis = basis.upper()
    if card.notable_changes:
        replaced.append(f"notable changes ({len(card.notable_changes)}) left out")
    card.notable_changes = []
    if card.core_catalyst:
        replaced.append("core catalyst left out")
    card.core_catalyst = None
    if card.quantified_impact:
        replaced.append(f"computed impacts ({len(card.quantified_impact)}) left out")
    card.quantified_impact = []
    driver = profit_driver(tagged)
    if driver:
        card.takeaway = driver   # the file says what moved profit; the model's own cause is left out
        replaced.append("takeaway from the file's profit bridge")
    context = memory_points(tagged, history)
    # the model keeps two points, or one beside two of code's: three at most
    card.why_it_matters = context + card.why_it_matters[:min(MAX_WHY, MAX_WHY + 1 - len(context))]
    if context:
        replaced.append(f"{len(context)} point(s) from memory by code")
    out.timeline_entry = f"{period} results ({basis or 'basis not stated'}): {phrase(top, top_word)}, {phrase(profit, 'net profit')}."
    return [f"results card from the XBRL file: {', '.join(replaced)}"]
