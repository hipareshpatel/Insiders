"""TODO 148 (owner, 31 Oct 2026 ~13:45 IST): the rows a bank's results XBRL lacks, read from its annual-report PDF. No AI, no OCR.

Three rows only, each from the schedules every Indian bank prints in the RBI format (Third Schedule of the Banking Regulation Act):

- Depreciation, from Schedule 16 (Operating Expenses), "Depreciation on Bank's property" (or "on Fixed Assets", a) and b) added):
  a bank filing a direct cash flow has none in its file (Bank of Maharashtra, every year; F228);
- CWIP, from Schedule 10 (Fixed Assets), "Capital Work-in-Progress" / "Assets (Premises) under Construction": the file keeps it
  inside ``FixedAssets`` (172 of 197 bank Fixed Assets gaps equal screener's CWIP within 1.5, F228);
- Fixed Assets = Schedule 10's grand total - CWIP (ICICI Bank and SBI consolidated March: screener's figure is the report's).

The text layer is read page by page (``pymupdf``, already a dependency). What the three test reports taught (31 Oct 2026):
SBI FY23 prints in thousands with Indian grouping and a crore group first ("3297,27,04" = 3,297.2704 Cr); Union FY25 in thousands
with the usual commas ("1,07,10,161"); Canara FY25 is bilingual, its Hindi text garbled, its figures split by spaces
("837 19 49" = 837.1949 Cr). In every case the separators carry no value once the unit is known, so a figure is its digits times
the unit. Union prints CWIP as a movement (opening, additions, deductions, closing), with the closing figures on the deductions
line between the deductions themselves; the closing figure is the one opening + additions - deductions gives, the previous year's
closing being this year's opening.

Nothing here decides a stored row: ``read`` gives what the report prints, by basis and year, and ``screener_view.bank_pl`` and
``bank_bs`` take a figure only when the bank's own figures agree with it (``pl_figure``, ``bs_figures``):
- Depreciation: the schedule's items add up to its printed total, and that total is the file's ``OperatingExpenses`` (so the column,
  the basis and the unit are proven by the file), and 0 < depreciation < the total.
- CWIP and Fixed Assets: Schedule 10's total is the file's ``FixedAssets`` (Fixed Assets + CWIP = the file's FixedAssets); where the
  schedule prints the subtotal of the other groups, that subtotal + CWIP is the total; 0 <= CWIP < the total.
Anything else leaves the row as it is (empty, or inside Fixed Assets)."""

from __future__ import annotations

import json
import re
from itertools import permutations

from .metrics import CONSOLIDATED, STANDALONE

PREFIX = "raw/bank-pdf/"        # + <scrip>/<report file name>.json: what ``read`` found in one report (bank-pdf-read)
TOL = 1.0                       # crore: the file's figure and the report's agree within this (screener_view.ABS_TOL)
SLACK = 2                       # printed units: a movement or a sum of rounded items may be off by this many

# --- figures ---------------------------------------------------------------------------------------------------------

_NIL = re.compile(r"^[-–—\s]*$|^(?:nil|NIL|Nil)$")
_SPACED = re.compile(r"^(\(?)\s*(-?)\s*(\d{1,9}(?: \d{2}){1,2})\s*(\)?)$")       # Canara: "837 19 49", "(3203 43 22)", "- 57 49"
_TOKEN = re.compile(r"^(\(?)(-?)(\d[\d,]*(?:\.\d+)?)(\)?)$")


def figures(line: str) -> list[float] | None:
    """The figures of a line made only of figures, in printed units (separators dropped, brackets negative), or None for a line
    with words. "-" alone is a nil (0)."""
    s = line.strip().strip("`₹").strip()
    if not s:
        return None
    if _NIL.match(s):
        return [0.0] * max(1, len(re.findall(r"[-–—]+", s))) if re.search(r"[-–—]", s) or s.lower() == "nil" else None
    m = _SPACED.match(s)
    if m and "," not in s:
        value = float(m[3].replace(" ", ""))
        return [-value if (m[1] and m[4]) or m[2] else value]
    out = []
    for tok in s.split():
        if tok in ("-", "–", "—"):
            out.append(0.0)
            continue
        t = _TOKEN.match(tok)
        if not t:
            return None
        value = float(t[3].replace(",", ""))
        out.append(-value if (t[1] and t[4]) or t[2] else value)
    return out


