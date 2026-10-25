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

from . import gate, printed_figures
from .models import Fact, Insight, KeyNumber
from .periods import prior_year_period, quarter_from_index, quarter_index
from .settings import card_ebitda_profit_v2

MAX_WHY = 2
# a rich results card (RESULTS_RICH): the computed lines and the model's own quoted facts beside the file's four lines,
# and up to four of the model's points beside code's from memory
MAX_COMPUTED = 5
MAX_OWN_FACTS = 4
MAX_WHY_RICH = 4
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
    if m.metric == "pat_owners":
        label += " to shareholders"
    note = ""
    before = _year_ago(tagged, m) if m.yoy_pct is None else None
    if before is not None and (before.value < 0 or m.value < 0):
        was = f"a loss of {_cr(-before.value)}" if before.value < 0 else f"a profit of {_cr(before.value)}"
        note = f"against {was} a year earlier"
    return label, amount, note


_LABELS = (("revenue", "Revenue from operations"), ("interest_earned", "Interest earned"),
           ("pre_provision_operating_profit", "Operating profit before provisions"), ("ebitda", "EBITDA"),
           ("provisions", "Provisions"), ("pat", "Net profit"), ("pat_owners", "Net profit to shareholders"), ("eps", "EPS"))


_VIEW_LINE = re.compile(r"^\s*(Q[1-4]FY\d{2})\s*:\s*(-?\d[\d,]*(?:\.\d+)?)\s*([A-Z_]*)")


def asset_quality(now: dict) -> str | None:
    """A bank's bad loans as the file tags them: "net NPA 0.64%, gross 1.58%"."""
    net, gross = now.get("nnpa_pct"), now.get("gnpa_pct")
    parts = [f"net NPA {net.value:.2f}%" if net else None, f"gross {gross.value:.2f}%" if gross and net else
             f"gross NPA {gross.value:.2f}%" if gross else None]
    return ", ".join(p for p in parts if p) or None


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
        if all(i in series and series[i] > 0 for i in (now_index - 1, now_index - 4, now_index - 5)):
            g_now = (series[now_index] / series[now_index - 4] - 1) * 100
            g_last = (series[now_index - 1] / series[now_index - 5] - 1) * 100
            if g_now > 0 and g_last > 0 and abs(g_now - g_last) >= 5:
                points.append((3, f"{word.capitalize()} growth {'picked up' if g_now > g_last else 'slowed'} to "
                                  f"{g_now:+.0f}% YoY from {g_last:+.0f}% in {quarter_from_index(now_index - 1)}."))
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


def profit_driver(tagged, profit: str = "pat", label: str | None = None, v2: bool = False) -> str | None:
    """What moved net profit year on year, read from the file: the line whose change pulled profit furthest in the
    direction it went. The model gave causes the statement contradicts - Texmaco's profit up 71% on "cost control" when
    a tax credit did it and EBITDA fell 20%, Ramco's fall on "lower other income" when other income rose (round 5)."""
    if tagged is None or not tagged.period:
        return None
    ago = prior_year_period(tagged.period)
    val = {(m.metric, m.period): m.value for m in tagged.metrics if m.value is not None}
    pat, pat0 = val.get((profit, tagged.period)), val.get((profit, ago))
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
    if v2 and metric == "ebitda":
        word = "operating EBITDA (calculated)"
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
        contrast = f", while {'calculated ' if v2 else ''}EBITDA {'fell' if up else 'rose'} to {_cr(ebitda)} from {_cr(ebitda0)}"
    name = (label or ("net profit to shareholders" if profit == "pat_owners" else "net profit")) if v2 else "net profit"
    loss = lambda x: f"a net loss of {_cr(-x)}" if x < 0 else f"{name} of {_cr(x)}"  # noqa: E731
    return (f"{tagged.period} {loss(pat)} against {loss(pat0)} a year earlier; the largest move was "
            f"{driver}{contrast}.")


_RESTATED = re.compile(r"(?:comparative|previous|prior|corresponding)[^.]{0,160}?\b(?:have\s+been|has\s+been|are|were|is|was)\s+"
                       r"restated\b|\brestated\s+to\s+(?:give|reflect|include)", re.I | re.S)


