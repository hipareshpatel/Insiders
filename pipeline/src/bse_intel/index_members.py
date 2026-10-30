"""NSE's broad index constituents, refreshed every Sunday (owner, 30 Oct 2026: "map stocks from NSE broad indices", "a pipeline to
update it every Sunday").

NSE publishes one static CSV per index on its archive host (the host company_master.py already reads for industries): company name,
industry, symbol, series, ISIN. Each is read and its members kept in ``index_members`` (D1), joined to ``companies`` by ISIN in the Results
KPI report, so a quarter's growth can be filtered and summarised by index. Measured 30 Oct 2026: all eleven lists answered 200 with a
plain browser User-Agent; Nifty 500 and Smallcap 250 carry a placeholder row ``DUMMYHEG`` and Microcap 250 three (``DUMMYINGL1``,
``DUMMYINGL2``, ``DUMMYINXGN``), which are not companies and are skipped.

A list is taken only when its size is near the index's own (a failed or cut download must not empty an index): otherwise that index
is left as it is and the run ends with exit 1 after the others are written.

The table keeps history (owner, 30 Oct 2026: "track index changes so from next quarter onwards it shows the correct way"): a company
that joins an index gets a row with ``valid_from`` = the day of the read, one that leaves gets ``valid_to`` = that day, one that returns
gets a new row; an unchanged member writes nothing. The very first read of an index gives ``valid_from`` = ``FIRST_READ``, "a member
when we began tracking" (the day is kept in kv ``index_members:tracking_since``)."""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field

from .company_master import INDEX_URL

log = logging.getLogger(__name__)

# (id, label, file on NSE's archive host, the index's size). Order is the order the page lists them.
INDEXES = (
    ("NIFTY50", "Nifty 50", "ind_nifty50list.csv", 50),
    ("NIFTYNEXT50", "Nifty Next 50", "ind_niftynext50list.csv", 50),
    ("NIFTY100", "Nifty 100", "ind_nifty100list.csv", 100),
    ("NIFTY200", "Nifty 200", "ind_nifty200list.csv", 200),
    ("NIFTY500", "Nifty 500", "ind_nifty500list.csv", 500),
    ("LARGEMIDCAP250", "Nifty LargeMidcap 250", "ind_niftylargemidcap250list.csv", 250),
    ("MIDCAP150", "Nifty Midcap 150", "ind_niftymidcap150list.csv", 150),
    ("MIDSMALLCAP400", "Nifty MidSmallcap 400", "ind_niftymidsmallcap400list.csv", 400),
    ("SMALLCAP250", "Nifty Smallcap 250", "ind_niftysmallcap250list.csv", 250),
    ("MICROCAP250", "Nifty Microcap 250", "ind_niftymicrocap250_list.csv", 250),
    ("TOTALMARKET", "Nifty Total Market", "ind_niftytotalmarket_list.csv", 750),
)
SIZE_TOLERANCE = 0.10   # a list within 10% of the index's size is taken (Total Market is "about 750"; a cut download is far less)
BATCH = 500


FIRST_READ = "1900-01-01"   # valid_from of a member the first read of its index found (migration 0016)
TRACKING_KEY = "index_members:tracking_since"
LISTED = 30                 # symbols named per index in the report


@dataclass
class Report:
    members: dict[str, int] = field(default_factory=dict)   # index id -> constituents in the list read
    added: dict[str, list[str]] = field(default_factory=dict)    # index id -> symbols that joined (capped)
    closed: dict[str, list[str]] = field(default_factory=dict)   # index id -> symbols that left (capped)
    skipped: dict[str, str] = field(default_factory=dict)   # index id -> why it was left as it was
    adds: int = 0
    closes: int = 0
    written: int = 0                                          # rows sent: adds and closes

    def as_dict(self) -> dict:
        return {"members": self.members, "added": self.added, "closed": self.closed, "skipped": self.skipped,
                "adds": self.adds, "closes": self.closes, "written": self.written}


