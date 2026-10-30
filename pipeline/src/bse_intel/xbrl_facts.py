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
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime

from . import xbrl, xbrl_store
from .nse import looks_like_xml
from .periods import canonical_period, quarter_index
from .timeutil import today_ist

log = logging.getLogger(__name__)

PREFIX = "raw/xbrl-facts/"
VERSION = 1
TEXT_MAX = 1000
# Text memory reads in full (xbrl_extras.py; TODO 139: the raw file goes after 180 days, so what is cut here is lost): the auditor's
# clause answers (default, fraud, statutory dues), any modified-opinion or audit-qualification statement, the audit committee's
# remarks on a related-party transaction, "other" transaction details and the segment names. Each is read whole up to
# FULL_TEXT_MAX characters; everything else (notes, the whole auditor's report, which run to 35-50 thousand characters) stays at TEXT_MAX.
FULL_TEXT_MAX = 20000
FULL_TEXT = re.compile(r"^(DisclosureInAuditorsReportRelatingTo|RemarksOn|DetailsOfOther|DescriptionOf(ReportableSegment|SingleSegment)$)|Modif|Qualif")
CRORE = 1e7


def key(scrip: str, period: str, basis: str | None) -> str:
    return f"{PREFIX}{scrip}/{period}-{(basis or 'unknown').lower()}.json.gz"


def annual_key(scrip: str, fy: str, basis: str | None) -> str:
    """``raw/xbrl-facts/<scrip>/annual-<FY>-<basis>.json.gz``: an annual report's own XBRL (the MCA Ind AS taxonomy)."""
    return f"{PREFIX}{scrip}/annual-{fy}-{(basis or 'unknown').lower()}.json.gz"


def fy_of(end: date) -> str:
    """The label of the year ending ``end``: FY26 for March 2026; another year end keeps its month ("FY26-09" for September 2025)
    so two companies' years never read alike."""
    return f"FY{end.year % 100:02d}" if end.month == 3 else f"FY{(end.year + 1) % 100:02d}-{end.month:02d}"


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
    data = xbrl.as_utf8(data)
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
    used_contexts, used_units, facts = _collect(contexts, kinds, elements, year_end)
    return {"v": VERSION, "scrip": scrip, "period": result.period, "basis": result.basis, "template": result.template,
            "fy_end_month": result.fy_end_month, "url": url, "file_period": result.period, "n_facts": len(facts),
            "contexts": used_contexts, "units": used_units, "facts": facts}


def _collect(contexts: dict, kinds: dict, elements: list, year_end: int | None, labels: bool = True):
    """(contexts, units, facts) of the stored document from xbrl.py's contexts, unit kinds and fact elements. ``labels`` adds the
    period label xbrl.period_label gives a context (the integrated results files' April-March labels; an annual report's
    contexts get none)."""
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
            label = xbrl.period_label(info, year_end) if labels and "endDate" in info else None
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
            name = xbrl._local(el.tag)
            value = text[:FULL_TEXT_MAX if FULL_TEXT.search(name) else TEXT_MAX]
        facts.append([xbrl._local(el.tag), ctx, unit, value, _decimals(el.get("decimals"))])
    return used_contexts, used_units, facts


def _bare_result(contexts: dict, text_facts: dict, year_end: int | None) -> xbrl.XbrlResult:
    """Basis, latest period and year end of a results file xbrl.parse kept nothing of, from the file's own text facts and dates."""
    nature = " ".join(v for k, v in text_facts.items() if "Standalone" in k or "Consolidated" in k or k == "NatureOfReport").lower()
    basis = "CONSOLIDATED" if "consolidated" in nature else "STANDALONE" if "standalone" in nature else None
    ends = [c["endDate"] for c in contexts.values() if not c["dims"] and c.get("endDate")]
    period = xbrl.canonical_period(f"quarter ended {max(ends):%d.%m.%Y}") if ends else None
    return xbrl.XbrlResult("RESULTS", basis, period, fy_end_month=year_end)


def parse_annual_facts(data: bytes, scrip: str = "", url: str = "") -> dict | None:
    """An annual report's own XBRL (the MCA Ind AS taxonomy, ``annual_xbrl.py``) as the stored document, ``kind`` "annual": every
    fact with its context. Its contexts differ from the integrated results filing's: the year is a 12-month duration (current and
    prior year, 365 or 366 days) and the balance sheet an instant at the year end; there are no quarters, so no period labels,
    and the facts are found by end date and months as for any file. None when the file is no XBRL instance, has no 12-month period,
    or holds none of revenue, profit or assets (a sustainability report, BRSR, is not an annual report's statements). The basis is
    the file's own NatureOfReportStandaloneConsolidated; ``fy`` names the year (``fy_of``) and ``year_end`` its last day. Text blocks
    are cut at TEXT_MAX characters (the board's report and the notes run to many pages). L&T's standalone annual file has no
    ``DescriptionOfOtherExpenses`` row, so its finance-services finance cost cannot be applied from the annual report."""
    data = xbrl.as_utf8(data)
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    contexts = xbrl._contexts(root)
    elements = list(xbrl._fact_elements(root))
    if not contexts or not elements:
        return None
    names = {xbrl._local(el.tag) for el in elements}
    if not names & {"RevenueFromOperations", "ProfitLossForPeriod", "Assets"}:
        return None
    years = [c["endDate"] for c in contexts.values() if not c["dims"] and c.get("startDate") and c.get("endDate")
             and 11 <= (xbrl._months(c) or 0) <= 13]
    if not years:
        return None
    end = max(years)
    text_facts = {xbrl._local(el.tag): el.text.strip() for el in elements if el.get("unitRef") is None and not contexts.get(el.get("contextRef"), {}).get("dims")}
    nature = text_facts.get("NatureOfReportStandaloneConsolidated", "").lower()
    basis = "CONSOLIDATED" if "consolidated" in nature else "STANDALONE" if "standalone" in nature else None
    used_contexts, used_units, facts = _collect(contexts, xbrl._units(root), elements, None, labels=False)
    return {"v": VERSION, "kind": "annual", "scrip": scrip, "fy": fy_of(end), "year_end": end.isoformat(), "period": fy_of(end),
            "basis": basis, "template": "MCA-INDAS", "fy_end_month": end.month, "url": url, "n_facts": len(facts),
            "contexts": used_contexts, "units": used_units, "facts": facts}


