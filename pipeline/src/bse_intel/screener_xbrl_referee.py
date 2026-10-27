"""NSE's own results XBRL as the referee of the screener cross-check (owner, 26 Oct 2026). Read only: no memory write, no
card change, no AI, no screener request. It reads NSE (the results list per company, the XBRL files).

The cross-check's cached-text referee found nothing for 6,396 of about 6,430 disagreeing pairs (the text cache starts on
25 Oct 2026). Here, for every disagreeing pair (class not ``match`` and not ``naming``; gaps and memory's own period checks
are not pairs), the company's results list is fetched once (``NseClient.financial_results``), and the period's file is
downloaded once per run and read with the pipeline's own XBRL reader (``xbrl.parse``):

- the period's own file first (a financial year: the March quarter's file, which carries the year); if it holds no such
  figure, the next period's file (the next quarter's, or the next year's March file) and then the same quarter of the next
  year, whose comparative columns may carry it; ``official_file`` and ``official_from`` say which file gave the figure;
- the metric is read on the memory entry's basis (consolidated files for a consolidated memory entry, and so on); a
  lender's revenue is its ``revenue`` (revenue from operations), else ``interest_earned`` (a bank), as the cross-check's is;
- ours must agree with the official figure to a hundredth (it comes from the same kind of file); screener's rounds to a
  whole crore, so it gets the cross-check's own tolerance (``screener_crosscheck._close``).

Archive-only mode (``--archive-only``, owner 27 Oct 2026: "Run NSE on archive site which do not block access and we can do
super fast"): no results list is fetched. Memory records each seeded figure's file name (``lab.file_url`` of its
``xbrl:res:<scrip>:<period>`` source, F222); the file is read at that stored URL (never rebuilt) from the XBRL
store first, else from the archive host (``NseClient.download``). A pair that needs a period with no name in memory, or whose
file the archive does not serve, is ``not_run`` (never an API call).

Verdicts: ``ours_matches_official``, ``screener_matches_official``, ``both_match``, ``neither``, ``no_file`` (the reason in
``reason``), ``not_run`` (cut by ``--limit`` or the time budget).

A ``wrong_quarter`` pair also gets ``period_finding``: ``own_period_right`` (ours equals the official figure for ours own
period: the period is right, screener's column or chance is the oddity), ``saved_under_wrong_quarter:<period>`` (ours equals
the official figure of the other period the cross-check found: memory saved it under the wrong quarter), ``neither_period``
or ``unknown`` (no official figure for the periods).
"""

from __future__ import annotations

import csv
import io
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from collections import Counter

from .metrics import CONSOLIDATED
from .nse import FileCapReached, SourceBlockedError
from .periods import canonical_period, quarter_index
from .screener_crosscheck import _close, _neighbours, CLASSES, SIX_EXPLAINED, SIX_METRICS
from . import xbrl
from . import xbrl_store

log = logging.getLogger(__name__)

# steady_older is not here: a run of older quarters off by a steady ratio can be our error (a wrong basis), so the referee
# still sees it (blind review, 27 Oct 2026)
NOT_PAIRS = ("match", "naming", "screener_only", "memory_only", "memory_period_suspect", *SIX_EXPLAINED)
VERDICTS = ("ours_matches_official", "screener_matches_official", "both_match", "neither", "no_file", "not_run")
OURS_ABS, OURS_REL = 0.011, 0.0001
LENDER_TEMPLATES = xbrl.LENDER_TEMPLATES
MAX_FILE_BYTES = 8_000_000


def file_names(dossier: dict | None, scrip: str, basis: str | None) -> dict[str, str]:
    """quarter -> the NSE file url memory recorded for it (``lab.file_url``, stamped by the seed, F222), on ``basis``:
    read from the sources whose id is ``xbrl:res:<scrip>:<quarter>``. {} when memory holds none (a seed before F222)."""
    out: dict[str, str] = {}
    prefix = f"xbrl:res:{scrip}:"
    for entry in (dossier or {}).get("financial_metrics", []):
        rows = entry.get("sources") or [{"news_id": entry.get("source_news_id"), "lab": entry.get("lab"), "basis": entry.get("basis")}]
        for row in rows:
            nid, lab = str(row.get("news_id") or ""), row.get("lab") or {}
            if nid.startswith(prefix) and lab.get("file_url") and (row.get("basis") or lab.get("basis")) in (None, basis):
                out[nid[len(prefix):]] = lab["file_url"]
    return out


def _label(year: int, quarter: int) -> str:
    return f"Q{quarter}FY{year:02d}"


