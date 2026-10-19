"""Module 8: trade remedies (anti-dumping, countervailing, safeguard) from DGTR's case pages, linked to the listed
companies that asked for them (no AI).

DGTR (dgtr.gov.in, measured 2026-10-19, docs/SOURCES.md) lists its investigations 15 a page, ongoing ones first; each
case page has a table of its documents (initiation, preliminary finding, final finding, termination, customs
notification...) with a PDF and a date. The initiation notice names the applicant ("the application has been filed
by M/s DCW Limited") and often the other domestic producers that supported it ("Epigral Limited has supported the
application"). Those names are matched strictly to the company master, so a case reaches a company only when the
filing itself names it: a product match alone (the blueprint's first idea) would tie every chemical maker to every
chemical case.

What memory keeps, per company, under `dossier["trade_remedies"]`: the case (product, countries, type, link), the
company's role (applicant or supporter) and the case's documents with their dates, so a card can say where the case
stands and the company page can list it.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime

log = logging.getLogger(__name__)

BASE = "https://www.dgtr.gov.in"
LIST_PATHS = {
    "ANTI_DUMPING": "/en/anti-dumping-investigation-in-india",
    "COUNTERVAILING": "/en/countervailing-duty-investigation",
    "SAFEGUARD": "/en/safe-guard-investigation-in-india",
}

_TAGS = re.compile(r"<[^>]+>")


def _text(fragment: str) -> str:
    return " ".join(html.unescape(_TAGS.sub(" ", fragment)).split())


def parse_case_list(page: str) -> list[dict]:
    """The cases on one list page: link, title, product, status, countries, investigation and proceeding."""
    out = []
    for block in re.findall(r'<div class="investigation">([\s\S]*?)</div>\s*</div>', page):
        link = re.search(r'<a href="(/en/[^"]+)"[^>]*>([\s\S]*?)</a>', block)
        if not link:
            continue
        title = _text(link.group(2))
        status = _text((re.search(r'<span class="status">([\s\S]*?)</span>', block) or [None, ""])[1])
        status = re.sub(r"^\d+\s*-\s*", "", status)
        details = {k.strip().lower(): v.strip() for k, v in
                   re.findall(r"(Country|Type of Investigation|Type of Proceeding)\s*:\s*([^<]+)", block)}
        # the quoted product, not an acronym quoted in brackets: 'Para-tert-Octyl Phenol ("PTOP") Formaldehyde ...'
        product = re.search(r'(?<![(\s(])\s?["“”]([^"“”]{2,160})["“”]', title)
        product = product if product and not re.search(r"\(\s*$", title[:product.start(1) - 1]) else None
        out.append({
            "url": BASE + link.group(1), "title": title[:400],
            "product": (product.group(1) if product else _product_from_title(title))[:160],
            "status": status[:60] or None,
            "countries": details.get("country"),
            "investigation": details.get("type of investigation"),
            "proceeding": details.get("type of proceeding"),
        })
    return out


def _product_from_title(title: str) -> str:
    m = re.search(r"(?i)imports? of\s+(.+?)\s+(?:originating|from|exported)\b", title)
    return (m.group(1) if m else title).strip(" .\"'‘’“”")


def last_page(page: str) -> int:
    """The highest `?page=N` the list links to (0 when it has one page)."""
    pages = [int(n) for n in re.findall(r'href="\?[^"]*page=(\d+)"', page)]
    return max(pages, default=0)


def parse_case_documents(page: str) -> list[dict]:
    """A case page's documents: label, PDF link and ISO date, in the page's order."""
    out = []
    for row in re.findall(r"<tr>([\s\S]*?)</tr>", page):
        cells = re.findall(r"<td[^>]*>([\s\S]*?)</td>", row)
        pdf = re.search(r'href="([^"]+\.pdf)"', row, re.I)
        if len(cells) < 3 or not pdf:
            continue
        label = _text(cells[1])
        when = None
        for cell in reversed(cells):
            m = re.search(r"(\d{2})/(\d{2})/(\d{4})", _text(cell))
            if m:
                try:
                    when = datetime(int(m[3]), int(m[2]), int(m[1])).date().isoformat()
                except ValueError:
                    when = None
                break
        if label:
            out.append({"label": label[:120], "stage": stage_of(label), "date": when, "url": html.unescape(pdf.group(1))})
    return out


_STAGES = (
    ("TERMINATED", r"terminat|withdraw|discontinu|closure"),
    ("CUSTOMS_NOTIFICATION", r"customs|notification of (?:the )?ministry|ministry of finance|\bmof\b|duty imposed|imposition"),
    ("FINAL_FINDING", r"final\s*finding|\bff\b|final finding"),
    ("PRELIMINARY_FINDING", r"preliminary|\bpf\b"),
    ("INITIATION", r"initiat"),
)


def stage_of(label: str) -> str | None:
    """What a document is, from its label: initiation, preliminary or final finding, customs notification
    (the Finance Ministry's duty), termination; None for hearings, extensions and the like."""
    text = label.lower()
    if re.search(r"corrigendum|extension|hearing|postpone|questionnaire|disclosure statement", text):
        return None
    return next((stage for stage, pattern in _STAGES if re.search(pattern, text)), None)


def notice_text(pdf: bytes, pages: int = 3) -> str:
    """A notice's first pages as text: the text layer, else OCR of the page (most notices are scans with no text at
    all: 6 of 10 initiations on 2026-10-19). The applicant is named on the first two pages."""
    import pymupdf

    from . import ocr

    out = []
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        for page in list(doc)[:pages]:
            text = page.get_text()
            if len(text.strip()) < 200 and ocr.available():
                text = ocr.recognise(page.get_pixmap(dpi=200).tobytes("png"))
            out.append(text)
    return "\n".join(out)


# A name ends at its company word; scans read "M/s" as "N4/s", "M/S" or "Mis"
_COMPANY_WORD = r"(?:Private\s+Limited|Pvt\.?\s+Ltd\.?|Limited|Ltd\.?|LLP|Corporation|Industries|Company)"
_MS = r"(?:(?:M|N4)\s*/\s*[sS]\.?|Mis)\s+"
# the name runs to the last of a chain of company words: "Reliance Industries Limited", not "Reliance Industries"
_NAME = re.compile(rf"(?:{_MS})?([A-Z][A-Za-z0-9&.'’ -]{{1,90}}?\b{_COMPANY_WORD}(?:\s+{_COMPANY_WORD})*)\b\.?")
# Who applied, in the notice's own two forms: "The application has been filed by X and Y." and
# "X (hereinafter referred to as the 'applicant') has filed an application". A company named elsewhere (an exporter,
# an importer: "M/s EBC Corporation from Japan" on the CPVC review) is no applicant and is not linked.
_FILED_BY = re.compile(r"\bfiled\s+by\s+([^.;]{3,300})", re.I)
_HEREINAFTER = re.compile(r"([^.;()]{3,400})\(\s*hereinafter[^)]{0,80}?applicants?\b", re.I)
_SUPPORTER = re.compile(r"([^.;()]{3,200}?)\s+(?:\([^)]{0,80}\)\s+)?(?:has|have)\s+(?:also\s+)?supported\s+the\s+application", re.I)


def _names_in(segment: str) -> list[str]:
    """The company names in a phrase such as "M/s Reliance Industries Limited and Wellknown Polyester Limited"."""
    tail = re.split(r"(?i)\bRules,?\s+\d{4}[^,]*,|\),\s*", segment)[-1]   # after "... Rules, 1995 (...)," if any
    return [_clean(m.group(1)) for m in _NAME.finditer(tail)]


def named_companies(text: str) -> dict[str, str]:
    """Company names an initiation notice gives as applicant or supporter: {name: "APPLICANT" | "SUPPORTER"}."""
    flat = " ".join((text or "").split())
    out: dict[str, str] = {}
    for pattern in (_FILED_BY, _HEREINAFTER):
        for m in pattern.finditer(flat):
            for name in _names_in(m.group(1)):
                out.setdefault(name, "APPLICANT")
    for m in _SUPPORTER.finditer(flat):
        for name in _names_in(m.group(1)):
            out.setdefault(name, "SUPPORTER")
    return {k: v for k, v in out.items() if k}


def _clean(name: str) -> str:
    name = re.sub(r"^(?:(?:the|and|by|of|on behalf of|apart from|namely)\s+)+", "", name.strip(" ,.;:-"), flags=re.I)
    name = re.sub(rf"^{_MS}", "", name)
    # a clause the name ran into ("DGTR - An application has been filed by X Limited"): no name
    if re.search(r"\b(?:has|have|been|filed|application|referred|hereinafter)\b", name):
        return ""
    return " ".join(name.split())[:120]


def name_key(name: str | None) -> str:
    """One company however written: case and punctuation aside, 'Ltd' is 'Limited', 'Pvt' is 'Private'."""
    text = re.sub(r"[^A-Z0-9& ]", " ", (name or "").upper().replace("PVT", "PRIVATE").replace("LTD", "LIMITED"))
    text = re.sub(r"\b(?:THE|M S|MIS)\b", " ", text)
    return " ".join(text.split())


def loose_key(key: str) -> str:
    """A name key with each word's plural 's' dropped: notices misspell names that way ("Laxmi Organics Industries
    Limited" for Laxmi Organic Industries, live run 2026-10-19)."""
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("S") else w for w in key.split())


