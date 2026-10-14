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
        "deals": [],
        "operating_notes": [],
        "guidance": [],
        "watchlist": [],
        "timeline": [],
        "upcoming_events": [],
        "updated_at": None,
        "last_filed_at": None,
    }


def _forget(dossier: dict, news_id: str) -> None:
    for key in ("financial_metrics", "segment_mix", "balance_sheet", "capital_actions", "upcoming_events", "operating_notes"):
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

    deal = output.card.deal_value if output.card is not None else None
    if deal is not None and (deal.amount_cr or deal.updates_deal_id):
        entry = {"stage": deal.stage, "amount_cr": deal.amount_cr, "progress": deal.progress,
                 "as_of": as_of, "source_news_id": news_id}
        details = {k: v for k, v in deal.model_dump(include={"includes_gst", "counterparty", "segment", "execution_by"}).items()
                   if v is not None}
        deals = d.get("deals", [])
        target = next((x for x in deals if x["id"] == deal.updates_deal_id and x["as_of"] < as_of), None) \
            if deal.updates_deal_id else None
        if target is not None:
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

    notes = [{"text": n.strip()[:240], "as_of": as_of, "source_news_id": news_id} for n in delta.operating_notes[:3] if n.strip()]
    d["operating_notes"] = sorted(d.get("operating_notes", []) + notes, key=lambda e: e["as_of"])[-40:]

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
        items = [("KPI", k.kpi, k.check_in, k.target, None) for k in track.kpis_to_verify]
        items += [("APPROVAL", a, None, None, None) for a in track.pending_approvals]
        items += [("CONCERN", c.concern, None, None, c.management_response) for c in delta.analyst_concerns]
        for kind, text, check_in, target, response in items:
            wid = "w_" + _hash(filing.scrip_code, kind, _norm(text))
            if wid in watch:
                continue
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
            **({"management_said": w["response"]} if w.get("response") else {}),
            **({"overdue": True} if w.get("check_by") and w["check_by"] < cutoff[:10] else {}),
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
            "deals": deals[-guidance_n:],
            "operating_notes": notes[-max(3, guidance_n // 2):],
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
        snap = next((b for b in reversed(balance) if b.get(field) is not None), None)
        metric = latest(names)
        if snap and (not metric or snap["as_of"] >= metric["as_of"]):
            out[key] = {"period": snap.get("period"), "value": snap[field]}
        elif metric:
            out[key] = {"period": metric["period"], "value": metric["value"]}
    kpis = []
    for spec in footer:
        metric = latest((spec["metric"], *spec.get("aliases", ())), prefer_quarter=True)
        if metric:
            kpis.append({"label": spec["label"], "format": spec.get("format", "num"),
                         "period": metric["period"], "value": metric["value"]})
    if kpis:
        out["kpis"] = kpis[:2]
    return out


_RESULT_METRICS = (
    ("revenue", ("revenue", "revenue_from_operations", "total_revenue", "net_sales")),
    ("ebitda", ("ebitda", "operating_profit")),
    ("ebitda_margin", ("ebitda_margin", "opm", "operating_margin")),
    ("pbt", ("pbt", "profit_before_tax")),
    ("pat", ("pat", "net_profit", "profit_after_tax")),
    ("eps", ("eps", "basic_eps", "diluted_eps")),
)


def results_snapshot(dossier: dict, news_id: str) -> dict | None:
    """This filing's latest quarter against a year ago and the previous quarter, for the results tables.

    Each metric carries its value, the year-ago and previous-quarter values when memory has them,
    and the YoY / QoQ change (in basis points for the margin, which is derived from EBITDA and
    revenue when the filing did not state it).
    """
    from .periods import prior_quarter_period, prior_year_period

    mine = [m for m in dossier.get("financial_metrics", []) if m.get("source_news_id") == news_id]
    quarters = [m["period"] for m in mine if m["period"].startswith("Q") and due_date(m["period"])]
    if not quarters:
        return None
    period = max(quarters, key=due_date)
    table = {(m["metric"], m["period"]): m for m in dossier.get("financial_metrics", [])}
    periods = {"value": period, "prev_year": prior_year_period(period), "prev_quarter": prior_quarter_period(period)}

    def lookup(names: tuple[str, ...], p: str | None) -> float | None:
        if not p:
            return None
        entry = next((table[(n, p)] for n in names if (n, p) in table), None)
        return entry["value"] if entry and entry.get("value") is not None else None

    def margin(p: str | None) -> float | None:
        stated = lookup(_RESULT_METRICS[2][1], p)
        if stated is not None:
            return stated
        ebitda, revenue = lookup(_RESULT_METRICS[1][1], p), lookup(_RESULT_METRICS[0][1], p)
        return round(ebitda / revenue * 100, 2) if ebitda is not None and revenue else None

    out: dict = {"period": period, "prev_year_period": periods["prev_year"], "prev_quarter_period": periods["prev_quarter"]}
    for key, names in _RESULT_METRICS:
        values = {slot: (margin(p) if key == "ebitda_margin" else lookup(names, p)) for slot, p in periods.items()}
        if values["value"] is None:
            continue
        row = {slot: v for slot, v in values.items() if v is not None}
        for slot, label in (("prev_year", "yoy"), ("prev_quarter", "qoq")):
            base = values[slot]
            if base is None:
                continue
            if key == "ebitda_margin":
                row[f"{label}_bps"] = round((values["value"] - base) * 100)
            elif base:
                row[f"{label}_pct"] = round((values["value"] - base) / abs(base) * 100, 1)
        if key == "revenue" and "yoy_pct" not in row:
            stated = next((m for m in mine if m["metric"] in names and m["period"] == period and m.get("yoy_pct") is not None), None)
            if stated:
                row["yoy_pct"] = stated["yoy_pct"]
        out[key] = row
    return out if len(out) > 3 else None