_UNITS = ((re.compile(r"0{3}\s*s?\s*omitted|in\s*[‘'’`]?\s*0{3}|0{3}\s*[’'‘]?\s*s?\s*\)|in\s+thousands?", re.I), 1e-4),
          (re.compile(r"in\s+lakhs?|lakhs?\s*\)|lacs?\s*\)", re.I), 1e-2),
          (re.compile(r"in\s+millions?|millions?\s*\)", re.I), 1e-1),
          (re.compile(r"in\s+crores?|crores?\s*\)|[₹`]\s*crores?|rs\.?\s*crores?", re.I), 1.0))


def unit_of(lines: list[str]) -> float | None:
    """Crore per printed unit, from the first unit note in ``lines`` (a section's header), else None (no figure is read)."""
    for line in lines:
        for pattern, unit in _UNITS:
            if pattern.search(line):
                return unit
    return None


_DATES = (re.compile(r"\b31\s*[./-]\s*0?3\s*[./-]\s*(\d{4})\b"), re.compile(r"\b31(?:st)?\s+march,?\s+(\d{4})", re.I),
          re.compile(r"\bmarch\s+31,?\s+(\d{4})", re.I))


def years_of(lines: list[str]) -> list[str]:
    """The March years the lines name, newest first ("FY25", "FY24"): a report prints the current year's column first."""
    found = {int(y) for line in lines for p in _DATES for y in p.findall(line) if 1990 < int(y) < 2100}
    return [f"FY{y % 100:02d}" for y in sorted(found, reverse=True)]


# --- the schedules ---------------------------------------------------------------------------------------------------

_HEADING = re.compile(r"(?:^|/)\s*SCHEDULE\s*[-–]?\s*(\d{1,2})\s*[-–:.]?\s*([A-Za-z &,]+?)\s*[:.]?\s*(?:\((?:contd|continued)\.?\))?\s*$",
                      re.I)
FIXED, OPEX = "fixed assets", "operating expenses"
_ENUM = re.compile(r"^\s*(?:[IVX]{1,5}[A-Z]?\s*[.)]|\(?[a-hA-H]\)|[A-H]\s*\.|\([ivx]{1,4}\)|[ivx]{1,4}\))")
_MOVEMENT = re.compile(r"at\s+cost|opening|as\s+per\s+last|preceding\s+year|addition|deduction|transfer|capitali[sz]|adjust|"
                       r"\bless\b|depreciation\s+to\s+date|amorti[sz]ation\s+till|written\s+off|disposal|sold", re.I)
_TOTAL = re.compile(r"\btotal\b(?!\s+(?:expenditure|income|expenses\b))", re.I)
DEPRECIATION = re.compile(r"depreciation(?!\s+(?:to\s+date|till))(?!.*investment)", re.I)
CWIP = re.compile(r"capital\s+work[\s-]*in[\s-]*progress|under\s+construction", re.I)
_INTANGIBLE = re.compile(r"intangible", re.I)


def heading(line: str) -> tuple[int, str] | None:
    """(schedule number, its name lower-cased) when the line is a schedule's own heading, not a sentence naming it."""
    if len(line) > 140:
        return None
    m = _HEADING.search(line)
    if not m or not re.search(r"SCHEDULE", line):      # a heading is upper case (a note says "Schedule 16 - Operating Expenses (XII ...")
        return None
    return int(m[1]), re.sub(r"\s+", " ", m[2].strip().lower())


def _basis_marks(text: str) -> str | None:
    cons, stand = bool(re.search(r"\bconsolidated\b", text, re.I)), bool(re.search(r"\bstandalone\b", text, re.I))
    return CONSOLIDATED if cons and not stand else STANDALONE if stand and not cons else None


