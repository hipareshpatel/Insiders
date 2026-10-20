"""Event XBRL (Reg 30) from NSE: the structured form a company files beside an announcement's PDF (PLAN 18 part 3).

For orders and contracts, litigation, regulatory actions, director and KMP changes, licences, guarantees, ESOPs and
the like, NSE lists a machine-readable file in the "Announcements XBRL" tab (`/api/XBRL-announcements`, types
`announcements`, `para-b`, `action`; docs/SOURCES.md "Event XBRL"). Its fields are exact: an order's amount in rupees,
the counterparty and its CIN, the dates, New or Amendment, whether it is a related-party transaction. Code takes those
from the file; the model writes only the context around them.

Joining a file to its announcement (measured 2026-10-18 on 13-18 Oct, 300 files, 2,429 announcements):
* there is no shared key: the announcement's `seq_id` and the file's `appId` are different series, and NSE's
  `hasXbrl` is true on every announcement;
* the same file: 45 director-change rows point at the announcement's own attachment URL, and 76 of the 82 orders,
  actions and litigation rows that carry a PDF carry one of exactly the announcement's size (NSE prints both as
  "186.38 KB"), each time one announcement of that symbol;
* otherwise the file is confirmed from its content: an amount it states, printed in the PDF at some unit, or for an
  event without an amount a name it states (the director, the counterparty, the authority);
* the subject often differs: a director change is filed as "Appointment", "Resignation", "Cessation", "Outcome of
  Board Meeting"; an order or an ESOP vesting as "General Updates". So the event family ranks candidates but
  does not decide;
* the file follows the PDF by a median of 8 minutes, 79% within an hour, the longest 92 hours, and a director change's
  file can come a few minutes before its PDF (Camlin 10:59 / 11:03, Imagicaa 22:56 / 23:02). Hence the window.
"""

from __future__ import annotations

import html
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .timeutil import IST

KINDS = ("announcements", "para-b", "action")
BEFORE = timedelta(hours=6)    # a file may be broadcast this long before its PDF
AFTER = timedelta(days=5)      # ... and this long after it (the longest measured: 92 hours)
WAIT_MINUTES = 90              # a live filing of an XBRL event waits this long for its file (79% within an hour)
_WHEN = "%d-%b-%Y %H:%M:%S"
# Director and KMP changes get no card (owner, 2026-10-18), so their files are not read
NO_CARD_FAMILIES = ("management",)

# Event families, from the measured pairs of XBRL event type and announcement subject (13-18 Oct 2026)
FAMILIES = (
    ("orders", re.compile(r"orders?\s*/\s*contracts?|order\(s\)\s*/\s*contract\(s\)|bagging|awarding of order")),
    ("agreements", re.compile(r"^agreements?\b|rescission|termination\(s\)|amendment or termination of agreement")),
    ("legal", re.compile(r"litigation|dispute|action\(s\)|actions? taken|actions? initiated")),
    ("management", re.compile(r"director|kmp|\bsmp\b|resignation|appointment|cessation|change in management|retirement"
                              r"|company secretary|compliance officer|auditor|registrar|\brta\b")),
    ("licences", re.compile(r"licen[cs]e|regulatory approval|granting/withdrawal")),
    ("esop", re.compile(r"esop|esos|esps|options to purchase")),
    ("guarantees", re.compile(r"guarantee|indemnity|surety")),
    ("operations", re.compile(r"capacity|product launch|commencement|commercial production|new line")),
    ("fraud", re.compile(r"fraud|default|arrest")),
    ("framework", re.compile(r"regulatory framework")),
)
# Subjects a company files any event under (measured: orders, ESOPs, guarantees and actions as "General Updates")
GENERIC = re.compile(r"^(general )?updates?$|outcome of board meeting|press release|disclosure under|intimation")

# Fields that identify nothing or repeat the header
_SKIP = re.compile(r"Domain$|^MSEISymbol$|Signator|^Salutation|^PositionOfDirectorInBoard|^NameOfTheCompany$"
                   r"|^NSESymbol$|^ScripCode$|^ISIN$")
_EMPTY = {"", "na", "n.a.", "n/a", "nil", "none", "not applicable", "not available", "-"}
_NAME_FIELD = re.compile(r"^NameOf(?!TheCompany$|TheSignatory|TheCountry)|^NameOfDirector$|NSESymbolOfTheCounterparty")
_STOP = {"mr", "ms", "mrs", "dr", "shri", "smt", "the", "of", "and", "ltd", "limited", "private", "pvt", "co", "company",
         "india", "inc", "llp", "m", "s"}