def save_annual(sink, scrip: str, fy: str, basis: str | None, doc: dict) -> int:
    body = dumps(doc)
    sink.put_object(annual_key(scrip, fy, basis), body, content_type="application/gzip")
    return len(body)


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
        self.kind = doc.get("kind") or "results"          # "results" (an integrated results file) or "annual" (an annual report's XBRL)

    @property
    def source(self) -> str:
        """Where the facts come from, for a pair's record: the annual report's own XBRL, or the integrated results file."""
        return "annual_report_xbrl" if self.kind == "annual" else "q4_integrated_file"

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
                  instant: date | None = None, joined: bool = False) -> list[tuple[str, str, float]]:
        """(element, description, value in crore) of every dimensional money fact named in ``value_names`` at the period whose
        context carries a ``DescriptionOf...`` text matching the regex ``description`` (a filer's own line inside a breakdown,
        e.g. "Excise duty" inside other expenses).

        ``joined`` (the screener rows, screener_view.py; the reader fix of branch ``screener-rules`` 7e30240): an annual report tags a
        row's description on the year's DURATION and its amount on the INSTANT at the year end, both with the same dimension member
        (Infosys FY26: "Lease liabilities" 6,016 Cr and "Current lease liabilities" 3,160 Cr, whose sum is screener's 9,176 of
        Borrowings), and names the non-current text ``DescriptionOther...`` (no "Of"): every ``Description...`` text is read, and an
        amount with no description of its own context takes the description of the duration that ends on its date with the same
        dimensions. Off by default, so the cross-check's classes do not move until its on/off comparison is made."""
        rx = re.compile(description, re.I)
        prefix = "Description" if joined else "DescriptionOf"
        texts: dict[str, list[str]] = {}
        for el, ctx_id, unit, value, _ in self.rows:
            if el.startswith(prefix) and isinstance(value, str):
                texts.setdefault(ctx_id, []).append(value)
        by_dims: dict[tuple, list[str]] = {}
        if joined:
            for ctx_id, found in texts.items():
                c = self.contexts.get(ctx_id) or {}
                if c.get("d") and c.get("e"):
                    by_dims.setdefault((frozenset(c["d"].items()), c["e"]), []).extend(found)
        out, seen = [], set()
        for el, ctx_id, unit, value, _ in self.rows:
            if el not in value_names or not self._is_money(unit) or isinstance(value, str) or not self._at(ctx_id, end, months, instant):
                continue
            own = texts.get(ctx_id)
            if own is None and joined:
                c = self.contexts.get(ctx_id) or {}
                own = by_dims.get((frozenset(c["d"].items()), c["i"])) if c.get("d") and c.get("i") else None
            for text in own or ():
                # a row once: the older files tag a row's year to date with the quarter's own dates (Titan Q2FY24: Advertising
                # 268 Cr for the quarter and 542 Cr to date, both Jul-Sep), and the quarter's comes first in the file
                # one row a text, even across members: the older results files tag a row's year to date with the quarter's dates
                # AND its own member, so counting members apart takes the excise twice (Reliance Q2FY24 9,412 Cr twice; measured in
                # screener-rows run 40725169900, 24 quarters). Two different rows sharing one text stay one: rarer, and visible
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


def load_annual(sink, scrip: str, fy: str, basis: str | None) -> Facts | None:
    """The stored facts of one company's annual-report XBRL for a financial year and basis, or None."""
    try:
        body = sink.get_object(annual_key(scrip, fy, basis))
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


# --- every results file NSE lists (``--from-nse``, owner 28 Oct 2026: "download now every results XBRL and annual-report XBRL") ----

MAX_SHARDS = 16           # owner, 28 Oct 2026: 8 parallel downloads, then "Can we take it to 16" (the same day)
SINCE = "2020-04-01"      # the seed's own --since default: the selection below is the seed's (latest SEED_QUARTERS, older March quarters)
FACTS_QUARTERS = 13       # screener's 13 (stock-page audit, 30 Oct 2026: with the seed's 12, 1,159 of 1,229 companies on the site had no
                          # Q1FY24 and 821 a hole in their quarters; the test run 40837101219 with 13 fetched 90 files of Q1FY24 and Q2FY24)
MARKER_V = 3              # the marker's version: one written under another selection is no marker, its company is listed again
                          # (3: 13 quarters, 30 Oct 2026; 2 was the 13-quarter test run of 29 Oct)
LIST_REFRESH_DAYS = 7     # a company whose files are all stored is not listed again for this many days (its marker, ``listed_key``)
FAILED_SAMPLES = 200      # failed files named in the summary; every one is counted by reason
GONE_STATUSES = ("http_404", "http_410")     # a file NSE lists and does not serve: remembered in the marker, tried again after LIST_REFRESH_DAYS
GONE_REASONS = GONE_STATUSES + ("too_large", "not_results")   # likewise a file over the size limit, or one that holds no results: a rerun would meet the same
REFUSAL_STATUSES = (401, 403, 429, 503)      # the client's own BLOCKING_STATUS and the archive host's 503: the shard stops
ODD_LIMIT = 3             # good-status answers that are neither XML nor JSON, in a row: a block page the keyword list misses, a refusal
HEAD_BYTES = 2000         # of a response body kept to tell a challenge page from a file (300 bytes are logged)
CHALLENGE = re.compile(rb"cloudflare|akamai|just a moment|attention required|access denied|incapsula|captcha|cf-chl|cf-ray|"
                       rb"edgesuite|reference #\d", re.I)
TIME_VALUE = re.compile(r"\d{1,2}-[A-Za-z]{3}-\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|\d{1,2}:\d{2}")
# the timestamp fields NSE's two lists are known to carry (nse.py: broadcast_Date, revised_Date, creation_Date, qe_Date in the integrated
# list; filingDate, broadCastDate, exchdisstime, fromDate, toDate in the older one), a column each; every other field of the raw row
# whose value looks like a date or a time goes into ``times``, and ``raw_keys`` names every field the row has
TIME_FIELDS = ("broadcast_Date", "revised_Date", "creation_Date", "qe_Date", "filingDate", "broadCastDate", "exchdisstime",
               "fromDate", "toDate")
