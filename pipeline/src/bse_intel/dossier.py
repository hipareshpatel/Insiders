"""Living Company Dossiers: deterministic merge of AI-extracted facts.

The model never rewrites the dossier. It returns a small ``DossierDelta``
of facts stated in one filing; this module merges it with provenance
(``source_news_id``, ``as_of``). That keeps memory from drifting or being
silently truncated, makes re-analysis of a filing idempotent (its old facts
are removed first), and lets every fact be traced to a BSE filing.

``view_as_of`` builds the compact memory shown to the model for a filing,
using only facts known *before* that filing's timestamp. Backfill and live
processing can therefore interleave without leaking future knowledge into
older cards.
"""

from __future__ import annotations

import logging

import hashlib
import json
import re
from datetime import date, timedelta
from typing import Any

from .scoring import calibration
from .models import Filing, Pass2Output
from .periods import canonical_period, due_date, quarter_index, results_due

SCHEMA_VERSION = 3
MAX_TIMELINE = 600
MAX_BALANCE_SNAPSHOTS = 30   # Mar and Sep statements back to FY21 (seed) plus the cards' own; 16 until 2026-10-21
NOT_REPORTED_DAYS = 75   # a quarter's results are due in 45 days (60 for Q4), its call within the next two weeks
# Periods kept per metric, by kind: a seven-year table in a presentation must not push out the
# recent quarters, so each kind keeps its own latest periods (by period end, not by filing date).
KEEP_PERIODS = {"Q": 12, "H": 6, "9M": 4, "FY": 6, "M": 18, "other": 8}


SAME_DEAL_DAYS = 45
_PARTY_FILLER = {"limited", "ltd", "private", "pvt", "india", "of", "the", "and", "co", "company", "corporation", "corp",
                 "inc", "llc", "plc", "division", "unit", "group", "govt", "government"}


def _party(name: str | None) -> tuple[str, ...]:
    words = [w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if w not in _PARTY_FILLER]
    return tuple(words[:2])


_ORG_WORD = re.compile(r"\b(?:railways?|limited|ltd|corporation|corp|company|bank|authority|ministry|board|"
                       r"divisions?|department|undertaking|enterprises?|industries|finance|power|steel|oil|gas)\b", re.I)


def _organisation(part: str) -> bool:
    """A part of a counterparty that names a client, not its address or its parent ("Secunderabad", "Telangana",
    "Government of India")."""
    part = part.strip()
    if not part or re.match(r"(?i)(?:the\s+)?government\s+of\b", part):
        return False
    return bool(_ORG_WORD.search(part) or re.search(r"\b[A-Z]{3,}\b", part))


def is_recap(kind: str | None, counterparty: str | None) -> bool:
    """A press release listing the orders won since April is no order: its "deal" names many clients ("Indian
    Railways divisions, PNB, GAIL, DFCCIL, ...") and its amount is the sum of orders already on record
    (Magellanic's ₹111.04 Cr, round-2 re-run). Stored as one order it inflated every later ORDER_FLOW.
    Only parts that name an organisation count: one client written with its address ("South Central Railway,
    Secunderabad, Telangana") or its parent ("Ministry of Road Transport and Highways, Government of India") is
    one order, and dropping it would lose a real order from memory, ORDER_FLOW and SCALE."""
    parts = re.split(r",|;|/| and ", counterparty or "")
    return kind == "ORDER" and sum(1 for p in parts if _organisation(p)) >= 3


def same_deal(deals: list[dict], kind: str | None, amount: float | None, counterparty: str | None, as_of: str,
              news_id: str) -> dict | None:
    """The deal on record that a filing repeats: the press release beside an order's own intimation, filed the
    same day or a week later, names the same client and amount and was stored as a second order (Magellanic's
    railway LOAs, round-2 re-run: "17th order, ₹291 Cr" for 10 orders and ₹100 Cr)."""
    key = _party(counterparty)
    if not amount or not key:
        return None
    for x in reversed(deals):
        if x.get("source_news_id") == news_id or x.get("kind") != kind or _party(x.get("counterparty")) != key:
            continue
        days = (_day(as_of) - _day(x["as_of"])).days if _day(as_of) and _day(x.get("as_of")) else None
        if days is not None and 0 <= days <= SAME_DEAL_DAYS and x.get("amount_cr") \
                and abs(x["amount_cr"] - amount) <= max(0.01, 0.005 * amount):
            return x
    return None


def _day(text: str | None):
    from datetime import date
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def _hash(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:8]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


_DATED = re.compile(r"^\s*\d{4}-\d{2}-\d{2}\s*[:\-–]\s*")  # "2025-05-13: " as the memory view prints notes
_ROLE_SUFFIX = re.compile(r"(?:\s*\([^()]{1,40}\))+\s*$")    # "SML Isuzu Limited (Target Company) (Target Company)"


def _bare_name(name: str) -> str:
    return _ROLE_SUFFIX.sub("", name).strip() or name.strip()


_GRANTED = re.compile(r"\b(?:approved|granted|received|obtained|cleared|accorded|sanctioned|passed|approval\s+(?:was|has\s+been)\s+(?:given|received))\b", re.I)
# Words that mean the approval has not come through, even beside one that sounds as if it has. The last
# group is the stages of an approval process that read as the approval itself: an in-principle approval
# is not the final one (Shivam Autotech's listing approval was called "met" on NSE's in-principle
# letter), and a public announcement or draft letter of offer only opens an open offer (Novartis India
# had two approvals "met" on its public announcement alone). Audit round 1.
_NOT_YET = re.compile(r"\b(?:pending|awaited|awaiting|yet\s+to|subject\s+to|sought|seeks?|seeking|"
                      r"to\s+be\s+(?:obtained|received)|applied|proposed|conditional|"
                      r"(?:up)?on\s+receipt|after\s+obtaining|in[-\s]principle|"
                      r"public\s+announcement|detailed\s+public\s+statement|"
                      r"draft\s+letter\s+of\s+offer)\b", re.I)


_QUARTER_LABEL = re.compile(r"\bQ[1-4]\s*FY\s*'?\d{2,4}\b", re.I)
_TARGET = re.compile(r"(>=|<=|≥|≤|>|<|=)?\s*(?:₹|rs\.?|inr)?\s*(-?\d[\d,]*\.?\d*)", re.I)
_NUMBER_IN = re.compile(r"-?\d[\d,]*\.?\d*")


def kpi_verdict(watch: dict, status: str, evidence: str | None) -> str:
    """The model's verdict on a KPI watch item, checked in code. A cement card: "Cement EBITDA/tonne of
    ₹701 in Q2FY26 is below the >=700 target for Q3FY26" came back MISSED: 701 meets ">=700", and a
    Q2FY26 figure cannot settle a Q3FY26 check. Evidence for a quarter before the check's quarter (the
    first quarter named is the figure's own) keeps it PENDING; otherwise the first figure in the
    evidence, not the target's own, is compared with the target. Without a numeric target or figure,
    the model's verdict stands."""
    if watch.get("kind") != "KPI" or status not in ("MET", "MISSED"):
        return status
    evidence = evidence or ""
    due = quarter_index(canonical_period(str(watch.get("check_in") or "")))
    quarters = [quarter_index(canonical_period(m.group(0))) for m in _QUARTER_LABEL.finditer(evidence)]
    quarters = [q for q in quarters if q is not None]
    if due is not None and quarters and quarters[0] < due:
        return "PENDING"  # the figure's own quarter is named first ("₹701 in Q2FY26 … target for Q3FY26")
    target = _TARGET.search(str(watch.get("target") or ""))
    if not target:
        return status
    sign = {"≥": ">=", "≤": "<=", None: ">="}.get(target.group(1), target.group(1))
    goal = float(target.group(2).replace(",", ""))
    plain = _QUARTER_LABEL.sub(" ", evidence)
    plain = re.sub(r"(?:>=|<=|≥|≤|>|<|target(?:\s+of)?)\s*(?:₹|rs\.?|inr)?\s*" + re.escape(target.group(2)), " ", plain, flags=re.I)
    figures = [float(n.replace(",", "")) for n in _NUMBER_IN.findall(plain) if n.replace(",", "").replace(".", "").lstrip("-")]
    figures = [f for f in figures if not (1990 <= f <= 2100 and f == int(f))]  # years ("as of Dec 2025")
    if not figures:
        return status
    actual = figures[0]
    hit = {">=": actual >= goal, ">": actual > goal, "<=": actual <= goal, "<": actual < goal,
           "=": abs(actual - goal) <= abs(goal) * 0.02}[sign]
    return "MET" if hit else "MISSED"


_NO_NEWS = re.compile(r"not (?:yet )?(?:disclosed|reported|available|provided|updated|mentioned)|no (?:update|disclosure|mention|new information)|"
                      r"\bassumed\b|\boverdue\b|not part of (?:this|the) filing", re.I)
_TOPIC_STOP = {"with", "from", "that", "this", "than", "into", "over", "under", "after", "before", "target", "growth",
               "improvement", "check", "level", "levels", "ratio", "approval", "shareholder", "company", "quarter", "results"}


def _topic_words(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]{4,}", (text or "").lower()) if w not in _TOPIC_STOP}


WATCH_STALE_DAYS = 120   # a watch due this long before a filing has expired; that filing cannot settle it


def watch_verdict(watch: dict, status: str, evidence: str | None, as_of: str | None = None) -> str:
    """The model's verdict on a watch item, checked in code. "Met"/"missed" with no news ("not disclosed
    in Q1FY26 results; watchlist item overdue", "no update in filing; assumed resolved") or with
    evidence about another item (a debt/EBITDA check answered with a director's appointment) stays
    PENDING; a KPI verdict is then checked against its target and quarter (kpi_verdict)."""
    if status not in ("MET", "MISSED"):
        return status
    if watch.get("status") in ("MET", "MISSED"):
        return "PENDING"  # settled already: Novartis's Q4FY25 margin watch, met in May 2025, was "met" again in Q2FY26
    if as_of and watch.get("check_by") and watch["check_by"] < (date.fromisoformat(as_of[:10]) - timedelta(days=WATCH_STALE_DAYS)).isoformat():
        return "PENDING"  # its quarter is long past: a later quarter's figure does not answer it (live review 2)
    evidence = evidence or ""
    if _NO_NEWS.search(evidence):
        return "PENDING"
    topic = _topic_words(watch.get("text", "")) if watch.get("kind") == "KPI" else set()  # approvals: approval_granted
    if topic and evidence and not topic & _topic_words(evidence):
        return "PENDING"
    return kpi_verdict(watch, status, evidence)


def approval_granted(evidence: str | None) -> bool:
    """Evidence that an approval came through, not that it is still pending."""
    return bool(evidence) and bool(_GRANTED.search(evidence)) and not _NOT_YET.search(evidence)


def _real_holding(own) -> bool:
    """A shareholding as reported: as of a quarter-end, and holder groups that fit in 100%. SML's
    open-offer letter gave a post-offer projection (promoter 85%, "MAY-2025") stored as the actual
    holding next to DII 40.76%."""
    end = due_date(_period(own.period)) if own.period else None
    if end is None or end.month not in (3, 6, 9, 12):
        return False
    return sum(v or 0 for v in (own.promoter_pct, own.fii_pct, own.dii_pct)) <= 100.5


_APPROVAL_GENERIC = frozenset(
    "approval approvals approve approved pending required requirement requirements regulatory statutory "
    "shareholder shareholders member members board for of the and to from by in on a an any its their "
    "receipt obtain obtaining subject other necessary applicable final".split())


def _approval_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _APPROVAL_GENERIC and len(w) > 1}


def _same_approval(a: str, b: str) -> bool:
    """Two wordings of one pending approval: most of the shorter one's specific words are in the other
    ("CCI approval for the open offer and SPAs" / "Approval from Competition Commission of India (CCI)")."""
    wa, wb = _approval_words(a), _approval_words(b)
    if not wa or not wb:
        return False
    return len(wa & wb) / min(len(wa), len(wb)) >= 0.5


def _period(text: str) -> str:
    return canonical_period(text)