def file_periods(period: str) -> list[str]:
    """The quarters whose files are tried for a period, in order: a quarter's own, the next quarter's, the same quarter a
    year on; a year's March file, then the next year's."""
    if period.startswith("FY"):
        nxt = _neighbours(period)[1]
        return [f"Q4{period}", f"Q4{nxt}"]
    idx = quarter_index(period)
    if idx is None:
        return []
    out = [period]
    for step in (1, 4):
        year, q = divmod(idx + step - 1, 4)
        out.append(_label(year, q + 1))
    return out


def ours_close(ours: float, official: float, metric: str) -> bool:
    absolute = 0.011 if metric == "eps" else OURS_ABS
    return abs(ours - official) <= max(absolute, OURS_REL * abs(official))


def verdict_of(ours: float, theirs: float, official: float, metric: str) -> str:
    mine, yours = ours_close(ours, official, metric), _close(official, theirs, metric)
    if mine and yours:
        return "both_match"
    if mine:
        return "ours_matches_official"
    if yours:
        return "screener_matches_official"
    return "neither"


def _line_names(parsed, metric: str) -> tuple[str, ...]:
    """The metric lines of a parsed file that carry ``metric``: a lender's revenue is its revenue from operations, else (a
    bank, whose file has none) its interest earned (F186)."""
    if metric == "revenue" and parsed.template in LENDER_TEMPLATES:
        return ("revenue", "interest_earned")
    return (metric,)


class CompanyFiles:
    """One company's results list and files on one basis, each fetched once."""

    def __init__(self, nse, symbol: str, basis: str | None, sink=None, names: dict[str, str] | None = None):
        self.nse, self.symbol, self.basis, self.sink = nse, symbol, basis, sink   # sink: R2 keeps the files (xbrl_store, F191)
        self.names = names     # archive-only: quarter -> file name from memory; None = the default mode (NSE's results list)
        self.missing = False   # archive-only: a file a read needed has no name in memory or is not on the archive
        self.rows: dict[str, object] | None = None
        self.error = ""
        self.parsed: dict[str, tuple[object | None, str]] = {}   # url -> (XbrlResult or None, why not)
        self.calls = {"list": 0, "files": 0, "store": 0}

    def _list(self) -> dict[str, object]:
        if self.rows is None:
            self.rows = {}
            try:
                self.calls["list"] += 1
                listed = self.nse.financial_results(self.symbol)
            except SourceBlockedError:
                raise
            except Exception as exc:   # noqa: BLE001 - one company's list failing is a reason, not a stop
                self.error = f"results list unavailable ({type(exc).__name__})"
                listed = []
            want = self.basis == CONSOLIDATED
            # the same choice as the seed: integrated filing over the older list, then the later filing, wins
            for row in sorted((r for r in listed if r.consolidated == want and r.period_end),
                              key=lambda r: (not getattr(r, "legacy", False), r.filed_at)):
                label = canonical_period(f"quarter ended {row.period_end[8:10]}.{row.period_end[5:7]}.{row.period_end[:4]}")
                if label:
                    self.rows[label] = row
        return self.rows

    def file_for(self, quarter: str) -> tuple[object | None, str, str]:
        """(parsed file, its url's name, why none)."""
        if self.names is not None:
            name = self.names.get(quarter, "")
            if not name:
                self.missing = True
                return None, "", f"no file name in memory for {quarter}"
            url = name   # the url the seed fetched, as stored: never rebuilt
            name = url.rsplit("/", 1)[-1]
        else:
            row = self._list().get(quarter)
            if row is None:
                return None, "", self.error or f"NSE lists no {(self.basis or '').lower()} results file for {quarter}"
            url = row.xbrl_url
            name = url.rsplit("/", 1)[-1]
        if url not in self.parsed:
            try:
                data = xbrl_store.get(self.sink, url)
                if data:
                    self.calls["store"] += 1
                else:
                    self.calls["files"] += 1
                    data = self.nse.download(url, max_bytes=MAX_FILE_BYTES)
                    if data:
                        xbrl_store.put(self.sink, url, data)
            except SourceBlockedError:
                raise
            except Exception as exc:   # noqa: BLE001
                self.missing = self.names is not None
                self.parsed[url] = (None, f"download failed ({type(exc).__name__})")
            else:
                if data is None:
                    self.missing = self.names is not None
                    self.parsed[url] = (None, "file not on the archive" if self.names is not None
                                        else "NSE served no XML (missing, not XML, or over the size cap)")
                else:
                    result = xbrl.parse(data)
                    if not result or result.kind != "RESULTS" or not result.metrics:
                        self.parsed[url] = (None, "file holds no results figures")
                    elif result.basis and self.basis and result.basis != self.basis:
                        self.parsed[url] = (None, f"file is {result.basis.lower()}, memory's basis is {self.basis.lower()}")
                    else:
                        self.parsed[url] = (result, "")
        parsed, why = self.parsed[url]
        return parsed, name, why

    def official(self, period: str, metric: str) -> dict:
        """The official figure of ``period``: {value, file, used ('own' or 'next:<quarter>')} or {reason}."""
        reasons = []
        for i, quarter in enumerate(file_periods(period)):
            parsed, name, why = self.file_for(quarter)
            if parsed is None:
                reasons.append(f"{quarter}: {why}")
                continue
            for n in _line_names(parsed, metric):
                hit = next((m for m in parsed.metrics if m.metric == n and m.period == period and m.value is not None
                        and not (metric == "revenue" and n == "interest_earned" and not m.value)), None)   # a 0 is no revenue
                if hit:
                    return {"value": hit.value, "file": name, "used": "own" if i == 0 else f"next:{quarter}", "line": n}
            reasons.append(f"{quarter}: {period} {metric} not in {name}")
        return {"reason": "; ".join(reasons) or f"no file period for {period}"}

    def later(self, period: str, metric: str) -> dict:
        """ONLY the later file's figure of ``period``: {value, file, line} or {reason}. The later file is the last one
        ``file_periods`` tries, whose year-ago comparative column carries the period (a quarter: the same quarter a year on;
        a year: the next year's March file). Used by screener_explain to see whether a later filing restated the figure."""
        quarters = file_periods(period)
        if len(quarters) < 2:
            return {"reason": f"no later file period for {period}"}
        quarter = quarters[-1]
        parsed, name, why = self.file_for(quarter)
        if parsed is None:
            return {"reason": f"{quarter}: {why}"}
        for n in _line_names(parsed, metric):
            hit = next((m for m in parsed.metrics if m.metric == n and m.period == period and m.value is not None
                        and not (metric == "revenue" and n == "interest_earned" and not m.value)), None)
            if hit:
                return {"value": hit.value, "file": name, "line": n}
        return {"reason": f"{quarter}: {period} {metric} not in {name}"}


