"""Explain the screener differences that corporate actions and later restatements cause (owner, 26 Oct 2026). Read only: no
memory write, no card change, no AI, no screener request. It reads memory's dossiers (recorded share-count actions, stored
later-file figures) and NSE (the results list per company, the XBRL files), on the pace the other referees use.

``screener-referee`` found that in 6,726 differing pairs our figure equals NSE's own file for the period. Memory was filled
from those files, so that proves nothing about which side is right. The owner's order: first explain what corporate actions
and later restatements cause, and send only the rest to the PDF referee (``pdf_referee``). Rows with verdict
``ours_matches_official`` are tried in this order; every other row passes through marked ``not_explained_input``:

0. ``eps_continuing_vs_total`` (EPS only). Where the period has a discontinued operation, memory's EPS is the continuing
   operations' EPS and screener's is on the whole profit (measured 26 Oct 2026 on memory's 25 Oct backup: ABB Q4FY26, ours
   16.14, screener 84.17; ABFRL Q4FY25, ours -1.34, screener -0.14). If memory holds ``pat_continuing`` for the period and
   screener's EPS is ours x P / ``pat_continuing`` (P: ``pat_owners`` when present, else ``pat``; the EPS tolerance), that
   is the cause.
1. ``share_adjusted`` (EPS only). The company's dossier lists its share-count actions (``corporate_actions``: kind BONUS,
   SPLIT or CONSOLIDATION with a ``factor``, the shares one share became). The product of the factors of the actions with an
   ex-date after the period's end, up to today, is the factor (an announced action with a future ex-date has not happened:
   left out). If screener's EPS is ours divided by that factor (the cross-check's own EPS tolerance), screener has put the old
   EPS on today's share count and ours is the figure as filed. ``factor`` and the action subjects go to ``detail``. A rights
   issue has no factor (partly-paid and premium shares: none is invented); it is left to step 2, and ``detail`` says
   "rights issue on <date> between the period and today" so the report can count those rows.
1a. ``excise_netted`` (revenue only). Screener reports sales net of excise duty where a company's revenue from operations
   includes it ("Companies are now required to report sales net of excise duty and discounts. Screener automatically excludes
   items where not excluded", screener.in/guides/optimizations, read 27 Oct 2026; measured the same day on PICCADIL Q2FY25,
   revenue 200.52 Cr with excise 15.61 Cr in it, screener 185). If memory holds ``excise_duty`` for the period on the row's
   basis and screener's revenue is ours less it, that is the cause and ours is the company's own line.
2. ``restated_later`` (revenue, profit, EPS). The same period's figure as printed in a LATER NSE results file. Memory
   already keeps a later file's comparative column as a separate source of the metric entry (``restated_from``,
   ``dossier._metric_entry``, F167; ``nse_selfcheck`` part a), so the dossier is read first (``later_from`` = memory, no
   request); only when it holds no later source does ``CompanyFiles.later`` fetch the later file from NSE (``later_from`` =
   nse): for a quarter the same quarter a year on, for a year the next March file. If that figure differs from ours and
   screener's is the later figure, a later filing restated it (a demerger recast as continuing operations, a restated
   comparative) and screener has the newer one. A later figure equal to ours is noted as ``later_same`` in ``detail`` (not a
   verdict: the row falls through).
3. ``unexplained``: the PDF referee's cases (``pdf-referee --explained``).

``not_run`` marks rows cut by the time budget or an NSE refusal (SourceBlockedError stops the run: exit 75).
"""

from __future__ import annotations

import csv
import io
import json
import logging
import time
from collections import Counter

from . import eps_adjust
from .corporate_actions import KEY as ACTIONS_KEY
from .nse import FileCapReached, SourceBlockedError
from .nse_selfcheck import _sources, _same_basis, is_exchange
from .periods import due_date
from .screener_crosscheck import _close
from .screener_xbrl_referee import CSV_HEADER as INPUT_HEADER, CompanyFiles, _num, ours_close
from .timeutil import today_ist

log = logging.getLogger(__name__)

VERDICTS = ("eps_continuing_vs_total", "share_adjusted", "excise_netted", "restated_later", "eps_owners_vs_total", "unexplained",
            "not_explained_input", "not_run")
