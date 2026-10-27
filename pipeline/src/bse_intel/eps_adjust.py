"""EPS across splits, bonuses and consolidations (F153, TODO 43).

A bonus or split changes the share count, so an EPS from before it is not the same kind of number as one after it:
Reliance's 1:1 bonus (Oct 2024) doubled its year-ago EPS and the metrics table showed EPS -45% beside a 14% profit rise;
LIC's card once said -38% YoY for the same reason. `corporate_actions.share_factor_after` held the factor and nothing
used it. Here the older period's EPS is divided by the factor between the two periods ("adjusted for bonus 1:1 on
<date>"); the stored figure is never changed. A filing restates its own comparatives for an action before its period
end, so when the profit-over-EPS share counts already sit nearer 1 than nearer the factor the figures are left as they
are. Real dilution (allotment, rights, QIP, ESOPs, merger) is not adjusted: the reported change shows. With no record,
only a share count that moved by an exact split or bonus ratio blanks the comparison (owner, 25 Oct 2026).

Cards use it behind `settings.eps_share_adjust()` (EPS_SHARE_ADJUST, default off); metrics.py, which is not on cards,
uses it always.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .periods import due_date, prior_quarter_period, prior_year_period
from .settings import card_eps_follows_profit, eps_base_check, eps_share_adjust

# Owner, 25 Oct 2026: a preferential allotment, rights issue, QIP, ESOPs or a merger is real dilution, so EPS growth
# shows the reported change there. Only a recorded split, bonus or consolidation is adjusted for; with no record, a share
# count that moved by exactly a split or bonus ratio (within 1%) is "possibly a bonus or split not on record" and blank.
EXACT_RATIOS = (2, 1.5, 3, 4, 5, 10)
RATIO_TOLERANCE = 0.01
NOT_ON_RECORD = "possible bonus or split not on record"
KEY = "corporate_actions"


def enabled() -> bool:
    return eps_share_adjust()


def implied_shares(profit, eps) -> float | None:
    """The share count the profit EPS is on implies, in the profit's unit over the EPS's (crore shares for crore)."""
    return abs(profit / eps) if profit and eps else None


def exact_ratio(ratio) -> bool:
    """Whether a share-count ratio is within 1% of an exact split/bonus ratio or its inverse."""
    return bool(ratio) and any(abs(ratio / r - 1) <= RATIO_TOLERANCE or abs(ratio * r - 1) <= RATIO_TOLERANCE
                               for r in EXACT_RATIOS)


@dataclass
class Compare:
    kind: str                  # "same" (as the file states it), "adjusted" or "blank"
    eps_old: float | None = None   # the older EPS on the newer period's share count
    note: str | None = None


def _actions_between(dossier: dict | None, old_end: str, new_end: str) -> list[dict]:
    return [a for a in (dossier or {}).get(KEY) or []
            if a.get("factor") and old_end < a.get("ex_date", "") <= new_end]


def factor_between(dossier: dict | None, old_period: str, new_period: str) -> float:
    """How many of the newer period's shares one share of the older period became (1.0 when none, or a date is unknown)."""
    from .corporate_actions import share_factor_after

    old_end, new_end = due_date(old_period), due_date(new_period)
    if not dossier or not old_end or not new_end:
        return 1.0
    old_end, new_end = old_end.isoformat(), new_end.isoformat()
    return share_factor_after(dossier, old_end) / share_factor_after(dossier, new_end)


def describe(action: dict) -> str:
    """"bonus 1:1 on 2024-10-28", "split 1:5 on ...", "consolidation 5:1 on ..." from a recorded action."""
    kind, factor = action.get("kind"), float(action["factor"])
    if kind == "BONUS":
        f = Fraction(factor - 1).limit_denominator(20)
        what = f"bonus {f.numerator}:{f.denominator}"
    elif kind == "CONSOLIDATION" or factor < 1:
        f = Fraction(1 / factor).limit_denominator(20)
        what = f"consolidation {f.numerator}:1"
    else:
        what = f"split 1:{Fraction(factor).limit_denominator(20)}"
    return f"{what} on {action.get('ex_date')}"


