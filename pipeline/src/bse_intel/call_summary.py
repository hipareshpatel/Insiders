"""Earnings calls by quarter: the key takeaways memory took from each quarter's call, sorted into fixed headings
(owner O13/O4, 2026-10-20: "only important points under different categories like Capex, Guidance ... no greetings of
management, short and sweet"). Built by code from the dossier, no AI: what pass 2 already put in memory from a
transcript or presentation (guidance, operating notes, analysts' concerns with management's answer, capex and other
deals, capital actions, the balance sheet), grouped by the quarter the call discussed.

A call filing is one whose timeline entry is CONCALL_PRESENTATION, or, when the timeline no longer holds it, one whose
guidance memory marked as said on a call or in a presentation. The quarter is the latest one a filing's summary names
that had ended by the filing date, else the last quarter ended before it (calls for June come in July-August).
"""

from __future__ import annotations

import re
from datetime import date

from .dossier import _deal_history, label
from .timeutil import now_iso
from .periods import due_date, quarter_index
from .signals import stated_net_debt

CALL_EVENT = "CONCALL_PRESENTATION"
CALL_SOURCES = ("CONCALL", "PRESENTATION")
CATEGORIES = ("Guidance", "Capex & capacity", "Demand & orders", "Margins & costs", "Balance sheet & funding", "Risks", "Other")
QUARTERS = 4
PER_CATEGORY = 4
PER_QUARTER = 16
CALL_POINTS_KEPT = 120   # checked takeaways kept in memory, newest calls first (about 8 quarters of 12-15)
MAX_CHARS = 200

_QUARTER = re.compile(r"\bQ([1-4])\s*FY\s*'?(\d{2})\b", re.I)
_CAPEX = re.compile(r"\bcapex\b|capacity|commission|plant|greenfield|brownfield|expansion|debottleneck|new line|"
                    r"facility|\bmtpa\b|\btpa\b|\bmw\b|\bgw\b|utili[sz]ation", re.I)
_DEMAND = re.compile(r"order\s*(?:book|inflow|backlog|pipeline)|\border|demand|volume|sales growth|market share|"
                     r"customer|client|export|realisation|realization|pricing|price hike|\bbid", re.I)
_MARGIN = re.compile(r"margin|ebitda|\bcost|raw material|\bfuel\b|pet ?coke|input price|commodit|freight|power and fuel|employee|"
                     r"gross profit|operating leverage|bps\b", re.I)
_FUNDING = re.compile(r"\bdebt\b|borrow|leverage|net cash|cash flow|working capital|receivable|inventor|"
                      r"\bqip\b|rights issue|preferential|fund ?rais|dividend|buyback|rating|interest cost|"
                      r"\bloan|repay|capital raise", re.I)
_GUIDE = re.compile(r"\bguid|\btarget|\bexpect|\boutlook|\baim|\bplans?\b|\bby fy\d{2}|next year|going forward|\bwill\b", re.I)
# What a call says about itself, not about the business: greetings, thanks, the safe-harbour statement, the call's own
# logistics. A point that is only this carries no takeaway.
_BOILERPLATE = re.compile(
    r"^(?:good (?:morning|afternoon|evening)|hello|hi\b|welcome|thank|thanks)|"
    r"\bthank(?:s| you)\b.{0,40}\b(?:join|participat|attend|time|patience)|"
    r"\bwelcome(?:d)?\b.{0,40}\b(?:everyone|all|participants|call)|"
    r"safe harbo(?:u)?r|forward[- ]looking statements?|disclaimer|"
    r"\bmoderator\b|\boperator\b|question[- ]and[- ]answer session|\bq ?& ?a\b|"
    r"(?:earnings|conference|investor|analyst)s?\s+(?:call|meet)\b.{0,40}\b(?:held|hosted|scheduled|conducted|organi[sz]ed)|"
    r"\b(?:audio|video) recording\b|\btranscript\b|\bwebcast\b|"
    r"\bjoined by\b.{0,60}\b(?:management|cfo|ceo|md|team)\b|"
    r"\bmanagement (?:team )?(?:was|were) represented\b", re.I)
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "of", "to", "in", "for", "and", "on", "by", "at", "is", "be", "with", "from", "its", "as", "it"}


