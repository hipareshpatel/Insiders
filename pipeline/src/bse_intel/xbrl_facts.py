"""Every fact of every results XBRL file, kept outside the dossier (owner, 28 Oct 2026: "we must save everything from XBRL,
adjust our numbers as per screener's treatment").

Memory keeps the elements of ``xbrl.RESULT_TAGS`` / ``BALANCE_TAGS`` / ``CASH_FLOW`` and nothing else. Since F191
(xbrl_store.py) the raw file is in R2 for 180 days; this module turns one such file into its facts and keeps those, so a
later check (the screener cross-check's complete screener view, TODO 93) can read any element - an excise-duty or lease line,
a breakdown of other expenses, a treasury-share count, the 12-month cash flow of a December year end - without a download
and without a second parse of the XML.

One file is one document, ``raw/xbrl-facts/<scrip>/<period>-<basis>.json.gz`` (the Worker's ``raw/`` prefix is allowed;
``xbrl_facts/`` is not and the Worker is not changed here; ``raw/xbrl-facts/`` is not under the lifecycle rule of
``raw/xbrl/``, so the facts stay when the raw file expires):

    {"v": 1, "scrip", "period", "basis", "template", "fy_end_month", "url", "file_period", "n_facts",
     "contexts": {id: {"s": start, "e": end, "i": instant, "m": months, "l": label, "d": {dimension: member}}},
     "units": {id: MONEY | PER_SHARE | SHARES | PURE},
     "facts": [[element, context id, unit id or null, value, decimals or null], ...]}

A number is a number only where the fact has a unit (a unitless text such as a script code stays text, exactly as filed);
money is in rupees as filed (``Facts.cr`` divides by 1e7). A text fact is cut at TEXT_MAX characters. Nothing is dropped:
dimensional facts (segments, the breakdown of other expenses, categories) are kept with their dimension.

The parsing is xbrl.py's: its contexts, units, legacy year-to-date fix, fact rule (``_fact_elements``), period labels and
basis (``xbrl.parse``); there is no second parser here. The command ``xbrl-facts`` (cli.py) reads only files already stored."""

from __future__ import annotations

import gzip
import json
import re
import xml.etree.ElementTree as ET
from datetime import date

from . import xbrl, xbrl_store
from .periods import quarter_index

PREFIX = "raw/xbrl-facts/"
VERSION = 1
TEXT_MAX = 1000
CRORE = 1e7


def key(scrip: str, period: str, basis: str | None) -> str:
    return f"{PREFIX}{scrip}/{period}-{(basis or 'unknown').lower()}.json.gz"


# --- parse ------------------------------------------------------------------------------------------------------

def _unit_kind(unit_id: str, kinds: dict[str, str]) -> str:
    """The unit's kind from its definition; a unit the file never defines (an instance cut down to a sample) from its id."""
    if unit_id in kinds:
        return kinds[unit_id]
    upper = unit_id.upper()
    if "PER" in upper:
        return "PER_SHARE"
    if "SHARE" in upper:
        return "SHARES"
    return "MONEY" if "INR" in upper else "PURE"


def _number(text: str):
    value = xbrl._num(text)
    if value is None:
        return None
    return int(value) if re.fullmatch(r"-?\d{1,15}", text.replace(",", "").strip()) else value


def _decimals(raw: str | None):
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return raw     # "INF"