def compare(dossier: dict | None, new_period: str, old_period: str, eps_new, eps_old,
            profit_new=None, profit_old=None) -> Compare:
    """How the older period's EPS stands against the newer one's."""
    if eps_new is None or eps_old is None:
        return Compare("same")
    factor = factor_between(dossier, old_period, new_period)
    new_shares, old_shares = implied_shares(profit_new, eps_new), implied_shares(profit_old, eps_old)
    ratio = new_shares / old_shares if new_shares and old_shares else None
    if abs(factor - 1) < 1e-9:
        if exact_ratio(ratio):
            return Compare("blank", note=f"{NOT_ON_RECORD}: share count between {old_period} and {new_period} moved "
                                         f"{ratio:.2f}x; EPS not comparable")
        return Compare("same")   # the reported change, issues and all
    if ratio is not None and abs(ratio - 1) < abs(ratio / factor - 1):
        return Compare("same")   # the file already restated the older EPS to the new share count
    old_end, new_end = due_date(old_period).isoformat(), due_date(new_period).isoformat()
    actions = sorted(_actions_between(dossier, old_end, new_end), key=lambda a: a["ex_date"])
    return Compare("adjusted", eps_old / factor, "adjusted for " + " and ".join(describe(a) for a in actions))


def _pct(now: float, before: float) -> float | None:
    return round((now / before - 1) * 100, 1) if before and before > 0 else None


def adjust_result(tagged, dossier: dict | None) -> int:
    """Put a results file's EPS changes on one share count, in place: each EPS line's YoY and QoQ against the older
    quarter's EPS (the file's own, else worked back from the stated change), with `eps_note` saying what was done.
    Returns how many changes were adjusted or left out."""
    if not enabled() or tagged is None or getattr(tagged, "kind", None) != "RESULTS":
        return 0
    by = {(m.metric, m.period): m for m in tagged.metrics if m.value is not None}

    def profit(period: str):
        for name in ("pat_owners", "pat"):
            m = by.get((name, period))
            if m is not None:
                return m.value
        return None

    changed = 0
    for m in tagged.metrics:
        if m.metric != "eps" or m.value is None:
            continue
        for slot, back in (("yoy_pct", prior_year_period(m.period)), ("qoq_pct", prior_quarter_period(m.period))):
            if not back or (("eps", back) not in by and getattr(m, slot) is None):
                continue
            old = by.get(("eps", back))
            old_value = old.value if old is not None else (
                m.value / (1 + getattr(m, slot) / 100) if getattr(m, slot) not in (None, -100) else None)
            result = compare(dossier, m.period, back, m.value, old_value, profit(m.period), profit(back))
            if result.kind == "same":
                continue
            setattr(m, slot, _pct(m.value, result.eps_old) if result.kind == "adjusted" else None)
            m.eps_note = result.note
            changed += 1
    return changed


def snapshot_row(row: dict, dossier: dict | None, periods: dict, profit) -> dict:
    """The results table's EPS row (value, prev_year, prev_quarter, yoy_pct, qoq_pct) on one share count; `profit(p)` is
    the profit EPS is on for period p. A change left out is removed, an adjusted one rewritten with `eps_note`."""
    if not enabled() or dossier is None or row.get("value") is None:
        return row
    row, notes = dict(row), []
    for slot, label in (("prev_year", "yoy"), ("prev_quarter", "qoq")):
        base = row.get(slot)
        if base is None or not periods.get(slot):
            continue
        result = compare(dossier, periods["value"], periods[slot], row["value"], base,
                         profit(periods["value"]), profit(periods[slot]))
        if result.kind == "same":
            continue
        for key in (f"{label}_pct", f"{label}_turn"):
            row.pop(key, None)
        if result.kind == "adjusted" and result.eps_old > 0 and row["value"] >= 0:
            row[f"{label}_pct"] = round((row["value"] - result.eps_old) / result.eps_old * 100, 1)
        notes.append(result.note)
    if notes:
        row["eps_note"] = "; ".join(dict.fromkeys(notes))
    return row