def unconfirmed_changes(tagged, text: str) -> list[str]:
    """Drop a change whose comparative the filing does not print. The year-ago and previous-quarter figures come from
    those quarters' own files, which keep the figures first reported; a statement that restates them (Ambuja after the
    Orient Cement purchase-price allocation, Titagarh) prints the restated ones, and the change against the old figure
    was wrong (round 6, 2026-10-19). Figures too small to tell apart in the text are left as they are."""
    if not text or tagged is None:
        return []
    # a statement that says its comparatives were restated prints the first-reported figures too, in its reconciliation
    # (Pitti's amalgamation, Q2FY27: "Profit after tax 3,558.25 | 451.17 | 4,009.42", as reported, the merged companies,
    # restated), so the old comparative is "printed" and a change against it passed: the card read PAT -4.7% YoY for
    # -15.5% (daily audit, 23 Oct 2026). Memory keeps the first-reported figures, so no change against it stands.
    restated = bool(_RESTATED.search(text))
    numbers = sorted({float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*\.?\d*", text)
                      if n.replace(",", "").replace(".", "").isdigit()})
    dropped = []
    for m in tagged.metrics:
        if m.period != tagged.period or m.value is None or m.unit == "PCT" or (m.unit == "INR" and not restated):
            continue   # a per-share figure cannot be looked for in the text, but against a restated year it goes too
        for attr, label in (("yoy_pct", "YoY"), ("qoq_pct", "QoQ")):
            pct = getattr(m, attr)
            if pct is None or pct <= -99.95:
                continue
            if restated or _printed(m.value, pct, numbers) is False:
                setattr(m, attr, None)
                dropped.append(f"{m.metric} {label}")
    return dropped


def _printed(value: float, pct: float, numbers: list[float]) -> bool | None:
    """Whether the text has a figure, in crore, lakh, million, thousand or rupees, that gives this change. The change is
    stored to one decimal, so the comparative is a range (₹6,296.67 Cr at +12.3% is anything from ₹5,604.5 to ₹5,609.5
    Cr), not the one figure worked back from it. None when the comparative is too small to tell from other numbers."""
    ends = [abs(value) / (1 + (pct + d) / 100) for d in (0.05, -0.05)]
    checked = False
    for scale in (1, 100, 10, 10_000, 1e7):  # crore, lakh, million, thousand, rupees
        low, high = min(ends) * scale - 0.5, max(ends) * scale + 0.5
        if high < 10:
            continue
        checked = True
        if any(low <= n <= high for n in numbers):
            return True
    return False if checked else None


def _net_of_excise(tagged):
    """Revenue less the excise it carries, with its year-on-year change when the file has both years' figures. Excise
    is the government's, and a rise in it reads as growth: ITC's Q1FY27 revenue was "+27.6%" gross and about -11% net
    (round 6, 2026-10-19). None when the file tags no excise."""
    from .models import FinancialMetric
    from .periods import prior_year_period

    val = {(m.metric, m.period): m.value for m in tagged.metrics if m.value is not None}
    now_rev, now_exc = val.get(("revenue", tagged.period)), val.get(("excise_duty", tagged.period))
    if now_rev is None or not now_exc:
        return None
    ago = prior_year_period(tagged.period)
    then_rev, then_exc = val.get(("revenue", ago)), val.get(("excise_duty", ago))
    net = round(now_rev - now_exc, 2)
    yoy = None
    if then_rev is not None and then_exc is not None and then_rev - then_exc > 0:
        yoy = round((net / (then_rev - then_exc) - 1) * 100, 1)
    return FinancialMetric(metric="revenue_net_excise", period=tagged.period, value=net, yoy_pct=yoy, by="calc",
                           derived_from=[f"revenue:{tagged.period}", f"excise_duty:{tagged.period}"])


_AMOUNT = re.compile(r"\d[\d,]*\.\d+|\d{1,3}(?:,\d{2,3})+|\d{3,}")


def _amounts(text: str) -> set[str]:
    return {m.replace(",", "") for m in _AMOUNT.findall(text or "")}


def _model_facts(card, tagged, facts, shown: str = "") -> list[Fact]:
    """The model's own quoted facts that say what the file's figures do not: a driver, cash, capital, capex or capacity
    in the filing's words. A fact quoting the XBRL table or the computed block repeats code's lines and is left out, and
    so is one whose every amount is already in code's lines: a later step re-points a quote at the nearest table line,
    so the quote alone let "EBITDA ₹111.18 Cr, up 87.8%" and "borrowings ₹938.96 Cr" repeat code's (sampling, 24 Oct)."""
    table = tagged.table()
    block = "\n".join(f.text for f in facts or [] if f.text)
    known = _amounts(f"{table}\n{block}\n{shown}")
    out = []
    for f in card.what_happened:
        if not f.quote or gate.quote_found(f.quote, table) or (block and gate.quote_found(f.quote, block)):
            continue
        said = _amounts(f.text)
        if said and said <= known:
            continue
        out.append(f)
    return out