def parse_facts(data: bytes, scrip: str = "", url: str = "") -> dict | None:
    """One results file's facts as the stored document (see the module's header); None when the file is no XBRL instance or
    xbrl.py finds no results in it (a shareholding file, a file with nothing we read). Dimensions are kept as xbrl._contexts reads them (the axis with its
    prefix, the member without)."""
    result = xbrl.parse(data)
    if result is not None and result.kind != "RESULTS":
        return None
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    contexts = xbrl._contexts(root)
    if not contexts:
        return None
    xbrl._legacy_year_to_date(contexts)
    kinds = xbrl._units(root)
    elements = list(xbrl._fact_elements(root))
    text_facts = {xbrl._local(el.tag): el.text.strip() for el in elements if el.get("unitRef") is None}
    year_end = xbrl.fy_end_month(text_facts)
    if result is None:
        # xbrl.parse keeps no figure of a file with no quarter in it (a half-yearly filer, or a year end other than March
        # whose half and full years carry no label): its facts are kept all the same when it is a results file
        if not {xbrl._local(el.tag) for el in elements} & set(xbrl.RESULT_TAGS):
            return None
        result = _bare_result(contexts, text_facts, year_end)
    used_contexts: dict[str, dict] = {}
    used_units: dict[str, str] = {}
    facts: list[list] = []
    for el in elements:
        ctx, unit, text = el.get("contextRef"), el.get("unitRef"), el.text.strip()
        info = contexts.get(ctx)
        if info is None:
            continue
        if ctx not in used_contexts:
            entry: dict = {}
            if "startDate" in info:
                entry["s"] = info["startDate"].isoformat()
            if "endDate" in info:
                entry["e"] = info["endDate"].isoformat()
            if "instant" in info:
                entry["i"] = info["instant"].isoformat()
            months = xbrl._months(info)
            if months is not None:
                entry["m"] = months
            label = xbrl.period_label(info, year_end) if "endDate" in info else None
            if label:
                entry["l"] = label
            if info["dims"]:
                entry["d"] = dict(info["dims"])
            used_contexts[ctx] = entry
        value = None
        if unit is not None:
            used_units.setdefault(unit, _unit_kind(unit, kinds))
            value = _number(text)
        if value is None:
            value = text[:TEXT_MAX]
        facts.append([xbrl._local(el.tag), ctx, unit, value, _decimals(el.get("decimals"))])
    return {"v": VERSION, "scrip": scrip, "period": result.period, "basis": result.basis, "template": result.template,
            "fy_end_month": result.fy_end_month, "url": url, "file_period": result.period, "n_facts": len(facts),
            "contexts": used_contexts, "units": used_units, "facts": facts}


def _bare_result(contexts: dict, text_facts: dict, year_end: int | None) -> xbrl.XbrlResult:
    """Basis, latest period and year end of a results file xbrl.parse kept nothing of, from the file's own text facts and dates."""
    nature = " ".join(v for k, v in text_facts.items() if "Standalone" in k or "Consolidated" in k or k == "NatureOfReport").lower()
    basis = "CONSOLIDATED" if "consolidated" in nature else "STANDALONE" if "standalone" in nature else None
    ends = [c["endDate"] for c in contexts.values() if not c["dims"] and c.get("endDate")]
    period = xbrl.canonical_period(f"quarter ended {max(ends):%d.%m.%Y}") if ends else None
    return xbrl.XbrlResult("RESULTS", basis, period, fy_end_month=year_end)


def dumps(doc: dict) -> bytes:
    """The document as stored: compact JSON, gzipped with mtime 0 (the same facts are the same bytes)."""
    return gzip.compress(json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), mtime=0)


def loads(body: bytes) -> dict:
    return json.loads(gzip.decompress(body).decode("utf-8"))


# --- read -------------------------------------------------------------------------------------------------------

def _end(ctx: dict) -> str | None:
    return ctx.get("i") or ctx.get("e")