LISTING_HEADER = (["scrip", "symbol", "period", "basis", "status", "list", "url", "filed_at", "period_end", "taxonomy", "revised",
                   "name_stamp_raw", "name_stamp_iso"] + list(TIME_FIELDS) + ["times", "raw_keys"])


def shard_slice(companies: list[tuple[str, str]], index: int, count: int) -> list[tuple[str, str]]:
    """The ``index``-th of ``count`` slices of the company list: sorted by scrip, then every ``count``-th company from the
    ``index``-th, so each shard gets a like mix of sizes and the slices are the same on every run and cover everyone once."""
    if not 0 <= index < count <= MAX_SHARDS:
        raise ValueError(f"shard {index}/{count}: need 0 <= I < N <= {MAX_SHARDS}")
    return sorted(companies)[index::count]


def listed_key(scrip: str) -> str:
    """``raw/xbrl-facts/<scrip>/_listed.json``: what NSE's list gave for the company on the day it was last asked (the periods
    and bases chosen, and the files NSE listed but did not serve), so a rerun can skip the list while every period is stored."""
    return f"{PREFIX}{scrip}/_listed.json"


def select_files(rows) -> list[tuple[str, str, object]]:
    """(period, basis, row) of the files to keep from NSE's results list: the seed's own selection (``seed._nse_quarters``: consolidated
    over standalone, the integrated filing over the older list's row, then the later filing, from SINCE; ``seed._recent_and_years``:
    the latest quarters and the March quarters before them), with BOTH bases of each chosen quarter (the seed keeps one, and the
    standalone files of a consolidated filer apart). Newest first. The latest FACTS_QUARTERS (screener shows 13; NSE lists Q2FY24
    with a file for HDFCBANK, TCS, INFY, LT, MARUTI, KOTAKBANK, ULTRACEMCO, JSWSTEEL, BAJAJ-AUTO and NESTLEIND, measured 29 Oct 2026,
    but the comparison starts at FY26)."""
    from . import seed

    by_basis: dict[bool, dict] = {True: {}, False: {}}
    for row in sorted(rows, key=lambda r: (not getattr(r, "legacy", False), r.filed_at)):
        if not row.period_end or row.period_end < SINCE:
            continue
        label = canonical_period(f"quarter ended {row.period_end[8:10]}.{row.period_end[5:7]}.{row.period_end[:4]}")
        if label:
            by_basis[bool(row.consolidated)][label] = row
    chosen = seed._recent_and_years({**by_basis[False], **by_basis[True]}, FACTS_QUARTERS)
    out = [(label, "CONSOLIDATED" if consolidated else "STANDALONE", row)
           for consolidated in (True, False) for label, row in by_basis[consolidated].items() if label in chosen]
    return sorted(out, key=lambda t: (t[2].period_end, t[1] == "CONSOLIDATED"), reverse=True)


_NAME_STAMP = re.compile(r"(?<!\d)(\d{14})(?!\d)")


def file_name_stamp(url: str) -> tuple[str, str]:
    """(the 14 digits in the file name, as an ISO time) - "INTEGRATED_FILING_INDAS_1664294_06052026105412_WEB.xml" holds
    06052026105412, read as DDMMYYYYHHMMSS like the shareholding names (nse.shareholding_filed_at); ("", "") when the name has none;
    the digits alone when they are no valid time. The clock NSE stamps it with is for the later timing measurement to settle."""
    m = _NAME_STAMP.search(url.rsplit("/", 1)[-1])
    if not m:
        return "", ""
    try:
        return m[1], datetime.strptime(m[1], "%d%m%Y%H%M%S").isoformat()
    except ValueError:
        return m[1], ""


def _is_refusal(info: dict) -> bool:
    """A refusal by its status, or a Cloudflare / Akamai challenge page served with a good status (anything that is neither
    JSON nor XML and carries the challenge's own words)."""
    if info["status"] in REFUSAL_STATUSES:
        return True
    head = info["head"]
    return (200 <= info["status"] < 300 and not info["xml"] and head.lstrip()[:1] not in (b"{", b"[")
            and bool(CHALLENGE.search(head)))


class Tap:
    """What the NSE client does not tell: the last answer's status, size, first bytes (the client raises a refusal without its
    body and returns None for a file it will not use without saying why), and NSE's raw list rows (the client's parsed rows keep one
    date, the raw row has every timestamp). Attached from outside, with no change to the client: an httpx response hook on its own
    ``httpx.Client`` and the ``raw`` store hook it already has for every JSON answer."""

    def __init__(self) -> None:
        self.last: dict | None = None
        self.refusal: dict | None = None
        self.rows: dict[str, tuple[str, dict]] = {}

    def reset(self) -> None:
        self.last = None
        self.refusal = None

    def hook(self, response) -> None:
        url = response.request.url
        if url.path in ("", "/") and (url.host or "").endswith("nseindia.com"):
            return      # the client's warm-up visit to the home page: it tolerates a 403 there on purpose (nse.py warm_up), so it is no refusal
        try:
            body = response.read()
        except Exception:   # noqa: BLE001 - a body that cannot be read is no body
            body = b""
        head = body[:HEAD_BYTES]
        info = {"status": response.status_code, "url": str(response.request.url), "size": len(body), "head": head,
                "xml": looks_like_xml(head), "type": response.headers.get("content-type", "")}
        self.last = info
        if self.refusal is None and _is_refusal(info):
            self.refusal = info

    def save(self, url: str, params, status: int, body: bytes) -> None:      # the client's raw-store call, for every JSON answer
        try:
            data = json.loads(body)
        except ValueError:
            return
        rows = data.get("data") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return
        kind = "integrated" if "integrated" in url else "older"
        for row in rows:
            link = str(row.get("xbrl") or "").strip() if isinstance(row, dict) else ""
            if link:
                self.rows[link if link.startswith("http") else f"https://nsearchives.nseindia.com/{link.lstrip('/')}"] = (kind, row)


