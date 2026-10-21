"""Estimate D1 rows written per pipeline step, before and after a change to db/statements (no network, no AI).

D1 counts a written row for each table row, each index entry and each full-text row a statement touches, triggers
included. This applies db/migrations to an in-memory SQLite, runs each scenario with the statements of a git revision
(``--before``, default HEAD) and of the working tree, and counts SQLite's total_changes (rows, trigger rows, full-text
rows) plus the index entries that changed (primary-key autoindexes too).

    python pipeline/scripts/d1_write_cost.py [--before HEAD]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPANIES = 200   # companies in the maintenance scenarios (results are scaled to 1,000)


def statements(rev: str | None) -> dict[str, str]:
    out = {}
    for path in sorted((ROOT / "db" / "statements").glob("*.sql")):
        if rev is None:
            out[path.stem] = path.read_text()
        else:
            rel = path.relative_to(ROOT).as_posix()
            out[path.stem] = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{rel}"], capture_output=True,
                                            text=True, check=True).stdout
    return out


class Db:
    def __init__(self, sql: dict[str, str]):
        self.sql = sql
        self.c = sqlite3.connect(":memory:")
        for migration in sorted((ROOT / "db" / "migrations").glob("*.sql")):
            self.c.executescript(migration.read_text())
        self.indexes = []   # (table, index name, columns, partial WHERE)
        for (table,) in self.c.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND sql NOT LIKE '%VIRTUAL%'"
                                       " AND name NOT LIKE '%fts%' AND name NOT LIKE 'sqlite_%'"):
            for row in self.c.execute(f"PRAGMA index_list('{table}')"):
                name = row[1]
                cols = [r[2] for r in self.c.execute(f"PRAGMA index_info('{name}')")]
                ddl = (self.c.execute("SELECT sql FROM sqlite_master WHERE name = ?", [name]).fetchone() or [None])[0]
                where = re.search(r"\bWHERE\b(.*)$", ddl or "", re.S | re.I)
                self.indexes.append((table, name, cols, where.group(1).strip().rstrip(";") if where else None))

    def _entries(self) -> dict[str, set]:
        out = {}
        for table, name, cols, where in self.indexes:
            q = f"SELECT {', '.join(cols)}, rowid FROM {table}" + (f" WHERE {where}" if where else "")
            out[name] = set(self.c.execute(q).fetchall())
        return out

    def run(self, statement: str, rows: list[dict]) -> int:
        before_idx, before = self._entries(), self.c.total_changes
        self.c.execute(self.sql[statement], [json.dumps(rows)])
        changed = self.c.total_changes - before
        after_idx = self._entries()
        index = sum(max(len(after_idx[n] - before_idx[n]), len(before_idx[n] - after_idx[n])) for n in after_idx)
        return changed + index


def ledger(i: int, **extra) -> dict:
    return {"news_id": f"n{i}", "scrip_code": f"5{i % COMPANIES:05d}", "company_name": f"Company {i % COMPANIES}",
            "symbol": f"SYM{i % COMPANIES}", "headline": "Outcome of board meeting", "subject": "Results",
            "category": "Result", "subcategory": "", "filed_at": f"2026-10-20T{10 + i % 8:02d}:00:00+05:30",
            "filing_date": "2026-10-20", "pdf_url": f"https://nsearchives.nseindia.com/corporate/F_{i}.pdf",
            "xbrl_url": None, "status": "PENDING", "route": "PASS1", "event_type": "RESULTS", "reason": "results",
            "updated_at": "2026-10-20T18:01:00+05:30", **extra}


def company(i: int, **extra) -> dict:
    return {"scrip_code": f"5{i:05d}", "symbol": f"SYM{i}", "company_name": f"Company {i}", "isin": f"INE{i:06d}01",
            "industry": "Cement", "sector": "cement", "market_cap_cr": 1000.0 + i, "size_category": "SMALL",
            "last_price": 100.0 + i, "price_date": "2026-10-20", "ret_1w": 1.5, "ret_1m": -2.0, "ret_1y": 9.0,
            "technicals_json": json.dumps({"rs": i % 100}), "updated_at": "2026-10-20T06:00:00+05:30",
            "memory_summary_json": json.dumps({"open": i % 3}), "earliest_open_due": "2027-03-31",
            "former_names_json": "[]", **extra}


def card(i: int, **extra) -> dict:
    body = {"news_id": f"n{i}", "headline": f"Company {i} Q2 revenue up 12%", "what_happened": ["Revenue ₹120 Cr"] * 6,
            "review": {"status": "OK"}}
    return {"news_id": f"n{i}", "scrip_code": f"5{i % COMPANIES:05d}", "symbol": f"SYM{i % COMPANIES}",
            "company_name": f"Company {i % COMPANIES}", "filing_date": "2026-10-20",
            "filed_at": f"2026-10-20T{10 + i % 8:02d}:00:00+05:30", "sector": "cement", "event_category": "RESULTS",
            "impact_level": "MODERATE", "headline": body["headline"], "grounding_score": 0.97, "needs_review": 0,
            "memory_complete": 1, "card": body, "pdf_url": f"https://x/F_{i}.pdf", "model": "writer",
            "created_at": "2026-10-20T18:05:00+05:30", "market_session": "AFTER_MARKET", "actionability_score": 40,
            "is_actionable_signal": 0, "held": 0, **extra}


def analysed(i: int) -> list[tuple[str, list[dict]]]:
    """One filing's commit (pipeline._commit_rows): its company with the memory summary, the card, a catalyst, the
    ledger status."""
    return [("companies_upsert", [company(i % COMPANIES, memory_summary_json=json.dumps({"open": i}),
                                          updated_at="2026-10-20T18:05:00+05:30")]),
            ("cards_upsert", [card(i)]),
            ("catalysts_upsert", [{"id": f"c{i}", "scrip_code": f"5{i % COMPANIES:05d}", "event_type": "AGM",
                                   "event_date": "2027-08-20", "description": "AGM", "source_news_id": f"n{i}",
                                   "created_at": "2026-10-20T18:05:00+05:30"}]),
            ("filings_update", [{"news_id": f"n{i}", "status": "ANALYZED", "event_type": "RESULTS", "reason": None,
                                 "last_error": None, "updated_at": "2026-10-20T18:05:00+05:30"}])]


def scenarios(db: Db) -> dict[str, float]:
    out = {}
    db.run("companies_upsert", [company(i) for i in range(COMPANIES)])
    n = 50
    db.run("filings_discover", [ledger(i) for i in range(n)])
    first = sum(db.run(s, rows) for i in range(n) for s, rows in analysed(i))
    out["analysed filing, first reading (commit)"] = first / n
    again = sum(db.run(s, [dict(r, updated_at="2026-10-20T19:00:00+05:30", created_at="2026-10-20T19:00:00+05:30")
                           if s in ("cards_upsert", "filings_update") else r for r in rows])
                for i in range(n) for s, rows in analysed(i))
    out["same filing committed again, same card (retry, re-run)"] = again / n
    db.run("filings_discover", [ledger(i) for i in range(n, n + 100)])
    cut = db.run("filings_update", [{"news_id": f"n{i}", "status": "PENDING", "attempts": 0,
                                     "updated_at": "2026-10-20T20:00:00+05:30"} for i in range(n, n + 100)])
    out["filing left PENDING by a run cut short"] = cut / 100
    out["known filing discovered again (live runs, resumed day)"] = db.run("filings_discover",
                                                                         [ledger(i) for i in range(n + 100)]) / (n + 100)
    scale = 1000 / COMPANIES
    same = [{k: v for k, v in company(i).items() if k in ("scrip_code", "last_price", "price_date", "ret_1w", "ret_1m",
                                                         "ret_1y", "technicals_json", "market_cap_cr", "size_category")}
            | {"company_name": f"5{i:05d}", "updated_at": "2026-10-20T13:00:00+05:30"} for i in range(COMPANIES)]
    out["market-data, second run of a day (1,000 companies)"] = db.run("companies_upsert", same) * scale
    moved = [dict(r, last_price=r["last_price"] + 1, price_date="2026-10-21", ret_1w=2.0) for r in same]
    out["market-data, a new trading day (1,000 companies)"] = db.run("companies_upsert", moved) * scale
    summaries = [{"scrip_code": f"5{i:05d}", "company_name": f"Company {i}", "updated_at": "2026-10-21T01:00:00+05:30",
                  "memory_summary_json": json.dumps({"open": i % 3 if i % 20 else 99}), "earliest_open_due": "2027-03-31",
                  "inflection_last_at": None, "former_names_json": "[]"} for i in range(COMPANIES)]
    db.run("companies_upsert", summaries)   # the first refresh after the code change
    out["refresh-summaries, nothing changed (1,000 companies)"] = db.run("companies_upsert", [
        dict(r, updated_at="2026-10-22T01:00:00+05:30") for r in summaries]) * scale
    out["refresh-card-blocks re-sending 1,000 unchanged cards"] = db.run("cards_upsert", [
        card(i, created_at="2026-10-22T01:00:00+05:30") for i in range(n)]) * 1000 / n
    run = {"run_id": "r1", "mode": "all", "started_at": "a", "status": "RUNNING"}
    done = dict(run, finished_at="b", status="OK", stats={"analyzed": 3})
    out["pipeline run record (start + finish + one retried finish)"] = (db.run("runs_upsert", [run]) + db.run(
        "runs_upsert", [done]) + db.run("runs_upsert", [done]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--before", default="HEAD", help="git revision of the statements to compare against")
    args = ap.parse_args()
    before, after = scenarios(Db(statements(args.before))), scenarios(Db(statements(None)))
    # seed-memory --universe: one kv write per company before, one per ten companies after (cli.SEED_SAVE_EVERY)
    kv = Db(statements(None)).run("kv_set", [{"key": "seed:universe_last", "value": "1", "updated_at": "a"}])
    before["seed-memory --universe resume point (1,000 companies)"] = 1000 * kv
    after["seed-memory --universe resume point (1,000 companies)"] = 100 * kv
    width = max(map(len, before))
    print(f"{'step':<{width}}  {'before':>8}  {'after':>8}")
    for key in before:
        print(f"{key:<{width}}  {before[key]:>8.1f}  {after[key]:>8.1f}")


if __name__ == "__main__":
    main()