def referee_pair(files: CompanyFiles, row: dict) -> dict:
    """The verdict fields for one cross-check row."""
    period, metric = row["period"], row["metric"]
    ours, theirs = _num(row.get("memory_value")), _num(row.get("screener_value"))
    out = {"verdict": "no_file", "official_value": None, "official_file": "", "official_from": "", "reason": "",
           "period_finding": ""}
    files.missing = False
    got = files.official(period, metric)
    if "value" not in got:
        out["reason"] = got["reason"]
        if files.missing:   # archive-only: a file memory has no name for, or the archive lacks, settles nothing
            out["verdict"] = "not_run"
    elif ours is None or theirs is None:
        out["reason"] = "the row has no figure on one side"
    else:
        out.update(verdict=verdict_of(ours, theirs, got["value"], metric), official_value=got["value"],
                   official_file=got["file"], official_from=got["used"])
    if row["class"] == "wrong_quarter" and ours is not None:
        if "value" in got and ours_close(ours, got["value"], metric):
            out["period_finding"] = "own_period_right"
        else:
            other = [p for p in _shifted(row) if p != period]
            found = ""
            for p in other[:2]:
                alt = files.official(p, metric)
                if "value" in alt and ours_close(ours, alt["value"], metric):
                    found = f"saved_under_wrong_quarter:{p}"
                    break
            if found:
                out["period_finding"] = found
            elif "value" in got:
                out["period_finding"] = "neither_period"
            else:
                out["period_finding"] = "unknown"
    return out


def _shifted(row: dict) -> list[str]:
    shifted = row.get("shifted")
    if isinstance(shifted, str):
        shifted = [s for s in shifted.split("|") if s]
    return list(shifted or [])


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def disagreeing(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("metric") and r.get("class") not in NOT_PAIRS]