class _Both:
    def __init__(self, *stores) -> None:
        self.stores = stores

    def save(self, *args) -> None:
        for store in self.stores:
            store.save(*args)


def attach(client) -> Tap:
    """A Tap on the client: a client with neither hook (a test double) gives a Tap that stays empty."""
    tap = Tap()
    inner = getattr(client, "_client", None)
    hooks = getattr(inner, "event_hooks", None)
    if isinstance(hooks, dict):
        inner.event_hooks = {**hooks, "response": [*hooks.get("response", []), tap.hook]}
    if hasattr(client, "raw"):
        client.raw = tap if client.raw is None else _Both(client.raw, tap)
    return tap


def failure_reason(exc: Exception | None, info: dict | None, limit: int) -> str:
    """Why a call gave no file, as one short key for the summary's count."""
    if info:
        if 200 <= info["status"] < 300:
            return "too_large" if info["size"] > limit else "not_xml"
        return f"http_{info['status']}"
    if exc is not None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status:
            return f"http_{status}"
        return "request_failed" if isinstance(exc, RuntimeError) else type(exc).__name__
    return "no_response"


class Guard:
    """Every call to NSE of a shard goes through ``call``: a refusal (a 401, 403, 429 or 503, or a challenge page, seen in any answer of
    the call, retries included) stops the shard at once, logged with its status and the first 300 bytes of its body; any other
    failure comes back as a reason and the run goes on. The file cap still stops the run as the planned stop it is."""

    def __init__(self, client) -> None:
        warm_up = getattr(client, "warm_up", None)
        if callable(warm_up):
            warm_up()      # the client's lazy cookie visit, before the tap: its 403 on the home page is tolerated, never a refusal
        self.tap = attach(client)
        self.refusal: dict | None = None
        self.last: dict | None = None      # the last answer of the last call: status, size, head, xml
        self.odd = {"file": 0, "list": 0}      # block-like pages in a row, of files and of lists apart (see ODD_LIMIT)

    def _stop(self, exc: Exception | None, note: str = ""):
        from .nse import SourceBlockedError

        info = self.tap.refusal or self.tap.last
        if info and self.refusal is None:
            self.refusal = {"status": info["status"], "url": info["url"], "size": info["size"],
                            "body_head": info["head"][:300].decode("utf-8", "replace")}
            log.error("NSE refused the shard: HTTP %s for %s; first 300 bytes of the body: %r", info["status"], info["url"],
                      info["head"][:300])
        if isinstance(exc, SourceBlockedError):
            raise exc
        status = info["status"] if info else "?"
        raise SourceBlockedError(f"NSE refused the request (HTTP {status}){note}: " + (info["url"] if info else ""))

    def call(self, fn, *args, limit: int = 1 << 62, kind: str = "file", **kwargs):
        """(result, reason): ``reason`` is None when the call gave something; SourceBlockedError on a refusal."""
        from .nse import FileCapReached, SourceBlockedError

        self.tap.reset()
        try:
            result = fn(*args, **kwargs)
        except FileCapReached:
            raise
        except SourceBlockedError as exc:
            self._stop(exc)
        except Exception as exc:   # noqa: BLE001 - one dead file or list is that company's gap, not the shard's
            self.last = self.tap.last
            if self.tap.refusal:      # a 503 the client retried and gave up on (it raises RuntimeError for those)
                self._stop(exc)
            self._note_odd(kind)
            return None, failure_reason(exc, self.tap.last, limit)
        self.last = self.tap.last
        if self.tap.refusal:          # a challenge page served with a good status, or a refusal met on the way
            self._stop(None, " [challenge page or refusal in the answer]")
        if result is None or result == b"":
            self._note_odd(kind)
            return None, failure_reason(None, self.tap.last, limit)
        self.odd[kind] = 0
        return result, None

    def _note_odd(self, kind: str) -> None:
        """Called when a call gave nothing. A block page the keyword list does not know: a good status with a body that is neither
        XML nor JSON (an HTML page for a list or a file). One is a counted failure; ODD_LIMIT in a row, across companies, is a
        refusal and stops the shard. Any other outcome of the same kind (list or file) ends the run of them."""
        info = self.tap.last
        if info and 200 <= info["status"] < 300 and info["head"].strip() and not info["xml"] \
                and info["head"].lstrip()[:1] not in (b"{", b"["):
            self.odd[kind] += 1
            if self.odd[kind] >= ODD_LIMIT:
                self._stop(None, f" [{self.odd[kind]} block-like {kind} pages in a row: a good status with a body that is neither XML nor JSON]")
        else:
            self.odd[kind] = 0


class ListingCsv:
    """The listing rows as they are decided, one line each, flushed at once: a run that is stopped, killed or timed out leaves the
    rows it had reached (the CSV of ``--from-nse``: status and every timestamp NSE's row carries, for the timing measurement)."""

    def __init__(self, path) -> None:
        import csv

        self._fh = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._fh, LISTING_HEADER, lineterminator="\n", extrasaction="ignore")
        self._writer.writeheader()
        self._fh.flush()

    def __call__(self, row: dict) -> None:
        self._writer.writerow(row)
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


class _OutOfTime(Exception):
    """The run's time budget is spent: stop between two files, with everything so far saved."""


# --- the command ------------------------------------------------------------------------------------------------------

MISSING_HEADER = "scrip,symbol,period,basis,url,reason".split(",")


ANNUAL_YEARS = 3     # the latest years of annual reports kept a basis: a file is about 7 MB and screener's columns are read against few


ANNUAL_FILING_DAYS = 60    # the earliest an annual report's XBRL can be listed after its March year end (the report itself comes in June)
_ANNUAL_KEY = re.compile(r"annual-FY(\d{2})-(?:consolidated|standalone|unknown)\.json\.gz$")


def newest_filed_year(today: date) -> int:
    """The latest year NSE could have an annual report for: the last March year end at least ANNUAL_FILING_DAYS before ``today``
    (28 Oct 2026: FY26, the year to 31 March 2026), as the two-digit year."""
    year = today.year if date(today.year, 3, 31).toordinal() + ANNUAL_FILING_DAYS <= today.toordinal() else today.year - 1
    return year % 100