def new_dossier(filing: Filing, company: dict | None = None) -> dict:
    company = company or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "scrip_code": filing.scrip_code,
        "company_name": company.get("company_name") or filing.company_name,
        "symbol": company.get("symbol") or filing.symbol,
        "industry": company.get("industry"),
        "sector": company.get("sector"),
        "business_summary": None,
        "financial_metrics": [],
        "segment_mix": [],
        "balance_sheet": [],
        "capital_actions": [],
        "deals": [],
        "operating_notes": [],
        "guidance": [],
        "watchlist": [],
        "timeline": [],
        "upcoming_events": [],
        "identity": {"former_names": [], "entities": []},
        "ownership": [],
        "governance": {"auditor": None, "auditor_history": []},
        "predictions": [],
        "updated_at": None,
        "last_filed_at": None,
    }


def period_kind(period: str) -> str:
    p = period.upper()
    for kind in ("9M", "Q", "H", "FY"):
        if p.startswith(kind):
            return kind
    return "M" if re.match(r"^[A-Z]{3}-?20\d{2}$", p) else "other"


def _sources(entry: dict | None) -> list[dict]:
    """Every filing that stated this figure. A single-source figure is stored flat."""
    if not entry:
        return []
    return entry.get("sources") or [{
        "news_id": entry.get("source_news_id"), "as_of": entry["as_of"], "value": entry.get("value"),
        "unit": entry.get("unit"), "yoy_pct": entry.get("yoy_pct"), "qoq_pct": entry.get("qoq_pct"),
        **({"basis": entry["basis"]} if entry.get("basis") else {}),
    }]


log = logging.getLogger(__name__)

BALANCE_SCALE = 3   # a balance-sheet figure this many times off the other sources for its date is a unit slip