def _printed_ebitda_lines(printed, period: str) -> tuple[Fact, KeyNumber]:
    """The company's own EBITDA as a fact and a key number, quoting the line it is printed on. Its year-ago figure and
    change only when the filing prints them."""
    yoy, before = printed.yoy_pct(), printed.prev_year_cr
    note = (f" ({yoy:+.1f}% YoY, against {_cr(before)} a year earlier)" if yoy is not None
            else f" (against {_cr(before)} a year earlier)" if before is not None else "")
    fact = Fact(text=f"{printed.name} {period} (Filing): {_cr(printed.value_cr)}{note}.", quote=printed.quote)
    key = KeyNumber(label=f"{printed.name} (Filing)", value=_cr(printed.value_cr),
                    change=f"{yoy:+.1f}% YoY" if yoy is not None else None, quote=printed.quote)
    return fact, key


def _theirs(label: str, m) -> str:
    """The company's own name for its profit line, for a loss too ("PAT loss")."""
    return f"{label} loss" if m.value < 0 else label


def _plain(x: float) -> set[str]:
    return {f"{abs(x):.2f}".rstrip("0").rstrip("."), f"{abs(x):,.2f}".rstrip("0").rstrip(".").replace(",", "")}


def _drop_second_profit(items: list, kept: float, other: float | None) -> list:
    """One profit figure on a card (TODO 15): a line that states the other profit line's amount, and not the chosen
    one's, is left out (the cash-conversion line "178% of net profit ₹74 Cr" on the total where the card headlines the
    shareholders' profit)."""
    if other is None or abs(other - kept) <= 0.005 * abs(kept) + 0.011:
        return items
    return [t for t in items
            if not (re.search(r"profit|\bPAT\b", getattr(t, "text", "") or "", re.I) and _amounts(t.text) & _plain(other)
                    and not _amounts(t.text) & _plain(kept))]