def _day(ts: str | None) -> str:
    return (ts or "")[:10]


def _short(text: str, limit: int = MAX_CHARS) -> str:
    text = " ".join(str(text or "").split()).strip(" .;")
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:-") + "…"


def boilerplate(text: str) -> bool:
    """Greetings, thanks, the safe harbour and the call's own logistics; also too short to say anything."""
    words = _WORD.findall(text.lower())
    return len(words) < 4 or bool(_BOILERPLATE.search(text))


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


def _same(a: set[str], b: set[str]) -> bool:
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) >= 0.7


def category(text: str, kind: str) -> str:
    """The heading a point goes under: its kind first (a capital action is funding), then its words."""
    if kind == "funding":
        return "Balance sheet & funding"
    if kind == "capex" or _CAPEX.search(text):
        return "Capex & capacity"
    if kind == "guidance":
        return "Guidance"
    if _FUNDING.search(text):
        return "Balance sheet & funding"
    if _MARGIN.search(text):
        return "Margins & costs"
    if _DEMAND.search(text):
        return "Demand & orders"
    if _GUIDE.search(text):
        return "Guidance"
    return "Other"


def quarter_of(filed_at: str, summary: str | None = None) -> str | None:
    """The quarter a call filed on `filed_at` discussed."""
    try:
        filed = date.fromisoformat(_day(filed_at))
    except ValueError:
        return None
    named = []
    for m in _QUARTER.finditer(summary or ""):
        period = f"Q{m[1]}FY{m[2]}"
        end = due_date(period)
        if end and end <= filed:
            named.append(period)
    if named:
        return max(named, key=lambda p: quarter_index(p) or 0)
    # the last quarter ended before the filing: Dec (Q3) for Jan-Mar, Mar (Q4) for Apr-Jun, Jun (Q1) and Sep (Q2) after
    q, fy = {0: (3, filed.year), 1: (4, filed.year), 2: (1, filed.year + 1), 3: (2, filed.year + 1)}[(filed.month - 1) // 3]
    return f"Q{q}FY{fy % 100:02d}"


def call_filings(dossier: dict) -> dict[str, dict]:
    """news_id -> {date, quarter, pdf_url} for every call or presentation memory knows of."""
    calls: dict[str, dict] = {}
    for t in dossier.get("timeline", []):
        if t.get("event_type") == CALL_EVENT and t.get("news_id"):
            calls[t["news_id"]] = {"date": _day(t.get("date")), "quarter": quarter_of(t.get("date") or "", t.get("summary")),
                                   **({"pdf_url": t["pdf_url"]} if t.get("pdf_url") else {})}
    known = {t.get("news_id") for t in dossier.get("timeline", [])}
    for g in dossier.get("guidance", []):
        nid = g.get("source_news_id")
        if nid and nid not in calls and nid not in known and str(g.get("source_type") or "").upper() in CALL_SOURCES:
            calls[nid] = {"date": _day(g.get("given_on")), "quarter": quarter_of(g.get("given_on") or "")}
    return calls


def remember_call_points(dossier: dict, news_id: str, filed_at: str, takeaways) -> None:
    """The call's verified takeaways (call_summary.check_ai_takeaways) into memory, replacing this filing's earlier
    ones: what the quarterly summary on the company page is built from first."""
    kept = [p for p in dossier.get("call_points", []) if p.get("news_id") != news_id]
    for t in takeaways or []:
        get = t.get if isinstance(t, dict) else lambda k, d=None, t=t: getattr(t, k, d)   # a stored card's, or a model's
        if get("verified", False) and get("text"):
            kept.append({"news_id": news_id, "date": _day(filed_at), "category": get("category") or "Other",
                         "text": get("text"), **({"versus_prior": get("versus_prior")} if get("versus_prior") else {}),
                         # what the call said, as our AI read it and our checks passed; no page or quote yet (memory label)
                         "lab": label("ai", "call", now_iso(), ok=True)})
    kept.sort(key=lambda p: p.get("date") or "", reverse=True)
    dossier["call_points"] = kept[:CALL_POINTS_KEPT]


def _points(dossier: dict, calls: dict[str, dict]) -> list[dict]:
    """Every candidate point from a call filing: text, kind, its filing and date, and a rank (figures first). The
    call's own checked takeaways rank above what memory took from it."""
    out: list[dict] = []
    for p in dossier.get("call_points", []):
        if p.get("news_id") in calls and not boilerplate(p.get("text") or ""):
            out.append({"text": _short(p["text"]), "category": p["category"] if p.get("category") in CATEGORIES else "Other",
                        "news_id": p["news_id"], "date": calls[p["news_id"]]["date"],
                        "rank": 9 + (2 if re.search(r"\d", p["text"]) else 0),
                        **({"versus": p["versus_prior"]} if p.get("versus_prior") else {})})

    def add(text: str | None, kind: str, news_id: str | None, rank: int, **extra) -> None:
        if not text or news_id not in calls:
            return
        text = _short(re.sub(r"^\d{4}-\d{2}-\d{2}:\s*", "", str(text)))
        if boilerplate(text):
            return
        out.append({"text": text, "category": category(text, kind), "news_id": news_id,
                    "date": calls[news_id]["date"], "rank": rank + (2 if re.search(r"\d", text) else 0), **extra})

    for g in dossier.get("guidance", []):
        parts = [g.get("statement") or ""]
        if g.get("target") and _words(g["target"]) - _words(parts[0]):
            parts.append(g["target"])
        if g.get("due") and _words(g["due"]) - _words(" ".join(parts)):
            parts.append(f"by {g['due']}")
        text = " · ".join(p.strip() for p in parts if p.strip())
        add(text, "capex" if _CAPEX.search(text) else "guidance", g.get("source_news_id"), 5)
        for r in g.get("repeated", []):   # the same target said again on a later call
            add(text, "capex" if _CAPEX.search(text) else "guidance", r.get("source_news_id"), 4, reiterated=True)
    for d in dossier.get("deals", []):
        what = d.get("expansion") or d.get("segment") or d.get("counterparty") or (d.get("kind") or "").title()
        for h in _deal_history(d):   # each call's word on the deal goes to that call's quarter
            if h.get("source_news_id") not in calls:
                continue
            bits = [what, f"₹{h['amount_cr']:,.0f} Cr" if h.get("amount_cr") else None,
                    (h.get("stage") or "").replace("_", " ").lower() or None, h.get("progress")]
            add(", ".join(str(b) for b in bits if b), "capex" if d.get("kind") == "CAPEX" else "deal", h["source_news_id"], 4)
    for n in dossier.get("operating_notes", []):
        add(n.get("text"), "note", n.get("source_news_id"), 3)
    for w in dossier.get("watchlist", []):
        if w.get("kind") == "CONCERN" and w.get("response"):
            add(f"{w['text'].rstrip(' .?')}: {w['response']}", "concern", w.get("source_news_id"), 2)
    for a in dossier.get("capital_actions", []):
        bits = [a.get("instrument"), f"₹{a['amount_cr']:,.0f} Cr" if a.get("amount_cr") else None, a.get("ratio")]
        add(" ".join(str(b) for b in bits if b) + " planned", "funding", a.get("source_news_id"), 3)
    for s in dossier.get("balance_sheet", []):
        net = stated_net_debt(s)
        cash = "cash and cash equivalents" if str(s.get("source_news_id") or "").startswith("xbrl:") else "cash"
        bits = [f"gross debt ₹{s['gross_debt_cr']:,.0f} Cr" if s.get("gross_debt_cr") is not None else None,
                f"net debt ₹{net:,.0f} Cr" if net is not None else None,
                f"{cash} ₹{s['cash_cr']:,.0f} Cr" if s.get("cash_cr") is not None else None,
                f"rated {s['credit_rating']}" if s.get("credit_rating") else None]
        bits = [b for b in bits if b]
        if bits:
            add(("Balance sheet: " + ", ".join(bits))[:MAX_CHARS], "funding", s.get("source_news_id"), 1)
    return out


def summarize_calls(dossier: dict) -> list[dict]:
    """The last QUARTERS quarters with a call, newest first: [{quarter, date, sources, categories: [{name, points}]}],
    at most PER_CATEGORY points a heading and PER_QUARTER a quarter, each point once (its date and filing kept)."""
    calls = call_filings(dossier)
    by_quarter: dict[str, list[dict]] = {}
    for p in _points(dossier, calls):
        quarter = calls[p["news_id"]]["quarter"]
        if quarter:
            by_quarter.setdefault(quarter, []).append(p)
    out = []
    for quarter in sorted(by_quarter, key=lambda q: quarter_index(q) or 0, reverse=True)[:QUARTERS]:
        # the best first: a stated figure, guidance before a note, the newest of equals
        ranked = sorted(sorted(by_quarter[quarter], key=lambda p: p["date"], reverse=True), key=lambda p: -p["rank"])
        kept: list[dict] = []
        seen: list[set[str]] = []
        count = dict.fromkeys(CATEGORIES, 0)
        for p in ranked:
            words = _words(p["text"])
            if any(_same(words, s) for s in seen):
                continue
            if count[p["category"]] >= PER_CATEGORY or len(kept) >= PER_QUARTER:
                continue
            seen.append(words)
            count[p["category"]] += 1
            kept.append(p)
        if not kept:
            continue
        ids = sorted({p["news_id"] for p in kept}, key=lambda n: calls[n]["date"], reverse=True)
        out.append({
            "quarter": quarter,
            "date": calls[ids[0]]["date"],
            "sources": [{"news_id": n, "date": calls[n]["date"], **({"pdf_url": calls[n]["pdf_url"]} if calls[n].get("pdf_url") else {})}
                        for n in ids],
            "categories": [{"name": c, "points": [
                {"text": p["text"], "date": p["date"], "news_id": p["news_id"], **({"reiterated": True} if p.get("reiterated") else {}),
                 **({"versus": p["versus"]} if p.get("versus") else {})}
                for p in kept if p["category"] == c]} for c in CATEGORIES if count[c]],
        })
    return out


CARD_PER_CATEGORY = 3
CARD_TOTAL = 8
MEMORY_KINDS = ("guidance", "recent_timeline", "watchlist", "deals", "previous_calls")
_ISO_TIME = re.compile(r"\d{4}-\d{2}-\d{2}(?:T[\d:.+\-]+)?")


def _memory_item(view: dict | None, ref: str) -> dict | None:
    for kind in MEMORY_KINDS:
        for item in (view or {}).get(kind, []):
            if item.get("id") == ref:
                return item
    return None


def _memory_text(item: dict) -> str:
    """A memory item as text a takeaway's figures and periods are looked up in: its values, and the quarter each
    dated part of it (a call, a results line, a deal's stage) speaks for, so "the Q1FY27 call" can be found."""
    import json

    raw = json.dumps(item, ensure_ascii=False)
    quarters = {quarter_of(m.group(0), item.get("summary")) for m in _ISO_TIME.finditer(raw)}
    return f"{_ISO_TIME.sub(' ', raw)} {' '.join(q for q in quarters if q)}"


def _figures(text: str) -> list[tuple[float, int, bool]]:
    """(value, decimals, is a percentage) of each figure a line states; period labels and dates are not figures.
    A range's first end is a percentage when its second is ("10-12%")."""
    from . import gate

    flat = gate._PERIOD_LABEL.sub(" ", gate._WRITTEN_DATE.sub(" ", gate._flat(text or "")))
    out = []
    for m in gate._CLAIM_NUMBER.finditer(flat):
        raw = m.group(0).replace(",", "").rstrip(".")
        try:
            value = float(raw)
        except ValueError:
            continue
        after = flat[m.end():m.end() + 12]
        pct = bool(re.match(r"\s*%|\s*(?:-|–|to)\s*\d[\d.]*\s*%", after))
        out.append((value, len(raw.partition(".")[2]), pct))
    return out


def _stated_in(figure: tuple[float, int, bool], sources: list[str]) -> bool:
    """A figure is in a source when the source prints it, or the card's figure is the source's rounded to its digits."""
    value, decimals, _ = figure
    tolerance = 0.5 * 10 ** -decimals + 1e-9
    return any(abs(v - value) <= tolerance for s in sources for v, _, _ in _figures(s))


# a versus_prior that says the figure is the same as before: from the quote alone it compares the call with itself
_SAME = re.compile(r"\b(?:match\w*|reiterat\w*|same as|unchanged|in line with|consistent with|confirm\w*)\b", re.I)

NEAR_CHARS = 2500   # the transcript around a takeaway's quote where a quarter its versus_prior names may stand


def _near(quote: str | None, text: str) -> str:
    """The transcript around where the quote stands: the speaker's answer it comes from, give or take, where the
    quarter a versus_prior names may be said. '' when the quote cannot be placed."""
    from . import gate

    flat, q = gate._flat(text or ""), gate._flat(quote or "")
    at = flat.find(q[:60]) if q else -1
    if at < 0:
        return ""
    return flat[max(0, at - NEAR_CHARS):at + len(q) + NEAR_CHARS]


def _computed(figure: tuple[float, int, bool], sources: list[str], bps: bool) -> bool:
    """A figure the quote's own figures give by one subtraction: "within 20 bps of the 15% target" from 15% and
    14.8% (22 Oct 2026, Tech Mahindra). Percentages only, and basis points when the takeaway says so."""
    value, decimals, pct = figure
    stated = [v for s in sources for v, _, is_pct in _figures(s) if is_pct]
    if len(stated) < 2 or not (pct or bps):
        return False
    tolerance = 0.5 * 10 ** -decimals + 1e-9
    for i, a in enumerate(stated):
        for b in stated[i + 1:]:
            gap = abs(a - b)
            if abs((gap * 100 if bps else gap) - value) <= tolerance and gap > 0:
                return True
    return False


def _periods(text: str) -> list[str]:
    from . import gate

    return [re.sub(r"[\s']", "", m.group(0)).upper() for m in gate._PERIOD_LABEL.finditer(gate._flat(text or ""))]


# Bumped when the check accepts more (22 Oct 2026: a figure from the same answer, one subtraction, a quarter the quote
# names); refresh-card-blocks re-checks a stored call card checked under an earlier version (card_refresh.recheck_calls).
TAKEAWAY_CHECK_VERSION = 2


def check_ai_takeaways(card, text: str, reading: str = "", view: dict | None = None, unit: int | None = None) -> list[str]:
    """Each of the model's call takeaways checked by code; `verified` set on the ones the card's face may show.

    One is verified only when its quote is in the filing (the filing's own words, or with small differences); every
    figure its text states is in that sentence or in a memory item it cites (a crore amount at the filing's unit);
    and its versus_prior, when given, cites memory and names only figures and periods that memory item holds. A
    takeaway that fails is kept unverified, for the AI reading, and never holds the card. Returns the notes."""
    from . import gate

    notes: list[str] = []
    for item in getattr(card, "call_takeaways", None) or []:
        item.verified, item.issue = False, None
        refs = [r for r in item.memory_refs if _memory_item(view, r)]
        item.memory_refs = refs
        memory = [_memory_text(_memory_item(view, r)) for r in refs]
        issue = None
        quote = item.quote
        if boilerplate(item.text):
            issue = "greeting or call logistics, not a takeaway"
        elif not quote:
            issue = "no quote"
        elif not gate.quote_found(quote, text, reading):
            quote = gate.quote_near(quote, text, reading)
            if quote is None:
                issue = "quote not in the filing"
        near = _near(quote, text) if issue is None else ""
        if issue is None:
            bps = bool(re.search(r"\bbps\b|basis points?", item.text, re.I))
            for figure in _figures(item.text):
                if _stated_in(figure, [quote, *memory]):
                    continue
                # one subtraction of the quote's own percentages (22 Oct 2026). A figure said elsewhere in the same
                # answer is not accepted: of 45 takeaways it let through on stored cards, an independent review found 5
                # wrong (an analyst's figure, another column of a slide, another company's call) and no distance or
                # shape that tells them from the 37 right ones (docs/audit/call-takeaways-2026-10-22.md)
                if _computed(figure, [quote], bps):
                    continue
                # a crore amount read from a statement in lakh or million: the quote's figure at the filing's unit
                shown = f"{figure[0]:.{figure[1]}f}"
                if not figure[2] and figure[0] > 31 and not any(m.replace(",", "") == shown
                                             for m in gate.numbers_in_quote(item.text, quote, gate.quote_unit(quote, text, unit))):
                    continue
                issue = f"{shown}{'%' if figure[2] else ''} is not in its quote or the memory it cites"
                break
        if issue is None and item.versus_prior:
            prior = _figures(item.versus_prior)
            periods_named = _periods(item.versus_prior)
            if (not memory and prior and all(_stated_in(f, [quote]) for f in prior)
                    and not _SAME.search(item.versus_prior)
                    and all(p in _periods(f"{quote} {near}") for p in periods_named)):
                pass   # the filing's own sentence gives the earlier figure: "I had guided 9-11%, revising to 11-12%",
                # and any quarter it names is named there too ("the 9-11% we guided in Q1FY27"). A "matches" or
                # "reiterates" from the call's own sentence compares the call with itself: DCW's "net debt ₹71 Cr
                # matches the FY26 call's closing figure" (independent review, 22 Oct 2026) needs memory
            elif not memory:
                issue = "compares with an earlier figure but cites no memory"
            else:
                unfound = [f for f in _figures(item.versus_prior) if not _stated_in(f, memory)]
                periods = {p for m in memory for p in _periods(m)}
                missing = [p for p in _periods(item.versus_prior) if p not in periods]
                if unfound or missing:
                    issue = ("the earlier figure or period is not in the memory it cites: "
                             + ", ".join([*(f"{v:g}" for v, _, _ in unfound), *missing]))
        item.issue = issue
        item.verified = issue is None
        if issue:
            notes.append(f'call takeaway "{item.text[:50]}": {issue}')
    return notes


def card_takeaways(dossier: dict, news_id: str | None, filed_at: str) -> list[dict] | None:
    """The call card's code-made block: the key takeaways memory took from THIS filing (by its news_id), under the
    company page's headings, at most CARD_PER_CATEGORY a heading and CARD_TOTAL in all, figures first, greetings and
    the safe harbour dropped. [{name, points: [{text, reiterated?}]}], or None when memory took none from it.
    Each point passed the checked memory merge, so it is the filing's own content, not the model's reading."""
    if not news_id:
        return None
    points = _points(dossier, {news_id: {"date": _day(filed_at), "quarter": None}})
    # a stated figure first, then the kind's rank (guidance before an operating note)
    ranked = sorted(points, key=lambda p: (not re.search(r"\d", p["text"]), -p["rank"]))
    kept: list[dict] = []
    seen: list[set[str]] = []
    count = dict.fromkeys(CATEGORIES, 0)
    for p in ranked:
        if len(kept) >= CARD_TOTAL:
            break
        words = _words(p["text"])
        if count[p["category"]] >= CARD_PER_CATEGORY or any(_same(words, s) for s in seen):
            continue
        seen.append(words)
        count[p["category"]] += 1
        kept.append(p)
    if not kept:
        return None
    return [{"name": c, "points": [{"text": p["text"], **({"reiterated": True} if p.get("reiterated") else {})}
                                   for p in kept if p["category"] == c]} for c in CATEGORIES if count[c]]
