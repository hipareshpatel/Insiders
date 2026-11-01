"""Companies that are not listed on NSE, found and removed from the master (owner, 25 Oct 2026: "remove all other than
NSE listed companies from our database"; TODO row 45, TRACKER F158).

Since D34 the platform is NSE only, but the companies table still holds every BSE scrip it was seeded with (about
5,260 rows against NSE's 2,629 main-board companies): BSE-only equities, mutual-fund and ETF scrips, REIT/InvIT units,
delisted or suspended names. The pipeline never read them: the universe (universe.select) starts from NSE's equity list
and joins our rows to it by ISIN, else symbol, so only matched companies are ``included`` and memory-gaps, discovery and
the market-data job work from that list. What the rows cost is the public companies list, and noise in counts.

A row is NSE's when its ISIN is on NSE's equity list (EQUITY_L.csv), or, with no ISIN stored, its symbol or key is a symbol
on the list. NSE Emerge's SME list (SME_EQUITY_L.csv) is read as well, so an SME scrip is named as one (the universe is
the main board, so SME rows go too unless ``keep_sme``). A row whose ISIN differs from NSE's but whose symbol matches is
kept and reported (``isin_mismatch``): a renamed or re-ISIN'd company is not removed on a guess.

Removal rules (``plan``): a company with a card (published or held), or on the owner's watchlist, is never removed; it is
listed apart as ``has_cards`` for the owner to decide (keep, or hide from lists; the schema has no hidden flag, so
nothing is flagged). Only a company with no cards at all is removed, with its memory file. ``apply`` first writes every
row it will remove, with the keys and content of their memory files, to R2 ``backup/prune-companies-<date>.json``, reads
that object back, and only then deletes the memory objects and company rows (companies_prune re-checks "no cards" in
SQL). The filing ledger rows of removed companies stay (the noise audit's history); their counts are in the report.

Kept BSE-only companies (owner, 26 Oct 2026, Option A): a row classified ``bse_only_equity`` whose stored market_cap_cr is
``BSE_KEEP_MIN_MCAP_CR`` (500 Cr) or more is never removed (``bse_kept``): it is set aside, listed in the report (scrip, name,
ISIN, market cap) and counted apart (about 131 rows on 25 Oct), for a later BSE daily pass. ``--bse-keep-min-mcap N`` changes
the line, 0 turns the keep off. Fund / ETF and REIT / InvIT rows are removed whatever their value."""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

PAGE = 1000
READ_WORKERS = 8
APPLY_BATCH = 200
MIN_NSE_ROWS = 2000     # NSE's main board has ~2,600; a shorter answer is a broken file, and pruning against it would empty the table
MIN_SME_ROWS = 100
BSE_KEEP_MIN_MCAP_CR = 500   # owner, 26 Oct 2026: BSE-only companies worth this much or more are kept and set aside
BACKUP_PREFIX = "backup/prune-companies-"
TRUST = re.compile(r"\b(reit|invit|real estate investment trust|infrastructure investment trust)\b", re.I)

BSE_ONLY = "bse_only_equity"
FUND = "mutual_fund_etf"
REIT = "reit_invit"
SME = "nse_sme"
BSE_KEPT = "bse_kept"   # a kept type, never removed: a BSE-only equity at or over BSE_KEEP_MIN_MCAP_CR
REMOVE_TYPES = (BSE_ONLY, FUND, REIT, SME)
DOSSIER_SECTIONS = ("financial_metrics", "ownership", "timeline", "deals", "balance_sheet", "capital_actions")


def classify(company: dict, nse_isins: set[str], nse_symbols: set[str], sme_isins: set[str], sme_symbols: set[str]) -> str:
    """'nse' (keep), 'isin_mismatch' (keep, report), or the type of a row to remove."""
    isin = (company.get("isin") or "").strip().upper()
    names = {(company.get("symbol") or "").strip().upper(), str(company.get("scrip_code") or "").strip().upper()} - {""}
    if isin and isin in nse_isins:
        return "nse"
    if isin and isin in sme_isins:
        return SME
    if not isin:
        if names & nse_symbols:
            return "nse"
        if names & sme_symbols:
            return SME
    elif names & nse_symbols:
        return "isin_mismatch"
    if isin.startswith("INF"):
        return FUND
    if TRUST.search(company.get("company_name") or ""):
        return REIT
    return BSE_ONLY


def stored_with_counts(sink) -> list[dict]:
    """Every company row with its real card count and ledger count (companies_prune_counts), paged."""
    rows: list[dict] = []
    after = ""
    while True:
        page = sink.query("companies_prune_counts", [after, PAGE])
        if not page:
            return rows
        rows += page
        after = page[-1]["scrip_code"]


def _dossier_counts(dossier: dict | None) -> dict:
    if not dossier:
        return {}
    return {k: len(dossier[k]) for k in DOSSIER_SECTIONS if isinstance(dossier.get(k), list) and dossier[k]}


def is_bse_kept(company: dict, kind: str, min_mcap: float) -> bool:
    cap = company.get("market_cap_cr")
    return bool(min_mcap) and kind == BSE_ONLY and cap is not None and float(cap) >= min_mcap