def _out_of_scale(snapshot: dict, existing: list[dict], news_id: str) -> list[str]:
    """The fields of a card's balance-sheet snapshot that sit three or more times off what the other sources
    say for the same date, the company's own XBRL first. Kanoria's Mar-2025 net worth was ₹601.22 Cr from two
    filings and ₹520.82 Cr from its XBRL when an AGM presentation's card put in ₹5,794.25 Cr, ten times too
    large; memory took it, and a later card quoted net worth "falling 91%" from it (loop round 3c,
    2026-10-18). A figure the company's XBRL tagged is never refused here: it is what the others answer to."""
    if news_id.startswith(XBRL_SOURCE):
        return []
    end = due_date(snapshot.get("period"))
    if end is None:
        return []
    same = [e for e in existing if e.get("source_news_id") != news_id and due_date(e.get("period")) == end]
    tagged = [e for e in same if str(e.get("source_news_id", "")).startswith(XBRL_SOURCE)]
    refused = []
    for field in ("net_worth_cr", "gross_debt_cr", "cash_cr"):
        value = snapshot.get(field)
        others = [abs(e[field]) for e in (tagged or same) if isinstance(e.get(field), (int, float)) and abs(e[field]) >= 1]
        if not isinstance(value, (int, float)) or abs(value) < 1 or not others:
            continue
        ref = sorted(others)[len(others) // 2]
        if max(abs(value), ref) / min(abs(value), ref) >= BALANCE_SCALE:
            refused.append(field)
    return refused

XBRL_SOURCE = "xbrl:"  # the seed's synthetic ids: "xbrl:res:<scrip>:<period>"

# Flows accumulate over a financial year; balances, margins and per-share figures do not.
FLOW_METRICS = frozenset({
    "revenue", "total_income", "total_expenses", "ebitda", "pbt", "pat", "pat_continuing", "pat_owners", "other_income",
    "employee_cost", "other_expenses", "depreciation", "finance_cost", "tax_expense", "current_tax",
    "deferred_tax", "exceptional_items", "cost_of_materials", "purchases_stock_in_trade",
    "raw_material_cost", "inventory_change", "operating_cash_flow",
    # the banking template's flows
    "interest_earned", "interest_expended", "pre_provision_operating_profit", "provisions"})
RECONCILE_TOLERANCE = 0.02  # a filing's own crore figures are rounded


def unreconciled(entries: list[dict]) -> set[tuple[str, str]]:
    """(metric, period) pairs that break the way Indian results accumulate.

    Results are filed cumulatively, so for any flow H1 = Q1 + Q2, 9M = H1 + Q3 and FY = 9M + Q4. A figure
    that breaks the identity is wrong whoever wrote it, and needs no PDF to catch. A machine-tagged member
    of a failing set is kept and the card-written ones are returned, because the filer's own tagging beats a
    model reading a PDF; when every member came from a card, all of them are returned, since nothing here
    says which one is wrong. Audit round 1 found Kanoria's Q1FY26 revenue stored as 453.78 where H1 minus Q2
    gives 201.38, and every later card read it as the year-ago figure.
    """
    by: dict[tuple[str, str], dict] = {}
    for e in entries:
        if e.get("metric") in FLOW_METRICS and e.get("unit") == "INR_CR" and e.get("value") is not None:
            by[(e["metric"], e["period"])] = e
    bad: set[tuple[str, str]] = set()
    for metric in {m for m, _ in by}:
        periods = {p for m, p in by if m == metric}
        for fy in {p[-4:] for p in periods if p[-4:].startswith("FY")}:
            get = lambda p: by.get((metric, p))  # noqa: E731
            q1, q2, q3, q4 = (get(f"Q{i}{fy}") for i in (1, 2, 3, 4))
            h1, m9, full = get(f"H1{fy}"), get(f"9M{fy}"), get(fy)
            for whole, parts in ((h1, (q1, q2)), (m9, (h1, q3)), (full, (m9, q4))):
                members = [m for m in (whole,) + parts if m is not None]
                if whole is None or len(members) != 3:
                    continue
                total = sum(m["value"] for m in parts)
                if abs(total - whole["value"]) <= max(0.05, abs(whole["value"]) * RECONCILE_TOLERANCE):
                    continue
                from_card = [m for m in members
                             if not str(m.get("value_news_id") or m.get("source_news_id") or "").startswith(XBRL_SOURCE)]
                for m in (from_card or members):
                    bad.add((m["metric"], m["period"]))
    return bad



def _metric_entry(metric: str, period: str, sources: list[dict]) -> dict:
    """One figure from its sources: the value is the latest restatement; ``as_of`` is when it was
    first known (known_since), which a later filing re-reporting it as a comparative never moves.

    A machine-tagged XBRL source outranks any card, however recent. The figures in an XBRL instance are
    tagged by the company's own filing agent and cannot be misread, while a card is a model reading a
    PDF; letting the newest writer win meant one card turned Jubilant's FY24 revenue from the seed's
    exact 7,587.51 into 78.4, and every later card then compared against that (audit round 1).

    Only within one basis, though: the value comes from the consolidated sources when any source is consolidated
    (a source with no basis recorded counts with either). Heritage's standalone Q4FY25 file (PAT 20.51) outranked
    five consolidated sources (38.17) and a card said PAT +16.7% YoY where it fell 37% (T5, 2026-10-20)."""
    sources = sorted(sources, key=lambda s: s["as_of"])
    bases = {s.get("basis") for s in sources} - {None}
    keep = "CONSOLIDATED" if "CONSOLIDATED" in bases else next(iter(bases), None)
    usable = [s for s in sources if s.get("basis") in (None, keep)] or sources
    tagged = [s for s in usable if str(s.get("news_id", "")).startswith(XBRL_SOURCE)]
    last = tagged[-1] if tagged else usable[-1]
    entry = {"metric": metric, "period": period, "value": last["value"], "unit": last.get("unit") or "INR_CR",
             "yoy_pct": last.get("yoy_pct"), "qoq_pct": last.get("qoq_pct"), "as_of": sources[0]["as_of"],
             "source_news_id": sources[0]["news_id"]}
    if len(sources) == 1 and sources[0].get("basis"):
        entry["basis"] = sources[0]["basis"]
    if len(sources) > 1:
        entry.update(sources=sources, updated_as_of=last["as_of"], value_news_id=last["news_id"])
    return entry


# Whose words a forecast is: a rating agency's or an analyst's view is not the company's promise (laptop test,
# 2026-10-19: "Ind-Ra expects ..." listed among Prism Johnson's overdue promises)
_THIRD_PARTY = re.compile(
    r"^\W*(?:the\s+)?(?:rating\s+agency\s+|agency\s+)?(?:crisil|icra|care(?:\s+ratings)?|ind-?ra|india\s+ratings|acuit[eé]|brickwork|infomerics"
    r"|moody'?s|fitch|s&p|analysts?|brokerages?|the\s+street)\b"
    r"|\b(?:crisil|icra|care(?:\s+ratings)?|ind-?ra|india\s+ratings|acuit[eé]|brickwork|infomerics|moody'?s|fitch|s&p|analysts?|brokerages?)"
    r"\s+(?:now\s+)?(?:expects?|believes?|projects?|estimates?|forecasts?|anticipates?|sees?|views?|opines?|assumes?)\b",
    re.I)


def third_party_view(text: str | None) -> bool:
    """True for a forecast stated by a rating agency, an analyst or a broker rather than the company."""
    return bool(text and _THIRD_PARTY.search(text))


# The kinds of entity the company page lists as its group, plants and brands. A lawsuit's other parties, customers,
# lenders and regulators are not (laptop test, 2026-10-19: Meta, Google, X Corp and a ministry among a company's
# entities); an entity with no type at all says nothing about the relation and is left out too.
_GROUP_TYPE = re.compile(r"subsidiar|step[- ]?down|\bwos\b|wholly|target\s+compan|acqui|investee|\bjv\b|joint\s+venture|associate|holding|parent|promoter"
                         r"|group\s+compan|sister|affiliate|\bllp\b|partnership|\bspv\b|trust|plant|factory|unit\b|facility"
                         r"|division|brand|branch|office|warehouse|mine|refinery|hospital|hotel|store", re.I)


_OTHER_RENAME = re.compile(r"\(\s*now\b|\bnow\s+known\s+as\b|\brenamed\s+(?:as|to)\b", re.I)


# a model's placeholder for "no former name" ("None", "N/A", "-") stored as one: Persistent showed "formerly None"
_NO_NAME = re.compile(r"\s*(?:none|nil|null|n[./]?\s?a\.?|not\s+applicable|-+)?\s*$", re.I)


# a professional firm is never the company's former name: Vedanta showed "formerly M S K A & Associates", its auditor
# (owner, 2026-10-20). Measured on the 58 former names on live cards: this drops that one and no other.
_FIRM = re.compile(r"&\s*(?:associates|co\.?)(?:\s|$)|\bassociates\b|\bLLP\b|chartered\s+accountants|"
                   r"\b(?:advocates|solicitors|auditors?|consultants)\b", re.I)


def own_former_name(name: str | None, dossier: dict) -> bool:
    """A former name of the listed company itself, not another entity's rename: "AGH Dreams Private Limited (now AGH
    Dreams Limited)" and "Heritage Novandie Foods Private Limited (now ...)" are a group company's, shown as Jindal
    Stainless's and Heritage's own (owner's review, 2026-10-20), and a name that is one of its group entities is too."""
    if not name or _NO_NAME.match(name) or _OTHER_RENAME.search(name) or _FIRM.search(name):
        return False
    entities = {_norm(_bare_name(e.get("name") or "")) for e in (dossier.get("identity") or {}).get("entities", [])}
    return _norm(_bare_name(name)) not in entities


def group_entity(kind: str | None) -> bool:
    return bool(kind and _GROUP_TYPE.search(kind))


def reported_by(entry: dict, news_id: str) -> bool:
    return any(s["news_id"] == news_id for s in _sources(entry))


def _cap_metrics(entries: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for e in entries:
        groups.setdefault((e["metric"], period_kind(e["period"])), []).append(e)
    kept = []
    for (_, kind), items in groups.items():
        items.sort(key=lambda e: (str(due_date(e["period"]) or ""), e["period"]))
        kept += items[-KEEP_PERIODS[kind]:]
    return sorted(kept, key=lambda e: e["as_of"])


_TIMELINE_STOP = {"with", "from", "that", "this", "will", "were", "been", "effective", "company", "limited", "board",
                  "approves", "approved", "appoints", "appointed", "announces", "announced", "regulation", "disclosure"}


def _timeline_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{4,}", (text or "").lower()) if w not in _TIMELINE_STOP}


def similar_timeline_entry(dossier: dict, filing: Filing, entry: str, days: int = 10, threshold: float = 0.5) -> dict | None:
    """An earlier timeline entry of the same company that reads as this event again: within `days` days and sharing at
    least `threshold` of the content words (SML Mahindra's MD and CEO change reached the feed as three cards, each worded
    differently: one event is one entry). Another filing of the same news id is not a repeat of itself.

    Ten days, not three: a concall deck follows its results by up to a week, and a SAST disclosure and the
    company's own intimation of the same transfer arrived six days apart (measured on the rebuild)."""
    from datetime import date

    try:
        when = date.fromisoformat(filing.filed_at[:10])
    except ValueError:
        return None
    mine = _timeline_words(entry)
    for t in dossier.get("timeline", []):
        if t.get("news_id") == filing.news_id:
            continue
        try:
            gap = (when - date.fromisoformat(str(t.get("date", ""))[:10])).days
        except ValueError:
            continue
        if gap < 0:
            continue  # a later entry: in a re-run or a backfill an older filing is not the repeat of a newer one
        theirs = _timeline_words(t.get("summary", ""))
        if gap <= days and mine and theirs and len(mine & theirs) / len(mine | theirs) >= threshold:
            return t
    return None


def timeline_entry_dated(dossier: dict, filing: Filing, claimed: str, days: int = 15) -> dict | None:
    """The company's timeline entry on the date the gatekeeper named, when it is close enough to be the
    same event. The gatekeeper judges whether this filing repeats that entry; this only checks that the
    entry is really there and near in time, so a hallucinated date drops nothing. Another filing of the
    same news id is never a repeat of itself.
    """
    from datetime import date

    claimed = (claimed or "").strip()[:10]
    if len(claimed) != 10:
        return None
    try:
        when, said = date.fromisoformat(filing.filed_at[:10]), date.fromisoformat(claimed)
    except ValueError:
        return None
    if not 0 <= (when - said).days <= days:
        return None  # only an entry on or before this filing can be the event it repeats
    for entry in dossier.get("timeline", []):
        if entry.get("news_id") == filing.news_id:
            continue
        if str(entry.get("date", ""))[:10] == claimed:
            return entry
    return None


def add_timeline_entry(dossier: dict, filing: Filing, event_type: str, entry: str, updated_at: str) -> dict:
    """The dossier with one dated timeline line for a routine filing (no card). A re-run replaces its own earlier line."""
    d = json.loads(json.dumps(dossier))
    _forget(d, filing.news_id)  # an earlier full analysis of this filing (before it was routed here) leaves no residue
    d["timeline"] = [t for t in d.get("timeline", []) if t.get("news_id") != filing.news_id]
    d["timeline"] = sorted(d["timeline"] + [{
        "id": "t_" + _hash(filing.news_id), "date": filing.filed_at, "event_type": event_type, "impact_level": None,
        "summary": entry.strip(), "news_id": filing.news_id, "tier": "TIMELINE",
        **({"pdf_url": filing.pdf_url} if filing.pdf_url else {}),
    }], key=lambda e: e["date"])[-MAX_TIMELINE:]
    d["updated_at"] = updated_at
    return d


GOVERNANCE_QUARTERS = 8   # quarterly governance reports kept in memory (two years)


def merge_governance(d: dict, entry: dict, as_of: str, source: str) -> bool:
    """One quarter's governance report (governance_xbrl.GovernanceReport.memory()) into memory: it replaces an
    earlier file for the same quarter (a revision), and the latest GOVERNANCE_QUARTERS quarters are kept. Returns
    whether memory changed."""
    gov = d.setdefault("governance", {"auditor": None, "auditor_history": []})
    quarters = gov.setdefault("quarters", [])
    if any(q.get("source") == source and q.get("parser") == entry.get("parser") for q in quarters):
        return False   # the same file read by the same parser; a parser fix files it again
    row = {**entry, "as_of": as_of, "source": source}
    quarters = [q for q in quarters if q.get("quarter_end") != entry.get("quarter_end")] + [row]
    gov["quarters"] = sorted(quarters, key=lambda q: str(q.get("quarter_end") or ""))[-GOVERNANCE_QUARTERS:]
    return True


def annual_profit_cr(dossier: dict | None) -> float | None:
    """The company's annual profit after tax from memory, ₹ Cr: the last four quarters when memory has them, else the
    latest year. None when memory has neither."""
    rows = [m for m in (dossier or {}).get("financial_metrics", [])
            if m.get("metric") in ("pat", "net_profit") and m.get("value") is not None
            and (m.get("unit") or "INR_CR") == "INR_CR" and due_date(m["period"])]
    quarters = {m["period"]: m["value"] for m in rows if m["period"].startswith("Q")}
    if len(quarters) >= 4:
        return sum(v for _, v in sorted(quarters.items(), key=lambda kv: due_date(kv[0]))[-4:])
    years = sorted((m for m in rows if m["period"].startswith("FY")), key=lambda m: due_date(m["period"]))
    return years[-1]["value"] if years else None


def governance_view(quarters: list[dict]) -> dict | None:
    """The latest governance quarter known, as the model sees it: the board's size and independence, what the
    company itself flagged as not in terms of SEBI's rules, fines, money lent or guaranteed to insiders, and who
    joined or left the board since the quarter before."""
    if not quarters:
        return None
    last = quarters[-1]
    view = {"quarter_end": last.get("quarter_end"), "board_size": last.get("board_size"),
            "independent_directors": last.get("independent_directors"),
            "chair_related_to_md": last.get("chair_related_to_md") or None,
            "exceptions": last.get("exceptions") or None,
            "tax_litigation_open": len(last.get("tax_litigation") or []) or None}
    if len(quarters) > 1:
        before = {b["name"].lower() for b in quarters[-2].get("board") or [] if not b.get("ceased")}
        now = {b["name"].lower(): b["name"] for b in last.get("board") or [] if not b.get("ceased")}
        joined = [now[n] for n in now if n not in before]
        left = [b["name"] for b in quarters[-2].get("board") or [] if not b.get("ceased") and b["name"].lower() not in now]
        if joined or left:
            view["board_changes"] = {"joined": joined or None, "left": left or None}
    return {k: v for k, v in view.items() if v is not None}


def forget_filing(dossier: dict, news_id: str) -> bool:
    """Take out everything one filing put in memory; True when there was something. For a filing that, read
    again, turns out not material or a duplicate: what its earlier analysis stored would otherwise stay for
    good - Kanoria's AGM presentation, now not material, still held net worth at ten times its value (audit of
    discard paths, 2026-10-18)."""
    before = json.dumps(dossier, sort_keys=True, default=str)
    _forget(dossier, news_id)
    return json.dumps(dossier, sort_keys=True, default=str) != before


def forget_source(dossier: dict, news_id: str) -> bool:
    """One source's facts out of memory (a seeded quarter the seed no longer keeps). Returns whether any were there."""
    before = json.dumps(dossier, sort_keys=True, ensure_ascii=False)
    _forget(dossier, news_id)
    return json.dumps(dossier, sort_keys=True, ensure_ascii=False) != before


def _forget(dossier: dict, news_id: str) -> None:
    metrics = []
    for e in dossier.get("financial_metrics", []):
        sources = [s for s in _sources(e) if s["news_id"] != news_id]
        if sources:
            metrics.append(_metric_entry(e["metric"], e["period"], sources))
    dossier["financial_metrics"] = metrics
    for key in ("segment_mix", "balance_sheet", "capital_actions", "upcoming_events", "operating_notes"):
        dossier[key] = [e for e in dossier.get(key, []) if e.get("source_news_id") != news_id]
    deals = []
    for deal in dossier.get("deals", []):
        history = [h for h in _deal_history(deal) if h.get("source_news_id") != news_id]
        if history:
            deals.append(_with_history(deal, history))
    dossier["deals"] = deals
    dossier["timeline"] = [e for e in dossier.get("timeline", []) if e.get("news_id") != news_id]
    for key in ("guidance", "watchlist"):
        kept = []
        for item in dossier.get(key, []):
            history = [h for h in item.get("status_history", []) if h.get("source_news_id") != news_id]
            if item.get("source_news_id") == news_id and not history:
                continue  # re-created by this analysis if it still applies; kept if later filings updated it
            item["status_history"] = history
            item["status"] = history[-1]["status"] if history else "OPEN"
            kept.append(item)
        dossier[key] = kept
    summary = dossier.get("business_summary")
    if summary and summary.get("source_news_id") == news_id:
        dossier["business_summary"] = None
    identity = dossier.setdefault("identity", {"former_names": [], "entities": []})
    identity["entities"] = [e for e in identity.get("entities", []) if e.get("source_news_id") != news_id]
    dossier["ownership"] = [o for o in dossier.get("ownership", []) if o.get("source_news_id") != news_id]
    gov = dossier.setdefault("governance", {"auditor": None, "auditor_history": []})
    gov["auditor_history"] = [a for a in gov.get("auditor_history", []) if a.get("source_news_id") != news_id]
    gov["auditor"] = gov["auditor_history"][-1] if gov["auditor_history"] else None
    predictions = []
    for p in dossier.get("predictions", []):
        if p.get("source_news_id") == news_id:
            continue
        if p.get("resolved_by") == news_id:
            p = {k: v for k, v in p.items() if k not in ("resolved_by", "resolved_on", "actual")} | {"status": "OPEN"}
        predictions.append(p)
    dossier["predictions"] = predictions


# gnpa_pct, "GNPA", "credit cost", "slippages" too: CSB's gross NPA 1.81% was "missed" against "at or below 1.84%"
# (live review 2, 2026-10-20)
_LOWER_IS_BETTER = re.compile(r"(?:\b|_)(?:reduc\w*|declin\w*|lower\w*|cut\w*|deleverag\w*|debt|[gn]?npa|cost[- ]to[- ]income|"
                              r"leverage|losses?|credit[ _-]?costs?|slippages?|cost[ _-]of[ _-](?:funds|borrowing)|attrition|churn|"
                              r"opex[ _-]ratio|expense[ _-]ratio|combined[ _-]ratio)(?:\b|_)", re.I)
_AT_MOST = re.compile(r"\b(?:at\s+or\s+below|or\s+(?:lower|less|below)|not\s+(?:to\s+)?exceed\w*|at\s+most|below|under|"
                      r"maximum|max\.?|up\s+to|within)\b|≤|<=", re.I)
_FULL_YEAR = re.compile(r"\b(?:full[- ]year|for\s+the\s+(?:full\s+)?year|annual(?:ised)?|year[- ]end|FY\s*'?\d{2}(?:-\d{2})?\s+"
                        r"(?:target|guidance|average)|average\s+for\s+(?:the\s+)?(?:year|FY))\b", re.I)


def _plausible_target(d: dict, metric: str, value: float) -> bool:
    """A numeric KPI target in the scale of the company's own figures for that metric: one more than 5x
    away from the latest stored value (a refund amount as a net-worth target, a segment's growth %
    as a revenue target, "EBITDA margin >= 1" against a 9% margin) is not a target."""
    latest = [m for m in d.get("financial_metrics", []) if m.get("metric") == metric and m.get("value")]
    if not latest:
        return True
    ref = abs(float(max(latest, key=lambda m: m.get("as_of") or "")["value"]))
    return ref < 1 or ref / 5 <= abs(float(value)) <= ref * 5


def merge(dossier: dict, output: Pass2Output, filing: Filing, impact_level: str | None, updated_at: str,
          basis: str | None = None) -> dict:
    """Return the dossier with this filing's facts merged in (input is not mutated). `basis` is the figures'
    (CONSOLIDATED / STANDALONE): the seed gives its file's, a card its own `basis`."""
    d = json.loads(json.dumps(dossier))  # deep copy, JSON-safe
    d.setdefault("schema_version", SCHEMA_VERSION)
    news_id, as_of = filing.news_id, filing.filed_at
    _forget(d, news_id)
    delta = output.dossier_delta

    if delta.business_summary and not d.get("business_summary"):
        d["business_summary"] = {"text": delta.business_summary.strip(), "as_of": as_of, "source_news_id": news_id}

    metrics = {(m["metric"], m["period"]): m for m in d.get("financial_metrics", [])}
    basis = basis or (output.card.basis if output.card is not None else None)
    # A quarter's profit and loss comes from its results filing (or the company's XBRL); another card only fills a
    # quarter memory has no figure for: an M&A card's "fundamentals" gave Heritage's standalone Q4FY25 revenue and
    # profit beside five consolidated sources (T5, 2026-10-20), while a rights issue's quarter is often all there is
    kind = output.event_type if output.event_type not in (None, "", "OTHER") else filing.event_type
    results_source = news_id.startswith(XBRL_SOURCE) or (kind or "RESULTS") == "RESULTS"
    for m in delta.financial_metrics:
        if m.value is None:
            continue
        key = (_norm(m.metric), _period(m.period))
        if not results_source and key[0] in FLOW_METRICS and key[1].startswith("Q") \
                and any(s["news_id"] != news_id for s in _sources(metrics.get(key))):
            continue
        source = {"news_id": news_id, "as_of": as_of, "value": m.value, "unit": m.unit,
                  "yoy_pct": m.yoy_pct, "qoq_pct": m.qoq_pct, **({"basis": basis} if basis else {})}
        metrics[key] = _metric_entry(*key, [s for s in _sources(metrics.get(key)) if s["news_id"] != news_id] + [source])
    d["financial_metrics"] = _cap_metrics(list(metrics.values()))

    segments = {(_norm(s["segment"]), _period(s["period"])): s for s in d.get("segment_mix", [])}
    for s in delta.segment_mix:
        key = (_norm(s.segment), _period(s.period))
        existing = segments.get(key)
        if existing and existing.get("as_of", "") > as_of:
            continue
        segments[key] = {
            "segment": s.segment.strip(), "period": key[1], "revenue_cr": s.revenue_cr,
            "share_pct": s.share_pct, "as_of": as_of, "source_news_id": news_id,
        }
    d["segment_mix"] = sorted(segments.values(), key=lambda e: e["as_of"])[-120:]

    if delta.balance_sheet and not delta.balance_sheet.is_empty():
        snapshot = {k: v for k, v in delta.balance_sheet.model_dump().items() if v is not None}
        for field in _out_of_scale(snapshot, d.get("balance_sheet", []), news_id):
            log.info("memory: %s %s %s from %s refused: out of scale with the other sources for that date",
                     field, snapshot.get("period"), snapshot[field], news_id)
            snapshot.pop(field)
        snapshot.update(as_of=as_of, source_news_id=news_id)
        d["balance_sheet"] = sorted(d.get("balance_sheet", []) + [snapshot], key=lambda e: e["as_of"])[-MAX_BALANCE_SNAPSHOTS:]

    actions = [a.model_dump() | {"as_of": as_of, "source_news_id": news_id} for a in delta.capital_actions]
    d["capital_actions"] = sorted(d.get("capital_actions", []) + actions, key=lambda e: e["as_of"])[-40:]

    deal = output.card.deal_value if output.card is not None else None
    if deal is not None and (deal.amount_cr or deal.updates_deal_id):
        entry = {"stage": deal.stage, "amount_cr": deal.amount_cr, "progress": deal.progress,
                 "as_of": as_of, "source_news_id": news_id}
        details = {k: v for k, v in deal.model_dump(include={"includes_gst", "counterparty", "segment", "execution_by", "expansion", "usage"}).items()
                   if v is not None}
        deals = d.get("deals", [])
        # only a deal of the same kind moves on: Ceigall's ₹18.4 Cr purchase of a project company was linked to its
        # ₹5,300 Cr transmission order, and memory then held the order at ₹0.05 Cr (round 5 arm B, 2026-10-19)
        target = next((x for x in deals if x["id"] == deal.updates_deal_id and x["as_of"] < as_of
                       and (not x.get("kind") or not deal.kind or x["kind"] == deal.kind)), None) \
            if deal.updates_deal_id else None
        target = target or same_deal(deals, deal.kind, deal.amount_cr, deal.counterparty, as_of, news_id)
        if target is None and is_recap(deal.kind, deal.counterparty):
            pass  # a list of orders already on record, not one more
        elif target is not None:
            # a later stage of a deal already on record (LOI -> contract, in-principle -> final terms)
            target.update(details)
            deals[deals.index(target)] = _with_history(target, _deal_history(target) + [entry])
        elif deal.amount_cr:
            did = "d_" + _hash(news_id)
            existing = next((x for x in deals if x["id"] == did), None)
            base = deal.model_dump(exclude={"updates_deal_id"}) | {"id": did, "as_of": as_of, "source_news_id": news_id}
            history = ([h for h in _deal_history(existing) if h["source_news_id"] != news_id] if existing else []) + [entry]
            deals = [x for x in deals if x["id"] != did] + [_with_history(base, history)]
        d["deals"] = sorted(deals, key=lambda e: e["as_of"])[-60:]

    # The memory view shows notes as "2025-05-13: text", and models copy that back as a new note.
    known_notes = {_norm(n["text"]) for n in d.get("operating_notes", [])}
    notes = []
    for n in delta.operating_notes[:3]:
        text = _DATED.sub("", n.strip())[:240]
        if text and _norm(text) not in known_notes:
            known_notes.add(_norm(text))
            notes.append({"text": text, "as_of": as_of, "source_news_id": news_id})
    d["operating_notes"] = sorted(d.get("operating_notes", []) + notes, key=lambda e: e["as_of"])[-40:]

    guidance = {g["id"]: g for g in d.get("guidance", [])}
    for item in delta.guidance:
        gid = "g_" + _hash(filing.scrip_code, _norm(item.statement))
        if gid in guidance or third_party_view(f"{item.statement} {item.target or ''}"):
            continue
        deadline = due_date(item.due)
        # the same target said again in other words (Heritage's ₹6,000 Cr FY27 revenue, May 2025 and May 2026): one
        # commitment, said twice, not two (T5, 2026-10-20)
        same = next((g for g in guidance.values() if item.metric and item.target and deadline
                     and _norm(g.get("metric") or "") == _norm(item.metric) and _norm(g.get("target") or "") == _norm(item.target)
                     and g.get("due_date") == deadline.isoformat()), None)
        if same is not None:
            same["repeated"] = [*same.get("repeated", []), {"as_of": as_of, "source_news_id": news_id}][-5:]
            continue
        guidance[gid] = {
            "id": gid, "statement": item.statement.strip(), "metric": item.metric, "target": item.target,
            "due": item.due, "due_date": deadline.isoformat() if deadline else None,
            "source_type": item.source_type.upper(), "given_on": as_of,
            "source_news_id": news_id, "status": "OPEN", "status_history": [],
        }
    for update in output.dossier_delta.promise_updates:
        g = guidance.get(update.guidance_id)
        if g is None or g.get("given_on", "") >= as_of:
            continue  # unknown id (hallucinated) or guidance newer than this filing
        if update.status == "ON_TRACK" and g.get("due_date") and judged_on(g.get("due"), g["due_date"]) < as_of[:10]:
            continue  # past its deadline a promise is delivered or missed, not on track ("2 MLPD by FY26" in Q2FY27);
            # a period's deadline passes when its results are due, not at its end (O12, owner 2026-10-20)
        g["status_history"] = sorted(
            g.get("status_history", []) + [{
                "status": update.status, "evidence": update.evidence, "as_of": as_of, "source_news_id": news_id,
            }],
            key=lambda h: h["as_of"],
        )
        g["status"] = g["status_history"][-1]["status"]
    d["guidance"] = sorted(guidance.values(), key=lambda g: g["given_on"])

    watch = {w["id"]: w for w in d.get("watchlist", [])}
    if output.card is not None:
        track = output.card.track_next
        items = [("KPI", k.kpi, k.check_in, k.target, None) for k in track.kpis_to_verify]
        items += [("APPROVAL", a, None, None, None) for a in track.pending_approvals]
        items += [("CONCERN", c.concern, None, None, c.management_response) for c in delta.analyst_concerns]
        for kind, text, check_in, target, response in items:
            wid = "w_" + _hash(filing.scrip_code, kind, _norm(text))
            if wid in watch:
                continue
            if kind == "APPROVAL" and any(w["kind"] == "APPROVAL" and w.get("status") in ("OPEN", "PENDING")
                                          and _same_approval(text, w["text"]) for w in watch.values()):
                continue  # the same approval in other words (SML's CCI approval was listed five times)
            check_by = due_date(check_in)
            watch[wid] = {
                "id": wid, "kind": kind, "text": text.strip(), "check_in": check_in, "target": target,
                "check_by": check_by.isoformat() if check_by else None, "created_on": as_of,
                "source_news_id": news_id, "status": "OPEN", "status_history": [],
                **({"response": response.strip()} if response else {}),
            }
    for update in delta.watch_updates:
        w = watch.get(update.watch_id)
        if w is None or w.get("created_on", "") >= as_of:
            continue
        if w["kind"] == "APPROVAL" and update.status == "MET" and not approval_granted(update.evidence):
            continue  # SML: "Approval met: CCI approval ..." with the evidence "CCI approval pending"
        status = watch_verdict(w, update.status, update.evidence, as_of)
        if status == "PENDING" and update.status != "PENDING":
            continue  # no news, another item's news, or an earlier quarter's figure: settles nothing yet
        w["status_history"] = sorted(w.get("status_history", []) + [{
            "status": status, "evidence": update.evidence, "as_of": as_of, "source_news_id": news_id,
        }], key=lambda h: h["as_of"])
        w["status"] = w["status_history"][-1]["status"]
    # Open items are never dropped for size; closed ones go first, oldest first.
    items = sorted(watch.values(), key=lambda w: w["created_on"])
    closed = [w for w in items if w.get("status") not in ("OPEN", "PENDING", "PARTIAL")]
    overflow = max(0, len(items) - 80)
    drop = {w["id"] for w in closed[:overflow]}
    d["watchlist"] = [w for w in items if w["id"] not in drop]

    identity = d.setdefault("identity", {"former_names": [], "entities": []})
    names = {n.lower(): n for n in identity.get("former_names", [])}
    for name in delta.former_names:
        name = " ".join(name.split())[:120]
        if name and name.lower() != (d.get("company_name") or "").lower() and own_former_name(name, d):
            names.setdefault(name.lower(), name)
    identity["former_names"] = [n for n in names.values() if own_former_name(n, d)][:6]
    # The view shows entities as "Name (type)"; models copy that back as the name.
    entities = {_norm(_bare_name(e["name"])): e for e in identity.get("entities", [])}
    for e in delta.entities[:6]:
        name = _bare_name(e.name.strip())
        key = _norm(name)
        if key and key not in entities and group_entity(e.type):
            entities[key] = {"name": name[:120], "type": e.type, "as_of": as_of, "source_news_id": news_id}
    identity["entities"] = list(entities.values())[-20:]
    identity["former_names"] = [n for n in identity["former_names"] if own_former_name(n, d)]   # against this filing's entities too

    # Only a shareholding pattern sets memory's ownership: Clean Max's NCD-security and share-purchase cards wrote a
    # "20.02% pledged" holding (one as "SEP-2026"), and every later card warned of a promoter pledge that no shareholding
    # file shows (round 6, 2026-10-19). The patterns' own XBRL comes in through seed.file_shareholding.
    shareholding = "shareholding" in f"{filing.headline or ''} {filing.subject or ''}".lower() \
        or output.event_type == "SHAREHOLDING"
    if shareholding and delta.ownership \
            and any(v is not None for k, v in delta.ownership.model_dump().items() if k != "period") \
            and _real_holding(delta.ownership):
        period = _period(delta.ownership.period)
        rows = [o for o in d.get("ownership", []) if o["period"] != period]
        rows.append({k: v for k, v in delta.ownership.model_dump().items() if v is not None}
                    | {"period": period, "as_of": as_of, "source_news_id": news_id})
        d["ownership"] = sorted(rows, key=lambda o: (str(due_date(o["period"]) or ""), o["as_of"]))[-8:]

    if delta.auditor and (delta.auditor.opinion or delta.auditor.change or delta.auditor.name):
        gov = d.setdefault("governance", {"auditor": None, "auditor_history": []})
        entry = {k: v for k, v in delta.auditor.model_dump().items() if v is not None} | {"as_of": as_of, "source_news_id": news_id}
        gov["auditor_history"] = sorted(gov.get("auditor_history", []) + [entry], key=lambda a: a["as_of"])[-6:]
        gov["auditor"] = gov["auditor_history"][-1]

    predictions = {p["id"]: p for p in d.get("predictions", [])}
    if output.card is not None:
        for k in output.card.track_next.kpis_to_verify:
            if not (k.metric and k.period and k.value is not None):
                continue
            comparison = k.comparison or ">="
            if comparison == ">=" and (_LOWER_IS_BETTER.search(f"{k.kpi} {k.metric}") or _AT_MOST.search(k.kpi or "")):
                comparison = "<="  # "Net debt reduction ... target >= 1,200" meant at most 1,200
            if comparison == ">=" and not k.value:
                continue  # "revenue >= 0": any figure passes, no target (SML, live review 2)
            if _period(k.period).startswith("Q") and _FULL_YEAR.search(k.kpi or ""):
                # a full-year target is judged on the year, not one quarter (CSB's "~1.5% RoA for FY26, building through
                # the year" marked missed at Q2's 1.33%, live review 2)
                k = k.model_copy(update={"period": "FY" + _period(k.period)[-2:]})
            if not _plausible_target(d, _norm(k.metric), k.value):
                continue  # "Net worth target >= 128.1" (a refund) for a ₹1,357 Cr net worth
            pid = "p_" + _hash(filing.scrip_code, _norm(k.metric), _period(k.period), f"{k.value:g}")
            key = (_norm(k.metric), _period(k.period))
            if any((m["metric"], m["period"]) == key for m in d["financial_metrics"]):
                continue  # the period's figure is already in: nothing left to predict
            # one open target per metric and period: a later card's number replaces the earlier one (Heritage's VAP
            # share Q2FY27 had targets 38, 48 and 49 from three cards; T5, 2026-10-20)
            for old in [q for q in predictions.values() if q["status"] == "OPEN" and (q["metric"], q["period"]) == key
                        and q["id"] != pid]:
                predictions.pop(old["id"])
            predictions.setdefault(pid, {
                "id": pid, "metric": _norm(k.metric), "period": _period(k.period), "value": k.value,
                "comparison": comparison, "kpi": k.kpi.strip()[:200], "created_on": as_of,
                "source_news_id": news_id, "status": "OPEN",
            })
    by_key = {(m["metric"], m["period"]): m for m in d["financial_metrics"]}
    for p in predictions.values():
        if p["status"] != "OPEN" or p["created_on"] >= as_of:
            continue
        actual = by_key.get((p["metric"], p["period"]))
        if actual is None or not reported_by(actual, news_id):
            continue
        hit = {">=": actual["value"] >= p["value"], "<=": actual["value"] <= p["value"],
               "=": abs(actual["value"] - p["value"]) <= abs(p["value"]) * 0.02}[p["comparison"]]
        p.update(status="MET" if hit else "MISSED", actual=actual["value"], resolved_on=as_of, resolved_by=news_id)
    for p in predictions.values():
        # the period's results and call came and went without the figure (a deck-only KPI, another key): not
        # reported, rather than open for ever
        end = due_date(p["period"])
        if p["status"] == "OPEN" and end and (end + timedelta(days=NOT_REPORTED_DAYS)).isoformat() < as_of[:10]:
            p.update(status="NOT_REPORTED", resolved_on=as_of)
    d["predictions"] = sorted(predictions.values(), key=lambda p: p["created_on"])[-60:]

    if output.is_material:
        d["timeline"] = sorted(d.get("timeline", []) + [{
            "id": "t_" + _hash(news_id),
            "date": as_of,
            "event_type": output.event_type,
            "impact_level": impact_level,
            "summary": output.timeline_entry.strip(),
            "news_id": news_id,
            **({"pdf_url": filing.pdf_url} if filing.pdf_url else {}),   # the call summary links each quarter's call
        }], key=lambda e: e["date"])[-MAX_TIMELINE:]

    events = {(e["event_type"], e["date"]): e for e in d.get("upcoming_events", [])}
    for ev in delta.upcoming_events:
        events[(ev.event_type, ev.date)] = {
            "event_type": ev.event_type, "date": ev.date, "description": ev.description,
            "as_of": as_of, "source_news_id": news_id,
        }
    d["upcoming_events"] = sorted(events.values(), key=lambda e: e["date"])

    d["updated_at"] = updated_at
    d["last_filed_at"] = max(d.get("last_filed_at") or "", as_of)
    return d


def judged_on(due: str | None, stored: str | None) -> str:
    """The first day a deadline counts as passed: for a reporting period ("H1FY27") its end plus the results window
    (``periods.results_due``), else the stored day. Jindal Stainless's H1FY27 guidance was overdue on 16 Oct, a month
    before its results were due (O12, owner 2026-10-20)."""
    judged = results_due(due)
    return judged.isoformat() if judged else stored or ""


def _guidance_status_at(g: dict, cutoff: str) -> str:
    history = [h for h in g.get("status_history", []) if h["as_of"] < cutoff]
    return history[-1]["status"] if history else "OPEN"


SAME_EVENT_DAYS = 10   # a memory item this close before a filing that shares its amount may be the same event
SAME_EVENT_NOTE = ("items with same_event: probably this same event, disclosed days earlier in another document; "
                   "never present one as history, a repeat or part of an earlier order book")
_TIMELINE_CRORE = re.compile(r"(?:₹|rs\.?|inr)\s*(\d[\d,]*(?:\.\d+)?)\s*(?:cr\b|crores?\b)", re.I)


def _significant(value: float) -> int:
    return len(f"{abs(value):.2f}".rstrip("0").rstrip(".").replace(".", "").lstrip("0"))


def _amount_in(index, value: float | None, min_digits: int) -> bool:
    """A crore amount the filing text states at its own precision (in crore, lakh, million or rupees)."""
    if not value or value <= 0 or _significant(value) < min_digits:
        return False
    return index.stated_crore(value, len(f"{value:.2f}".rstrip("0").partition(".")[2]))


def _party_in(words: set[str], counterparty: str | None) -> bool:
    key = [w for w in _party(counterparty) if len(w) >= 3]
    return bool(key) and all(w in words for w in key)


def mark_same_event(view: dict | None, filing_text: str | None, cutoff: str, days: int = SAME_EVENT_DAYS) -> int:
    """Mark the deals and timeline items from the few days before this filing that are probably its own event, told
    earlier in another document (the exchange intimation before the press release, an LoI before the order): a deal
    whose counterparty and amount this filing states (the amount alone, to four figures, when memory names no
    counterparty), or a timeline line whose crore amount it states. Aarti's sibling filing was called "the existing
    order book" and BEL's order a repeat (live reviews, 2026-10-20); the prompt said so in words, and this puts the
    mark on the item itself. Returns how many items were marked."""
    from .grounding import SourceIndex
    start = _day(cutoff)
    if not view or not filing_text or start is None:
        return 0

    def recent(day: str | None) -> bool:
        d = _day(day)
        return d is not None and 0 <= (start - d).days <= days

    index = SourceIndex(filing_text)
    words = set(re.findall(r"[a-z0-9]+", filing_text.lower()))
    marked = 0
    for deal in view.get("deals", []):
        party = deal.get("counterparty")
        if recent(deal.get("date")) and ((_party_in(words, party) and _amount_in(index, deal.get("amount_cr"), 2))
                                         or (not _party(party) and _amount_in(index, deal.get("amount_cr"), 4))):
            deal["same_event"] = True
            marked += 1
    for item in view.get("recent_timeline", []):
        amounts = [float(m.group(1).replace(",", "")) for m in _TIMELINE_CRORE.finditer(item.get("summary") or "")]
        if recent(item.get("date")) and any(_amount_in(index, a, 3) for a in amounts):
            item["same_event"] = True
            marked += 1
    if marked:
        view["notes"] = list(view.get("notes") or []) + [SAME_EVENT_NOTE]
    return marked


def _restated(entry: dict) -> str:
    """' restated <date>, first reported <value>' when a later filing of the same basis changed memory's figure."""
    sources = [s for s in entry.get("sources") or [] if s.get("basis") in (None, entry.get("_basis"))]
    if len(sources) < 2 or sources[0].get("value") is None or entry.get("value") is None:
        return ""
    first, value = sources[0]["value"], entry["value"]
    if abs(first - value) <= max(0.01, abs(value) * 0.005):
        return ""
    return f" restated {str(entry.get('updated_as_of') or '')[:10]}, first reported {first:g}"


def view_as_of(dossier: dict | None, cutoff: str, budget_chars: int = 6000, printed: set[str] | None = None,
               filing_text: str | None = None) -> dict | None:
    """Compact memory for the prompt, containing only facts known before ``cutoff``.

    Each figure carries its basis (once for a metric whose figures share one, else on its line) and, when a later
    filing of that basis changed it, the value first reported. A metric with consolidated figures shows none of its
    standalone-only ones: Heritage's standalone PAT beside five consolidated quarters gave a card the wrong YoY.
    With ``printed`` (the periods this filing prints, ``periods.printed_periods``) memory's figures for those periods
    are withheld and a note says so: the filing's own column wins, restated or not (Kanoria, Star Health, Man
    Industries). With ``filing_text``, deals and timeline items that are probably this same event are marked
    (``mark_same_event``). Without either it is the view code reads memory's figures from (results_card)."""

    if not dossier:
        return None
    before = lambda e, field="as_of": e.get(field, "") < cutoff  # noqa: E731

    as_known = []
    for m in dossier.get("financial_metrics", []):
        known = [s for s in _sources(m) if s["as_of"] < cutoff]
        if known:
            entry = _metric_entry(m["metric"], m["period"], known)
            bases = {s.get("basis") for s in known} - {None}
            entry["_basis"] = "CONSOLIDATED" if "CONSOLIDATED" in bases else next(iter(bases), None)
            as_known.append(entry)
    consolidated = {e["metric"] for e in as_known if e["_basis"] == "CONSOLIDATED"}
    as_known = [e for e in as_known if not (e["metric"] in consolidated and e["_basis"] == "STANDALONE")]
    printed = printed or set()
    withheld = sorted({e["period"] for e in as_known if e["period"] in printed}, key=lambda p: (str(due_date(p) or ""), p))
    as_known = [e for e in as_known if e["period"] not in printed]
    # A figure that breaks the cumulative identity never reaches the model: a wrong comparative is worse
    # than no comparative, because the card states it as fact (audit round 1).
    broken = unreconciled(as_known)
    if broken:
        log.info("memory: %d figures left out, they do not reconcile with their own periods: %s",
                 len(broken), sorted(f"{m} {p}" for m, p in broken)[:8])
    metrics_by_name: dict[str, list[dict]] = {}
    for entry in as_known:
        if (entry["metric"], entry["period"]) not in broken:
            metrics_by_name.setdefault(entry["metric"], []).append(entry)

    def metric_lines(periods: int) -> dict[str, list[str]]:
        out = {}
        for name, entries in metrics_by_name.items():
            by_kind: dict[str, list[dict]] = {}
            for e in entries:
                by_kind.setdefault(period_kind(e["period"]), []).append(e)
            entries = []
            for kind, items in by_kind.items():
                items.sort(key=lambda e: (str(due_date(e["period"]) or ""), e["period"]))
                entries += items[-(periods if kind in ("Q", "M") else max(1, periods // 2)):]
            entries.sort(key=lambda e: (str(due_date(e["period"]) or ""), e["period"]))
            bases = {e["_basis"] for e in entries}
            shared = next(iter(bases)) if len(bases) == 1 else None
            out[name] = ([f"basis: {shared.lower()}"] if shared else []) + [
                f"{e['period']}: {e['value']:g} {e['unit']}"
                + (f" (YoY {e['yoy_pct']:+g}%)" if e.get("yoy_pct") is not None else "")
                + (f" {e['_basis'].lower()}" if e["_basis"] and not shared else "")
                + _restated(e)
                for e in entries
            ]
        return out

    balance = [b for b in dossier.get("balance_sheet", []) if before(b)]
    guidance = [
        {
            "id": g["id"], "statement": g["statement"], "target": g.get("target"), "due": g.get("due"),
            "given_on": g["given_on"][:10], "status": _guidance_status_at(g, cutoff),
            **({"overdue": True} if g.get("due_date") and judged_on(g.get("due"), g["due_date"]) < cutoff[:10] else {}),
        }
        for g in dossier.get("guidance", []) if before(g, "given_on")
    ]
    timeline = [
        {"id": t["id"], "date": t["date"][:10], "type": t["event_type"], "summary": t["summary"]}
        for t in dossier.get("timeline", []) if before(t, "date")
    ]
    watch = [
        {
            "id": w["id"], "kind": w["kind"], "text": w["text"], "check_in": w.get("check_in"),
            **({"management_said": w["response"]} if w.get("response") else {}),
            **({"overdue": True} if w.get("check_by") and judged_on(w.get("check_in"), w["check_by"]) < cutoff[:10] else {}),
        }
        for w in dossier.get("watchlist", [])
        if w.get("created_on", "") < cutoff and _guidance_status_at(w, cutoff) in ("OPEN", "PENDING", "PARTIAL")
    ]
    upcoming = [
        {"type": e["event_type"], "date": e["date"], "description": e.get("description", "")}
        for e in dossier.get("upcoming_events", []) if before(e) and e["date"] >= cutoff[:10]
    ]
    deals = []
    for e in dossier.get("deals", []):
        state = deal_state(e, cutoff)
        if state is None:
            continue
        deals.append({
            "id": e["id"], "date": e["as_of"][:10], "kind": e["kind"], "amount_cr": state["amount_cr"], "stage": state["stage"],
            **({"progress": state["progress"]} if state.get("progress") else {}),
            **({"segment": e["segment"]} if e.get("segment") else {}),
            **({"counterparty": e["counterparty"]} if e.get("counterparty") else {}),
            **({"incl_gst": True} if e.get("includes_gst") else {}),
        })
    notes = [f"{n['as_of'][:10]}: {n['text']}" for n in dossier.get("operating_notes", []) if before(n)]
    identity = dossier.get("identity") or {}
    entities = [f"{e['name']} ({e['type']})" if e.get("type") else e["name"] for e in identity.get("entities", []) if before(e)]
    ownership = [{k: v for k, v in o.items() if k not in ("as_of", "source_news_id", "holders")}   # holders: the page's
                 for o in dossier.get("ownership", []) if before(o)][-2:]
    auditors = [a for a in (dossier.get("governance") or {}).get("auditor_history", []) if before(a)]
    governance = governance_view([q for q in (dossier.get("governance") or {}).get("quarters", []) if before(q)])
    predictions = [{"id": p["id"], "kpi": p["kpi"], "metric": p["metric"], "period": p["period"], "target": f"{p['comparison']} {p['value']:g}"}
                   for p in dossier.get("predictions", []) if p.get("created_on", "") < cutoff
                   and (p["status"] == "OPEN" or (p.get("resolved_on") or "") >= cutoff)]
    summary = dossier.get("business_summary")

    for periods, timeline_n, guidance_n in ((6, 12, 20), (4, 8, 12), (2, 5, 8), (1, 3, 5)):
        lines = metric_lines(periods)
        # one basis for every metric: said once, not on each (the budget stays the same)
        heads = {v[0] if v and v[0].startswith("basis: ") else None for v in lines.values()}
        metrics_basis = heads.pop()[len("basis: "):] if len(heads) == 1 and None not in heads else None
        if metrics_basis:
            lines = {k: v[1:] for k, v in lines.items()}
        view: dict[str, Any] = {
            "company": dossier.get("company_name"),
            "metrics_basis": metrics_basis,
            "notes": [f"this filing prints {', '.join(withheld)}: memory's figures for these periods are withheld, "
                      "use the filing's own columns"] if withheld else None,
            "business_summary": summary["text"] if summary and before(summary) else None,
            "metrics": lines,
            "balance_sheet": {k: v for k, v in balance[-1].items() if k != "source_news_id"} if balance else None,
            "guidance": [g for g in guidance if g["status"] in ("OPEN", "ON_TRACK", "DELAYED", "REVISED")][-guidance_n:],
            "watchlist": watch[-guidance_n:],
            "recent_timeline": timeline[-timeline_n:],
            "deals": deals[-guidance_n:],
            "operating_notes": notes[-max(3, guidance_n // 2):],
            "upcoming_events": upcoming[:6],
            "former_names": identity.get("former_names") or None,
            "entities": entities[-8:],
            "ownership": ownership,
            "auditor": {k: v for k, v in auditors[-1].items() if k not in ("as_of", "source_news_id")} if auditors else None,
            "governance": governance,
            "predictions": predictions[-guidance_n:],
            "calibration": (calibration(dossier, cutoff) or {}).get("rule"),  # Loop 2: how its targets turn out
        }
        view = {k: v for k, v in view.items() if v}
        if len(json.dumps(view, ensure_ascii=False)) <= budget_chars:
            break
    if filing_text:
        marked = mark_same_event(view, filing_text, cutoff)
        if marked or withheld:
            log.info("memory: %d periods withheld (the filing prints them), %d items marked as the same event",
                     len(withheld), marked)
    return view if len(view) > 1 else None


def dossier_as_of(dossier: dict | None, cutoff: str, inclusive: bool = True) -> dict | None:
    """The dossier as it stood at ``cutoff`` (including that moment's own filing when ``inclusive``).

    Signals, the footer and the results table read memory through this, so a backfilled May card
    is never sized against October revenue or told about guidance that came later.
    """
    if not dossier:
        return dossier
    limit = cutoff + "~" if inclusive else cutoff  # "~" sorts after every character of a timestamp
    ok = lambda ts: (ts or "") < limit  # noqa: E731
    d = dict(dossier)
    metrics = []
    for e in dossier.get("financial_metrics", []):
        known = [s for s in _sources(e) if ok(s["as_of"])]
        if known:
            metrics.append(_metric_entry(e["metric"], e["period"], known))
    d["financial_metrics"] = metrics
    for key in ("segment_mix", "balance_sheet", "capital_actions", "operating_notes", "upcoming_events"):
        d[key] = [e for e in dossier.get(key, []) if ok(e.get("as_of"))]
    d["timeline"] = [e for e in dossier.get("timeline", []) if ok(e.get("date"))]
    deals = []
    for e in dossier.get("deals", []):
        history = [h for h in _deal_history(e) if ok(h["as_of"])]
        if history:
            deals.append(_with_history(e, history))
    d["deals"] = deals
    d["ownership"] = [o for o in dossier.get("ownership", []) if ok(o.get("as_of"))]
    if dossier.get("pledges"):
        d["pledges"] = {"events": [e for e in dossier["pledges"].get("events", []) if ok(e.get("as_of"))]}
    if dossier.get("trade_remedies"):   # DGTR cases (dgtr.py, module 8): each step from its own date
        remedies = []
        for c in dossier["trade_remedies"]:
            docs = [x for x in c.get("documents", []) if x.get("date") and ok(x["date"] + "T00:00:00+05:30")]
            if docs:
                remedies.append(c | {"documents": docs, "stage": docs[-1]["stage"], "stage_on": docs[-1]["date"]})
        d["trade_remedies"] = remedies
    gov = dossier.get("governance") or {}
    history = [a for a in gov.get("auditor_history", []) if ok(a.get("as_of"))]
    d["governance"] = {"auditor": history[-1] if history else None, "auditor_history": history,
                       "quarters": [q for q in gov.get("quarters", []) if ok(q.get("as_of"))]}
    d["predictions"] = [
        p if ok(p.get("resolved_on")) else {k: v for k, v in p.items() if k not in ("resolved_by", "resolved_on", "actual")} | {"status": "OPEN"}
        for p in dossier.get("predictions", []) if ok(p.get("created_on"))]
    for key, born in (("guidance", "given_on"), ("watchlist", "created_on")):
        items = []
        for item in dossier.get(key, []):
            if not ok(item.get(born)):
                continue
            history = [h for h in item.get("status_history", []) if ok(h["as_of"])]
            items.append({**item, "status_history": history, "status": history[-1]["status"] if history else "OPEN"})
        d[key] = items
    return d


def memory_ids(view: dict | None) -> set[str]:
    if not view:
        return set()
    ids = {g["id"] for g in view.get("guidance", [])}
    ids |= {t["id"] for t in view.get("recent_timeline", [])}
    ids |= {w["id"] for w in view.get("watchlist", [])}
    ids |= {d["id"] for d in view.get("deals", []) if d.get("id")}
    return ids


def _deal_history(deal: dict | None) -> list[dict]:
    """A deal's stage history; deals stored before histories existed count as one entry."""
    if not deal:
        return []
    return deal.get("history") or [{"stage": deal.get("stage"), "amount_cr": deal.get("amount_cr"), "progress": deal.get("progress"),
                                     "as_of": deal["as_of"], "source_news_id": deal.get("source_news_id")}]


def _with_history(deal: dict, history: list[dict]) -> dict:
    """The deal with its history sorted and its current stage, size and progress taken from it."""
    history = sorted(history, key=lambda h: h["as_of"])
    out = {**deal, "history": history, "as_of": history[0]["as_of"], "source_news_id": history[0]["source_news_id"],
           "updated_as_of": history[-1]["as_of"], "stage": history[-1]["stage"]}
    out["amount_cr"] = next((h["amount_cr"] for h in reversed(history) if h.get("amount_cr")), deal.get("amount_cr"))
    out["progress"] = next((h["progress"] for h in reversed(history) if h.get("progress")), None)
    return out


def deal_state(deal: dict, cutoff: str) -> dict | None:
    """Stage, size and progress of a deal as known just before ``cutoff`` (None if not yet on record)."""
    history = [h for h in _deal_history(deal) if h["as_of"] < cutoff]
    if not history:
        return None
    return {"stage": history[-1]["stage"],
            "amount_cr": next((h["amount_cr"] for h in reversed(history) if h.get("amount_cr")), None),
            "progress": next((h["progress"] for h in reversed(history) if h.get("progress")), None)}


def latest_fundamentals(dossier: dict, footer: tuple[dict, ...] | list[dict] = ()) -> dict:
    """Latest revenue (quarter preferred), debt and net worth, and the sector's footer KPIs
    (GNPA for a bank, EBITDA/t for cement, ARPU for telecom...), for the card's financial footer."""
    out: dict = {}
    metrics = dossier.get("financial_metrics", [])

    def latest(names: tuple[str, ...], prefer_quarter: bool = False):
        rows = [m for m in metrics if m["metric"] in names and m.get("value") is not None and due_date(m["period"])]
        if prefer_quarter and any(m["period"].startswith("Q") for m in rows):
            rows = [m for m in rows if m["period"].startswith("Q")]
        return max(rows, key=lambda m: (due_date(m["period"]), m["as_of"]), default=None)

    revenue = latest(("revenue", "revenue_from_operations", "total_revenue", "net_sales"), prefer_quarter=True)
    if revenue:
        out["revenue"] = {"period": revenue["period"], "value": revenue["value"]}
    balance = dossier.get("balance_sheet", [])
    for key, names, field in (("debt", ("gross_debt", "borrowings", "total_debt"), "gross_debt_cr"),
                              ("net_worth", ("net_worth", "total_equity"), "net_worth_cr")):
        # the latest period's balance sheet, not the latest filed: a later filing restating FY25 hid Kellton's FY26
        # (live review 2, 2026-10-20)
        snap = max((b for b in balance if b.get(field) is not None),
                   key=lambda b: (str(due_date(b.get("period")) or ""), b.get("as_of") or ""), default=None)
        metric = latest(names)
        snap_end, metric_end = (str(due_date(x.get("period")) or "") if x else "" for x in (snap, metric))
        if snap and (not metric or (snap_end, snap["as_of"]) >= (metric_end, metric["as_of"])):
            out[key] = {"period": snap.get("period"), "value": snap[field]}
        elif metric:
            out[key] = {"period": metric["period"], "value": metric["value"]}
    kpis = []
    for spec in footer:
        fmt = spec.get("format", "num")
        names = (spec["metric"], *spec.get("aliases", ()))
        rows = [m for m in metrics if m["metric"] in names and m.get("value") is not None and due_date(m["period"])
                and _unit_fits(fmt, m)]
        if any(m["period"].startswith("Q") for m in rows):
            rows = [m for m in rows if m["period"].startswith("Q")]
        metric = max(rows, key=lambda m: (due_date(m["period"]), m["as_of"]), default=None)
        if metric:
            kpis.append({"label": spec["label"], "format": fmt, "period": metric["period"], "value": metric["value"]})
    if kpis:
        out["kpis"] = kpis[:2]
    return out


def _unit_fits(fmt: str, metric: dict) -> bool:
    """A footer figure is shown only in the unit its label promises: a gross NPA given in ₹ Cr is
    not printed as a percentage, and a margin given as a fraction is not printed as 0.2%."""
    unit = str(metric.get("unit") or "").upper().replace(" ", "")
    value = metric["value"]
    if fmt == "pct":
        if unit in ("PCT", "%", "PERCENT"):
            return True
        return not unit.startswith("INR") and unit not in ("X", "RATIO") and 0 <= abs(value) <= 100
    if fmt == "cr":
        return unit in ("INR_CR", "", "CR")
    if fmt == "x":
        return unit in ("X", "RATIO", "TIMES", "") and abs(value) < 100
    if fmt == "usd":
        return unit.startswith("USD") or unit in ("$", "")
    return unit not in ("PCT", "%", "PERCENT")


_RESULT_METRICS = (
    ("revenue", ("revenue", "revenue_from_operations", "total_revenue", "net_sales")),
    ("ebitda", ("ebitda", "operating_profit")),
    ("ebitda_margin", ("ebitda_margin", "opm", "operating_margin")),
    ("pbt", ("pbt", "profit_before_tax")),
    ("pat", ("pat", "net_profit", "profit_after_tax")),
    ("eps", ("eps", "basic_eps", "diluted_eps")),
    ("exceptional_items", ("exceptional_items",)),
    # a bank's own lines (the banking template): its table is read on these, not on revenue and EBITDA
    ("interest_earned", ("interest_earned",)),
    ("nii", ("nii", "net_interest_income")),
    ("ppop", ("pre_provision_operating_profit",)),
    ("provisions", ("provisions",)),
    ("gnpa_pct", ("gnpa_pct",)),
    ("nnpa_pct", ("nnpa_pct",)),
    ("roa_pct", ("roa_pct",)),
    # an insurer's (the GI and LI templates)
    ("gross_premium", ("gross_premium",)),
    ("incurred_claims", ("incurred_claims",)),
    ("combined_ratio", ("combined_ratio",)),
    ("claims_ratio", ("claims_ratio",)),
)
# lines that can turn from a loss to a profit; any other line across a change of sign gets no change at all
_TURN_LINES = {"ebitda", "pbt", "pat", "eps", "ppop", "nii"}
# lines whose change is in basis points, not per cent
_BPS_LINES = {"ebitda_margin", "gnpa_pct", "nnpa_pct", "roa_pct", "combined_ratio", "claims_ratio"}
# The table's rows in the order each statement is read (owner, 2026-10-19: "do not get fixed at one sector"). The
# statement is told apart by the lines the file tagged; the sector's own KPI rows follow (sectors.toml footer).
_LENSES = (
    ("bank", "interest_earned", (("interest_earned", "Interest earned", "cr"), ("nii", "Net interest income", "cr"),
                                 ("ppop", "Operating profit", "cr"), ("provisions", "Provisions", "cr"),
                                 ("exceptional_items", "Exceptional items", "cr"), ("pbt", "PBT", "cr"),
                                 ("pat", "Net profit", "cr"), ("gnpa_pct", "Gross NPA", "pct"),
                                 ("nnpa_pct", "Net NPA", "pct"), ("roa_pct", "Return on assets", "pct"),
                                 ("eps", "EPS (₹)", "inr"))),
    ("insurer", "gross_premium", (("gross_premium", "Gross premium", "cr"), ("revenue", "Net premium", "cr"),
                                  ("incurred_claims", "Claims", "cr"), ("claims_ratio", "Claims ratio", "pct"),
                                  ("combined_ratio", "Combined ratio", "pct"), ("pbt", "PBT", "cr"),
                                  ("pat", "PAT", "cr"), ("eps", "EPS (₹)", "inr"))),
    # a company's table is the five lines that tell the quarter, plus at most one mover (owner, 2026-10-20, O15: "show
    # only revenue, EBITDA, margin, PAT and EPS, and the one line that moved profit when it matters"); PBT and
    # exceptional items stay in the snapshot, off the table unless exceptional items are that mover
    ("company", "revenue", (("revenue", "Revenue", "cr"), ("ebitda", "EBITDA", "cr"), ("ebitda_margin", "EBITDA margin", "pct"),
                            ("pat", "PAT", "cr"), ("eps", "EPS (₹)", "inr"))),
)
# The lines that can be a company table's mover (O15): (key, names in memory, sign of its pull on profit, label). The
# two operating costs are judged on their change beyond what the revenue change carries, so a cost that only grew with
# sales is no mover, and a payroll that jumped ahead of output is (a new plant staffed before it produces).
_MOVERS = (
    ("employee_cost", ("employee_cost", "employee_benefit_expense"), -1, "Employee cost"),
    ("raw_material_cost", ("raw_material_cost", "cost_of_materials"), -1, "Raw material cost"),
    ("other_income", ("other_income",), +1, "Other income"),
    ("depreciation", ("depreciation",), -1, "Depreciation"),
    ("finance_cost", ("finance_cost",), -1, "Finance cost"),
    ("tax_expense", ("tax_expense",), -1, "Tax"),
    ("exceptional_items", ("exceptional_items",), +1, "Exceptional items"),
)
_SCALES_WITH_REVENUE = {"employee_cost", "raw_material_cost"}
# When a mover is shown: profit moved YoY by at least MOVER_PAT_MOVE of the year-ago PAT (and ₹1 Cr), and the line's
# pull, in the direction profit went, is at least MOVER_SHARE of that move, ₹1 Cr and MOVER_REVENUE of the quarter's
# revenue (a ₹2 Cr line at a ₹5,000 Cr company is not news however its small profit moved)
MOVER_PAT_MOVE = 0.10
MOVER_SHARE = 0.25
MOVER_REVENUE = 0.01


CALL_QUARTER_DAYS = 120   # a call or presentation discusses the quarter that ended at most this long before it


def call_results_snapshot(dossier: dict, filed_at: str, footer: tuple[dict, ...] | list[dict] = ()) -> dict | None:
    """The results table for an earnings call or investor presentation: the latest quarter in memory, as the results
    filing that reported it gives it (design audit 2026-10-20, fix 10). None when memory has no quarter that ended
    within CALL_QUARTER_DAYS of the call, so a call never shows an older quarter as the one it discusses."""
    from datetime import date as _date

    filed = _date.fromisoformat(filed_at[:10])
    latest = None
    for m in dossier.get("financial_metrics", []):
        if m.get("metric") not in ("revenue", "pat") or not str(m.get("period", "")).startswith("Q"):
            continue
        end = due_date(m["period"])
        if end is None or end > filed or (filed - end).days > CALL_QUARTER_DAYS:
            continue
        reporters = [s for s in _sources(m) if s.get("news_id")]
        if reporters and (latest is None or end > latest[0]):
            latest = (end, min(reporters, key=lambda s: s.get("as_of") or "")["news_id"])
    if latest is None:
        return None
    snap = results_snapshot(dossier, latest[1], footer)
    return {**snap, "discussed": True} if snap else None


# Lines whose comparatives are looked for in the filing's own text (results_snapshot's `printed`): amounts in crore,
# at the unit the filing prints the line's current figure in, EPS to the paisa, and the ratios a filing states (an
# insurer's claims and combined ratios, a bank's NPAs, a stated margin, the sector's % KPIs) as printed.
_PRINTED_CR = {"revenue", "ebitda", "pbt", "pat", "interest_earned", "nii", "ppop", "provisions", "gross_premium",
               "incurred_claims"}
_PRINTED_PCT = {"ebitda_margin", "gnpa_pct", "nnpa_pct", "roa_pct", "combined_ratio", "claims_ratio"}
_UNITS = (1, 100, 10, 10_000, 1e7)   # crore, lakh, million, thousand, rupees
# The lines whose refused comparatives tell that the filing restated that column, which then goes whole: EBITDA and
# its margin are mostly derived, not printed, so they never count
_RESTATED_BY = (_PRINTED_CR | _PRINTED_PCT | {"eps"}) - {"ebitda", "ebitda_margin"}
RESTATED_LINES = 2
ROUNDING = 0.0005   # a comparative within this share of a printed figure is that figure (as computed._base_printed)
ROW_WINDOW = 6      # numbers either side of a figure in the text that can be cells of its row


def _number_sequence(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*\.?\d*", text)
            if n.replace(",", "").replace(".", "").isdigit()]


def _printed_numbers(text: str | None) -> list[float] | None:
    if not text:
        return None
    return sorted(set(_number_sequence(text)))


def _tolerance(value: float, unit: float, near: float = 0.0) -> float:
    """How far a printed figure may be from this one at this unit: the precision it is stored at (4,917.0 Cr is
    ±0.5 Cr, 16.99 Cr ±0.005 Cr), half a printed unit (₹0.005 Cr in crore, 0.5 in lakh) or `near` of it, whichever is
    widest. The old match, ±0.5 Cr at every unit, let any integer near a figure pass: Kanoria's year-ago EBITDA
    ₹16.99 Cr and PBT ₹-37.94 Cr were "printed" as a note's 17 and a page's 38 (review 6, 2026-10-20)."""
    shown = repr(float(abs(value)))
    decimals = 0 if shown.endswith(".0") or "e" in shown else min(len(shown.split(".")[1]), 6)
    return max(0.5 * 10 ** -decimals * unit, 0.005 * unit if unit < 100 else 0.5, near * abs(value) * unit) + 1e-9


def _printed_at(value: float, numbers: list[float], units=_UNITS, near: float = 0.0) -> tuple[float, ...]:
    """The units at which the filing's text prints this figure (numbers: _printed_numbers)."""
    from bisect import bisect_left

    found = []
    for unit in units:
        target, tol = abs(value) * unit, _tolerance(value, unit, near)
        i = bisect_left(numbers, target - tol)
        if i < len(numbers) and numbers[i] <= target + tol:
            found.append(unit)
    return tuple(found)


def _beside(a: float, b: float, sequence: list[float], unit: float, near: float = 0.0) -> bool:
    """Whether the text prints figure b within ROW_WINDOW numbers of figure a, both at this unit: cells of one row."""
    ta, tola, tb, tolb = abs(a) * unit, _tolerance(a, unit), abs(b) * unit, _tolerance(b, unit, near)
    return any(abs(n - tb) <= tolb for i, m in enumerate(sequence) if abs(m - ta) <= tola
               for n in sequence[max(0, i - ROW_WINDOW): i + ROW_WINDOW + 1])


def _mover(out: dict, lookup, periods: dict) -> tuple[str, tuple[str, ...], str] | None:
    """The one line that moved a company's profit most year on year, when that move is significant (O15, owner
    2026-10-20); None when profit barely moved or no single line carried it. Values come from the table's own lookup,
    so a comparative the filing does not print makes no mover. results_card.profit_driver reads the same bridge from
    the tagged file for the card's words."""
    pat = out.get("pat") or {}
    now, then = pat.get("value"), pat.get("prev_year")
    if now is None or then is None:
        return None
    moved = now - then
    if abs(moved) < max(1.0, MOVER_PAT_MOVE * abs(then)):
        return None
    revenue = out.get("revenue") or {}
    rev, rev0 = revenue.get("value"), revenue.get("prev_year")
    floor = max(1.0, MOVER_REVENUE * abs(rev)) if rev else 1.0
    best = None
    for key, names, sign, label in _MOVERS:
        a, b = lookup(names, periods["value"]), lookup(names, periods["prev_year"])
        if a is None or b is None:
            continue
        if key in _SCALES_WITH_REVENUE:
            if not rev or not rev0 or rev0 <= 0:
                continue
            b = b * rev / rev0   # the year-ago cost at this quarter's sales
        pull = sign * (a - b)
        if (pull > 0) != (moved > 0) or abs(pull) < max(floor, MOVER_SHARE * abs(moved)):
            continue
        if best is None or abs(pull) > best[0]:
            best = (abs(pull), key, names, label)
    return best[1:] if best else None


# Flow lines a half year or nine months adds up from its quarters (not a margin, a ratio, EPS or a balance)
_ADDITIVE = {"revenue", "ebitda", "pbt", "pat", "exceptional_items", "interest_earned", "nii", "ppop", "provisions"}
# a quarter as the cumulative period that ends with it, less the one before: (cumulative, earlier part)
_FROM_CUMULATIVE = {"Q1": ("H1", "Q2"), "Q2": ("H1", "Q1"), "Q3": ("9M", "H1"), "Q4": ("FY", "9M")}


def _quarter_from_cumulative(table: dict, names: tuple[str, ...], quarter: str) -> dict | None:
    """Q1 as H1 - Q2, Q2 as H1 - Q1, Q3 as 9M - H1, Q4 as FY - 9M, of the same year and the same line name, when memory
    holds both; marked derived. None otherwise."""
    m = re.fullmatch(r"(Q[1-4])(FY\d{2})", quarter or "")
    if not m:
        return None
    whole, part = _FROM_CUMULATIVE[m.group(1)]
    fy = m.group(2)
    for name in names:
        a, b = table.get((name, f"{whole}{fy}" if whole != "FY" else fy)), table.get((name, f"{part}{fy}"))
        if a and b and a.get("value") is not None and b.get("value") is not None:
            return {"metric": name, "period": quarter, "value": round(a["value"] - b["value"], 2), "derived": True,
                    "sources": []}
    return None


def results_snapshot(dossier: dict, news_id: str, footer: tuple[dict, ...] | list[dict] = (),
                     printed: str | None = None, like: dict | None = None) -> dict | None:
    """This filing's latest quarter against a year ago and the previous quarter, for the results tables.

    Each metric carries its value, the year-ago and previous-quarter values when memory has them,
    and the YoY / QoQ change (in basis points for the margin, which is derived from EBITDA and
    revenue when the filing did not state it). `printed` is the filing's text, which its comparatives are judged
    against; `like` a stored table of the same quarter, whose missing comparatives stay out.
    """
    from .periods import prior_quarter_period, prior_year_period

    mine = [m for m in dossier.get("financial_metrics", []) if reported_by(m, news_id)]
    quarters = [m["period"] for m in mine if m["period"].startswith("Q") and due_date(m["period"])]
    if not quarters:
        return None
    period = max(quarters, key=due_date)
    table = {(m["metric"], m["period"]): m for m in dossier.get("financial_metrics", [])}
    periods = {"value": period, "prev_year": prior_year_period(period), "prev_quarter": prior_quarter_period(period)}
    sequence = _number_sequence(printed) if printed else []
    numbers = sorted(set(sequence)) or None
    ratios = _PRINTED_PCT | {spec["metric"] for spec in footer if spec.get("format") == "pct"}

    def stored(names: tuple[str, ...], p: str | None) -> tuple[dict | None, float | None]:
        entry = next((table[(n, p)] for n in names if (n, p) in table), None) if p else None
        if not entry and p and names[0] in _ADDITIVE:
            # a quarter memory never had on its own, from the half or nine months it did: E2E's Q1FY27 revenue as its
            # H1FY27 less Q2FY27, before the company's quarterly history was seeded (owner, 2026-10-21)
            derived = _quarter_from_cumulative(table, names, p)
            return (derived, derived["value"]) if derived else (None, None)
        if not entry:
            return None, None
        # the comparative this filing prints wins over what an earlier filing said for that quarter: a regrouped
        # year-ago column (Man Industries' Q1FY26 EBITDA ₹75.80 Cr here, ₹49.11 Cr in last year's own XBRL, made
        # +192% of +89%; live review 3)
        sources = _sources(entry)
        kept = {src.get("basis") for src in sources} - {None}
        basis = "CONSOLIDATED" if "CONSOLIDATED" in kept else next(iter(kept), None)   # as _metric_entry keeps it
        own = next((src for src in sources if src.get("news_id") == news_id and src.get("value") is not None
                    and src.get("basis") in (None, basis)), None)
        return entry, own["value"] if own is not None else entry["value"] if entry.get("value") is not None else None

    def refused(names: tuple[str, ...], p: str | None, alone: bool = False) -> bool:
        """An earlier filing's figure for a quarter this statement restates: Kapston's year-ago EPS ₹3.48 before its
        1:2 bonus (the statement prints ₹2.32), Bajaj Finance's year-ago revenue as first reported (live review 5,
        2026-10-20). A comparative credited to this filing is judged too: the earlier quarters' files' figures are
        stored under the filing that read them (xbrl.add_comparatives), so Bajaj's ₹20,178.90 Cr was "its own".
        Judged only on a line whose current figure the text prints, and only at the unit it prints it in, so a table
        the text missed keeps its comparatives; never EBITDA or its margin, which the statement mostly does not print.
        A line refused `alone` (not as part of a restated column) also needs its row read whole: its other
        comparative printed beside its current figure. A cell the OCR garbled or lost is no restatement: UCO Bank's
        PBT ₹1,247.11 Cr read "1,24,7Ll", Kapston's consolidated year-ago PAT missing from its row (reviews 1, 5)."""
        if p == period or not numbers or names[0] in ("ebitda", "ebitda_margin"):
            return False
        units = _UNITS if names[0] in _PRINTED_CR else (1,) if names[0] == "eps" or names[0] in ratios else ()
        entry, value = stored(names, p)
        current = table.get((entry["metric"], period), {}).get("value") if entry else None
        if not units or value is None or current is None or abs(value) < 1 or abs(current) < 1:
            return False
        at = _printed_at(current, numbers, units)
        if not at or _printed_at(value, numbers, at, ROUNDING):
            return False
        if not alone:
            return True
        peer = stored(names, periods["prev_quarter"] if p == periods["prev_year"] else periods["prev_year"])[1]
        return peer is not None and any(_beside(current, peer, sequence, unit, ROUNDING) for unit in at)

    # A column the filing restates goes whole (review 6, 2026-10-20): Kanoria's year-ago quarter after APAG moved to
    # discontinued operations, Star Health's first Ind AS quarter. Memory holds the comparatives as first reported, so
    # when two judged lines refuse the same column, every line loses it: the derived EBITDA and margin, exceptional
    # items, a PAT whose old figure a previous-GAAP reconciliation still prints, and the mover.
    judged = [names for key, names in _RESULT_METRICS if key in _RESTATED_BY]
    restated = {p for slot, p in periods.items() if slot != "value" and p and numbers
                and sum(refused(names, p) for names in judged) >= RESTATED_LINES}

    def built(p: str) -> bool:
        """Whether a derived EBITDA comparative the text does not print is built from figures it does: each part
        memory used (xbrl: PBT + finance cost + depreciation - other income - exceptional items) printed at the unit
        of that part's current figure (the statement's, where its PBT is printed, when memory has none or a nil);
        not judged when the text does not print this quarter's PBT. Jubilant Agri's year-ago EBITDA ₹62.08 Cr took other income ₹1.90 Cr from
        memory where the statement prints 59 lakh (₹63.39 Cr; review of 2026-10-20)."""
        value = stored(_RESULT_METRICS[1][1], p)[1]
        if value is None or _printed_at(value, numbers, _UNITS, ROUNDING):
            return True
        pbt = stored(("pbt",), period)[1]
        statement = _printed_at(pbt, numbers) if pbt else ()
        if not statement:
            return True   # the text missed the statement (a press release's revenue is no table): nothing to judge by
        for part in ("pbt", "finance_cost", "depreciation", "other_income", "exceptional_items"):
            then, now = stored((part,), p)[1], stored((part,), period)[1]
            if not then:
                continue   # nothing taken from memory (an exceptional item that did not occur)
            at = _printed_at(now, numbers) if now else statement
            if at and not _printed_at(then, numbers, at, ROUNDING):
                return False   # a part whose current figure the text does not print cannot be judged, as any line
        return True

    unbuilt = {p for slot, p in periods.items() if slot != "value" and p and numbers and not built(p)}

    def lookup(names: tuple[str, ...], p: str | None) -> float | None:
        if not p or p in restated or (p in unbuilt and names in (_RESULT_METRICS[1][1], _RESULT_METRICS[2][1])):
            return None
        value = stored(names, p)[1]
        return None if value is None or refused(names, p, alone=True) else value

    def margin(p: str | None) -> float | None:
        stated = lookup(_RESULT_METRICS[2][1], p)
        if stated is not None:
            return stated
        ebitda, revenue = lookup(_RESULT_METRICS[1][1], p), lookup(_RESULT_METRICS[0][1], p)
        return round(ebitda / revenue * 100, 2) if ebitda is not None and revenue else None

    out: dict = {"period": period, "prev_year_period": periods["prev_year"], "prev_quarter_period": periods["prev_quarter"]}
    def nii(p: str | None) -> float | None:
        """Net interest income as stated, else interest earned less interest expended (both from the file)."""
        stated = lookup(("nii", "net_interest_income"), p)
        if stated is not None:
            return stated
        earned, expended = lookup(("interest_earned",), p), lookup(("interest_expended",), p)
        return round(earned - expended, 2) if earned is not None and expended is not None else None

    # a refresh without the filing's text (card_refresh) cannot judge comparatives, so it never brings back one the
    # stored table of this quarter does not have: a line's, or a column no line has
    kept = like if like and like.get("period") == period else None

    def withheld(key: str, slot: str) -> bool:
        if kept is None or slot == "value":
            return False
        row = kept.get(key)
        return slot not in row if isinstance(row, dict) else not any(isinstance(r, dict) and slot in r for r in kept.values())

    def line(pick, bps: bool, key: str = "") -> dict | None:
        values = {slot: None if withheld(key, slot) else pick(p) for slot, p in periods.items()}
        if values["value"] is None:
            return None
        row = {slot: v for slot, v in values.items() if v is not None}
        for slot, label in (("prev_year", "yoy"), ("prev_quarter", "qoq")):
            base = values[slot]
            if base is None:
                continue
            if bps:
                row[f"{label}_bps"] = round((values["value"] - base) * 100)
            elif base < 0 or values["value"] < 0:
                if key not in _TURN_LINES:
                    continue   # an exceptional charge that did not recur is not "loss to profit" (live review 3)
                # a % across a loss means nothing (Prism Johnson's PAT "+2127%" from a small loss, T11): name the turn
                now = values["value"]
                row[f"{label}_turn"] = ("LOSS_TO_PROFIT" if now >= 0 else "PROFIT_TO_LOSS" if base >= 0
                                        else "LOSS_NARROWED" if now > base else "LOSS_WIDENED")
            elif base:
                row[f"{label}_pct"] = round((values["value"] - base) / abs(base) * 100, 1)
        return row

    for key, names in _RESULT_METRICS:
        pick = margin if key == "ebitda_margin" else nii if key == "nii" else (lambda p, names=names: lookup(names, p))
        row = line(pick, key in _BPS_LINES, key)
        if row is None:
            continue
        if key == "revenue" and "yoy_pct" not in row:
            stated = next((m for m in mine if m["metric"] in names and m["period"] == period and m.get("yoy_pct") is not None), None)
            if stated:
                row["yoy_pct"] = stated["yoy_pct"]
        out[key] = row
    if len(out) <= 3:
        return None
    lens, rows = next(((name, rows) for name, top, rows in _LENSES if top in out), ("company", _LENSES[-1][2]))
    lines = [{"key": key, "label": label, "unit": unit} for key, label, unit in rows if key in out]
    if lens == "company":
        mover = _mover(out, lookup, periods)
        if mover is not None:
            key, names, label = mover
            if key not in out:
                out[key] = line(lambda p, names=names: lookup(names, p), False, key)
            at = next((i for i, spec in enumerate(lines) if spec["key"] == "pat"), len(lines))
            lines.insert(at, {"key": key, "label": label, "unit": "cr", "mover": True})
    # the sector's own figures (EBITDA a tonne for cement, ARPU for telecom, occupancy for hospitals...) where memory
    # holds them for this quarter; a KPI the statement already shows is not repeated
    shown = {key for key, _, _ in rows}
    for spec in footer:
        names = (spec["metric"], *spec.get("aliases", ()))
        if shown & set(names):
            continue
        unit = {"pct": "pct", "cr": "cr", "inr": "inr"}.get(spec.get("format", "num"), "num")
        row = line(lambda p, names=names: lookup(names, p), unit == "pct", f"kpi:{spec['metric']}")
        if row is not None:
            out[f"kpi:{spec['metric']}"] = row
            lines.append({"key": f"kpi:{spec['metric']}", "label": spec["label"], "unit": unit})
    out["lens"] = lens
    out["lines"] = lines
    return out