def build(out, tagged, company_name: str | None, history=None, text: str = "", facts=None, rich: bool = False,
          v2: bool | None = None) -> list[str]:
    """Put the file's figures on a results card. Returns what was replaced (empty when the file cannot carry it).

    `rich` (RESULTS_RICH, owner 24 Oct 2026: "so much of information which is missing"): the figures computed in code
    (`facts`, facts.py) join the file's lines, and the model keeps its quoted facts, its points from memory, its
    notable changes and its core catalyst. Every one still goes through the quote, grounding and computed checks after
    this, as any other card's do; only the headline, the key numbers and the takeaway stay code's alone."""
    card = getattr(out, "card", None)
    if card is None or tagged is None or getattr(tagged, "kind", None) != "RESULTS" or not tagged.period:
        return []
    if v2 is None:
        v2 = card_ebitda_profit_v2()
    unconfirmed = unconfirmed_changes(tagged, text)
    now = {m.metric: m for m in tagged.metrics if m.period == tagged.period and m.value is not None}
    if now.get("pat_owners") is not None and now["pat_owners"].value == 0 and (now.get("pat") or now["pat_owners"]).value:
        # a zero the file carries for the owners' share beside a real profit is a filler, not a figure: Ahluwalia's
        # Q4FY25 card read "net profit to shareholders ₹0 Cr" beside PAT ₹83.33 Cr (live review 2, 2026-10-20)
        del now["pat_owners"]
    top = now.get("revenue") or now.get("interest_earned") or now.get("total_income")
    net = _net_of_excise(tagged)
    if net is not None and top is not None and top.metric == "revenue":
        top = net
    profit = now.get("pat")
    owners = now.get("pat_owners")
    if owners is not None and profit is not None and abs(owners.value - profit.value) > 0.005 * abs(profit.value) + 0.01:
        profit = owners   # minority interests take a part: the shareholders' profit is the company's (Bajaj Finserv)
    profit_label = None   # the company's own name for its headline profit (v2)
    printed = None        # the company's own EBITDA (v2)
    other_profit = None   # the profit line not chosen, whose figure no other line may state (v2)
    if v2:
        # ONE profit line (TODO 15): the one the company headlines in its release, else the shareholders' profit
        picked = {k: now[k].value for k in ("pat", "pat_owners") if k in now}
        metric, profit_label = printed_figures.choose_profit(picked, text)
        if metric is not None:
            profit = now[metric]
            other_profit = next((v for k, v in picked.items() if k != metric), None)
        # the company's printed EBITDA beside ours (TODO 11, 14); a lender has no EBITDA of ours, so none here either
        if "ebitda" in now and "interest_earned" not in now:
            printed = printed_figures.printed_ebitda(text, tagged.period, now["ebitda"].value)
    if top is None or profit is None:
        return []
    profit_word = (profit_label if v2 and profit_label else
                   "net profit to shareholders" if profit.metric == "pat_owners" else "net profit")
    name = _short_name(company_name)
    basis = (tagged.basis or "").lower()
    period = tagged.period
    top_word = "revenue net of excise" if top.metric == "revenue_net_excise" else "revenue" if top.metric == "revenue" else "interest earned" if top.metric == "interest_earned" else "total income"

    def phrase(m, word: str) -> str:
        if m.metric in ("pat", "pat_owners"):
            label, amount, note = _profit_words(tagged, m)
            if v2 and profit_label:
                label, amount = _theirs(profit_label, m), _cr(abs(m.value))
            change = f" ({_pct(m.yoy_pct)} YoY)" if m.yoy_pct is not None else f" ({note})" if note else ""
            return f"{label if v2 and profit_label else label.lower()} {amount}{change}"
        change = f" ({_pct(m.yoy_pct)} YoY)" if m.yoy_pct is not None else ""
        return f"{word} {_cr(m.value)}{change}"

    headline = f"{name} {period}: {phrase(top, top_word)}, {phrase(profit, profit_word)}"
    quality = asset_quality(now) if top.metric == "interest_earned" else None
    if quality:
        # a bank is read on its profit and its bad loans, not on interest earned (owner, 2026-10-19: Punjab & Sind
        # Bank's card led with "interest earned ₹3,213.37 Cr" and gave its net NPA only in the model's words)
        headline = f"{name} {period}: {phrase(profit, profit_word)}; {quality}"
    if len(headline) > 110:
        headline = f"{name} {period}: {phrase(profit, profit_word)}"
    facts_found = [f for f in facts or [] if f.text]
    lines, keys = [], []
    for metric, label in _LABELS:
        m = now.get(metric)
        if m is None or (metric == "provisions" and "interest_earned" not in now):
            continue
        if v2 and metric in ("pat", "pat_owners") and m is not profit:
            continue   # one profit line
        value = f"₹{m.value:,.2f} a share" if metric == "eps" else _cr(m.value)
        changes = _changes(m)
        if metric == "pat" or (v2 and metric == "pat_owners"):
            label, value, note = _profit_words(tagged, m)
            if v2 and profit_label:
                label = _theirs(profit_label, m)
            changes = ", ".join(x for x in (changes, note) if x)
        if v2 and metric == "ebitda":
            if printed is not None:
                fact_p, key_p = _printed_ebitda_lines(printed, period)
                lines.append(fact_p)
                keys.append(key_p)
            label = "Operating EBITDA (calculated)"
        text = f"{label} {period}: {value}" + (f" ({changes})" if changes else "")
        if metric == "ebitda" and now.get("ebitda_margin") is not None:
            text += f"; margin {now['ebitda_margin'].value:.1f}%"
        if v2 and metric == "ebitda":
            other = now.get("other_income")
            text += f"; leaves out other income {_cr(other.value)}" if other is not None else "; leaves out other income"
        lines.append(Fact(text=text + ".", quote=_line(m)))
        keys.append(KeyNumber(label=label, value=value, change=(f"{_pct(m.yoy_pct)} YoY" if m.yoy_pct is not None else None),
                              quote=_line(m)))
    margin = now.get("ebitda_margin")
    if margin is not None:
        keys.append(KeyNumber(label="Operating EBITDA margin (calculated)" if v2 else "EBITDA margin",
                              value=f"{margin.value:.1f}%", change=None, quote=_line(margin)))
    replaced = ["headline", "what_happened", "key_numbers", "timeline"]
    card.headline = headline
    computed_lines = [Fact(text=f.text + ".", quote=f.text) for f in facts_found if not f.memory_ref]
    # set against memory (guidance, a deal's history): "Our reading", citing the memory it used
    against_memory = [Insight(text=f.text + ".", basis="MEMORY", memory_refs=[f.memory_ref])
                      for f in facts_found if f.memory_ref]
    own_facts = _model_facts(card, tagged, facts_found, " ".join(f.text for f in lines)) if rich else []
    if v2 and other_profit is not None:
        computed_lines = _drop_second_profit(computed_lines, profit.value, other_profit)
        own_facts = _drop_second_profit(own_facts, profit.value, other_profit)
    card.what_happened = (lines[:5 if v2 else 4] + computed_lines[:MAX_COMPUTED] + own_facts[:MAX_OWN_FACTS]) or card.what_happened
    if own_facts:
        replaced.append(f"{len(own_facts[:MAX_OWN_FACTS])} quoted fact(s) of the model kept")
    card.key_numbers = keys[:6]
    if basis in ("consolidated", "standalone"):
        card.basis = basis.upper()
    if rich:
        return _rich_rest(out, card, tagged, history, period, basis, phrase, top, top_word, profit, profit_word,
                          replaced, unconfirmed, against_memory, v2, profit_label)
    if card.notable_changes:
        replaced.append(f"notable changes ({len(card.notable_changes)}) left out")
    card.notable_changes = []
    if card.core_catalyst:
        replaced.append("core catalyst left out")
    card.core_catalyst = None
    if card.quantified_impact:
        replaced.append(f"computed impacts ({len(card.quantified_impact)}) left out")
    card.quantified_impact = []
    driver = profit_driver(tagged, profit.metric, profit_label.lower() if profit_label else None, True) if v2 \
        else profit_driver(tagged)
    if driver:
        card.takeaway = driver   # the file says what moved profit; the model's own cause is left out
        replaced.append("takeaway from the file's profit bridge")
    else:
        # The quarter's own figures, as the headline states them: the model's takeaway set them against memory's
        # quarters and got them wrong - LIC's EPS "-38% YoY" against a year-ago from before its 1:1 bonus, Ambuja's
        # year-ago profit from before its restatement (round 6, 2026-10-19)
        card.takeaway = f"{period}: {phrase(top, top_word)}, {phrase(profit, profit_word)}."
        replaced.append("takeaway from the file's figures")
    context = memory_points(tagged, history)
    # The model's own memory comparisons are left out: code makes them from memory (memory_points), where the model
    # put figures under the wrong quarters (round 5) and compared across a bonus issue or a restatement (round 6)
    own = [w for w in card.why_it_matters if w.basis not in ("MEMORY", "BALANCE_SHEET")]
    if len(own) < len(card.why_it_matters):
        replaced.append(f"{len(card.why_it_matters) - len(own)} model point(s) from memory left out")
    # the model keeps two points, or one beside two of code's: three at most
    context = context + against_memory[:2]
    card.why_it_matters = context + own[:max(0, min(MAX_WHY, MAX_WHY + 1 - len(context)))]
    if context:
        replaced.append(f"{len(context)} point(s) from memory by code")
    out.timeline_entry = f"{period} results ({basis or 'basis not stated'}): {phrase(top, top_word)}, {phrase(profit, profit_word)}."
    if unconfirmed:
        replaced.append(f"changes left out, their comparative not in the filing: {', '.join(unconfirmed)}")
    return [f"results card from the XBRL file: {', '.join(replaced)}"]