def plan(sink, equities, sme, keep_sme: bool = False, workers: int = READ_WORKERS,
         bse_keep_min_mcap: float = BSE_KEEP_MIN_MCAP_CR) -> dict:
    """The dry-run report (pure reads). ``equities``/``sme`` are NSE's lists (nse.Equity rows)."""
    if len(equities) < MIN_NSE_ROWS:
        raise ValueError(f"NSE's equity list has {len(equities)} rows (expected {MIN_NSE_ROWS}+): not pruning against it")
    if len(sme) < MIN_SME_ROWS:   # also with keep_sme: the list is how an SME row is told from a BSE-only one
        raise ValueError(f"NSE's SME list has {len(sme)} rows (expected {MIN_SME_ROWS}+): retry")
    nse_isins = {e.isin for e in equities}
    nse_symbols = {e.symbol for e in equities}
    sme_isins = {e.isin for e in sme}
    sme_symbols = {e.symbol for e in sme}
    companies = stored_with_counts(sink)
    # the REITs and InvITs reit_results.py put in: not on NSE's equity list, and kept (their ISINs are in kv)
    trusts = set(json.loads(sink.kv_get("reit_trust_isins") or "[]"))
    keep, mismatch, bse_kept = 0, [], []
    candidates: list[dict] = []
    for company in companies:
        kind = classify(company, nse_isins, nse_symbols, sme_isins, sme_symbols)
        if (company.get("isin") or "").strip().upper() in trusts:
            kind = "nse"
        if kind == "nse":
            keep += 1
        elif kind == "isin_mismatch":
            mismatch.append(_row(company, kind))
        elif kind == SME and keep_sme:
            keep += 1
        elif is_bse_kept(company, kind, bse_keep_min_mcap):
            bse_kept.append(_row(company, BSE_KEPT))
        else:
            candidates.append(_row(company, kind))
    have = set(sink.list_dossiers())
    todo = [c for c in candidates if c["scrip_code"] in have]
    if workers <= 1 or len(todo) <= 1:
        read = [sink.get_dossier(c["scrip_code"]) for c in todo]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            read = list(pool.map(lambda c: sink.get_dossier(c["scrip_code"]), todo))
    for company, dossier in zip(todo, read):
        company["memory"] = _dossier_counts(dossier)
    for company in candidates:
        company["has_memory"] = company["scrip_code"] in have
    protected = [c for c in candidates if c["cards"] or c["card_count"] or c["watchlist"]]
    remove = [c for c in candidates if not (c["cards"] or c["card_count"] or c["watchlist"])]
    return {"companies": len(companies), "nse_kept": keep, "nse_listed": len(equities), "sme_listed": len(sme),
            "keep_sme": keep_sme, "isin_mismatch_kept": mismatch, "remove": remove, "has_cards": protected,
            "bse_kept": bse_kept, "bse_keep_min_mcap": bse_keep_min_mcap,
            "summary": summarise(remove, protected, len(companies), keep, len(mismatch), len(bse_kept))}


def _row(company: dict, kind: str) -> dict:
    return {"scrip_code": company["scrip_code"], "symbol": company.get("symbol"), "company_name": company.get("company_name"),
            "isin": company.get("isin"), "type": kind, "market_cap_cr": company.get("market_cap_cr"),
            "watchlist": int(company.get("watchlist") or 0), "cards": int(company.get("cards") or 0),
            "card_count": int(company.get("card_count") or 0), "filings": int(company.get("filings") or 0)}


def summarise(remove: list[dict], protected: list[dict], total: int, kept: int, mismatch: int, bse_kept: int = 0) -> dict:
    def by_type(rows: list[dict]) -> dict:
        out: dict[str, dict] = {}
        for r in rows:
            s = out.setdefault(r["type"], {"rows": 0, "with_memory": 0, "memory_items": 0, "filings": 0, "cards": 0,
                                           "mcap_500_plus": 0})
            s["rows"] += 1
            s["with_memory"] += bool(r.get("has_memory"))
            s["memory_items"] += sum((r.get("memory") or {}).values())
            s["filings"] += r["filings"]
            s["cards"] += r["cards"]
            s["mcap_500_plus"] += (r.get("market_cap_cr") or 0) >= 500
        return out

    return {"companies_in_table": total, "kept_on_nse": kept, "isin_mismatch_kept": mismatch,
            "bse_kept": bse_kept, "to_remove": len(remove), "to_remove_by_type": by_type(remove),
            "kept_for_cards_or_watchlist": len(protected), "kept_for_cards_by_type": by_type(protected)}