class Facts:
    """One stored document, read by element name and period. A duration is picked by its end date and length in months
    (3, 6, 9 or 12), an instant by its date; dimensional facts are read apart (``described``)."""

    def __init__(self, doc: dict):
        self.doc = doc
        self.contexts: dict[str, dict] = doc.get("contexts") or {}
        self.units: dict[str, str] = doc.get("units") or {}
        self.rows: list[list] = doc.get("facts") or []
        self.basis = doc.get("basis")
        self.fy_end_month = doc.get("fy_end_month")

    def __len__(self) -> int:
        return len(self.rows)

    def _at(self, ctx_id: str, end: date | None, months: int | None, instant: date | None) -> bool:
        ctx = self.contexts.get(ctx_id) or {}
        if instant is not None:
            return ctx.get("i") == instant.isoformat()
        if end is None or ctx.get("e") != end.isoformat():
            return False
        return months is None or ctx.get("m") == months

    def _is_money(self, unit: str | None) -> bool:
        return unit is not None and self.units.get(unit) == "MONEY"

    def get(self, name: str, *, end: date | None = None, months: int | None = None, instant: date | None = None):
        """The raw value of an undimensioned fact at the period (the first in the file), else None."""
        for el, ctx_id, unit, value, _ in self.rows:
            ctx = self.contexts.get(ctx_id) or {}
            if el == name and not ctx.get("d") and self._at(ctx_id, end, months, instant) and not isinstance(value, str):
                return value
        return None

    def cr(self, name: str, **period) -> float | None:
        """A money fact in crore."""
        for el, ctx_id, unit, value, _ in self.rows:
            ctx = self.contexts.get(ctx_id) or {}
            if el == name and not ctx.get("d") and self._at(ctx_id, period.get("end"), period.get("months"), period.get("instant")) \
                    and self._is_money(unit) and not isinstance(value, str):
                return value / CRORE
        return None

    def find(self, pattern: str, *, end: date | None = None, months: int | None = None, instant: date | None = None,
             money: bool = True) -> list[tuple[str, float]]:
        """(element, value in crore) of every undimensioned numeric fact at the period whose element name matches the regex
        ``pattern`` (case-insensitive, searched in the name). ``money=False`` gives the raw values."""
        out = []
        rx = re.compile(pattern, re.I)
        for el, ctx_id, unit, value, _ in self.rows:
            ctx = self.contexts.get(ctx_id) or {}
            if isinstance(value, str) or ctx.get("d") or not rx.search(el) or not self._at(ctx_id, end, months, instant):
                continue
            if money:
                if self._is_money(unit):
                    out.append((el, value / CRORE))
            else:
                out.append((el, value))
        return out

    def described(self, value_names: tuple[str, ...], description: str, *, end: date | None = None, months: int | None = None,
                  instant: date | None = None) -> list[tuple[str, str, float]]:
        """(element, description, value in crore) of every dimensional money fact named in ``value_names`` at the period whose
        context carries a ``DescriptionOf...`` text matching the regex ``description`` (a filer's own line inside a breakdown,
        e.g. "Excise duty" inside other expenses)."""
        rx = re.compile(description, re.I)
        texts: dict[str, list[str]] = {}
        for el, ctx_id, unit, value, _ in self.rows:
            if el.startswith("DescriptionOf") and isinstance(value, str):
                texts.setdefault(ctx_id, []).append(value)
        out, seen = [], set()
        for el, ctx_id, unit, value, _ in self.rows:
            if el in value_names and self._is_money(unit) and not isinstance(value, str) and ctx_id in texts \
                    and self._at(ctx_id, end, months, instant):
                for text in texts[ctx_id]:
                    # a row once: the older files tag a row's year to date with the quarter's own dates (Titan Q2FY24: Advertising
                    # 268 Cr for the quarter and 542 Cr to date, both Jul-Sep), and the quarter's comes first in the file
                    if rx.search(text) and (el, text) not in seen:
                        seen.add((el, text))
                        out.append((el, text, value / CRORE))
                        break
        return out

    def durations(self) -> list[tuple[date, int]]:
        """The (end date, months) of every undimensioned duration context that has facts, newest first."""
        seen = {(c["e"], c["m"]) for c in self.contexts.values() if not c.get("d") and c.get("e") and c.get("m")}
        return sorted(((date.fromisoformat(e), m) for e, m in seen), reverse=True)

    def instants(self) -> list[date]:
        return sorted({date.fromisoformat(c["i"]) for c in self.contexts.values() if not c.get("d") and c.get("i")}, reverse=True)

    def element_names(self) -> set[str]:
        return {row[0] for row in self.rows}