def run(nse, rows: list[dict], limit: int | None = None, time_budget: float | None = None, clock=time.monotonic,
        sink=None, progress=None, every: int = 20, names_for=None, workers: int = 1) -> dict:
    """Referee the disagreeing pairs among the cross-check's ``rows``, company by company. ``limit`` caps the pairs
    refereed (a company is not split: the one that crosses the cap is finished); pairs left over are ``not_run``.
    ``progress`` (optional) gets the summary so far every ``every`` companies, so a run stopped by hand keeps its work
    (26 Oct 2026: a cancelled 2 h run had written nothing). ``names_for(scrip, basis)`` (archive-only mode) gives a company's
    quarter -> file name from memory (``file_names``): then no results list is fetched, and a pair needing a file memory
    has no name for, or the archive lacks, is ``not_run``. ``workers`` (archive-only only) reads that many companies at
    once (owner 27 Oct 2026: "use multiple downloads at once")."""
    pairs = disagreeing(rows)
    # the cross-check's six other lines (Operating Profit ... Tax %) are not refereed here: a file is read for revenue,
    # profit and EPS only; their rows pass through as not_run
    skipped = [r for r in pairs if r["metric"] in SIX_METRICS]
    pairs = [r for r in pairs if r["metric"] not in SIX_METRICS]
    by_company: dict[tuple[str, str, str], list[dict]] = {}
    for r in pairs:
        by_company.setdefault((r["scrip"], r["symbol"], r.get("basis") or ""), []).append(r)
    started = clock()
    state = {"done": 0, "blocked": False, "out_of_time": False, "capped": False}   # shared by the workers, under `lock`
    lock = threading.Lock()   # F222: archive-only mode reads companies in parallel; the default mode has one worker
    results: list[dict] = []
    calls = {"list": 0, "files": 0, "store": 0, "companies": 0, "archive_only": names_for is not None}

    def not_run(r: dict, why: str) -> dict:
        return {**r, "verdict": "not_run", "reason": why, "official_value": None, "official_file": "", "official_from": "",
                "period_finding": ""}

    results += [not_run(r, "metric not refereed") for r in skipped]

    def company(key: tuple[str, str, str], items: list[dict]) -> list[dict]:
        scrip, symbol, basis = key
        with lock:
            if not state["blocked"] and time_budget is not None and clock() - started > time_budget:
                state["out_of_time"] = True
            why = ("blocked" if state["blocked"] else "file cap" if state["capped"] else "time budget" if state["out_of_time"]
                   else "limit" if limit is not None and state["done"] >= limit else "")
        if why:
            return [not_run(r, why) for r in items]
        files = CompanyFiles(nse, symbol, basis or None, sink, names_for(scrip, basis or None) if names_for else None)
        out: list[dict] = []
        for r in items:
            if state["blocked"] or state["capped"]:
                out.append(not_run(r, "blocked" if state["blocked"] else "file cap"))
                continue
            try:
                out.append({**r, **referee_pair(files, r)})
                with lock:
                    state["done"] += 1
            except FileCapReached as exc:
                state["capped"] = True
                log.warning("file cap reached (%s): stopping the referee; the rest waits for the next run", exc)
                out.append(not_run(r, "file cap"))
            except SourceBlockedError as exc:
                state["blocked"] = True
                log.warning("NSE refused (%s): stopping the referee", exc)
                out.append(not_run(r, "blocked"))
        with lock:
            calls["companies"] += 1
            for k in ("list", "files", "store"):
                calls[k] += files.calls[k]
        return out

    def collect(rows: list[dict]) -> None:
        results.extend(rows)
        if progress and calls["companies"] % every == 0:
            progress(summarise(results, calls, state["blocked"], state["out_of_time"]))

    if workers <= 1 or names_for is None:
        for key, items in by_company.items():
            collect(company(key, items))
    else:
        # the archive host only, on its own pace (F169): NseClient's pace lock and counter are thread-safe, and a refusal
        # from the host puts every later request back on the API's pace behind one lock
        warm = getattr(nse, "warm_up", None)
        if warm:
            warm()   # the cookie visit once, before the threads start
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(company, key, items) for key, items in by_company.items()]
            for future in futures:   # in company order, so the CSV reads the same as a serial run
                collect(future.result())
    blocked, out_of_time, capped = state["blocked"], state["out_of_time"], state["capped"]
    summary = summarise(results, calls, blocked, out_of_time)
    if capped:
        summary["file_cap_reached"] = True
    return summary