def _rich_rest(out, card, tagged, history, period, basis, phrase, top, top_word, profit, profit_word, replaced,
               unconfirmed, against_memory=(), v2: bool = False, profit_label: str | None = None) -> list[str]:
    """The rest of a rich results card: the takeaway from the file, code's memory points, and the model's notable
    changes, core catalyst and points (memory ones too: those cite their memory ids and are checked against memory)."""
    driver = profit_driver(tagged, profit.metric, profit_label.lower() if profit_label else None, True) if v2 \
        else profit_driver(tagged)
    card.takeaway = driver or f"{period}: {phrase(top, top_word)}, {phrase(profit, profit_word)}."
    replaced.append("takeaway from the file's profit bridge" if driver else "takeaway from the file's figures")
    if card.quantified_impact:
        replaced.append(f"computed impacts ({len(card.quantified_impact)}) left out")
    card.quantified_impact = []
    context = memory_points(tagged, history) + list(against_memory)[:3]
    # a point from memory must name the memory it comes from: one without an id is the model's own recollection
    own = [w for w in card.why_it_matters if w.basis not in ("MEMORY", "BALANCE_SHEET") or w.memory_refs]
    if len(own) < len(card.why_it_matters):
        replaced.append(f"{len(card.why_it_matters) - len(own)} model point(s) from memory without an id left out")
    card.why_it_matters = context + own[:MAX_WHY_RICH]
    if context:
        replaced.append(f"{len(context)} point(s) from memory by code")
    out.timeline_entry = f"{period} results ({basis or 'basis not stated'}): {phrase(top, top_word)}, {phrase(profit, profit_word)}."
    if unconfirmed:
        replaced.append(f"changes left out, their comparative not in the filing: {', '.join(unconfirmed)}")
    return [f"results card from the XBRL file (rich): {', '.join(replaced)}"]