def annual_covered(scrip: str, stored_facts: set[str], today: date, annual_years: int = ANNUAL_YEARS) -> bool:
    """Whether the company's stored annual facts cover EVERY year the run would keep: the ``annual_years`` years from the newest NSE
    could have filed down, each with at least one stored basis. Then the list need not be asked for again (a rerun makes no NSE
    request for it). A company half filled (FY26 stored by a dry run or a FILE_CAP stop, FY25 and FY24 missing) is not covered: its
    list is asked for again, and only the files not yet stored are read or fetched. The newest year alone proved nothing."""
    have = {int(m[1]) for k in stored_facts if k.startswith(f"{PREFIX}{scrip}/") and (m := _ANNUAL_KEY.search(k))}
    newest = newest_filed_year(today)
    return all((newest - back) % 100 in have for back in range(max(1, annual_years)))


def is_ind_as(report_type: str) -> bool:
    """An Ind AS statements file; a BRSR (sustainability) file, or a type nobody named, is not."""
    kind = (report_type or "").upper()
    return "IND" in kind and "BRSR" not in kind


def fetch_annual(sink, client, url: str) -> bytes | None:
    """One annual-report XBRL file the way the pipeline reads it (``Pipeline._xbrl_file`` on the annual-report path): our copy in
    R2 first, else ``client.download`` with the annual-report size limit (``nse.ANNUAL_REPORT_MAX_BYTES``), at the client's own
    pace, one file for FILE_CAP; R2 keeps what comes (xbrl_store)."""
    from .nse import ANNUAL_REPORT_MAX_BYTES

    data = xbrl_store.get(sink, url)
    if data:
        return data
    data = client.download(url, max_bytes=ANNUAL_REPORT_MAX_BYTES)
    if data:
        xbrl_store.put(sink, url, data)
    return data