def groups(lines: list[str]) -> list[tuple[str, list[float]]]:
    """(label, figures) in reading order: a line of words starts a label (joined to the label before it when that one has no
    figures yet and this line is not a new item), a line of figures adds to the current label. A one-letter line (a rupee glyph) is
    noise."""
    out: list[tuple[str, list[float]]] = []
    for raw in lines:
        line = raw.strip()
        if len(line) <= 1 and line not in ("-", "–", "—"):
            continue
        nums = figures(line)
        if nums is not None:
            if out:
                out[-1][1].extend(nums)
            continue
        if not re.search(r"[A-Za-z]{2,}", line) and not _ENUM.match(line):
            continue
        new = not out or out[-1][1] or _MOVEMENT.search(line) or _TOTAL.search(line) or \
            (_ENUM.match(line) and re.search(r"[A-Za-z]{3,}", out[-1][0]))
        if new:
            out.append((line, []))
        else:
            out[-1] = (out[-1][0] + " " + line, out[-1][1])
    return out


def _pair(nums: list[float]) -> tuple[float, float] | None:
    return (nums[0], nums[1]) if len(nums) == 2 else None


def movement_closing(block: list[list[float]]) -> tuple[float, float] | None:
    """The (current, previous) closing figures of a movement block (its groups' figures: opening pair, additions pair, then the
    deductions with the closing figures among them), proved by opening + additions - deductions = closing in both years and the
    previous closing = the current opening. None when not exactly one reading fits."""
    if len(block) < 3 or len(block[0]) != 2 or len(block[1]) != 2:
        return None
    (o_c, o_p), (a_c, a_p) = block[0], block[1]
    rest = [x for nums in block[2:] for x in nums]
    if len(rest) != 4:
        return None
    fits = set()
    # the deductions line starts with this year's deduction, and a year's deduction comes before its closing (Union: d, x, d', x';
    # the other order printed: d, d', x, x'); without that the two current figures could swap (both add up the same)
    for a, b, c, d in permutations(range(4), 4):
        if a != 0 or c > d:
            continue
        d_c, x_c, d_p, x_p = rest[a], rest[b], rest[c], rest[d]
        if abs(o_c + a_c - d_c - x_c) <= SLACK and abs(o_p + a_p - d_p - x_p) <= SLACK and abs(x_p - o_c) <= SLACK:
            fits.add((x_c, x_p))
    return fits.pop() if len(fits) == 1 else None


def opex_section(gs: list[tuple[str, list[float]]]) -> dict | None:
    """Schedule 16: (current, previous) of the depreciation lines (added) and of the printed total, and whether the items add up to
    that total in both years."""
    dep, items, total = [0.0, 0.0], [0.0, 0.0], None
    found = False
    for label, nums in gs:
        if _TOTAL.search(label):
            total = _pair(nums)
            break
        pair = _pair(nums)
        if pair is None:
            if nums:            # a line read as other than two columns: the items cannot be added up
                items = [float("nan")] * 2
            continue
        items = [items[0] + pair[0], items[1] + pair[1]]
        if DEPRECIATION.search(label):
            dep, found = [dep[0] + pair[0], dep[1] + pair[1]], True
    if total is None or not found:
        return None
    adds = [abs(items[i] - total[i]) <= SLACK * 6 for i in (0, 1)]      # a dozen rounded items
    return {"depreciation": dep, "total": list(total), "adds_up": adds}


def fixed_section(gs: list[tuple[str, list[float]]]) -> dict | None:
    """Schedule 10: the grand total (the last total with two figures); CWIP (current, previous), every CWIP line added, when each of
    them reads; and where the schedule prints a subtotal of the other groups just before a CWIP group, that subtotal and the CWIP
    lines after it (SBI consolidated FY23: premises under construction 317.55 inside the subtotal 44,341.36, capital work in
    progress 66.02 after it, total 44,407.38)."""
    totals = [(i, _pair(n)) for i, (label, n) in enumerate(gs) if _TOTAL.search(label) and _pair(n)]
    if not totals:
        return None
    end, grand = totals[-1]
    read: list[tuple[int, tuple[float, float]]] = []
    hits = [i for i, (label, _) in enumerate(gs[:end]) if CWIP.search(label) and not _INTANGIBLE.search(label)]
    for i in hits:
        nums = gs[i][1]
        pair = _pair(nums)
        if pair is None and not nums and i + 1 < end and _MOVEMENT.search(gs[i + 1][0]):
            block, j = [gs[i + 1][1]], i + 2
            while j < end and _MOVEMENT.search(gs[j][0]) and not _TOTAL.search(gs[j][0]):
                block.append(gs[j][1])
                j += 1
            pair = movement_closing(block)
        if pair is None:
            return {"total": list(grand), "cwip": None, "subtotal": None, "cwip_after_subtotal": None}
        read.append((i, pair))
    cwip = [sum(p[0] for _, p in read), sum(p[1] for _, p in read)] if read else None
    subtotal = after = None
    for t, pair in reversed(totals[:-1]):
        later = [p for i, p in read if i > t]
        if later and min(i for i, _ in read if i > t) - t <= 2:
            subtotal, after = list(pair), [sum(p[0] for p in later), sum(p[1] for p in later)]
            break
    return {"total": list(grand), "cwip": cwip, "subtotal": subtotal, "cwip_after_subtotal": after}