def family(text: str | None) -> str | None:
    text = " ".join((text or "").lower().split())
    return next((name for name, rx in FAMILIES if rx.search(text)), None)


def generic(subject: str | None) -> bool:
    return bool(GENERIC.search(" ".join((subject or "").lower().split())))


@dataclass(frozen=True)
class EventFile:
    """One row of NSE's event XBRL list."""

    app_id: str
    symbol: str
    kind: str
    event_type: str
    broadcast_at: datetime
    xbrl_url: str | None          # the .xml, or a .zip holding it
    attachment_url: str | None
    attachment_size: str | None   # as NSE prints it: "186.38 KB"
    revision: str = "Original"
    prev_app_id: str | None = None

    @property
    def family(self) -> str | None:
        return family(self.event_type)


def parse_list(rows, kind: str) -> list[EventFile]:
    out = []
    for row in rows if isinstance(rows, list) else []:
        try:
            at = datetime.strptime(str(row.get("broadcastDateTime") or "").strip(), _WHEN).replace(tzinfo=IST)
        except ValueError:
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or row.get("appId") in (None, ""):
            continue
        attachment = str(row.get("attachment") or "").strip() or None
        xbrl = str(row.get("xbrl") or "").strip() or None
        if xbrl is None and attachment and attachment.lower().endswith((".xml", ".zip")):
            xbrl = attachment   # a director change's row: the file, or a zip of it and the PDF, in `attachment`
        out.append(EventFile(str(row["appId"]), symbol, kind, html.unescape(str(row.get("eventType") or row.get("subject") or "")),
                             at, xbrl, attachment, row.get("attachfileSize") if kind != "announcements" else None,
                             str(row.get("typeOfAnn") or row.get("revision") or "Original"),
                             str(row["prevAppId"]) if row.get("prevAppId") else None))
    return out


@dataclass
class EventFacts:
    """What one file states. `main` is the event's header; `items` one dict per order, action, person or party."""

    app_id: str = ""
    symbol: str = ""
    isin: str = ""
    scrip_code: str = ""
    event_type: str = ""
    main: dict[str, str] = field(default_factory=dict)
    items: list[dict[str, str]] = field(default_factory=list)
    money: set[str] = field(default_factory=set)   # names of the fields in rupees
    pdf_size: int | None = None                    # the PDF beside it in the zip, when there is one
    company: str = ""

    def get(self, name: str) -> str | None:
        if name in self.main:
            return self.main[name]
        return next((i[name] for i in self.items if name in i), None)

    def amounts_cr(self) -> list[float]:
        out = []
        for part in [self.main, *self.items]:
            for name, value in part.items():
                if name in self.money:
                    try:
                        rupees = float(value.replace(",", ""))
                    except ValueError:
                        continue
                    if rupees > 0:
                        out.append(rupees / 1e7)
        return out

    def names(self, strict: bool = False) -> list[str]:
        """The names the file states. ``strict`` leaves out those that do not tell this event from the company's
        others: the company itself (an action "against the listed entity" names it, as does every filing of the
        company) and an authority (RBI, SEBI or a tax office write to a company about many things). Measured 13-18 Oct
        2026: under a generic subject both paired files with the wrong PDF (Yes Bank's ESG-rating letter, Reliance
        Power's letter); under the event's own subject they are what identifies a regulatory action. The company's
        own name is never one (round 5, 2026-10-19: Dabur's 7 Aug court-stay file paired with its 6 Aug FDA letter on
        "Dabur India Limited" alone, and the card told of a stay granted the day after its own filing)."""
        own = _words(self.company)
        return [v for part in [self.main, *self.items] for k, v in part.items()
                if _NAME_FIELD.search(k) and _words(v) != own and not (strict and "Authority" in k)]


def xml_of(body: bytes | None) -> tuple[bytes | None, int | None]:
    """The XML in a downloaded file (a zip holds it beside the PDF), and that PDF's size."""
    if not body:
        return None, None
    if body[:2] == b"PK":
        try:
            archive = zipfile.ZipFile(io.BytesIO(body))
        except zipfile.BadZipFile:
            return None, None
        names = archive.namelist()
        xml = next((n for n in names if n.lower().endswith(".xml")), None)
        pdf = next((n for n in names if n.lower().endswith(".pdf")), None)
        return (archive.read(xml) if xml else None), (archive.getinfo(pdf).file_size if pdf else None)
    return body, None