def run(sink, companies: list[tuple[str, str]], *, download: bool = False, client=None, force: bool = False,
        dry_run: bool = False, limit: int | None = None, annual: bool = False, annual_years: int = ANNUAL_YEARS,
        today: date | None = None, from_nse: bool = False, time_budget: float | None = None, row_sink=None, progress=None,
        clock=time.monotonic) -> dict:
    """Facts of every stored results file of ``companies`` ((scrip, symbol) pairs); the filings whose file is not stored are
    listed. Reads R2 and memory only: no request goes to NSE unless ``download`` is set and a ``client`` is given, and then
    only for the files not stored, through seed._fetch (the cache, then R2, then ``client.download`` with its pacing, and R2
    keeps what comes) - every such file counts toward FILE_CAP (file_cap.py), and the run stops where the cap or a refusal
    does. ``dry_run`` parses and counts but writes no facts and, with ``download``, lists the files it would fetch and fetches
    none (``would_download`` counts them). ``force`` reads again the files whose facts are stored.

    ``annual`` also keeps the facts of each company's annual-report XBRL (Ind AS only, never a BRSR file) for its latest
    ``annual_years`` years and each basis, as ``annual-<FY>-<basis>``. NSE's annual-report list is one request a company (a list, not
    a file: it does not count toward FILE_CAP), so it needs the ``client``; a file is read from R2 when stored, and fetched
    (``fetch_annual``: NSE's pace, FILE_CAP) only with ``download`` and never in a dry run. The list is not asked for again for a
    company whose stored annual facts cover every year kept (``annual_covered``) unless ``force``, nor in a dry run without
    ``download`` (``force`` or not: nothing would be fetched): ``annual_list_skipped`` counts both, ``annual_lists`` the requests made.

    ``from_nse`` (``--from-nse``, owner 28 Oct 2026) does not ask memory which files exist: each company's results are listed from NSE's
    own list (``seed._rows_or_partial``, the call the seed makes; one company's list is not a file and does not count toward FILE_CAP),
    ``select_files`` picks the seed's latest quarters in both bases, and each file whose facts are not stored goes through
    ``seed._fetch`` (the cache, then R2, then ``client.download`` at the client's own pace, with the annual-report size limit; R2
    keeps the file) and its facts are saved at once. It writes NO memory and NO dossier. A company whose marker (``listed_key``) is
    under LIST_REFRESH_DAYS old and whose every period is stored (or was NSE's 404) is not listed again. ``dry_run`` without
    ``download`` asks NSE for nothing; with it the lists are asked for and no file is fetched. Any 401, 403, 429, 503 or challenge
    page stops the run at once (``refusal`` in the summary: status and the first 300 bytes of the body); a file that comes back empty
    for another reason (HTTP status, size limit, not XML) is counted in ``failed_reasons`` and the run goes on. ``row_sink`` gets one
    dict per listed row (LISTING_HEADER) as its status is known; ``progress`` is called with the summary about once a minute;
    ``time_budget`` (seconds on ``clock``) ends the run cleanly between two files (``out_of_time``)."""
    from . import seed
    from .nse import ANNUAL_REPORT_MAX_BYTES, FileCapReached, SourceBlockedError, stop_reason

    if from_nse and not dry_run and (not download or client is None):
        raise ValueError("from_nse downloads: it needs download=True and a client (or dry_run=True)")
    deadline = clock() + time_budget if time_budget else None
    guard = Guard(client) if (from_nse and client is not None and not (dry_run and not download)) else None

    summary: dict = {"companies": 0, "files_listed": 0, "facts_stored_before": 0, "facts_saved": 0, "not_results": 0,
                     "missing": 0, "no_url": 0, "downloaded": 0, "would_download": 0, "download_failed": 0, "bytes": 0, "facts": 0, "stopped": "",
                     "store_available": xbrl_store.enabled(sink), "dry_run": dry_run, "download": download, "interesting": {},
                     "missing_rows": [], "failed": [], "no_url_companies": 0, "capped": False,
                     "annual": annual, "annual_lists": 0, "annual_have": 0, "annual_saved": 0, "annual_missing": 0,
                     "annual_downloaded": 0, "annual_bytes": 0, "annual_not_ind_as": 0, "annual_skipped": "",
                     "annual_list_skipped": {"covered": 0, "dry_run": 0},
                     "from_nse": from_nse, "lists": 0, "lists_skipped": {"stored": 0, "dry_run": 0}, "partial_lists": 0,
                     "list_failed": 0, "listed_files": 0, "skipped_stored": 0, "from_store": 0, "not_reached": 0,
                     "failed_reasons": {}, "refusal": None, "out_of_time": False, "store_full": False, "company_errors": 0,
                     "infra_stop": False}
    stored_files = xbrl_store.stored_keys(sink)
    stored_facts = set(sink.list_objects(PREFIX))

    def keep(scrip: str, period: str, basis: str, url: str, data: bytes) -> bool:
        """The file's facts saved (counted only, in a dry run); False when the file holds no results."""
        doc = parse_facts(data, scrip, url)
        if doc is None:
            summary["not_results"] += 1
            return False
        doc["period"] = period      # memory's label of the file: what the cross-check looks it up by
        size = len(dumps(doc))
        if not dry_run:
            save(sink, scrip, period, basis, doc)
        summary["facts_saved"] += 1
        summary["bytes"] += size
        summary["facts"] += doc["n_facts"]
        for name in interesting(Facts(doc)):
            summary["interesting"][name] = summary["interesting"].get(name, 0) + 1
        return True

    def keep_annual(scrip: str, fy: str, basis: str, url: str, data: bytes) -> None:
        doc = parse_annual_facts(data, scrip, url)
        if doc is None:
            summary["not_results"] += 1
            return
        size = len(dumps(doc))
        if not dry_run:
            save_annual(sink, scrip, fy, basis, doc)       # NSE's own year and basis name the file, as the "have" check looks it up
        summary["annual_saved"] += 1
        summary["annual_bytes"] += size
        summary["facts"] += doc["n_facts"]

    annual_rest: dict[str, tuple[str, list]] = {}      # company -> (symbol, its older years' rows), for the second pass (newest year first)

    def annual_company(scrip: str, symbol: str, phase: str = "newest") -> None:
        """The company's annual-report XBRL, newest year first. Phase "newest" asks for the list (one request) and does the newest
        year's files of every basis, keeping the older years' rows; phase "rest" (a second pass over the companies, after every
        company's newest year) does those. A capped or stopped run thus has every company's newest year before any older one."""
        if phase == "rest":
            symbol, rows = annual_rest.pop(scrip, (symbol, []))
            annual_rows(scrip, symbol, rows)
            return
        if dry_run and not download:
            summary["annual_list_skipped"]["dry_run"] += 1     # nothing would be fetched, --force or not: no request for a list
            return
        if not force and annual_covered(scrip, stored_facts, today or today_ist(), annual_years):
            summary["annual_list_skipped"]["covered"] += 1     # every year kept is stored already
            return
        if client is None:
            summary["annual_skipped"] = "no NSE client: the annual-report list is one request a company"
            return
        if guard is not None:
            listing, why = guard.call(client.annual_reports, symbol, kind="list")
            summary["annual_lists"] += 1
            if why:
                note_failure(why, f"{scrip} annual list", guard.last, "")
                return
        else:
            try:
                listing = client.annual_reports(symbol)
                summary["annual_lists"] += 1
            except SourceBlockedError:
                raise
            except Exception as exc:   # noqa: BLE001 - one company's list failing is a reason, not a stop
                summary["failed"].append(f"{scrip} annual list: {type(exc).__name__}")
                return
        rows = [r for r in listing if is_ind_as(r.report_type)]
        summary["annual_not_ind_as"] += len(listing) - len(rows)
        keep_years = set(sorted({r.to_year for r in rows}, reverse=True)[:annual_years])
        chosen = sorted((r for r in rows if r.to_year in keep_years), key=lambda r: r.to_year, reverse=True)    # newest year first
        newest = [r for r in chosen if chosen and r.to_year == chosen[0].to_year]
        older = chosen[len(newest):]
        if older:
            annual_rest[scrip] = (symbol, older)
        annual_rows(scrip, symbol, newest)

    def annual_rows(scrip: str, symbol: str, rows: list) -> None:
        for row in rows:
            fy = f"FY{row.to_year % 100:02d}"
            if annual_key(scrip, fy, row.basis) in stored_facts and not force:
                summary["annual_have"] += 1
                continue
            data = None
            if xbrl_store.key(row.xbrl_url) in stored_files:
                data = xbrl_store.get(sink, row.xbrl_url)
            else:
                summary["annual_missing"] += 1
                summary["missing_rows"].append({"scrip": scrip, "symbol": symbol, "period": f"annual-{fy}", "basis": row.basis,
                                                "url": row.xbrl_url, "reason": "file not stored"})
                if download and dry_run:
                    summary["would_download"] += 1
                    summary["missing_rows"][-1]["reason"] = "file not stored (dry run: not downloaded)"
                elif download and guard is not None:
                    check_time()
                    data, why = guard.call(fetch_annual, sink, client, row.xbrl_url, limit=ANNUAL_REPORT_MAX_BYTES)
                    if why:
                        note_failure(why, f"{scrip} annual {fy}", guard.last, row.xbrl_url)
                    else:
                        summary["annual_downloaded"] += 1
                elif download:
                    try:
                        data = fetch_annual(sink, client, row.xbrl_url)
                    except SourceBlockedError:
                        raise
                    except Exception as exc:   # noqa: BLE001
                        summary["download_failed"] += 1
                        summary["failed"].append(f"{scrip} annual {fy}: {type(exc).__name__}")
                    else:
                        summary["annual_downloaded"] += bool(data)
                        if data is None:
                            summary["download_failed"] += 1
                            summary["failed"].append(f"{scrip} annual {fy}: no file served")
            if data:
                keep_annual(scrip, fy, row.basis, row.xbrl_url, data)

    def check_time() -> None:
        if deadline is not None and clock() >= deadline:
            raise _OutOfTime

    def note_failure(reason: str, what: str, info: dict | None, url: str, counter: str = "download_failed") -> None:
        """A call that gave no file or list for a reason that does not stop the run: counted by reason, named (the first
        FAILED_SAMPLES), and logged with the answer's status, size and whether the body looked like XML where it is known."""
        summary[counter] += 1
        label = reason if counter != "list_failed" else f"list:{reason}"
        summary["failed_reasons"][label] = summary["failed_reasons"].get(label, 0) + 1
        if len(summary["failed"]) < FAILED_SAMPLES:
            summary["failed"].append(f"{what}: {label}")
        log.warning("xbrl-facts %s: nothing kept (%s): HTTP %s, %s bytes, body looked like XML: %s %s", what, label,
                    info["status"] if info else "unknown", info["size"] if info else "unknown",
                    info["xml"] if info else "unknown", url)

    def emit(scrip: str, symbol: str, label: str, basis: str, row, status: str) -> None:
        """One CSV line for a listed row with its status and every timestamp the raw row carries (``Tap.rows``)."""
        if row_sink is None:
            return
        kind, raw = guard.tap.rows.get(row.xbrl_url, ("", {})) if guard is not None else ("", {})
        stamp, stamp_iso = file_name_stamp(row.xbrl_url)
        record = {"scrip": scrip, "symbol": symbol, "period": label, "basis": basis, "status": status, "list": kind,
                  "url": row.xbrl_url, "filed_at": row.filed_at, "period_end": row.period_end, "taxonomy": row.taxonomy,
                  "revised": row.revised, "name_stamp_raw": stamp, "name_stamp_iso": stamp_iso,
                  "times": json.dumps({k: v for k, v in raw.items() if isinstance(v, str) and TIME_VALUE.search(v)},
                                      ensure_ascii=False, sort_keys=True),
                  "raw_keys": "|".join(sorted(raw))}
        record.update({name: raw.get(name) or "" for name in TIME_FIELDS})
        row_sink(record)

    def listing_covered(scrip: str) -> bool:
        """Whether the company's marker says its list need not be asked for: written under LIST_REFRESH_DAYS ago, and every period it
        names has its facts stored (or was a file NSE listed and did not serve). No request: the folder was listed once at the start."""
        if force or listed_key(scrip) not in stored_facts:
            return False
        try:
            doc = json.loads(sink.get_object(listed_key(scrip)))
            if doc.get("v") != MARKER_V:
                return False
            age = ((today or today_ist()) - date.fromisoformat(doc["listed_on"])).days
            gone = {(p, b) for p, b, _ in doc.get("gone", [])}
            return 0 <= age < LIST_REFRESH_DAYS and all((p, b) in gone or key(scrip, p, b) in stored_facts
                                                         for p, b in doc.get("files", []))
        except Exception:   # noqa: BLE001 - a marker that cannot be read is no marker: the list is asked for
            return False

    def nse_company(scrip: str, symbol: str) -> None:
        if dry_run and not download:
            summary["lists_skipped"]["dry_run"] += 1      # nothing would be fetched and the list is a request: none is made
            return
        if listing_covered(scrip):
            summary["lists_skipped"]["stored"] += 1       # every period of its last list is stored: no request at all
            return
        check_time()
        guard.tap.rows.clear()
        stats = seed.SeedStats()
        listed, why = guard.call(seed._rows_or_partial, client, symbol, stats, scrip, kind="list")
        summary["lists"] += 1
        if why:
            note_failure(why, f"{scrip} list", guard.last, "", "list_failed")
            return
        partial = bool(stats.failures)      # the integrated list failed and only the older one came back: not a complete list
        summary["partial_lists"] += partial
        selected = select_files(listed)
        summary["listed_files"] += len(selected)
        summary["files_listed"] += len(selected)
        gone: list[list[str]] = []
        for index, (label, basis, row) in enumerate(selected):
            try:
                gone += file_of_company(scrip, symbol, label, basis, row)
            except (SourceBlockedError, _OutOfTime):
                for rest_label, rest_basis, rest_row in selected[index:]:
                    summary["not_reached"] += 1
                    emit(scrip, symbol, rest_label, rest_basis, rest_row, "not_reached")
                raise
        if not dry_run and not partial:
            marker = {"v": MARKER_V, "listed_on": (today or today_ist()).isoformat(), "symbol": symbol,
                      "files": [[label, basis] for label, basis, _ in selected], "gone": gone}
            sink.put_object(listed_key(scrip), json.dumps(marker, separators=(",", ":")).encode(), content_type="application/json")

    def file_of_company(scrip: str, symbol: str, label: str, basis: str, row) -> list[list[str]]:
        """One listed file: skipped when its facts are stored, else read from R2 or fetched, its facts saved at once. The
        [period, basis, reason] of a file NSE does not serve (404) comes back for the company's marker."""
        if key(scrip, label, basis) in stored_facts and not force:
            summary["facts_stored_before"] += 1
            summary["skipped_stored"] += 1
            emit(scrip, symbol, label, basis, row, "skipped_stored")
            return []
        data, why, source = None, None, ""
        if xbrl_store.key(row.xbrl_url) in stored_files:
            data = xbrl_store.get(sink, row.xbrl_url)
            source = "from_store" if data else ""
        if not data:
            summary["missing"] += 1
            if dry_run:
                summary["would_download"] += 1
                emit(scrip, symbol, label, basis, row, "would_fetch")
                return []
            check_time()
            data, why = guard.call(seed._fetch, client, row.xbrl_url, None, sink, limit=ANNUAL_REPORT_MAX_BYTES,
                                   max_bytes=ANNUAL_REPORT_MAX_BYTES)
            source = "fetched"
        if why or not data:
            note_failure(why or "no_response", f"{scrip} {label} {basis.lower()}", guard.last, row.xbrl_url)
            emit(scrip, symbol, label, basis, row, f"failed:{why}")
            return [[label, basis, why]] if why in GONE_REASONS else []
        summary["from_store" if source == "from_store" else "downloaded"] += 1
        if keep(scrip, label, basis, row.xbrl_url, data):
            emit(scrip, symbol, label, basis, row, source)
            return []
        emit(scrip, symbol, label, basis, row, "not_results")
        return [[label, basis, "not_results"]]

    consecutive_errors = 0
    last_progress = clock()
    try:
        for scrip, symbol in (companies[:limit] if limit else companies):
            check_time()
            if from_nse:
                summary["companies"] += 1
                try:
                    if annual:
                        annual_company(scrip, symbol)
                    nse_company(scrip, symbol)
                    consecutive_errors = 0
                except (SourceBlockedError, _OutOfTime):
                    raise
                except Exception as exc:   # noqa: BLE001 - one company's trouble (R2 hiccup, odd row) is that company's gap
                    reason = f"company_error:{type(exc).__name__}"
                    consecutive_errors += 1
                    note_failure(reason, f"{scrip} {symbol}", None, "", "company_errors")
                    log.exception("xbrl-facts %s %s failed", scrip, symbol)
                    if consecutive_errors >= 5:      # R2 or the Worker down: stopping saves nothing less than going on
                        summary["stopped"] = f"5 companies in a row failed ({reason}): stopped (infrastructure, not an NSE refusal)"
                        summary["infra_stop"] = True
                        log.error("xbrl-facts infrastructure stop: %s", summary["stopped"])
                        break
                if progress is not None and clock() - last_progress >= 60:
                    progress(summary)
                    last_progress = clock()
                continue
            if annual:
                annual_company(scrip, symbol)
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
        if annual and not summary["infra_stop"]:
            for scrip in list(annual_rest):          # every company's older annual years, after every company's newest
                check_time()
                if from_nse:
                    try:
                        annual_company(scrip, "", "rest")
                    except (SourceBlockedError, _OutOfTime):
                        raise
                    except Exception as exc:   # noqa: BLE001 - as in the first pass: that company's gap
                        note_failure(f"company_error:{type(exc).__name__}", f"{scrip} annual", None, "", "company_errors")
                        log.exception("xbrl-facts %s annual (older years) failed", scrip)
                else:
                    annual_company(scrip, "", "rest")
    except _OutOfTime:
        summary["out_of_time"] = True
        summary["stopped"] = (f"time budget reached after {summary['companies']} companies: everything fetched is saved, "
                              "the rest waits for the next run")
    except SourceBlockedError as exc:
        summary["stopped"] = stop_reason(exc)
        summary["capped"] = isinstance(exc, FileCapReached)
    if guard is not None:
        summary["refusal"] = guard.refusal
    summary["store_full"] = xbrl_store.is_full()
    if progress is not None:
        progress(summary)
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
    if summary.get("annual"):
        skipped = summary["annual_list_skipped"]
        lines += [f"annual-report list requests made {summary['annual_lists']}, skipped {skipped['covered']} (every year kept already stored) "
                  f"and {skipped['dry_run']} (dry run without download)"]
        lines += [f"annual reports (Ind AS only): facts already stored {summary['annual_have']}, "
                  f"written {summary['annual_saved']} ({summary['annual_bytes'] / 1000:.0f} KB gzipped), files not stored "
                  f"{summary['annual_missing']}, downloaded {summary['annual_downloaded']}, not Ind AS (left out) {summary['annual_not_ind_as']}"]
        if summary["annual_skipped"]:
            lines.append("annual reports skipped: " + summary["annual_skipped"])
    if summary.get("from_nse"):
        skipped = summary["lists_skipped"]
        lines += [f"NSE results lists asked for      {summary['lists']} (skipped {skipped['stored']}: every period stored, "
                  f"{skipped['dry_run']}: dry run without download), failed {summary['list_failed']}, "
                  f"older list only {summary['partial_lists']}",
                  f"results files listed (seed's selection, both bases) {summary['listed_files']}: facts already stored "
                  f"{summary['skipped_stored']}, read from R2 {summary['from_store']}, downloaded {summary['downloaded']}, "
                  f"not reached {summary['not_reached']}"]
        if summary["failed_reasons"]:
            lines.append("no file kept, by reason: " + ", ".join(f"{k} {v}" for k, v in sorted(summary["failed_reasons"].items())))
        if summary["refusal"]:
            r = summary["refusal"]
            lines.append(f"REFUSED: HTTP {r['status']} for {r['url']}; body starts: {r['body_head']!r}")
        if summary["store_full"]:
            lines.append("the raw-file store is full (XBRL_STORE_MAX_MB): files were read and their facts kept, but not stored raw")
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