def load(sink, scrip: str, period: str, basis: str | None) -> Facts | None:
    """The stored facts of one company-period-basis, or None when none are stored (or the object is unreadable)."""
    try:
        body = sink.get_object(key(scrip, period, basis))
        return Facts(loads(body)) if body else None
    except Exception:   # noqa: BLE001 - a damaged object is no facts
        return None


def save(sink, scrip: str, period: str, basis: str | None, doc: dict) -> int:
    """Keep one document; the stored (gzipped) size in bytes."""
    body = dumps(doc)
    sink.put_object(key(scrip, period, basis), body, content_type="application/gzip")
    return len(body)


# --- the files of a company --------------------------------------------------------------------------------------

_RES_ID = re.compile(r"xbrl:res(?:-sa)?:([^:]*):(.+)")


def file_urls(dossier: dict | None, scrip: str) -> dict[tuple[str, str], str]:
    """(period, basis) -> the url of the results file memory recorded for it: the url stamped on a figure's label by the
    seed (``lab.file_url``, F222, NSE's archive), else the figure's ``source_url`` (the BSE fill's). The sources are the
    ``xbrl:res:<scrip>:<period>`` ids of the main basis and ``xbrl:res-sa:`` ids of the standalone part. A period whose file
    memory never recorded is not here (the caller lists it as having no url)."""
    from .dossier import STANDALONE_KEY
    from .metrics import CONSOLIDATED, STANDALONE

    out: dict[tuple[str, str], str] = {}
    if not dossier:
        return out
    sections = [(dossier.get("financial_metrics") or [], None), ((dossier.get(STANDALONE_KEY) or {}).get("metrics") or [], STANDALONE)]
    for entries, forced in sections:
        for entry in entries:
            rows = entry.get("sources") or [{"news_id": entry.get("source_news_id"), "lab": entry.get("lab"),
                                             "basis": entry.get("basis"), "source_url": entry.get("source_url")}]
            for row in rows:
                m = _RES_ID.fullmatch(str(row.get("news_id") or ""))
                if not m or m[1] != scrip:
                    continue
                lab = row.get("lab") or {}
                url = lab.get("file_url") or row.get("source_url") or entry.get("source_url")
                basis = forced or row.get("basis") or lab.get("basis") or entry.get("basis")
                if url and basis in (CONSOLIDATED, STANDALONE):
                    out.setdefault((m[2], basis), url)
    return out


def plan(dossier: dict | None, scrip: str, stored_files: set[str], stored_facts: set[str]) -> dict:
    """What the command does for one company, without any request: ``have`` (facts stored), ``todo`` (file stored, facts not
    yet), ``missing`` (the raw file is not in R2: the filings to download first) and ``no_url`` (memory knows the period
    but never recorded its file's url, so the stored file cannot be found). Each entry is (period, basis, url)."""
    out: dict[str, list] = {"have": [], "todo": [], "missing": [], "no_url": []}
    urls = file_urls(dossier, scrip)
    for (period, basis), url in sorted(urls.items()):
        if key(scrip, period, basis) in stored_facts:
            out["have"].append((period, basis, url))
        elif xbrl_store.key(url) in stored_files:
            out["todo"].append((period, basis, url))
        else:
            out["missing"].append((period, basis, url))
    seen = {p for p, _ in urls}
    for entry in (dossier or {}).get("financial_metrics") or []:
        for row in entry.get("sources") or [{"news_id": entry.get("source_news_id")}]:
            m = _RES_ID.fullmatch(str(row.get("news_id") or ""))
            if m and m[1] == scrip and m[2] not in seen and quarter_index(m[2]):
                seen.add(m[2])
                out["no_url"].append((m[2], "", ""))
    return out