def _root(data: bytes):
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        # Some files declare UTF-8 and carry Windows-1252 bytes (ACME Solar's "�06.04.2028")
        text = re.sub(r"^\s*<\?xml[^>]*\?>", "", data.decode("utf-8", errors="replace"))
        try:
            return ET.fromstring(text)
        except ET.ParseError:
            return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse(data: bytes | None, app_id: str = "") -> EventFacts | None:
    xml, pdf_size = xml_of(data)
    root = _root(xml) if xml else None
    if root is None:
        return None
    money_units = {u.get("id") for u in root.iter() if _local(u.tag) == "unit"
                   and any("INR" in (m.text or "").upper() for m in u.iter() if _local(m.tag) == "measure")}
    by_context: dict[str, dict[str, str]] = {}
    money: set[str] = set()
    header = {}
    for el in root.iter():
        ctx = el.get("contextRef")
        if ctx is None or el.text is None:
            continue
        name, value = _local(el.tag), " ".join(el.text.split())
        if name in ("NSESymbol", "ScripCode", "ISIN", "NameOfTheCompany"):
            header[name] = value
        if _SKIP.search(name) or value.lower() in _EMPTY:
            continue
        if el.get("unitRef") in money_units:
            money.add(name)
        part = by_context.setdefault(ctx, {})
        part[name] = f"{part[name]}; {value}" if name in part and value not in part[name] else value
    if not by_context and not header:
        return None
    # NSE spreads one event over several contexts (Camlin's dates in one, its director in another). A context whose
    # fields another context also states is one of several orders, actions or people; the rest are the event's own.
    seen: dict[str, int] = {}
    for part in by_context.values():
        for name in part:
            seen[name] = seen.get(name, 0) + 1
    main: dict[str, str] = {}
    items = []
    for part in by_context.values():
        if any(seen[name] > 1 for name in part):
            items.append(part)
        else:
            main.update(part)
    event = next((main[k] for k in sorted(main) if k.startswith("SubTypeOfEvent")), None)         or next((v for k, v in main.items() if k.startswith("TypeOfEvent")), "")
    return EventFacts(app_id, header.get("NSESymbol", "").upper(), header.get("ISIN", "").upper(), header.get("ScripCode", ""),
                      event, main, items, money, pdf_size, header.get("NameOfTheCompany", ""))


def _size_label(size: int) -> str:
    """A byte count as NSE prints it beside an attachment ("385.29 KB", "1.73 MB")."""
    return f"{size / 1024:.2f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.2f} MB"


def same_file(file: EventFile, pdf_url: str | None, pdf_size: str | None, facts: EventFacts | None = None) -> bool:
    """The file was filed with this very attachment: the same URL, the same PDF re-attached (its size to the
    hundredth of a KB), or the PDF in its zip of that size."""
    if pdf_url and file.attachment_url and file.attachment_url == pdf_url:
        return True
    size = (pdf_size or "").strip()
    if size and file.attachment_url and file.attachment_url.lower().endswith(".pdf") and (file.attachment_size or "").strip() == size:
        return True
    return bool(size and facts and facts.pdf_size and _size_label(facts.pdf_size) == size)


_NUMBER = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?")


def _numbers(text: str) -> list[tuple[float, int]]:
    """Each number in the text and how many significant digits it is printed with."""
    out = []
    for raw in _NUMBER.findall(text or ""):
        digits = raw.replace(",", "")
        try:
            out.append((float(digits), len(digits.replace(".", "").lstrip("0"))))
        except ValueError:
            continue
    return out


def amount_found(crores: list[float], text: str) -> bool | None:
    """Whether one of these ₹ crore amounts is printed in the text in crore, lakh, million or rupees, with at least
    three significant digits (a bare "32" proves nothing). None when there is no amount to look for."""
    if not crores:
        return None
    numbers = _numbers(text)
    for crore in crores:
        for scale in (1, 100, 10, 1e7):
            want = crore * scale
            if want < 1:
                continue
            for value, digits in numbers:
                if digits >= 3 and abs(value - want) <= max(0.0051 * scale if scale < 1e7 else 1.0, want * 0.0005):
                    return True
    return False


def _words(text: str) -> str:
    return " ".join(w for w in re.findall(r"[a-z0-9]+", html.unescape(text or "").lower()) if w not in _STOP)


def name_found(names: list[str], text: str) -> bool | None:
    """Whether one of these names (a director, a counterparty, an authority) is in the text, honorifics and "Limited"
    aside. None when there is no name of two letters or more to look for."""
    wanted = [w for w in (_words(n) for n in names) if len(w) >= 4]
    if not wanted:
        return None
    body = f" {_words(text)} "
    return any(f" {w} " in body for w in wanted)


