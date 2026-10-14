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

import hashlib
import json
import re
from typing import Any

from .models import Filing, Pass2Output
from .periods import due_date

SCHEMA_VERSION = 2
MAX_METRICS = 600
MAX_TIMELINE = 600
MAX_BALANCE_SNAPSHOTS = 16


def _hash(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:8]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _period(text: str) -> str:
    return re.sub(r"\s+", "", text.upper())


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
        "guidance": [],
        "watchlist": [],
        "timeline": [],
        "upcoming_events": [],
        "updated_at": None,
        "last_filed_at": None,
    }


def _forget(dossier: dict, news_id: str) -> None:
    for key in ("financial_metrics", "segment_mix", "balance_sheet", "capital_actions", "upcoming_events"):
        dossier[key] = [e for e in dossier.get(key, []) if e.get("source_news_id") != news_id]
    dossier["timeline"] = [e for e in dossier.get("timeline", []) if e.get("news_id") != news_id]
    for key in ("guidance", "watchlist"):
        kept = []
        for item in dossier.get(key, []):
            if item.get("source_news_id") == news_id:
                continue
            history = [h for h in item.get("status_history", []) if h.get("source_news_id") != news_id]
            item["status_history"] = history
            item["status"] = history[-1]["status"] if history else "OPEN"
            kept.append(item)
        dossier[key] = kept
    summary = dossier.get("business_summary")
    if summary and summary.get("source_news_id") == news_id:
        dossier["business_summary"] = None


