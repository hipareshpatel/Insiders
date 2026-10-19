"""Rebuild the round-5 companies from scratch for the measured re-run of round 4 (as round 2 was, 2026-10-18).

Memory written under older rules is reused by every later card, so a measured re-run needs it rebuilt under the
rules being measured (owner, 2026-10-18: "Rebuild the round-2 companies' memory with the new rule"). Two steps:

  python -I -X utf8 scripts/audit_round4/reset.py d1 OUT.json        # local web server stopped
  python -I -X utf8 scripts/audit_round4/reset.py dossiers           # local web server running, sink env set

`d1` saves the companies' cards to OUT.json, deletes them and their catalysts, and puts every one of their filings
back in the queue. `dossiers` replaces each company's memory with an empty one. Then `seed-memory --scrips` puts
the XBRL history back and `backfill-companies --scrips` reads the filings again.
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
SPEC = json.loads((HERE / "companies.json").read_text())
SCRIPS = [c["scrip_code"] for c in SPEC["companies"]]
DB_GLOB = "data/wrangler/v3/d1/miniflare-D1DatabaseObject/*.sqlite"


def d1(out: pathlib.Path) -> None:
    root = HERE.parents[2]
    db = [p for p in root.glob(DB_GLOB) if p.name != "metadata.sqlite"][0]
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    marks = ",".join("?" * len(SCRIPS))
    cards = [dict(r) for r in conn.execute(f"select * from cards where scrip_code in ({marks})", SCRIPS)]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    deleted = conn.execute(f"delete from cards where scrip_code in ({marks})", SCRIPS).rowcount
    catalysts = conn.execute(f"delete from catalysts where scrip_code in ({marks})", SCRIPS).rowcount
    queued = conn.execute(f"update filings set status = 'PENDING', attempts = 0, last_error = null "
                          f"where scrip_code in ({marks})", SCRIPS).rowcount
    conn.commit()
    print(f"{len(cards)} cards saved to {out}; {deleted} cards and {catalysts} catalysts deleted; "
          f"{queued} filings back in the queue")


def dossiers() -> None:
    from bse_intel.dossier import new_dossier
    from bse_intel.models import Filing
    from bse_intel.settings import Settings
    from bse_intel.sinks import make_sink

    sink = make_sink(Settings())
    for c in SPEC["companies"]:
        filing = Filing(news_id="reset", scrip_code=c["scrip_code"], company_name=c["company_name"], headline="",
                        filed_at="2026-10-18T00:00:00+05:30", filing_date="2026-10-18", symbol=c.get("symbol"))
        sink.put_dossier(c["scrip_code"], new_dossier(filing, sink.company(c["scrip_code"])))
    print(f"{len(SPEC['companies'])} dossiers replaced with empty ones")


if __name__ == "__main__":
    if sys.argv[1:2] == ["d1"] and len(sys.argv) == 3:
        d1(pathlib.Path(sys.argv[2]))
    elif sys.argv[1:] == ["dossiers"]:
        dossiers()
    else:
        raise SystemExit(__doc__)