# rows the PDF referee still takes from explained.csv: an EPS on the whole profit where screener's is on the owners' share
# is a question about our figure, not an explanation (independent review, 26 Oct 2026: AFSL Q2FY25 EPS 5.46 on profit 27.38,
# screener 5.06 on owners' 25.39; 284 of 503 first "continuing" rows were this)
TO_PDF = ("unexplained", "eps_owners_vs_total", "not_run")
SHARE_FLOOR = 0.03   # apart()'s EPS floor for an exact recorded factor
SHARE_KINDS = ("BONUS", "SPLIT", "CONSOLIDATION")
RIGHTS_KIND = "RIGHTS"
ADDED = ["explain_verdict", "factor", "later_value", "later_file", "later_from", "detail"]
CSV_HEADER = INPUT_HEADER + ADDED
TAKEN = "ours_matches_official"


def share_factor(dossier: dict | None, period: str, today: str) -> tuple[float, list[dict]]:
    """(the product of the factors of the share-count actions with an ex-date after the period's end and not after today, those
    actions). 1.0 and [] when there are none or the period's end is unknown."""
    end = due_date(period)
    if not dossier or end is None:
        return 1.0, []
    used = sorted((a for a in dossier.get(ACTIONS_KEY) or []
                   if a.get("kind") in SHARE_KINDS and a.get("factor") and end.isoformat() < a.get("ex_date", "") <= today),
                  key=lambda a: a["ex_date"])
    factor = 1.0
    for a in used:
        factor *= float(a["factor"])
    return factor, used


def _entry(dossier: dict | None, metric: str, period: str, basis: str | None) -> dict | None:
    """The metric entry of the period on the row's basis: one on exactly that basis first, else one with no basis told."""
    rows = [e for e in (dossier or {}).get("financial_metrics") or [] if e.get("metric") == metric and e.get("period") == period]
    exact = next((e for e in rows if basis and e.get("basis") == basis), None)
    return exact or next((e for e in rows if _same_basis(basis, e.get("basis"))), None)


def memory_value(dossier: dict | None, metric: str, period: str, basis: str | None = None) -> float | None:
    """Memory's own figure of a metric and period on the row's basis (the entry's value), None when it holds none: a
    standalone profit is never put beside a consolidated EPS."""
    entry = _entry(dossier, metric, period, basis)
    return entry.get("value") if entry else None


def apart(ours: float, theirs: float, metric: str, eps_floor: float = 0.06) -> bool:
    """An explanation counts only for a gap of more than twice the tolerance: within it, a factor or a ratio can match by
    chance (review placebo: 3.7% false explanations at |EPS| under 0.5). A recorded bonus or split, an exact factor, takes
    a floor of 0.03 instead (second review: EASEMYTRIP 0.19 vs 0.09 after a 1:1 bonus, Motherson 0.30 vs 0.20 after 1:2)."""
    tol = max(eps_floor, 0.005 * abs(theirs)) if metric == "eps" else max(1.0, 0.005 * abs(theirs))
    return abs(ours - theirs) > 2 * tol + 1e-9   # a gap of exactly twice the tolerance is not apart (float noise)


def continuing_ratio(dossier: dict | None, period: str, basis: str | None = None) -> tuple[float, str] | None:
    """(the whole profit over the continuing operations' profit, the profit line used) for a period with a discontinued
    operation (``pat`` and ``pat_continuing`` apart by more than ₹1 Cr and 0.5%), None when there is none, or no usable
    whole profit, or the ratio is not above 0."""
    continuing, total = memory_value(dossier, "pat_continuing", period, basis), memory_value(dossier, "pat", period, basis)
    if not continuing or total is None or abs(total - continuing) <= max(1.0, 0.005 * abs(continuing)):
        return None
    owners = memory_value(dossier, "pat_owners", period, basis)
    whole, line = (owners, "pat_owners") if owners is not None else (total, "pat")
    ratio = whole / continuing
    return (ratio, line) if ratio > 0 else None


def owners_ratio(dossier: dict | None, period: str, basis: str | None = None) -> float | None:
    """The owners' profit over the whole profit, for a period with no discontinued operation: an EPS that screener's equals
    once put on the owners' share was worked on the whole profit (a question about our figure). None when not usable."""
    total, owners = memory_value(dossier, "pat", period, basis), memory_value(dossier, "pat_owners", period, basis)
    if not total or owners is None or owners / total <= 0 or abs(total - owners) <= max(0.5, 0.005 * abs(total)):
        return None
    return owners / total


def rights_note(dossier: dict | None, period: str, today: str) -> str:
    """The date of a rights issue between the period's end and today ("" when none): it has no factor and no EPS adjustment."""
    end = due_date(period)
    if not dossier or end is None:
        return ""
    ex = sorted(a.get("ex_date", "") for a in dossier.get(ACTIONS_KEY) or []
                if a.get("kind") == RIGHTS_KIND and end.isoformat() < a.get("ex_date", "") <= today)
    return f"rights issue on {ex[0]} between the period and today" if ex else ""