def render(report: dict) -> str:
    s = report["summary"]
    lines = [f"companies table {s['companies_in_table']}: on NSE {s['kept_on_nse']} (equity list {report['nse_listed']}, "
             f"SME list {report['sme_listed']}, SME kept: {report['keep_sme']}), ISIN differs but symbol matches (kept) "
             f"{s['isin_mismatch_kept']}",
             f"to remove (no cards, not starred): {s['to_remove']}"]
    for kind, v in sorted(s["to_remove_by_type"].items()):
        lines.append(f"  {kind:17} {v['rows']:5} rows, {v['with_memory']} with a memory file ({v['memory_items']} items), "
                     f"{v['filings']} ledger rows, {v['mcap_500_plus']} with a market cap of 500 Cr or more")
    lines.append(f"kept and set aside, BSE-only with a market cap of {report.get('bse_keep_min_mcap', 0):g} Cr or more: {s['bse_kept']}")
    for r in report.get("bse_kept", [])[:30]:
        lines.append(f"  {r['scrip_code']} {r['company_name']} {r.get('isin') or '-'} {r.get('market_cap_cr')} Cr")
    lines.append(f"not removed, they hold cards or are starred: {s['kept_for_cards_or_watchlist']}  (owner decides: keep or hide)")
    for r in report["has_cards"][:30]:
        lines.append(f"  {r['scrip_code']} {r['company_name']} [{r['type']}] cards {r['cards']} watchlist {r['watchlist']}")
    return "\n".join(lines)


def to_csv(report: dict) -> str:
    out = ["action,type,scrip_code,symbol,isin,company_name,market_cap_cr,cards,filings,memory_items"]
    for action, rows in (("remove", report["remove"]), ("keep_has_cards", report["has_cards"]),
                         ("keep_isin_mismatch", report["isin_mismatch_kept"]),
                         ("keep_bse_kept", report.get("bse_kept", []))):
        for r in rows:
            name = (r.get("company_name") or "").replace('"', "'")
            out.append(f'{action},{r["type"]},{r["scrip_code"]},{r.get("symbol") or ""},{r.get("isin") or ""},"{name}",'
                       f'{r.get("market_cap_cr") if r.get("market_cap_cr") is not None else ""},{r["cards"]},{r["filings"]},'
                       f'{sum((r.get("memory") or {}).values())}')
    return "\n".join(out) + "\n"


def apply(sink, report: dict, day: str) -> dict:
    """Back up, then delete. Returns what was done. Stops before any delete if the backup cannot be read back."""
    remove = report["remove"]
    if not remove:
        return {"removed": 0, "memory_deleted": 0, "backup": None}
    scrips = [c["scrip_code"] for c in remove]
    have = set(sink.list_dossiers())
    memory: dict[str, object] = {}
    for scrip in scrips:
        if scrip in have:
            memory[f"memory/{scrip}.json"] = sink.get_dossier(scrip)
    # the company rows as stored (every column), so a restore is a plain upsert
    rows = _full_rows(sink, set(scrips))
    key = f"{BACKUP_PREFIX}{day}.json"
    body = json.dumps({"day": day, "companies": rows, "plan": remove, "memory": memory}, ensure_ascii=False,
                      separators=(",", ":")).encode()
    sink.put_object(key, body)
    if sink.get_object(key) != body:
        raise RuntimeError(f"backup {key} did not read back as written: nothing deleted")
    written = 0
    for at in range(0, len(scrips), APPLY_BATCH):
        batch = [{"scrip_code": s} for s in scrips[at:at + APPLY_BATCH]]
        written += sink.execute("companies_prune", batch)
    left = {r["scrip_code"] for r in stored_with_counts(sink)} & set(scrips)
    gone = [s for s in scrips if s not in left]
    deleted_objects = 0
    for scrip in gone:   # only for rows the SQL really removed: a company that gained a card keeps its memory
        if f"memory/{scrip}.json" in memory:
            sink.delete_object(f"memory/{scrip}.json")
            deleted_objects += 1
    for at in range(0, len(gone), APPLY_BATCH):
        sink.execute("catalysts_prune", [{"scrip_code": s} for s in gone[at:at + APPLY_BATCH]])
    log.info("prune-companies: %d company rows removed, %d memory files, backup %s (%d bytes)", len(gone), deleted_objects, key, len(body))
    return {"removed": len(gone), "kept_by_sql_guard": sorted(left), "memory_deleted": deleted_objects, "backup": key,
            "backup_bytes": len(body), "rows_written": written}


def bse_kept_rows(sink, equities, sme, min_mcap: float = BSE_KEEP_MIN_MCAP_CR) -> list[dict]:
    """Only the kept BSE-only rows (the same classification and line as ``plan``), with no memory reads: for bse-verify-kept."""
    if len(equities) < MIN_NSE_ROWS or len(sme) < MIN_SME_ROWS:
        raise ValueError("NSE's lists are too short to classify against")
    nse_isins, nse_symbols = {e.isin for e in equities}, {e.symbol for e in equities}
    sme_isins, sme_symbols = {e.isin for e in sme}, {e.symbol for e in sme}
    rows = []
    for company in stored_with_counts(sink):
        kind = classify(company, nse_isins, nse_symbols, sme_isins, sme_symbols)
        if is_bse_kept(company, kind, min_mcap):
            rows.append(_row(company, BSE_KEPT))
    return rows


def _full_rows(sink, scrips: set[str]) -> list[dict]:
    rows: list[dict] = []
    after = ""
    while True:
        page = sink.query("export_companies", [after, PAGE])
        if not page:
            return rows
        rows += [r for r in page if r["scrip_code"] in scrips]
        after = page[-1]["scrip_code"]