def summarise(results: list[dict], calls: dict, blocked: bool = False, out_of_time: bool = False) -> dict:
    classes = [c for c in CLASSES if c != "match"]
    by_class: dict[str, Counter] = {}
    by_metric: dict[str, Counter] = {}
    by_class_metric: dict[str, Counter] = {}
    reasons: Counter = Counter()
    findings: Counter = Counter()
    used: Counter = Counter()
    for r in results:
        by_class.setdefault(r["class"], Counter())[r["verdict"]] += 1
        by_metric.setdefault(r["metric"], Counter())[r["verdict"]] += 1
        by_class_metric.setdefault(f"{r['class']}/{r['metric']}", Counter())[r["verdict"]] += 1
        if r["verdict"] in ("no_file", "not_run"):
            reasons[_short_reason(r.get("reason", ""))] += 1
        if r.get("period_finding"):
            findings[r["period_finding"].split(":")[0]] += 1
        if r.get("official_from"):
            used[r["official_from"].split(":")[0]] += 1
    return {"pairs": len(results), "companies": calls["companies"], "calls": {"results_lists": calls["list"], "files": calls["files"],
                                                                                         **({"store_hits": calls.get("store", 0)} if calls.get("archive_only") else {})},
            "archive_only": bool(calls.get("archive_only")),
            "blocked": blocked, "out_of_time": out_of_time,
            "verdicts": dict(Counter(r["verdict"] for r in results)),
            "by_class": {k: dict(v) for k, v in by_class.items()}, "by_metric": {k: dict(v) for k, v in by_metric.items()},
            "by_class_metric": {k: dict(v) for k, v in sorted(by_class_metric.items())},
            "official_from": dict(used), "wrong_quarter_findings": dict(findings),
            "no_file_reasons": dict(reasons.most_common(15)), "classes_order": classes, "rows": results}


def _short_reason(reason: str) -> str:
    """The reason without its period and file names, so reasons count together."""
    import re
    parts = [re.sub(r"Q[1-4]FY\d{2}|FY\d{2}|[A-Za-z0-9_.-]+\.xml", "<p>", p.split(": ", 1)[-1]) for p in reason.split("; ")]
    return "; ".join(dict.fromkeys(parts))[:120] or "unspecified"


CSV_HEADER = ("scrip,symbol,basis,period,metric,class,memory_value,screener_value,official_value,verdict,official_from,"
              "official_file,period_finding,reason,note").split(",")


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
    lines = [f"screener referee (NSE results XBRL, read only): {summary['pairs']} pairs, {summary['companies']} companies, "
             f"{summary['calls']['results_lists']} results lists, {summary['calls']['files']} files downloaded, "
             f"{summary['calls'].get('store_hits', 0)} from the store" + (" (archive only)" if summary.get("archive_only") else "")]
    lines += [f"  {v:28}{summary['verdicts'].get(v, 0)}" for v in VERDICTS]
    if summary["blocked"]:
        lines.append("stopped: NSE refused the session")
    if summary["out_of_time"]:
        lines.append("stopped: time budget")
    if summary.get("file_cap_reached"):
        lines.append("file cap reached: the rest waits for the next run")
    return "\n".join(lines)


def to_markdown(summary: dict, date: str) -> str:
    out = [f"# Screener referee, {date}", "",
           "Read only: NSE's own results XBRL decides each disagreeing pair of the screener cross-check (the period's own file, "
           "else the next period's as a comparative). Memory is not written and no card changes.", "",
           f"{summary['pairs']} pairs, {summary['companies']} companies, {summary['calls']['results_lists']} results lists and "
           f"{summary['calls']['files']} files downloaded, {summary['calls'].get('store_hits', 0)} read from the store"
           + (" (archive-only mode: file names from memory, no results list)." if summary.get("archive_only") else "."), ""]
    if summary["blocked"] or summary["out_of_time"]:
        out += ["The run stopped early (" + ("NSE refused the session" if summary["blocked"] else "time budget")
                + "); the rest is `not_run`.", ""]
    sep = "|---|" + "---|" * len(VERDICTS)

    def table(title: str, groups: dict) -> list[str]:
        rows = [f"## {title}", "", "| Group | " + " | ".join(VERDICTS) + " |", sep]
        rows += [f"| {k} | " + " | ".join(str(v.get(x, 0)) for x in VERDICTS) + " |" for k, v in sorted(groups.items())]
        return rows + [""]

    out += table("Verdicts per class", summary["by_class"]) + table("Verdicts per metric", summary["by_metric"])
    out += table("Verdicts per class and metric", summary["by_class_metric"])
    out += ["## Where the figure came from", "", ", ".join(f"{k} {n}" for k, n in sorted(summary["official_from"].items())) or "none", ""]
    out += ["## wrong_quarter: which period is right", ""]
    f = summary["wrong_quarter_findings"]
    out += [f"- own_period_right (ours equals the official figure for its own period): {f.get('own_period_right', 0)}",
            f"- saved_under_wrong_quarter (ours equals the official figure of the other period): {f.get('saved_under_wrong_quarter', 0)}",
            f"- neither_period: {f.get('neither_period', 0)}", f"- unknown (no official figure): {f.get('unknown', 0)}", ""]
    out += ["## Why no file", ""] + [f"- {k}: {n}" for k, n in summary["no_file_reasons"].items()] + [""]
    out += ["Every pair, with the official figure and the file it came from, is in the CSV artifact.", ""]
    return "\n".join(out)