def match_companies(names: dict[str, str], companies: dict[str, str]) -> dict[str, str]:
    """{scrip: role} for the names that are a company in the master ({name_key(company_name): scrip}). Exact keys only:
    "Epigral Limited" is Epigral; "DCW" alone, or a name with another word in it, is no match."""
    out: dict[str, str] = {}
    for name, role in names.items():
        key = name_key(name)
        # "Laxmi Organic Industries" stands for "Laxmi Organic Industries Limited"
        keys = [key] if key.endswith("LIMITED") else [key, f"{key} LIMITED"]
        scrip = next((companies[k] for k in keys if k in companies), None)
        if scrip is None:   # the plural slip, on both sides: still one name only, never a near one
            loose = {loose_key(k) for k in keys}
            found = {v for k, v in companies.items() if loose_key(k) in loose}
            scrip = found.pop() if len(found) == 1 else None
        if scrip and (scrip not in out or role == "APPLICANT"):
            out[scrip] = role
    return out


def merge(dossier: dict, case: dict, documents: list[dict], role: str) -> bool:
    """A case into a company's memory, or its documents refreshed. Returns whether memory changed."""
    cases = dossier.setdefault("trade_remedies", [])
    docs = sorted((d for d in documents if d.get("stage")), key=lambda d: d.get("date") or "")
    entry = {
        "case_url": case["url"], "product": case.get("product"), "countries": case.get("countries"),
        "investigation": case.get("investigation"), "proceeding": case.get("proceeding"), "status": case.get("status"),
        "role": role, "documents": docs,
        "stage": docs[-1]["stage"] if docs else None, "stage_on": docs[-1]["date"] if docs else None,
        # dated by its first document, so a card filed before the case began does not see it
        "as_of": (min((d["date"] for d in docs if d.get("date")), default=None) or "") + "T00:00:00+05:30",
    }
    for i, old in enumerate(cases):
        if old.get("case_url") == case["url"]:
            if {k: old.get(k) for k in entry} == entry:
                return False
            cases[i] = entry
            return True
    cases.append(entry)
    dossier["trade_remedies"] = sorted(cases, key=lambda c: c.get("as_of") or "")[-30:]
    return True