def memory_later(dossier: dict | None, row: dict) -> dict | None:
    """The period's figure from a later file's comparative column, as memory stores it: {value, file} from the newest source of
    the metric entry that is an exchange file with ``restated_from`` on the row's basis; None when memory holds none."""
    basis = row.get("basis") or None
    entry = _entry(dossier, row["metric"], row["period"], basis)
    if entry is None:
        return None
    later = sorted((s for s in _sources(entry) if s.get("restated_from") and is_exchange(s) and s.get("value") is not None
                    and _same_basis(basis, s.get("basis"))), key=lambda s: s.get("as_of") or "")
    return {"value": later[-1]["value"], "file": str(later[-1]["restated_from"])} if later else None


def explain_pair(files: CompanyFiles, dossier: dict | None, row: dict, today: str) -> dict:
    """The explain fields for one ours_matches_official row."""
    period, metric = row["period"], row["metric"]
    ours, theirs = _num(row.get("memory_value")), _num(row.get("screener_value"))
    out = {"explain_verdict": "unexplained", "factor": None, "later_value": None, "later_file": "", "later_from": "", "detail": ""}
    if ours is None or theirs is None:
        out["detail"] = "the row has no figure on one side"
        return out
    notes = []
    rights = rights_note(dossier, period, today) if metric == "eps" else ""
    if rights:
        notes.append(rights)
    if metric == "eps":
        ratio = continuing_ratio(dossier, period, row.get("basis") or None)
        if ratio and apart(ours, theirs, "eps") and _close(ours * ratio[0], theirs, "eps"):
            out.update(explain_verdict="eps_continuing_vs_total", factor=ratio[0],
                       detail=f"memory's EPS is on continuing operations; x{ratio[0]:.4g} = {ratio[1]} over pat_continuing")
            return out
        owners = owners_ratio(dossier, period, row.get("basis") or None)
        if owners and apart(ours, theirs, "eps") and _close(ours * owners, theirs, "eps"):
            out.update(explain_verdict="eps_owners_vs_total", factor=owners,
                       detail=f"our EPS fits the whole profit, screener's the owners' share (x{owners:.4g}); to the PDF referee")
            return out
        factor, actions = share_factor(dossier, period, today)
        if actions and abs(factor - 1) > 1e-9:
            out["factor"] = factor
            if apart(ours, theirs, "eps", eps_floor=SHARE_FLOOR) and _close(ours / factor, theirs, "eps"):
                out.update(explain_verdict="share_adjusted",
                           detail="; ".join([f"x{factor:g}: " + "; ".join(eps_adjust.describe(a) for a in actions)] + notes))
                return out
            notes.append(f"factor {factor:g} does not reach screener")
    if metric == "revenue":
        excise = memory_value(dossier, "excise_duty", period, row.get("basis") or None)
        if excise and excise > 0 and apart(ours, theirs, metric) and _close(ours - excise, theirs, metric):
            out.update(explain_verdict="excise_netted", detail=f"screener's revenue is ours less excise duty {excise:g}")
            return out
    got = memory_later(dossier, row)
    origin = "memory"
    if got is None:
        got, origin = files.later(period, metric), "nse"
    if "value" not in got:
        notes.append(got["reason"])
    else:
        out.update(later_value=got["value"], later_file=got["file"], later_from=origin)
        if ours_close(ours, got["value"], metric):
            notes.append("later_same")
        elif apart(ours, theirs, metric) and _close(got["value"], theirs, metric):
            out.update(explain_verdict="restated_later", detail="; ".join([f"a later file ({got['file']}) prints {got['value']:g}, screener's figure"] + notes))
            return out
        else:
            notes.append("later file prints a third figure")
    out["detail"] = "; ".join(notes)
    return out