_BARE = re.compile(r"^\s*(\d{1,4})\s*$")
EDGE = 10       # a printed page number sits within this many lines of a page's top or bottom


def _edge_numbers(lines: list[str]) -> list[tuple[int, int]]:
    """(line index, value) of the bare whole numbers among a page's first and last EDGE lines."""
    idx = [i for i, line in enumerate(lines) if line.strip()]
    edge = set(idx[:EDGE] + idx[-EDGE:])
    return [(i, int(m[1])) for i in sorted(edge) if (m := _BARE.match(lines[i]))]


def drop_page_numbers(pages: list[str], places: list[int] | None = None) -> list[list[str]]:
    """Each page's lines without its printed page number (SBI's "147" under Schedule 10's total read as a third figure). The number
    is told apart by the report's own offset between a page's place and its printed number, seen on many pages (SBI 3, Union 3,
    Canara 20)."""
    split = [text.splitlines() for text in pages]
    places = places or list(range(1, len(pages) + 1))
    counts: dict[int, int] = {}
    for p, lines in zip(places, split):
        for off in {p - v for _, v in _edge_numbers(lines)}:
            counts[off] = counts.get(off, 0) + 1
    common = {off for off, n in counts.items() if n >= max(3, len(pages) // 10)}
    out = []
    for p, lines in zip(places, split):
        drop = {i for i, v in _edge_numbers(lines) if p - v in common}
        out.append([line for i, line in enumerate(lines) if i not in drop])
    return out


def read_pages(pages: list[str], places: list[int] | None = None) -> dict:
    """What one report prints, by basis and year: {"STANDALONE": {"FY25": {"depreciation", "opex_total", "opex_adds_up",
    "fa_total", "cwip", "fa_subtotal", "pages": {...}}}}. A schedule's basis is the one its page names; a page naming neither takes
    the order of the report (the first readable schedule of a kind is standalone, the next consolidated). ``places``: each page's place
in the report (1 = the first page; default their order here), so trimmed pages keep their printed-number offset; the
"pages" noted are these places."""
    places = places or list(range(1, len(pages) + 1))
    text_of = dict(zip(places, pages))
    lines: list[tuple[int, str]] = [(p, line) for p, page in zip(places, drop_page_numbers(pages, places)) for line in page]
    starts = [(k, h) for k, (_, line) in enumerate(lines) if (h := heading(line))]
    out: dict[str, dict[str, dict]] = {}
    seen = {FIXED: 0, OPEX: 0}
    for n, (k, (number, name)) in enumerate(starts):
        kind = FIXED if name.startswith("fixed assets") else OPEX if name.startswith("operating expenses") else None
        if kind is None:
            continue
        stop = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        body = [line for _, line in lines[k + 1:min(stop, k + 900)]]
        page = lines[k][0]
        page_lines = [line for p, line in lines if p == page]
        header = page_lines + body[:40]
        unit, years = unit_of(header), years_of(header)
        if unit is None or len(years) < 2:
            continue
        gs = groups(body)
        section = fixed_section(gs) if kind == FIXED else opex_section(gs)
        if section is None:
            continue
        basis = _basis_marks(text_of[page]) or (STANDALONE if seen[kind] == 0 else CONSOLIDATED)
        seen[kind] += 1
        for col, fy in enumerate(years[:2]):
            cell = out.setdefault(basis, {}).setdefault(fy, {"pages": {}})
            if kind == OPEX:
                cell.update(depreciation=round(section["depreciation"][col] * unit, 4),
                            opex_total=round(section["total"][col] * unit, 4), opex_adds_up=section["adds_up"][col])
                cell["pages"]["opex"] = page
            else:
                cell.update({name: None if section[part] is None else round(section[part][col] * unit, 4)
                             for name, part in (("fa_total", "total"), ("cwip", "cwip"), ("fa_subtotal", "subtotal"),
                                                ("cwip_after_subtotal", "cwip_after_subtotal"))})
                cell["pages"]["fixed"] = page
    return out


def read(payload: bytes) -> dict:
    """``read_pages`` over a PDF's text layer (no OCR: a scanned report gives nothing)."""
    import pymupdf
    with pymupdf.open(stream=payload, filetype="pdf") as doc:
        return read_pages([page.get_text() for page in doc])


# --- what a bank's own figures accept --------------------------------------------------------------------------------

def _near(a: float | None, b: float | None, tol: float = TOL) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


def pl_figure(cell: dict | None, opex: float | None) -> tuple[float | None, str]:
    """(depreciation, why) for a year: accepted only when the schedule adds up and its total is the file's OperatingExpenses."""
    if not cell or cell.get("depreciation") is None:
        return None, "no Schedule 16 for the year"
    dep, total = cell["depreciation"], cell.get("opex_total")
    if not cell.get("opex_adds_up"):
        return None, "Schedule 16 items do not add up to its total"
    if not _near(total, opex):
        return None, f"Schedule 16 total {total} is not the file's OperatingExpenses {opex}"
    if not 0 < dep < total:
        return None, f"depreciation {dep} outside 0 and the total"
    return dep, f"annual report Schedule 16 p.{cell['pages'].get('opex')}"


def bs_figures(cell: dict | None, fixed: float | None) -> tuple[tuple[float, float] | None, str]:
    """((Fixed Assets, CWIP), why) at a March year end: Fixed Assets + CWIP = the file's FixedAssets, the CWIP line read."""
    if not cell or cell.get("fa_total") is None:
        return None, "no Schedule 10 for the year"
    total, cwip, sub, after = cell["fa_total"], cell.get("cwip"), cell.get("fa_subtotal"), cell.get("cwip_after_subtotal")
    if cwip is None:
        return None, "no readable CWIP line in Schedule 10"
    if not _near(total, fixed):
        return None, f"Schedule 10 total {total} is not the file's FixedAssets {fixed}"
    if not 0 <= cwip < total:
        return None, f"CWIP {cwip} outside 0 and the total"
    if sub is not None and not _near(sub + (after or 0.0), total, 0.01):
        return None, f"Schedule 10 subtotal {sub} + the CWIP after it {after} is not its total {total}"
    return (round(total - cwip, 4), cwip), f"annual report Schedule 10 p.{cell['pages'].get('fixed')}"


# --- stored figures --------------------------------------------------------------------------------------------------

def key(scrip: str, name: str) -> str:
    return f"{PREFIX}{scrip}/{name.rsplit('/', 1)[-1].removesuffix('.gz')}.json"


def merge(reports: list[dict]) -> dict[tuple[str, str], dict]:
    """{(fy, basis): cell} over several reports: a year is taken from its own report (where it is the current column) before the next
    year's comparative; a report is {"years": [current, previous], "figures": read()}."""
    out: dict[tuple[str, str], dict] = {}
    rank: dict[tuple[str, str], int] = {}
    for rep in reports:
        current = (rep.get("years") or [None])[0]
        for basis, by_year in (rep.get("figures") or {}).items():
            for fy, cell in by_year.items():
                r = 0 if fy == current else 1
                if (fy, basis) not in out or r < rank[(fy, basis)]:
                    out[(fy, basis)], rank[(fy, basis)] = cell, r
    return out


def load(sink, scrip: str) -> dict[tuple[str, str], dict]:
    """The stored readings of a company's reports (``raw/bank-pdf/<scrip>/``), merged; {} when there are none (no change)."""
    reports = []
    for k in sink.list_objects(f"{PREFIX}{scrip}/"):
        body = sink.get_object(k)
        try:
            reports.append(json.loads(body)) if body else None
        except ValueError:
            continue
    return merge(reports)


def attach(cf, sink, scrip: str) -> int:
    """Give a bank's ``screener_view.CompanyFacts`` its stored report readings (``cf.bank_pdf``); other families are not listed.
    The number of (year, basis) readings attached. A failed read is no reading (the rows stay as the file gives them)."""
    from . import screener_view as sv
    try:
        if not any(cf.family(b) == sv.BANK for b in {b for _, b in cf.results}):
            return 0
        cf.bank_pdf = load(sink, scrip)
    except Exception:  # noqa: BLE001 - an addition: the statements are built from the file as before
        cf.bank_pdf = {}
    return len(cf.bank_pdf)


# --- the run: read each bank's reports once, keep every file and every reading ----------------------------------------

_LINK = re.compile(r'<a[^>]+href="(https?://(?:www\.)?bseindia\.com/[^"]+?\.pdf)"[^>]*>\s*(?:Financial\s+Year\s+)?(\d{4})', re.I)


def screener_links(html: str) -> list[tuple[str, str]]:
    """(year "FY23", BSE PDF address) from the annual-reports box of a stored Screener page ("Financial Year 2023 / from bse"),
    once each, newest first. Only BSE addresses: NSE's copies come through keep-annual-pdfs and its own client."""
    start = html.find("annual-reports")
    if start < 0:
        return []
    end = html.find('class="documents', start + 20)
    box = html[start:end if end > 0 else start + 60_000]
    out, seen = [], set()
    for url, year in _LINK.findall(box):
        if url not in seen and 1990 < int(year) < 2100:
            seen.add(url)
            out.append((f"FY{int(year) % 100:02d}", url))
    return sorted(out, key=lambda x: x[0], reverse=True)


def checked(cf, figures: dict) -> list[dict]:
    """What the bank's own file says of each reading (``pl_figure``, ``bs_figures`` against the Q4 file's year and March balance):
    one line per (year, basis), for the run's report. Reads stored facts only."""
    from . import screener_view as sv
    out = []
    for basis, by_year in sorted(figures.items()):
        for fy, cell in sorted(by_year.items()):
            end = sv._fy_end(fy)
            f = cf.result(f"Q4{fy}", basis) if end else None
            row = {"fy": fy, "basis": basis, "depreciation": cell.get("depreciation"), "cwip": cell.get("cwip"),
                   "fa_total": cell.get("fa_total")}
            if f is None:
                row["file"] = f"no stored Q4{fy} {basis.lower()} file"
                out.append(row)
                continue
            year, sheet = sv._Reader(f, end=end, months=12), sv._Reader(f, instant=end)
            filed_dep = year.cr("AdjustmentsForDepreciationAndAmortisationExpense")
            dep, why = pl_figure(cell, year.cr("OperatingExpenses"))
            split, why_bs = bs_figures(cell, sheet.cr("FixedAssets"))
            row.update(file_depreciation=filed_dep, depreciation_ok=dep is not None, depreciation_why=why,
                       file_cwip=sheet.cr("CapitalWorkInProgress"), fixed_ok=split is not None, fixed_why=why_bs)
            out.append(row)
    return out


def run(sink, client, companies: list[tuple[str, str]], years: int = 4, time_budget: float | None = None,
        dry_run: bool = False) -> dict:
    """For each bank of ``companies`` ((scrip, symbol); others are skipped): every stored report (raw/annual-pdf/<SYMBOL>/) not
    read yet, and every BSE report of the newest ``years`` years on its stored Screener page not stored yet, fetched once through
    ``client`` (the BSE adapter as written; one file each for the file cap) and kept gzipped in the same store at once; each
    report read (``read``) and its reading kept at raw/bank-pdf/<scrip>/<file>.json at once, so a stopped run keeps what it did.
    ``dry_run``: the readings are not stored (fetched files are kept: owner, 27 Oct 2026). A refusal stops the run."""
    import gzip
    import time

    from . import annual_pdfs
    from . import screener_crosscheck as sc
    from . import screener_download as sd
    from . import screener_view as sv
    from . import xbrl_facts
    from .adapters.bse import Blocked, Failed, Missing
    from .nse import FileCapReached
    from .timeutil import now_iso

    began = time.monotonic()
    out = {"companies": len(companies), "banks": 0, "not_banks": 0, "reports_read": 0, "downloaded": 0, "missing": 0,
           "failed": 0, "bytes": 0, "no_text": 0, "capped": False, "blocked": None, "out_of_time": False, "readings": []}
    pages = sc.stored_pages(sink)[0]
    for scrip, symbol in companies:
        if time_budget is not None and time.monotonic() - began > time_budget:
            out["out_of_time"] = True
            break
        cf = sv.CompanyFacts(sink.list_objects(f"{xbrl_facts.PREFIX}{scrip}/"), sink.get_object)
        if not any(cf.family(b) == sv.BANK for b in {b for _, b in cf.results}):
            out["not_banks"] += 1
            continue
        out["banks"] += 1
        sym = symbol.upper()
        stored = [k for k in sink.list_objects(f"{annual_pdfs.PREFIX}{sym}/") if k.endswith(".gz")]
        done = set(sink.list_objects(f"{PREFIX}{scrip}/"))
        wanted = []
        for basis_key in (pages.get(symbol) or pages.get(sym) or {}).values():
            blob = sink.get_object(basis_key)
            if blob:
                wanted = screener_links(sd.unpack(blob))
                if wanted:
                    break
        newest = sorted({fy for fy, _ in wanted}, reverse=True)[:max(1, years)]
        todo = [(k, None) for k in stored]
        for fy, url in wanted:
            k = annual_pdfs.key(sym, url)
            if fy in newest and k not in stored:
                todo.append((k, url))
        for k, url in todo:
            if key(scrip, k) in done:
                continue
            if url is None:
                body = sink.get_object(k)
                body = gzip.decompress(body) if body else None
            else:
                try:
                    body = client.fetch_url(url, {}, "annual-pdf", file=True)
                except FileCapReached:          # a planned stop: what is kept stays kept
                    out["capped"] = True
                    return out
                except Blocked as exc:
                    out["blocked"] = str(exc)[:300]
                    return out
                except Missing:
                    out["missing"] += 1
                    continue
                except Failed as exc:
                    out["failed"] += 1
                    out["readings"].append({"symbol": sym, "url": url, "error": str(exc)[:200]})
                    continue
                if not body or not body.startswith(b"%PDF"):
                    out["missing"] += 1
                    continue
                sink.put_object(k, gzip.compress(body, 6, mtime=0), content_type="application/gzip")
                out["downloaded"] += 1
                out["bytes"] += len(body)
            if not body:
                continue
            try:
                figures = read(body)
            except Exception as exc:  # noqa: BLE001 - a damaged PDF is no reading; the run goes on
                out["failed"] += 1
                out["readings"].append({"symbol": sym, "file": k, "error": f"{type(exc).__name__}: {exc}"[:200]})
                continue
            out["reports_read"] += 1
            if not figures:
                out["no_text"] += 1
            fys = sorted({fy for by in figures.values() for fy in by}, reverse=True)
            report = {"scrip": scrip, "symbol": sym, "file": k, "url": url, "years": fys[:2], "figures": figures, "read_at": now_iso()}
            if not dry_run:
                sink.put_object(key(scrip, k), json.dumps(report, ensure_ascii=False).encode(), content_type="application/json")
            out["readings"].append({"symbol": sym, "file": k, "years": fys[:2], "checks": checked(cf, figures)})
    return out


def render(o: dict) -> str:
    lines = [f"bank-pdf-read: {o['banks']} banks of {o['companies']} companies; {o['reports_read']} reports read, "
             f"{o['downloaded']} downloaded ({o['bytes'] / 1e6:.1f} MB), {o['missing']} missing, {o['failed']} failed, "
             f"{o['no_text']} without a text layer" + (", file cap reached" if o["capped"] else "")
             + (", out of time" if o["out_of_time"] else "") + (f", REFUSED: {o['blocked']}" if o["blocked"] else "")]
    for r in o["readings"]:
        if "error" in r:
            lines.append(f"  {r['symbol']:12s} {r.get('file') or r.get('url')}: {r['error']}")
            continue
        for c in r.get("checks") or []:
            lines.append(f"  {r['symbol']:12s} {c['fy']} {c['basis'][:4].lower()}  dep {c.get('depreciation')} "
                         f"({'ok' if c.get('depreciation_ok') else c.get('depreciation_why') or c.get('file')})  "
                         f"cwip {c.get('cwip')} of {c.get('fa_total')} "
                         f"({'ok' if c.get('fixed_ok') else c.get('fixed_why') or c.get('file')})")
    return "\n".join(lines)