_WORDS = {"INITIATION": "started", "PRELIMINARY_FINDING": "issued its preliminary finding in",
          "FINAL_FINDING": "issued its final finding in", "CUSTOMS_NOTIFICATION": "has a customs duty notified in",
          "TERMINATED": "terminated"}


def signals(dossier: dict | None, filed_at: str, days: int = 180) -> list[tuple[str, str]]:
    """(severity, text) for a card: a trade-remedy step in the last `days` on a case the company asked for or
    supported. Memory must already be `dossier_as_of` the filing; each step counts only from its own date."""
    out = []
    cutoff = _minus_days(filed_at[:10], days)
    for case in (dossier or {}).get("trade_remedies", []):
        steps = [d for d in case.get("documents", []) if d.get("date") and cutoff <= d["date"] <= filed_at[:10]]
        if not steps:
            continue
        step = steps[-1]
        who = "the company applied" if case.get("role") == "APPLICANT" else "the company supported the application"
        kind = (case.get("investigation") or "trade-remedy investigation").lower()
        where = f" ({case['countries']})" if case.get("countries") else ""
        severity = "WARNING" if step["stage"] == "TERMINATED" else "POSITIVE" if step["stage"] in (
            "FINAL_FINDING", "CUSTOMS_NOTIFICATION", "PRELIMINARY_FINDING") else "INFO"
        out.append((severity, f"DGTR {_WORDS.get(step['stage'], 'acted in')} the {kind} on {case.get('product') or 'a product'}"
                              f"{where} on {step['date']}; {who}."))
    return out[:2]