# --- what a file has that memory has no line for ----------------------------------------------------------------------

INTERESTING = re.compile(r"excise|salestax|valueaddedtax|^vat|goodsandservicestax|^gst|discount|rebate|lease|rightofuse|treasury|"
                         r"currentmaturit|intangible|equitymethod|investmentproperty|deferredtax|ownshares", re.I)
INTERESTING_TEXT = re.compile(r"excise|sales tax|\bvat\b|value added tax|\bgst\b|goods (and|&) services tax|discount|rebate|"
                              r"lease liabilit|right.of.use|treasury|current maturit", re.I)


def interesting(facts: Facts) -> set[str]:
    """The element names (and the rows of breakdowns, as ``Element: description``) of a file that bear on screener's treatment,
    so a run says which of them filers really tag (the integrated taxonomy has none for levies, leases or treasury shares)."""
    out = {n for n in facts.element_names() if INTERESTING.search(n)}
    for el, ctx_id, unit, value, _ in facts.rows:
        if el.startswith("DescriptionOf") and isinstance(value, str) and INTERESTING_TEXT.search(value):
            out.add(f"{el}: {value[:80]}")
    return out


# --- the command ------------------------------------------------------------------------------------------------------

MISSING_HEADER = "scrip,symbol,period,basis,url,reason".split(",")


def run(sink, companies: list[tuple[str, str]], *, download: bool = False, client=None, force: bool = False,
        dry_run: bool = False, limit: int | None = None) -> dict:
    """Facts of every stored results file of ``companies`` ((scrip, symbol) pairs); the filings whose file is not stored are
    listed. Reads R2 and memory only: no request goes to NSE unless ``download`` is set and a ``client`` is given, and then
    only for the files not stored, through seed._fetch (the cache, then R2, then ``client.download`` with its pacing, and R2
    keeps what comes) - every such file counts toward FILE_CAP (file_cap.py), and the run stops where the cap or a refusal
    does. ``dry_run`` parses and counts but writes no facts and, with ``download``, lists the files it would fetch and fetches
    none (``would_download`` counts them). ``force`` reads again the files whose facts are stored."""
    from . import seed
    from .nse import FileCapReached, SourceBlockedError, stop_reason

    summary: dict = {"companies": 0, "files_listed": 0, "facts_stored_before": 0, "facts_saved": 0, "not_results": 0,
                     "missing": 0, "no_url": 0, "downloaded": 0, "would_download": 0, "download_failed": 0, "bytes": 0, "facts": 0, "stopped": "",
                     "store_available": xbrl_store.enabled(sink), "dry_run": dry_run, "download": download, "interesting": {},
                     "missing_rows": [], "failed": [], "no_url_companies": 0, "capped": False}
    stored_files = xbrl_store.stored_keys(sink)
    stored_facts = set(sink.list_objects(PREFIX))

    def keep(scrip: str, period: str, basis: str, url: str, data: bytes) -> None:
        doc = parse_facts(data, scrip, url)
        if doc is None:
            summary["not_results"] += 1
            return
        doc["period"] = period      # memory's label of the file: what the cross-check looks it up by
        size = len(dumps(doc))
        if not dry_run:
            save(sink, scrip, period, basis, doc)
        summary["facts_saved"] += 1
        summary["bytes"] += size
        summary["facts"] += doc["n_facts"]
        for name in interesting(Facts(doc)):
            summary["interesting"][name] = summary["interesting"].get(name, 0) + 1

    try:
        for scrip, symbol in (companies[:limit] if limit else companies):
            summary["companies"] += 1
            where = plan(sink.get_dossier(scrip), scrip, stored_files, stored_facts)
            summary["files_listed"] += sum(len(where[k]) for k in ("have", "todo", "missing"))
            summary["facts_stored_before"] += len(where["have"])
            summary["no_url"] += len(where["no_url"])
            summary["no_url_companies"] += bool(where["no_url"])
            for period, basis, url in where["todo"] + (where["have"] if force else []):
                data = xbrl_store.get(sink, url)
                if data:
                    keep(scrip, period, basis, url, data)
            for period, basis, url in where["missing"]:
                summary["missing"] += 1
                summary["missing_rows"].append({"scrip": scrip, "symbol": symbol, "period": period, "basis": basis, "url": url,
                                                "reason": "file not stored"})
                if not (download and url):
                    continue
                if dry_run:      # a dry run downloads nothing: the files are listed, with the count it would fetch
                    summary["would_download"] += 1
                    summary["missing_rows"][-1]["reason"] = "file not stored (dry run: not downloaded)"
                    continue
                if client is None:
                    continue
                try:
                    data = seed._fetch(client, url, None, sink)
                except SourceBlockedError:
                    raise
                except Exception as exc:   # noqa: BLE001 - one dead file is that filing's gap, not the run's
                    summary["download_failed"] += 1
                    summary["failed"].append(f"{scrip} {period}: {type(exc).__name__}")
                    continue
                if data:
                    summary["downloaded"] += 1
                    keep(scrip, period, basis, url, data)
                else:
                    summary["download_failed"] += 1
                    summary["failed"].append(f"{scrip} {period}: no file served")
            for period, _, _ in where["no_url"]:
                summary["missing_rows"].append({"scrip": scrip, "symbol": symbol, "period": period, "basis": "", "url": "",
                                                "reason": "memory recorded no file url for this period"})
    except SourceBlockedError as exc:
        summary["stopped"] = stop_reason(exc)
        summary["capped"] = isinstance(exc, FileCapReached)
    return summary