# ---- CARD_EPS_FOLLOWS_PROFIT (F183, TODO 78): the safety net behind the share-base logic above.
# Wipro's card (nse-106820253, 26 Oct 2026) showed EPS 3.23 against 2.74 and 2.50, +18%, while profit rose 1% and the CFO said
# EPS +0.9% QoQ: comparatives on another share base (Wipro's 1:1 bonus was ex 3 Dec 2024). EPS can rise faster than profit
# only when the share count falls (a buyback, a consolidation: recorded) or by rounding; so an EPS change more than the
# tolerance ABOVE the profit change, with no share-count event on record, is not shown, nor the comparative it rests on.
# An EPS change below the profit change is left as it is: that is real dilution (QIP, preferential allotment, ESOPs, a
# merger), which the owner wants shown (25 Oct 2026). Only hidden, never replaced (independent review: a figure read from
# the filing's words, "EPS declined by 5%", was signed wrongly).
PROFIT_TOLERANCE_PP = 5.0      # EPS may rise this many percentage points faster than profit ...
SHARE_NOISE_PCT = 3.0          # ... plus this much share-count noise (a small buyback, rounding of shares), scaled to the base
SHARE_EVENTS = ("BONUS", "SPLIT", "CONSOLIDATION", "BUYBACK", "RIGHTS", "DEMERGER")


def share_event(dossier: dict | None, old_period: str, new_period: str) -> dict | None:
    """A recorded action between two periods that changes the share count (corporate_actions), else None."""
    old_end, new_end = due_date(old_period), due_date(new_period)
    if not dossier or not old_end or not new_end:
        return None
    old_end, new_end = old_end.isoformat(), new_end.isoformat()
    return next((a for a in dossier.get(KEY) or [] if a.get("kind") in SHARE_EVENTS and old_end < a.get("ex_date", "") <= new_end), None)


def follows(profit_pct: float, eps_pct: float, base: float | None = None) -> bool:
    """Whether an EPS change is one the profit change allows: not more than 5 points plus share-count noise above it, plus
    the rounding of a small EPS (a base of 0.08 printed to two decimals moves 12% on its last digit)."""
    rounding = 100 * 0.01 / abs(base) if base else 0.0
    return eps_pct - profit_pct <= PROFIT_TOLERANCE_PP + SHARE_NOISE_PCT * (1 + max(profit_pct, 0) / 100) + rounding


def follow_profit(row: dict, dossier: dict | None, periods: dict, profit, printed: str | None = None) -> tuple[dict, list[dict]]:
    """The results table's EPS row with every change the profit does not carry taken out, with the comparative figure it
    rests on, and the notes of what was done. A change beside a recorded split, bonus, buyback or rights issue is left to
    ``snapshot_row``. ``printed`` is unused (kept for the caller's signature)."""
    if not card_eps_follows_profit() or row.get("value") is None:
        return row, []
    row, hidden = dict(row), []
    for slot, label in (("prev_year", "yoy"), ("prev_quarter", "qoq")):
        base, computed = row.get(slot), row.get(f"{label}_pct")
        if base is None or computed is None or not periods.get(slot):
            continue
        now_p, was_p = profit(periods["value"]), profit(periods[slot])
        if not (now_p and was_p and now_p > 0 and was_p > 0):
            continue   # a loss on either side: no percentage to judge by
        profit_pct = (now_p / was_p - 1) * 100
        if share_event(dossier, periods[slot], periods["value"]) is None and not follows(profit_pct, computed, base):
            for key in (f"{label}_pct", f"{label}_turn", slot):
                row.pop(key, None)
            hidden.append({"slot": label, "reason": f"EPS {computed:+g}% {label.upper()} ({base} to {row['value']}) is above profit "
                                                     f"{profit_pct:+.1f}% and no share-count event is on record"})
    if hidden:
        row["eps_note"] = "; ".join(dict.fromkeys(([row["eps_note"]] if row.get("eps_note") else []) + [h["reason"] for h in hidden]))
    return row, hidden