def run(nse, sink, rows: list[dict], time_budget: float | None = None, clock=time.monotonic, today: str | None = None) -> dict:
    """Explain the ``ours_matches_official`` rows of the screener-referee CSV company by company; the other rows pass through."""
    today = today or today_ist().isoformat()
    pairs = [r for r in rows if r.get("verdict") == TAKEN and r.get("metric") and r.get("period") and r.get("symbol")]
    taken = {id(r) for r in pairs}
    by_company: dict[tuple[str, str, str], list[dict]] = {}
    for r in pairs:
        by_company.setdefault((r["scrip"], r["symbol"], r.get("basis") or ""), []).append(r)
    started, blocked, out_of_time = clock(), False, False
    capped = False
    done: dict[int, dict] = {}
    calls = {"list": 0, "files": 0, "companies": 0}
    blank = {"factor": None, "later_value": None, "later_file": "", "later_from": ""}

    def not_run(r: dict, why: str) -> dict:
        return {**r, **blank, "explain_verdict": "not_run", "detail": why}

    for (scrip, symbol, basis), items in by_company.items():
        if not blocked and time_budget is not None and clock() - started > time_budget:
            out_of_time = True
        why = "blocked" if blocked else "file cap" if capped else "time budget" if out_of_time else ""
        if why:
            for r in items:
                done[id(r)] = not_run(r, why)
            continue
        files = CompanyFiles(nse, symbol, basis or None)
        calls["companies"] += 1
        dossier = sink.get_dossier(scrip)
        for r in items:
            if blocked or capped:
                done[id(r)] = not_run(r, "blocked" if blocked else "file cap")
                continue
            try:
                done[id(r)] = {**r, **explain_pair(files, dossier, r, today)}
            except FileCapReached as exc:   # the run's file cap (F213): the rest is not_run and waits for the next run
                capped = True
                log.warning("file cap reached (%s): stopping the explain run; the rest waits for the next run", exc)
                done[id(r)] = not_run(r, "file cap")
            except SourceBlockedError as exc:
                blocked = True
                log.warning("NSE refused (%s): stopping the explain run", exc)
                done[id(r)] = not_run(r, "blocked")
        calls["list"] += files.calls["list"]
        calls["files"] += files.calls["files"]
    results = [done[id(r)] if id(r) in taken else {**r, **blank, "explain_verdict": "not_explained_input", "detail": ""} for r in rows]
    summary = summarise(results, calls, blocked, out_of_time)
    if capped:
        summary["file_cap_reached"] = True
    return summary


def summarise(results: list[dict], calls: dict, blocked: bool = False, out_of_time: bool = False) -> dict:
    by_metric: dict[str, Counter] = {}
    for r in results:
        if r.get("explain_verdict") != "not_explained_input":
            by_metric.setdefault(r.get("metric", ""), Counter())[r["explain_verdict"]] += 1
    return {"rows_in": len(results), "companies": calls["companies"],
            "calls": {"results_lists": calls["list"], "files": calls["files"]}, "blocked": blocked, "out_of_time": out_of_time,
            "verdicts": dict(Counter(r["explain_verdict"] for r in results)),
            "by_metric": {k: dict(v) for k, v in sorted(by_metric.items())}, "rows": results}


def load_csv(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def _cell(v) -> str:
    return "" if v is None else f"{v:g}" if isinstance(v, float) else str(v)


def to_csv(summary: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for r in summary["rows"]:
        writer.writerow([_cell(r.get(k)) for k in CSV_HEADER])
    return buffer.getvalue()


def to_json(summary: dict) -> str:
    return json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False, indent=1) + "\n"


def render(summary: dict) -> str:
    lines = [f"screener explain (corporate actions and later files, read only): {summary['rows_in']} rows, "
             f"{summary['companies']} companies, {summary['calls']['results_lists']} results lists, {summary['calls']['files']} files"]
    lines += [f"  {v:22}{summary['verdicts'].get(v, 0)}" for v in VERDICTS]
    if summary["blocked"]:
        lines.append("stopped: NSE refused the session")
    if summary["out_of_time"]:
        lines.append("stopped: time budget")
    if summary.get("file_cap_reached"):
        lines.append("file cap reached: the rest waits for the next run")
    return "\n".join(lines)


def to_markdown(summary: dict, date_text: str) -> str:
    cols = [v for v in VERDICTS if v != "not_explained_input"]
    out = [f"# Screener explain, {date_text}", "",
           "Read only: of the pairs where our figure equals NSE's own file, which differences come from a share-count action "
           "(bonus, split, consolidation after the period) or from a later filing restating the figure (read from memory's "
           "stored later-file source first, else from NSE). Only `unexplained` goes on to `pdf-referee --explained`.", "",
           f"{summary['rows_in']} rows, {summary['companies']} companies, {summary['calls']['results_lists']} results lists and "
           f"{summary['calls']['files']} files fetched.", ""]
    if summary["blocked"] or summary["out_of_time"]:
        out += ["The run stopped early (" + ("NSE refused the session" if summary["blocked"] else "time budget")
                + "); the rest is `not_run`.", ""]
    out += ["## Verdicts", ""] + [f"- {v}: {summary['verdicts'].get(v, 0)}" for v in VERDICTS] + [""]
    out += ["## Verdicts per metric (rows taken from the input)", "", "| Metric | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    out += [f"| {m} | " + " | ".join(str(v.get(x, 0)) for x in cols) + " |" for m, v in summary["by_metric"].items()] + [""]
    return "\n".join(out)
