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

from .scoring import calibration
from .models import Filing, Pass2Output
from .periods import canonical_period, due_date, quarter_index

SCHEMA_VERSION = 3
MAX_TIMELINE = 600
MAX_BALANCE_SNAPSHOTS = 16
# Periods kept per metric, by kind: a seven-year table in a presentation must not push out the
# recent quarters, so each kind keeps its own latest periods (by period end, not by filing date).
KEEP_PERIODS = {"Q": 12, "H": 6, "9M": 4, "FY": 6, "M": 18, "other": 8}


def _hash(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:8]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


_DATED = re.compile(r"^\s*\d{4}-\d{2}-\d{2}\s*[:\-–]\s*")  # "2025-05-13: " as the memory view prints notes
_ROLE_SUFFIX = re.compile(r"(?:\s*\([^()]{1,40}\))+\s*$")    # "SML Isuzu Limited (Target Company) (Target Company)"


def _bare_name(name: str) -> str:
    return _ROLE_SUFFIX.sub("", name).strip() or name.strip()


_GRANTED = re.compile(r"\b(?:approved|granted|received|obtained|cleared|accorded|sanctioned|passed|approval\s+(?:was|has\s+been)\s+(?:given|received))\b", re.I)
_NOT_YET = re.compile(r"\b(?:pending|awaited|awaiting|yet\s+to|subject\s+to|sought|seeks?|seeking|to\s+be\s+(?:obtained|received)|applied|proposed)\b", re.I)


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


def watch_verdict(watch: dict, status: str, evidence: str | None) -> str:
    """The model's verdict on a watch item, checked in code. "Met"/"missed" with no news ("not disclosed
    in Q1FY26 results; watchlist item overdue", "no update in filing; assumed resolved") or with
    evidence about another item (a debt/EBITDA check answered with a director's appointment) stays
    PENDING; a KPI verdict is then checked against its target and quarter (kpi_verdict)."""
    if status not in ("MET", "MISSED"):
        return status
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
    }]


def _metric_entry(metric: str, period: str, sources: list[dict]) -> dict:
    """One figure from its sources: the value is the latest restatement; ``as_of`` is when it was
    first known (known_since), which a later filing re-reporting it as a comparative never moves."""
    sources = sorted(sources, key=lambda s: s["as_of"])
    last = sources[-1]
    entry = {"metric": metric, "period": period, "value": last["value"], "unit": last.get("unit") or "INR_CR",
             "yoy_pct": last.get("yoy_pct"), "qoq_pct": last.get("qoq_pct"), "as_of": sources[0]["as_of"],
             "source_news_id": sources[0]["news_id"]}
    if len(sources) > 1:
        entry.update(sources=sources, updated_as_of=last["as_of"], value_news_id=last["news_id"])
    return entry


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


_LOWER_IS_BETTER = re.compile(r"\b(?:reduc\w*|declin\w*|lower\w*|cut\w*|deleverag\w*|debt|npa|cost[- ]to[- ]income|"
                              r"leverage|losses?)\b", re.I)


def _plausible_target(d: dict, metric: str, value: float) -> bool:
    """A numeric KPI target in the scale of the company's own figures for that metric: one more than 5x
    away from the latest stored value (a refund amount as a net-worth target, a segment's growth %
    as a revenue target, "EBITDA margin >= 1" against a 9% margin) is not a target."""
    latest = [m for m in d.get("financial_metrics", []) if m.get("metric") == metric and m.get("value")]
    if not latest:
        return True
    ref = abs(float(max(latest, key=lambda m: m.get("as_of") or "")["value"]))
    return ref < 1 or ref / 5 <= abs(float(value)) <= ref * 5