def _minus_days(day: str, days: int) -> str:
    from datetime import date, timedelta

    try:
        return (date.fromisoformat(day) - timedelta(days=days)).isoformat()
    except ValueError:
        return day


STATE_KEY = "meta/dgtr_cases.json"   # per case: its documents and the names its initiation notice gave, read once
LIVE_PAGES = 1        # list pages read a day per investigation type: ongoing cases come first, 15 a page
RECHECK_DAYS = 7      # a known case's page is read again after a week (a new finding), or at once when it is linked
_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}


class Fetcher:
    """GET with retries and a pause: DGTR's server drops connections now and then (RemoteProtocolError on 2 of ~60
    requests, 2026-10-19), so each request is tried three times before it is reported."""

    def __init__(self, pause: float = 1.0, retries: int = 3, timeout: float = 60.0):
        import httpx

        self._client = httpx.Client(headers=_HEADERS, timeout=timeout, follow_redirects=True)
        self._pause, self._retries = pause, retries

    def __call__(self, url: str) -> bytes:
        import time

        last: Exception | None = None
        for attempt in range(self._retries):
            time.sleep(self._pause * (attempt + 1))
            try:
                response = self._client.get(url)
                if response.status_code < 500:
                    response.raise_for_status()
                    return response.content
                last = RuntimeError(f"HTTP {response.status_code}")
            except Exception as exc:  # network errors are retried; a 4xx is raised at once
                if getattr(getattr(exc, "response", None), "status_code", 500) < 500:
                    raise
                last = exc
        raise RuntimeError(f"DGTR request failed after {self._retries} attempts: {last}")


def company_names(sink) -> dict[str, str]:
    """{name_key(name): scrip} over the company master, former names included ("Meghmani Finechem Limited" is
    Epigral). A name two companies share is dropped rather than guessed."""
    import json

    from .company_master import stored_companies

    out: dict[str, str] = {}
    shared: set[str] = set()
    for row in stored_companies(sink):
        names = [row.get("company_name")]
        try:
            names += [n if isinstance(n, str) else (n or {}).get("name") for n in json.loads(row.get("former_names_json") or "[]")]
        except (ValueError, TypeError):
            pass
        for name in names:
            key = name_key(name)
            if not key:
                continue
            if out.get(key, row["scrip_code"]) != row["scrip_code"]:
                shared.add(key)
            out[key] = row["scrip_code"]
    return {k: v for k, v in out.items() if k not in shared}


def _initiation(documents: list[dict]) -> dict | None:
    """The notice that names the applicant: the latest initiation (a page also lists the case's earlier rounds: TDI's
    2016 original under its 2026 review), else the case's first document with a stage."""
    staged = sorted((d for d in documents if d.get("stage")), key=lambda d: d.get("date") or "")
    starts = [d for d in staged if d["stage"] == "INITIATION"]
    return starts[-1] if starts else (staged[0] if staged else None)