def confirm(facts: EventFacts, text: str, strict: bool = False) -> bool:
    """The file describes what this PDF describes: an amount it states is printed in it; for an event without an
    amount, a name it states is (with ``strict``, for a filing under a generic subject, a name that identifies the
    event). A file whose amount is not there belongs to another order of the same client."""
    found = amount_found(facts.amounts_cr(), text)
    if found is not None:
        return found
    return bool(name_found(facts.names(strict), text))


def candidates(files: list[EventFile], symbol: str, filed_at: datetime) -> list[EventFile]:
    """The company's files broadcast in the window around a filing, latest revision of each kept."""
    near = [f for f in files if f.symbol == symbol and filed_at - BEFORE <= f.broadcast_at <= filed_at + AFTER
            and f.family not in NO_CARD_FAMILIES]
    replaced = {f.prev_app_id for f in near if f.prev_app_id}
    return [f for f in near if f.app_id not in replaced]


@dataclass
class Match:
    file: EventFile
    facts: EventFacts
    how: str   # "same file" or "content"


def match(filing, files: list[EventFile], read, text: str) -> tuple[list[Match], list[str]]:
    """The event XBRL files that belong to this filing, and the app ids of every file looked at.

    ``read(file)`` returns the file's EventFacts (or None). A file of the same attachment is taken; otherwise a file
    whose content the PDF confirms, of the filing's event family or filed under a generic subject."""
    filed_at = datetime.fromisoformat(filing.filed_at)
    near = candidates(files, (filing.symbol or "").upper(), filed_at)
    mine = family(filing.subject)
    exact, confirmed = [], []
    for f in sorted(near, key=lambda f: abs((f.broadcast_at - filed_at).total_seconds())):
        quick = same_file(f, filing.pdf_url, filing.attachment_size)
        if not quick and mine != f.family and not generic(filing.subject):
            continue   # another event of the company's (its own announcement is elsewhere)
        facts = read(f)
        if facts is None or (facts.symbol and facts.symbol != f.symbol):
            continue
        if quick or same_file(f, filing.pdf_url, filing.attachment_size, facts):
            exact.append(Match(f, facts, "same file"))
        elif text and confirm(facts, text, strict=mine != f.family):
            confirmed.append(Match(f, facts, "content"))
    return (exact or confirmed), [f.app_id for f in near]


_SHORTER = ((re.compile(r"\s*as per regulation\s*30\s*para b of part a of schedule iii"), ""),
            (re.compile(r"orders? or contracts?"), "order"),
            (re.compile(r"director or key managerial personnel or senior management personnel or compliance officer"),
             "director/KMP"),
            (re.compile(r"actions? (taken|initiated) or orders passed"), "action"),
            (re.compile(r"\bof the listed entity\b"), "of the company"))