def parse_members(text: str) -> list[dict]:
    """The constituents of one NSE index CSV ("Company Name,Industry,Symbol,Series,ISIN Code"): {isin, symbol, company_name}. A row with no
    ISIN and a ``DUMMY`` placeholder (a demerger's stand-in, not a company) are left out; a repeated ISIN counts once."""
    out: dict[str, dict] = {}
    for row in csv.DictReader(io.StringIO((text or "").lstrip("﻿"))):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        isin, symbol = row.get("isin code", "").upper(), row.get("symbol", "").upper()
        if not isin or symbol.startswith("DUMMY"):
            continue
        out.setdefault(isin, {"isin": isin, "symbol": symbol, "company_name": row.get("company name", "")})
    return list(out.values())


def plausible(count: int, size: int) -> bool:
    """Whether a list of ``count`` members can be the whole index of ``size``."""
    return size * (1 - SIZE_TOLERANCE) <= count <= size * (1 + SIZE_TOLERANCE)


def read_all(fetch) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """Every index's members: ({index id: members}, {index id: why it was not taken}). ``fetch(file name)`` gives the CSV text. A source
    block (NSE refusing the session) is not caught: it stops the run, as in the company master."""
    from .nse import SourceBlockedError

    taken: dict[str, list[dict]] = {}
    skipped: dict[str, str] = {}
    for index_id, _label, name, size in INDEXES:
        try:
            members = parse_members(fetch(name))
        except SourceBlockedError:
            raise
        except Exception as exc:  # one list missing must not stop the others
            skipped[index_id] = f"not read: {exc}"
            continue
        if not plausible(len(members), size):
            skipped[index_id] = f"{len(members)} members read for an index of about {size}"
            continue
        taken[index_id] = members
    return taken, skipped


def write(sink, taken: dict[str, list[dict]], as_of: str, report: Report | None = None) -> Report:
    """Compare the taken lists with the open stretches of membership: add those who joined, close those who left, write nothing for the
    rest. An index with no open stretch at all is on its first read (or was emptied whole, which the size guard keeps from happening
    unseen): its members start at ``FIRST_READ``."""
    report = report or Report()
    # until the tracking day is saved (after every write below has gone through) this is still the first read, even when an earlier run
    # died halfway and left some members stored: the rest must start at FIRST_READ too, not at today
    first_read = sink.kv_get(TRACKING_KEY) is None
    open_rows: dict[str, dict[str, dict]] = {}
    for r in sink.query("index_members_open", []):
        open_rows.setdefault(r["index_id"], {})[r["isin"]] = r
    adds: list[dict] = []
    closes: list[dict] = []
    for index_id, members in taken.items():
        report.members[index_id] = len(members)
        held = open_rows.get(index_id, {})
        valid_from = FIRST_READ if first_read or not held else as_of   # a new index is a first read too: its earlier members are unknown
        now = {m["isin"] for m in members}
        joined = [m for m in members if m["isin"] not in held]
        left = [r for isin, r in held.items() if isin not in now]
        adds += [{"index_id": index_id, "isin": m["isin"], "symbol": m["symbol"], "company_name": m["company_name"],
                  "valid_from": valid_from} for m in joined]
        closes += [{"index_id": index_id, "isin": r["isin"], "valid_to": as_of} for r in left]
        if not first_read and held and joined:
            report.added[index_id] = [m["symbol"] for m in joined][:LISTED]
        if left:
            report.closed[index_id] = [r.get("symbol") or r["isin"] for r in left][:LISTED]
    for at in range(0, len(adds), BATCH):
        sink.execute("index_members_add", adds[at:at + BATCH])
    for at in range(0, len(closes), BATCH):
        sink.execute("index_members_close", closes[at:at + BATCH])
    report.adds, report.closes = len(adds), len(closes)
    report.written = len(adds) + len(closes)
    if taken and sink.kv_get(TRACKING_KEY) is None:
        sink.kv_set(TRACKING_KEY, as_of, as_of)
    return report


def sync(sink, client, as_of: str) -> Report:
    """Read NSE's lists and bring ``index_members`` up to date."""
    taken, skipped = read_all(lambda name: client._get(INDEX_URL.format(name=name)).text)
    report = write(sink, taken, as_of, Report(skipped=skipped))
    log.info("index members from NSE: %s", report.as_dict())
    return report