# ---- EPS_BASE_CHECK (F208, TODO 78): the same test on the file's own stored EPS changes (memory keeps `yoy_pct` / `qoq_pct`).
def base_check_result(tagged, dossier: dict | None) -> int:
    """Take out, in place, every EPS YoY / QoQ of a results file that the profit does not carry (``follows``) with no share-count
    event on record between the periods, so it is not stored as a comparable change. The EPS figures stay (memory keeps
    them); only the change goes, with `eps_note` saying why. Profit is the owners', else the total, from the same file.
    Returns how many changes were taken out."""
    if not eps_base_check() or tagged is None or getattr(tagged, "kind", None) != "RESULTS":
        return 0
    by = {(m.metric, m.period): m.value for m in tagged.metrics if m.value is not None}

    def profit(period: str):
        return by.get(("pat_owners", period)) or by.get(("pat", period))

    removed = 0
    for m in tagged.metrics:
        if m.metric != "eps" or m.value is None:
            continue
        for slot, back in (("yoy_pct", prior_year_period(m.period)), ("qoq_pct", prior_quarter_period(m.period))):
            change = getattr(m, slot)
            if not back or change is None:
                continue
            now_p, was_p = profit(m.period), profit(back)
            if not (now_p and was_p and now_p > 0 and was_p > 0):
                continue   # a loss on either side: no percentage to judge by
            profit_pct = (now_p / was_p - 1) * 100
            if share_event(dossier, back, m.period) is None and not follows(profit_pct, change, by.get(("eps", back))):
                setattr(m, slot, None)
                m.eps_note = f"EPS {change:+g}% {slot[:3].upper()} is above profit {profit_pct:+.1f}% and no share-count event is on record"
                removed += 1
    return removed


# EPS_BASE_CHECK, the class behind Wipro (F208): an AI-read results card stored the STANDALONE EPS (2.74, 2.50, 2.89) as consolidated,
# beside the consolidated profit. The company's share count does not depend on the basis, so profit over EPS shows which profit an
# EPS was divided by: the consolidated profit over a standalone EPS gives 1,298 Cr shares where the files say 1,047.
SHARE_MATCH_PCT = 3.0   # profit / EPS agrees with the file-derived share count within this (EPS prints two decimals; buybacks move a few %)


def _share_reference(metrics: dict, period: str) -> float | None:
    """The share count (profit over EPS, the profit's unit over the EPS) of the exchange file's own EPS nearest in time to ``period``,
    for quarters only, from consolidated figures of memory. None when no file EPS has a profit beside it."""
    from .dossier import XBRL_SOURCE

    target = due_date(period)
    if target is None:
        return None
    best = None
    for (name, p), e in metrics.items():
        if name != "eps" or not p.startswith("Q") or p == period or not e.get("value"):
            continue
        if not str(e.get("value_news_id") or e.get("source_news_id") or "").startswith(XBRL_SOURCE):
            continue
        profit = next((metrics[(n, p)]["value"] for n in ("pat_owners", "pat") if metrics.get((n, p), {}).get("value")), None)
        end = due_date(p)
        if profit and profit > 0 and end and e["value"] > 0 and (best is None or abs((end - target).days) < best[0]):
            best = (abs((end - target).days), profit / e["value"])
    return best[1] if best else None


def misbased_eps(metrics: dict, standalone: dict | None, period: str, value, basis: str | None) -> str | None:
    """Why an AI-read per-share figure stored as CONSOLIDATED is probably the standalone one, else None. It must differ from the
    file-derived share count by more than 3% with the consolidated profit, and match it within 3% with the standalone profit of
    that quarter. With near-equal profits on both bases (no subsidiaries) both match, so nothing is done."""
    if not eps_base_check() or basis != "CONSOLIDATED" or not value or value <= 0 or not period.startswith("Q"):
        return None
    ref = _share_reference(metrics, period)
    own = next((metrics[(n, period)]["value"] for n in ("pat_owners", "pat") if metrics.get((n, period), {}).get("value")), None)
    alone = next((e["value"] for n in ("pat_owners", "pat") for e in (standalone or {}).get("metrics", [])
                  if e.get("metric") == n and e.get("period") == period and e.get("value")), None)
    if not (ref and own and alone and own > 0 and alone > 0):
        return None

    def off(profit) -> float:
        return abs(profit / value / ref - 1) * 100

    if off(own) > SHARE_MATCH_PCT and off(alone) <= SHARE_MATCH_PCT:
        return (f"EPS {value:g} for {period} fits the standalone profit ({alone:g}), not the consolidated ({own:g}): "
                f"shares {alone / value:.0f} vs {own / value:.0f} against {ref:.0f} from the files")
    return None