def merge(dossier: dict, output: Pass2Output, filing: Filing, impact_level: str | None, updated_at: str) -> dict:
    """Return the dossier with this filing's facts merged in (input is not mutated)."""
    d = json.loads(json.dumps(dossier))  # deep copy, JSON-safe
    d.setdefault("schema_version", SCHEMA_VERSION)
    news_id, as_of = filing.news_id, filing.filed_at
    _forget(d, news_id)
    delta = output.dossier_delta

    if delta.business_summary and not d.get("business_summary"):
        d["business_summary"] = {"text": delta.business_summary.strip(), "as_of": as_of, "source_news_id": news_id}

    metrics = {(m["metric"], m["period"]): m for m in d.get("financial_metrics", [])}
    for m in delta.financial_metrics:
        if m.value is None:
            continue
        key = (_norm(m.metric), _period(m.period))
        source = {"news_id": news_id, "as_of": as_of, "value": m.value, "unit": m.unit,
                  "yoy_pct": m.yoy_pct, "qoq_pct": m.qoq_pct}
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
        status = watch_verdict(w, update.status, update.evidence)
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
        if name and name.lower() != (d.get("company_name") or "").lower():
            names.setdefault(name.lower(), name)
    identity["former_names"] = list(names.values())[:6]
    # The view shows entities as "Name (type)"; models copy that back as the name.
    entities = {_norm(_bare_name(e["name"])): e for e in identity.get("entities", [])}
    for e in delta.entities[:6]:
        name = _bare_name(e.name.strip())
        key = _norm(name)
        if key and key not in entities:
            entities[key] = {"name": name[:120], "type": e.type, "as_of": as_of, "source_news_id": news_id}
    identity["entities"] = list(entities.values())[-20:]

    if delta.ownership and any(v is not None for k, v in delta.ownership.model_dump().items() if k != "period") \
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
            if comparison == ">=" and _LOWER_IS_BETTER.search(f"{k.kpi} {k.metric}"):
                comparison = "<="  # "Net debt reduction ... target >= 1,200" meant at most 1,200
            if not _plausible_target(d, _norm(k.metric), k.value):
                continue  # "Net worth target >= 128.1" (a refund) for a ₹1,357 Cr net worth
            pid = "p_" + _hash(filing.scrip_code, _norm(k.metric), _period(k.period), f"{k.value:g}")
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
    d["predictions"] = sorted(predictions.values(), key=lambda p: p["created_on"])[-60:]

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
        known = [s for s in _sources(m) if s["as_of"] < cutoff]
        if known:
            metrics_by_name.setdefault(m["metric"], []).append(_metric_entry(m["metric"], m["period"], known))

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
    identity = dossier.get("identity") or {}
    entities = [f"{e['name']} ({e['type']})" if e.get("type") else e["name"] for e in identity.get("entities", []) if before(e)]
    ownership = [{k: v for k, v in o.items() if k not in ("as_of", "source_news_id")}
                 for o in dossier.get("ownership", []) if before(o)][-2:]
    auditors = [a for a in (dossier.get("governance") or {}).get("auditor_history", []) if before(a)]
    predictions = [{"id": p["id"], "kpi": p["kpi"], "metric": p["metric"], "period": p["period"], "target": f"{p['comparison']} {p['value']:g}"}
                   for p in dossier.get("predictions", []) if p.get("created_on", "") < cutoff
                   and (p["status"] == "OPEN" or (p.get("resolved_on") or "") >= cutoff)]
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
            "former_names": identity.get("former_names") or None,
            "entities": entities[-8:],
            "ownership": ownership,
            "auditor": {k: v for k, v in auditors[-1].items() if k not in ("as_of", "source_news_id")} if auditors else None,
            "predictions": predictions[-guidance_n:],
            "calibration": (calibration(dossier, cutoff) or {}).get("rule"),  # Loop 2: how its targets turn out
        }
        view = {k: v for k, v in view.items() if v}
        if len(json.dumps(view, ensure_ascii=False)) <= budget_chars:
            break
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
    gov = dossier.get("governance") or {}
    history = [a for a in gov.get("auditor_history", []) if ok(a.get("as_of"))]
    d["governance"] = {"auditor": history[-1] if history else None, "auditor_history": history}
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
        snap = next((b for b in reversed(balance) if b.get(field) is not None), None)
        metric = latest(names)
        if snap and (not metric or snap["as_of"] >= metric["as_of"]):
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
)


def results_snapshot(dossier: dict, news_id: str) -> dict | None:
    """This filing's latest quarter against a year ago and the previous quarter, for the results tables.

    Each metric carries its value, the year-ago and previous-quarter values when memory has them,
    and the YoY / QoQ change (in basis points for the margin, which is derived from EBITDA and
    revenue when the filing did not state it).
    """
    from .periods import prior_quarter_period, prior_year_period

    mine = [m for m in dossier.get("financial_metrics", []) if reported_by(m, news_id)]
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
