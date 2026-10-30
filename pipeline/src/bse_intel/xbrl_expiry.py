"""TODO 139 (3): before the R2 lifecycle rule xbrl-180d deletes a raw results file (raw/xbrl/, xbrl_store.py; first deletions
about late April 2027), its facts copy (raw/xbrl-facts/, xbrl_facts.py) must be there, since the facts are what memory, the
statements and the screener view are rebuilt from once the raw file is gone.

Read only. One listing of each folder, then every facts document is read for the url it was made from (a raw file is named by
``xbrl_store.key(url)``, so the url is the only link between the two). A raw file no facts document names is read and sorted:
``superseded`` (statements of a company, period and basis whose facts are kept from another file of it, a revised filing:
facts documents are keyed by period and basis, so the later file's facts replaced the earlier's), ``results`` and ``annual``
(statements no facts document holds: they are lost at 180 days, the defect this check is for), ``nothing_to_keep`` (a file with no results, which xbrl_facts would not keep either), ``unreadable`` (R2 failed or the body is
damaged). No NSE request and no write."""

from __future__ import annotations

import gzip
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from . import xbrl_facts, xbrl_store

log = logging.getLogger(__name__)

MAX_LISTED = 200     # missing files named in the summary (all are counted)


ID_ELEMENTS = ("Symbol", "ScripCode", "CorporateIdentityNumber")    # the file's own name for its company, first found


def identity(doc: dict) -> tuple | None:
    """(company, the file's own period, basis) as the file states them; None when the file names no company or no period."""
    names = {f[0]: str(f[3]).strip().upper() for f in doc.get("facts", []) if f[0] in ID_ELEMENTS and f[3]}
    company = next((names[n] for n in ID_ELEMENTS if names.get(n)), None)
    period = doc.get("file_period") or doc.get("period")
    if company is None or not period:     # a file with no period of its own is never matched to another one
        return None
    return company, period, str(doc.get("basis") or "").upper()


def _facts_info(sink, k: str) -> tuple[str | None, tuple | None, bool]:
    """(the url the facts document was made from, its identity, whether it was read)."""
    try:
        body = sink.get_object(k)
        if not body:
            return None, None, False
        doc = xbrl_facts.loads(body)
        return str(doc.get("url") or "") or None, identity(doc), True
    except Exception as exc:  # noqa: BLE001 - one damaged document is counted, the check goes on
        log.warning("facts document %s unreadable: %s", k, exc)
        return None, None, False


def classify(data: bytes | None) -> tuple[str, dict, tuple | None]:
    """What an uncovered raw file holds: (kind, a few fields to find it by, its identity)."""
    if not data:
        return "unreadable", {}, None
    try:
        doc = xbrl_facts.parse_facts(data)
        if doc is not None:
            return "results", {"period": doc.get("file_period"), "basis": doc.get("basis"), "n_facts": doc.get("n_facts")}, identity(doc)
        doc = xbrl_facts.parse_annual_facts(data)
        if doc is not None:
            return "annual", {"fy": doc.get("fy"), "basis": doc.get("basis"), "n_facts": doc.get("n_facts")}, identity(doc)
    except Exception as exc:  # noqa: BLE001 - a file the parser chokes on is unreadable, not a stop
        log.warning("raw file unparseable: %s", exc)
        return "unreadable", {}, None
    return "nothing_to_keep", {}, None


def _raw(sink, k: str) -> bytes | None:
    try:
        body = sink.get_object(k)
        return gzip.decompress(body) if body else None
    except Exception as exc:  # noqa: BLE001
        log.warning("raw file %s unreadable: %s", k, exc)
        return None


def check(sink, *, workers: int = 16) -> dict:
    """The summary: counts by kind and the first MAX_LISTED raw files whose facts are missing."""
    raw = sorted(k for k in sink.list_objects(xbrl_store.PREFIX) if k != xbrl_store.TOTAL_KEY)
    docs = sorted(k for k in sink.list_objects(xbrl_facts.PREFIX) if k.endswith(".json.gz"))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        infos = list(pool.map(lambda k: _facts_info(sink, k), docs))
    covered = {xbrl_store.key(u) for u, _, _ in infos if u}
    kept = {i for _, i, _ in infos if i}
    uncovered = [k for k in raw if k not in covered]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        kinds = list(pool.map(lambda k: classify(_raw(sink, k)), uncovered))
    summary = {"raw_files": len(raw), "facts_docs": len(docs), "facts_docs_unreadable": sum(1 for _, _, ok in infos if not ok),
               "facts_docs_without_url": sum(1 for u, _, ok in infos if ok and not u),
               "covered": len(raw) - len(uncovered), "superseded": 0, "results": 0, "annual": 0, "nothing_to_keep": 0,
               "unreadable": 0, "missing": []}
    for k, (kind, info, ident) in zip(uncovered, kinds):
        if kind in ("results", "annual") and ident in kept:
            kind = "superseded"
        summary[kind] += 1
        if kind in ("results", "annual", "unreadable") and len(summary["missing"]) < MAX_LISTED:
            summary["missing"].append({"key": k, "kind": kind, **info})
    summary["facts_missing"] = summary["results"] + summary["annual"]
    summary["not_verified"] = summary["unreadable"] + summary["facts_docs_unreadable"]   # an R2 failure is never a pass
    return summary


def render(s: dict) -> str:
    lines = [f"raw files (raw/xbrl/)           {s['raw_files']}",
             f"facts documents                 {s['facts_docs']} ({s['facts_docs_unreadable']} unreadable, "
             f"{s['facts_docs_without_url']} without a url)",
             f"raw files with a facts copy     {s['covered']}",
             f"no copy, a later file's kept    {s['superseded']}",
             f"no copy, holds results          {s['results']}",
             f"no copy, holds an annual report {s['annual']}",
             f"no copy, nothing to keep        {s['nothing_to_keep']}",
             f"no copy, unreadable             {s['unreadable']}"]
    if s["not_verified"]:
        lines.append(f"NOT VERIFIED: {s['not_verified']} objects could not be read; run the check again")
    if s["facts_missing"]:
        lines.append(f"FACTS MISSING for {s['facts_missing']} raw files: these lose their facts when the 180-day rule deletes them")
    elif not s["not_verified"]:
        lines.append("every raw file that holds results has its facts copy")
    return "\n".join(lines)


def to_json(s: dict) -> str:
    return json.dumps(s, indent=2, ensure_ascii=False)
