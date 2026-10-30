"""NSE's broad index constituents, refreshed every Sunday (owner, 30 Oct 2026: "map stocks from NSE broad indices", "a pipeline to
update it every Sunday").

NSE publishes one static CSV per index on its archive host (the host company_master.py already reads for industries): company name,
industry, symbol, series, ISIN. Each is read and its members kept in ``index_members`` (D1), joined to ``companies`` by ISIN in the Results
KPI report, so a quarter's growth can be filtered and summarised by index. Measured 30 Oct 2026: all eleven lists answered 200 with a
plain browser User-Agent; Nifty 500 and Smallcap 250 carry a placeholder row ``DUMMYHEG`` and Microcap 250 three (``DUMMYINGL1``,
``DUMMYINGL2``, ``DUMMYINXGN``), which are not companies and are skipped.

A list is taken only when its size is near the index's own (a failed or cut download must not empty an index): otherwise that index
keeps last week's rows and the run ends with exit 1 after the others are written. A company that left an index is removed by the
as_of of the newest read."""

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


@dataclass
class Report:
    members: dict[str, int] = field(default_factory=dict)   # index id -> constituents written
    skipped: dict[str, str] = field(default_factory=dict)   # index id -> why its old rows were kept
    written: int = 0

    def as_dict(self) -> dict:
        return {"members": self.members, "skipped": self.skipped, "written": self.written}


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


def write(sink, taken: dict[str, list[dict]], as_of: str) -> int:
    """Put the taken indices' members in the table and take out whoever left them. Returns the rows written."""
    rows = [{"index_id": index_id, "as_of": as_of, **m} for index_id, members in taken.items() for m in members]
    written = 0
    for at in range(0, len(rows), BATCH):
        written += sink.execute("index_members_upsert", rows[at:at + BATCH])
    if taken:
        sink.execute("index_members_prune", [{"index_id": index_id, "as_of": as_of} for index_id in taken])
    return written


def sync(sink, client, as_of: str) -> Report:
    """Read NSE's lists and refresh ``index_members``."""
    taken, skipped = read_all(lambda name: client._get(INDEX_URL.format(name=name)).text)
    report = Report(members={i: len(m) for i, m in taken.items()}, skipped=skipped, written=write(sink, taken, as_of))
    log.info("index members from NSE: %s", report.as_dict())
    return report