def merge(dossier: dict, output: Pass2Output, filing: Filing, impact_level: str | None, updated_at: str) -> dict:
    """Return the dossier with this filing's facts merged in (input is not mutated)."""
    d = json.loads(json.dumps(dossier))  # deep copy, JSON-safe
    d.setdefault("schema_version", SCHEMA_VERSION)
    news_id, as_of = filing.news_id, filing.filed_at
    _forget(d, news_id)
    delta = output.dossier_delta

    if delta.business_summary and not d.get("business_summary"):
        d["business_summary"] = {"text": delta.business_summary.strip(), "as_of": as_of, "source_news_id": news_id}

    metrics = {(_norm(m["metric"]), _period(m["period"])): m for m in d.get("financial_metrics", [])}
    for m in delta.financial_metrics:
        if m.value is None:
            continue
        key = (_norm(m.metric), _period(m.period))
        existing = metrics.get(key)
        if existing and existing.get("as_of", "") > as_of:
            continue  # a later filing already restated this figure
        metrics[key] = {
            "metric": key[0], "period": key[1], "value": m.value, "unit": m.unit,
            "yoy_pct": m.yoy_pct, "qoq_pct": m.qoq_pct, "as_of": as_of, "source_news_id": news_id,
        }
    d["financial_metrics"] = sorted(metrics.values(), key=lambda e: e["as_of"])[-MAX_METRICS:]

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
    d["segment_mix"] = sorted(segments.values(), key=lambda e: e["as_of"])[-MAX_METRICS:]

    if delta.balance_sheet and not delta.balance_sheet.is_empty():
        snapshot = {k: v for k, v in delta.balance_sheet.model_dump().items() if v is not None}
        snapshot.update(as_of=as_of, source_news_id=news_id)
        d["balance_sheet"] = sorted(d.get("balance_sheet", []) + [snapshot], key=lambda e: e["as_of"])[-MAX_BALANCE_SNAPSHOTS:]

    actions = [a.model_dump() | {"as_of": as_of, "source_news_id": news_id} for a in delta.capital_actions]
    d["capital_actions"] = sorted(d.get("capital_actions", []) + actions, key=lambda e: e["as_of"])[-40:]

    guidance = {g["id"]: g for g in d.get("guidance", [])}
    for item in delta.guidance:
        gid = "g_" + _hash(filing.scrip_code, _norm(item.statement))
        if gid in guidance:
            continue
        deadline = due_date(item.due)
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
        items = [("KPI", k.kpi, k.check_in, k.target) for k in track.kpis_to_verify]
        items += [("APPROVAL", a, None, None) for a in track.pending_approvals]
        for kind, text, check_in, target in items:
            wid = "w_" + _hash(filing.scrip_code, kind, _norm(text))
            if wid in watch:
                continue
            check_by = due_date(check_in)
            watch[wid] = {
                "id": wid, "kind": kind, "text": text.strip(), "check_in": check_in, "target": target,
                "check_by": check_by.isoformat() if check_by else None, "created_on": as_of,
                "source_news_id": news_id, "status": "OPEN", "status_history": [],
            }
    for update in delta.watch_updates:
        w = watch.get(update.watch_id)
        if w is None or w.get("created_on", "") >= as_of:
            continue
        w["status_history"] = sorted(w.get("status_history", []) + [{
            "status": update.status, "evidence": update.evidence, "as_of": as_of, "source_news_id": news_id,
        }], key=lambda h: h["as_of"])
        w["status"] = w["status_history"][-1]["status"]
    d["watchlist"] = sorted(watch.values(), key=lambda w: w["created_on"])[-80:]

    if output.is_material:
        d["timeline"] = sorted(d.get("timeline", []) + [{
            "id": "t_" + _hash(news_id),
            "date": as_of,
            "event_type": output.event_type,
            "impact_level": impact_level,
            "summary": output.timeline_entry.strip(),
            "news_id": news_id,
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


def _guidance_status_at(g: dict, cutoff: str) -> str:
    history = [h for h in g.get("status_history", []) if h["as_of"] < cutoff]
    return history[-1]["status"] if history else "OPEN"


def view_as_of(dossier: dict | None, cutoff: str, budget_chars: int = 6000) -> dict | None:
    """Compact memory for the prompt, containing only facts known before ``cutoff``."""
    if not dossier:
        return None
    before = lambda e, field="as_of": e.get(field, "") < cutoff  # noqa: E731

    metrics_by_name: dict[str, list[dict]] = {}
    for m in dossier.get("financial_metrics", []):
        if before(m):
            metrics_by_name.setdefault(m["metric"], []).append(m)

    def metric_lines(periods: int) -> dict[str, list[str]]:
        out = {}
        for name, entries in metrics_by_name.items():
            entries = sorted(entries, key=lambda e: e["as_of"])[-periods:]
            out[name] = [
                f"{e['period']}: {e['value']:g} {e['unit']}"
                + (f" (YoY {e['yoy_pct']:+g}%)" if e.get("yoy_pct") is not None else "")
                for e in entries
            ]
        return out

    balance = [b for b in dossier.get("balance_sheet", []) if before(b)]
    guidance = [
        {
            "id": g["id"], "statement": g["statement"], "target": g.get("target"), "due": g.get("due"),
            "given_on": g["given_on"][:10], "status": _guidance_status_at(g, cutoff),
            **({"overdue": True} if g.get("due_date") and g["due_date"] < cutoff[:10] else {}),
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
            **({"overdue": True} if w.get("check_by") and w["check_by"] < cutoff[:10] else {}),
        }
        for w in dossier.get("watchlist", [])
        if w.get("created_on", "") < cutoff and _guidance_status_at(w, cutoff) in ("OPEN", "PENDING", "PARTIAL")
    ]
    upcoming = [
        {"type": e["event_type"], "date": e["date"], "description": e.get("description", "")}
        for e in dossier.get("upcoming_events", []) if before(e) and e["date"] >= cutoff[:10]
    ]
    summary = dossier.get("business_summary")

    for periods, timeline_n, guidance_n in ((6, 12, 20), (4, 8, 12), (2, 5, 8), (1, 3, 5)):
        view: dict[str, Any] = {
            "company": dossier.get("company_name"),
            "business_summary": summary["text"] if summary and before(summary) else None,
            "metrics": metric_lines(periods),
            "balance_sheet": {k: v for k, v in balance[-1].items() if k != "source_news_id"} if balance else None,
            "guidance": [g for g in guidance if g["status"] in ("OPEN", "ON_TRACK", "DELAYED", "REVISED")][-guidance_n:],
            "watchlist": watch[-guidance_n:],
            "recent_timeline": timeline[-timeline_n:],
            "upcoming_events": upcoming[:6],
        }
        view = {k: v for k, v in view.items() if v}
        if len(json.dumps(view, ensure_ascii=False)) <= budget_chars:
            break
    return view if len(view) > 1 else None


def memory_ids(view: dict | None) -> set[str]:
    if not view:
        return set()
    ids = {g["id"] for g in view.get("guidance", [])}
    ids |= {t["id"] for t in view.get("recent_timeline", [])}
    ids |= {w["id"] for w in view.get("watchlist", [])}
    return ids