# --- a look at what is stored (read only) ---------------------------------------------------------------------------

def dump(sink, scrip: str, pattern: str, *, max_rows: int = 400) -> str:
    """Every stored facts document of one company, and in each the facts whose element matches ``pattern`` (a regular
    expression, case-insensitive) with their period, dimensions and value: to see why a recipe finds a line or not, without a
    download. Read only."""
    rx = re.compile(pattern, re.I)
    out = []
    for k in sorted(sink.list_objects(f"{PREFIX}{scrip}/")):
        if not k.endswith(".json.gz"):
            continue
        try:
            doc = loads(sink.get_object(k))
        except Exception as exc:  # noqa: BLE001
            out.append(f"{k}: unreadable ({type(exc).__name__})")
            continue
        ctxs = doc.get("contexts") or {}
        instants = sorted({c["i"] for c in ctxs.values() if c.get("i")})
        out.append(f"{k}: kind={doc.get('kind') or 'results'} period={doc.get('period')} file_period={doc.get('file_period')} "
                   f"fy={doc.get('fy')} year_end={doc.get('year_end')} basis={doc.get('basis')} n_facts={doc.get('n_facts')} "
                   f"instants={instants} url={doc.get('url')}")
        n = 0
        for element, ctx, unit, value, _dec in doc.get("facts") or []:
            if not rx.search(element):
                continue
            c = ctxs.get(ctx) or {}
            when = c.get("i") or f"{c.get('s')}..{c.get('e')} ({c.get('m')}m)"
            dims = ",".join(f"{a}={m}" for a, m in (c.get("d") or {}).items())
            text = value if isinstance(value, (int, float)) else str(value)[:80]
            out.append(f"    {element} @ {when}{' [' + dims + ']' if dims else ''} = {text}")
            n += 1
            if n >= max_rows:
                out.append("    ...")
                break
    return "\n".join(out) or f"no facts stored for {scrip}"