# A call card's key figures against the company's own XBRL for the quarter (daily audit, 21 Oct 2026: Bajaj Consumer's
# transcript read "a revenue of INR233 crores with a growth of 2.7%" for a quarter its results file tags at ₹332.83 Cr,
# +25.5%; the card's headline and key numbers repeated the slip while its own results block showed the filed figures).
# Compared only when the label is the plain line (not adjusted, operating, a segment or a product) and the quote speaks
# of the quarter and of no longer period: on the 198 stored call cards with a results block, a looser rule flagged 54,
# nearly all full-year figures labelled "Revenue", segment sales, adjusted EBITDA or the other basis; with the quarter
# named in the quote 7 still differed, mostly a management definition or the other basis. So the stated change must
# contradict the filed one too (more than CALL_CHANGE_GAP points): 2 of the 198, Bajaj Consumer's slip among them.
_CALL_METRICS = {"revenue": ("revenue", "total income", "revenue from operations"), "ebitda": ("ebitda",),
                 "pat": ("pat", "net profit", "profit after tax")}
_PLAIN_LABEL = re.compile(r"^(?:q[1-4]\s*(?:fy\d{2})?\s*)?(?:consolidated\s+)?(?:revenue(?: from operations)?|total income|"
                          r"ebitda|pat|net profit|profit after tax)$", re.I)
_QUARTER_WORDS = re.compile(r"\b(?:quarter|q[1-4])\b", re.I)
_LONGER_PERIOD = re.compile(r"\b(?:h[12]|9m|nine months|half|fy\s?\d{2,4}|full[- ]year|for the year|annual|ytd|year to date|"
                            r"financial year)\b", re.I)
_CRORE = re.compile(r"₹\s?([\d,]+(?:\.\d+)?)\s*(?:cr|crore)\b", re.I)
CALL_FIGURE_TOLERANCE = 0.05
CALL_CHANGE_GAP = 10.0
_CHANGE = re.compile(r"([+-−]?\d+(?:\.\d+)?)\s*%\s*(yoy|y-o-y|qoq|q-o-q)", re.I)


def _crore(text: str | None) -> float | None:
    m = _CRORE.search(text or "")
    return float(m.group(1).replace(",", "")) if m else None


def call_figure_conflicts(results: dict | None, key_numbers: list[dict]) -> list[dict]:
    """The key numbers of a call card whose quarter figure is none of the results block's (the quarter, its year-ago or
    its previous quarter) for that metric: a misread or a transcription slip, not the company's filed figure."""
    if not results or not results.get("period"):
        return []
    conflicts = []
    for k in key_numbers or []:
        label = " ".join((k.get("label") or "").lower().split())
        quote = k.get("quote") or ""
        if not _PLAIN_LABEL.match(label) or not _QUARTER_WORDS.search(quote) or _LONGER_PERIOD.search(quote):
            continue
        metric = next((m for m, words in _CALL_METRICS.items() if any(w in label for w in words)), None)
        value = _crore(k.get("value"))
        line = results.get(metric) if metric else None
        if line is None or value is None or not isinstance(line.get("value"), (int, float)):
            continue
        filed = [v for v in (line.get("value"), line.get("prev_year"), line.get("prev_quarter")) if isinstance(v, (int, float)) and v]
        stated = _CHANGE.search(k.get("change") or "")
        filed_change = (line.get("yoy_pct") if stated and stated.group(2).lower().startswith("y") else line.get("qoq_pct")) \
            if stated else None
        if not isinstance(filed_change, (int, float)) \
                or abs(float(stated.group(1).replace("−", "-")) - filed_change) <= CALL_CHANGE_GAP:
            continue
        if filed and all(abs(value - v) > max(1.0, abs(v) * CALL_FIGURE_TOLERANCE) for v in filed):
            conflicts.append({"label": k.get("label"), "value": k.get("value"), "metric": metric, "filed": line["value"],
                              "period": results["period"]})
    return conflicts