def to_csv(summary: dict) -> str:
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(MISSING_HEADER)
    for r in summary["missing_rows"]:
        writer.writerow([r[k] for k in MISSING_HEADER])
    return buffer.getvalue()


def to_json(summary: dict) -> str:
    return json.dumps({k: v for k, v in summary.items() if k != "missing_rows"}, ensure_ascii=False, indent=1) + "\n"


def render(summary: dict) -> str:
    n = summary["facts_saved"]
    lines = [f"xbrl-facts{' (dry run: nothing written)' if summary['dry_run'] else ''}:",
             f"companies                      {summary['companies']}",
             f"files listed by memory         {summary['files_listed']}",
             f"facts already stored           {summary['facts_stored_before']}",
             f"facts written this run         {n}" + (f" ({summary['facts']} facts, {summary['bytes'] / 1000:.1f} KB gzipped, "
                                                      f"{summary['bytes'] / n / 1000:.1f} KB a file)" if n else ""),
             f"files not stored (to download) {summary['missing']}",
             f"periods with no file url       {summary['no_url']} ({summary['no_url_companies']} companies)",
             f"downloaded this run            {summary['downloaded']}" + ("" if summary["download"] else " (download not asked for)")
             + (f" (dry run: {summary['would_download']} files would be downloaded, none was)" if summary["dry_run"] and summary["download"] else ""),
             f"not a results file             {summary['not_results']}"]
    if not summary["store_available"]:
        lines.append("this sink has no R2 XBRL store: no stored file can be read")
    if summary["download_failed"]:
        lines.append(f"downloads that failed          {summary['download_failed']}: " + "; ".join(summary["failed"][:10]))
    if summary["stopped"]:
        lines.append("stopped: " + summary["stopped"])
    if summary["interesting"]:
        lines.append("elements and breakdown rows that bear on screener's treatment (files that have them):")
        lines += [f"  {count:5}  {name}" for name, count in sorted(summary["interesting"].items(), key=lambda kv: (-kv[1], kv[0]))[:60]]
    elif n:
        lines.append("no element or breakdown row on levies, leases, treasury shares or discounts in the files read")
    return "\n".join(lines)