def sync(pipeline, deadline: float, pages: int = LIVE_PAGES, fetch=None, scrips: set[str] | None = None) -> dict:
    """Read DGTR's case lists, each new or changed case's documents and (once) its initiation notice, and put every
    case a listed company applied for or supported into that company's memory. Returns what it did."""
    import json
    import time
    from types import SimpleNamespace

    from . import universe
    from .dossier import new_dossier
    from .timeutil import today_ist

    report = {"cases": 0, "pages_read": 0, "notices_read": 0, "linked": 0, "companies": 0, "errors": [], "stopped": None}
    sink = pipeline.sink
    fetch = fetch or Fetcher()
    nse_map = universe.load_nse(sink)
    if not nse_map.built:
        report["stopped"] = "no NSE universe file yet"
        return report
    raw = sink.get_object(STATE_KEY)
    state: dict = json.loads(raw) if raw else {}
    names = company_names(sink)
    today = today_ist().isoformat()
    recheck = _minus_days(today, RECHECK_DAYS)

    def out_of_time() -> bool:
        if time.monotonic() >= deadline:
            report["stopped"] = report["stopped"] or "time budget"
            return True
        return False

    cases: list[dict] = []
    for investigation, path in LIST_PATHS.items():
        for n in range(pages):
            if out_of_time():
                break
            try:
                page = fetch(f"{BASE}{path}?page={n}").decode("utf-8", "replace")
            except Exception as exc:  # the next run reads it again
                report["errors"].append(f"list {investigation} page {n}: {type(exc).__name__}: {exc}"[:200])
                break
            found = parse_case_list(page)
            for case in found:
                case["investigation"] = case.get("investigation") or investigation.replace("_", "-").title()
            cases += found
            if not found or n >= last_page(page):
                break
    report["cases"] = len(cases)
    touched: dict[str, list[tuple[dict, list[dict], str]]] = {}
    for case in cases:
        if out_of_time():
            break
        known = state.get(case["url"]) or {}
        # a linked case is read daily (its next finding is news); any other weekly, or when its status changes
        due = recheck if not known.get("scrips") else _minus_days(today, 1)
        if known.get("checked", "") <= due or known.get("status") != case.get("status"):
            try:
                documents = parse_case_documents(fetch(case["url"]).decode("utf-8", "replace"))
                report["pages_read"] += 1
            except Exception as exc:
                report["errors"].append(f"case {case['url']}: {type(exc).__name__}: {exc}"[:200])
                continue
            known.update({"documents": documents, "checked": today, "status": case.get("status")})
        documents = known.get("documents") or []
        notice = _initiation(documents)
        if "names" not in known and notice:
            try:
                known["names"] = named_companies(notice_text(fetch(notice["url"])))
                report["notices_read"] += 1
            except Exception as exc:  # read again next run
                report["errors"].append(f"notice {notice['url']}: {type(exc).__name__}: {exc}"[:200])
        roles = match_companies(known.get("names") or {}, names)
        known["scrips"] = sorted(roles)
        state[case["url"]] = known
        for scrip, role in roles.items():
            if scrip in nse_map.included and (not scrips or scrip in scrips):
                touched.setdefault(scrip, []).append((case, documents, role))
    sink.put_object(STATE_KEY, json.dumps(state, ensure_ascii=False).encode())
    for scrip, items in touched.items():
        dossier = sink.get_dossier(scrip)
        if dossier is None:
            company = sink.company(scrip) or {}
            dossier = new_dossier(SimpleNamespace(scrip_code=scrip, company_name=company.get("company_name") or scrip,
                                                  symbol=company.get("symbol")), company)
        changed = [merge(dossier, case, documents, role) for case, documents, role in items]
        report["linked"] += len(items)
        if any(changed):
            sink.put_dossier(scrip, dossier)
            report["companies"] += 1
    report["errors"] = report["errors"][:20]
    return report