def _label(name: str) -> str:
    text = " ".join(re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|(?<=[a-z])(?=\d)", " ", name).split()).lower()
    for rx, short in _SHORTER:
        text = rx.sub(short, text)
    return " ".join(text.split())[:120]


def _value(name: str, value: str, money: set[str]) -> str:
    if name in money:
        try:
            rupees = float(value.replace(",", ""))
            return f"₹{rupees / 1e7:,.2f} crore (₹{rupees:.0f})"
        except ValueError:
            pass
    return value[:300]


def table(matches: list[Match]) -> str:
    """The files' fields as lines put in front of the filing's text."""
    if not matches:
        return ""
    lines = ["Event XBRL (the structured form the company filed with NSE for this event; exact: take amounts, parties,"
             " dates, new/amendment and related-party status from here, the PDF for context):"]
    for m in matches:
        lines.append(f"- file {m.file.app_id} ({m.file.revision}), broadcast {m.file.broadcast_at:%d %b %Y %H:%M}: "
                     f"{m.facts.event_type or m.file.event_type}")
        for name, value in m.facts.main.items():
            if not name.startswith(("TypeOfEvent", "SubTypeOfEvent")):
                lines.append(f"  {_label(name)}: {_value(name, value, m.facts.money)}")
        for n, item in enumerate(m.facts.items, 1):
            lines.append(f"  item {n}:" if len(m.facts.items) > 1 else "  details:")
            for name, value in item.items():
                lines.append(f"    {_label(name)}: {_value(name, value, m.facts.money)}")
    return "\n".join(lines)


_INCL = re.compile(r"\binclu\w*\s*(?:of\s*)?(?:gst|tax|taxes)|\(\s*including\s*tax", re.I)
_EXCL = re.compile(r"\bexclu\w*\s*(?:of\s*)?(?:gst|tax|taxes)|\(\s*excluding\s*tax", re.I)


def _yes(value: str | None) -> bool | None:
    v = (value or "").strip().lower()
    return True if v in ("true", "yes") else False if v in ("false", "no") else None


@dataclass
class Order:
    """One order or contract as the file states it."""

    amount_cr: float
    counterparty: str | None
    received: bool               # bagged/received (an order win), not awarded by the company to someone
    announcement: str | None     # New / Amendment
    dated: str | None
    execution_by: str | None
    includes_gst: bool | None
    related_party: bool | None
    promoter_interest: bool | None
    domestic: str | None


def orders(matches: list[Match]) -> list[Order]:
    out = []
    for m in matches:
        f = m.facts
        sub = (f.get("SubTypeOfEventAsPerRegulation30ParaBOfPartAOfScheduleIII") or f.event_type or m.file.event_type).lower()
        if family(sub) != "orders":
            continue
        for item in f.items or [f.main]:
            raw = item.get("AmountOfTheOrdersOrContracts")
            try:
                amount = float((raw or "").replace(",", "")) / 1e7
            except ValueError:
                continue
            if amount <= 0:
                continue
            broad = item.get("BroadConsiderationForTheOrdersOrContracts") or ""
            out.append(Order(round(amount, 4), item.get("NameOfTheEntityAwardingTheOrdersOrContracts"),
                             "awarding" not in sub, f.get("TypeOfAnnouncementAsPerRegulation30ParaBOfPartAOfScheduleIII"),
                             item.get("DateOfBaggingOrReceivingOfOrdersOrContracts"),
                             item.get("TimePeriodByWhichTheOrdersOrContractsIsToBeExecuted"),
                             True if _INCL.search(broad) else False if _EXCL.search(broad) else None,
                             _yes(item.get("WhetherTheOrderOrContractWouldFallWithinRelatedPartyTransactions")),
                             _yes(item.get("WhetherThePromoterOrPromoterGroupOrGroupCompaniesHaveAnyInterestInThatEntityToWhomTheOrdersOrContractsIsAwarded")),
                             item.get("WhetherOrdersOrContractsIsAwardedByDomesticOrInternationalEntity")))
    return out


def apply_orders(card, found: list[Order]) -> list[str]:
    """Put one order's exact figures on the card's deal (code, not the model, owns them). Several orders in the
    files leave the deal as the model read it: which of them the card's deal is cannot be told here. Returns
    what changed."""
    if card is None or len(found) != 1:
        return []
    from .models import DealValue

    order = found[0]
    deal = card.deal_value
    notes = []
    if deal is None:
        card.deal_value = DealValue(kind="ORDER" if order.received else "OTHER", amount_cr=order.amount_cr,
                                    counterparty=order.counterparty, includes_gst=order.includes_gst,
                                    execution_by=order.execution_by)
        return [f"deal: ₹{order.amount_cr:g} Cr from the event XBRL"]
    if deal.amount_cr is None or abs(deal.amount_cr - order.amount_cr) > max(0.01, 0.005 * order.amount_cr):
        notes.append(f"deal amount {deal.amount_cr} -> {order.amount_cr:g} Cr (event XBRL)")
        deal.amount_cr = order.amount_cr
    if order.counterparty and deal.counterparty != order.counterparty:
        notes.append(f"counterparty {deal.counterparty!r} -> {order.counterparty!r} (event XBRL)")
        deal.counterparty = order.counterparty
    if order.includes_gst is not None and deal.includes_gst != order.includes_gst:
        notes.append(f"includes_gst {deal.includes_gst} -> {order.includes_gst} (event XBRL)")
        deal.includes_gst = order.includes_gst
    if order.execution_by and not deal.execution_by:
        deal.execution_by = order.execution_by
    if order.received and deal.kind == "OTHER":
        deal.kind = "ORDER"
    return notes


def summary(matches: list[Match], checked: list[str]) -> dict:
    """What the card records about its event XBRL (card_json["event_xbrl"])."""
    found = orders(matches)
    return {"files": [{"app_id": m.file.app_id, "event": m.facts.event_type or m.file.event_type, "how": m.how,
                       "broadcast_at": m.file.broadcast_at.isoformat(), "url": m.file.xbrl_url,
                       "announcement": m.facts.get("TypeOfAnnouncementAsPerRegulation30ParaBOfPartAOfScheduleIII")
                       or m.facts.get("TypeOfAnnouncement")} for m in matches],
            "orders": [o.__dict__ for o in found] or None, "checked": checked}
