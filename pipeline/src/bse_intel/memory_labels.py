"""Label everything already in memory, once, with no AI (docs/design/memory-labels.md step 2, TRACKER F150).

Step 1 (F144) labels what is written from now on. Memory written before it has no label. This job gives each such item
one, by the design's "Old memory (no AI)" rules and no others:

- an ``xbrl:`` id (the seed's synthetic ids) is ``file``; so is every section only an exchange feed writes (corporate
  actions, market deals, pledges, insider trades, trade remedies, governance reports, former names), once, in
  ``section_lab``. EBITDA, its margin and revenue net of excise are ``calc`` even under an ``xbrl:`` id: our code worked
  them out from the file's lines (the ``from`` list is the inputs memory holds for that period);
- an item from a call or its slides (the filing's event type and headline say so) is ``ai``: no page or quote exists, so
  it is only ever "said on <date>";
- a figure under an ``nse-...`` id is ``file`` only when the stored card of that filing carries an XBRL block and its
  results table holds the same value for that quarter (a derived line, EBITDA or its margin, is ``calc``); else
  ``unknown``;
- everything else is ``unknown`` (never shown as a fact, never an input of a computed figure, later steps).

A label already there is never touched (step 1's labels are newer and better). ``at`` is the item's own date when it has
one. Readers ignore labels, so no card changes: ``tests/test_memory_labels_job.py`` shows ``view_as_of`` is the same.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from .backup import BackupError, RunBackup
from .dossier import _RESULT_METRICS, SCREENER_KEY, SCREENER_PREFIX, STANDALONE_KEY, XBRL_SOURCE, doc_kind, keep_concurrent_writes, label
from .nse import NEWS_ID_PREFIX
from .timeutil import now_iso

log = logging.getLogger(__name__)

RESUME_KEY = "labelmem:last"   # kv: the last company (key order) a real run finished
READERS = 8                    # dossiers read at a time
PAGE = 200                     # cards read per export_cards query
LABELS = ("file", "ai", "calc", "unknown", "screener")   # "screener": the one-time screener.in fill (F161), labelled when written
DERIVED = ("ebitda", "ebitda_margin", "revenue_net_excise")   # worked out by our code from the file's lines
_EBITDA_PARTS = ("pbt", "finance_cost", "depreciation", "other_income", "exceptional_items")
_KEY_OF = {name: key for key, names in _RESULT_METRICS for name in names}   # a metric's name -> the results line's key
SECTIONS = (
    "financial_metrics", "screener_fill", "standalone_metrics", "standalone_balance_sheet", "balance_sheet", "segment_mix", "capital_actions",
    "deals", "operating_notes", "guidance", "watchlist", "predictions", "upcoming_events", "timeline", "entities",
    "ownership", "auditor", "business_summary", "call_points",
    "corporate_actions", "market_deals", "pledges", "insider_trades", "trade_remedies", "governance_quarters", "former_names",
)


def card_facts(rows) -> dict[str, dict]:
    """What the job keeps of each stored card (export_cards rows): its event type, headline and, for a results card made
    with its XBRL file, the table's quarter and each line's value."""
    out: dict[str, dict] = {}
    for row in rows:
        try:
            card = json.loads(row["card_json"]) if isinstance(row.get("card_json"), str) else (row.get("card_json") or {})
        except ValueError:
            continue
        info = {"event_type": card.get("event_type"), "headline": row.get("headline") or "", "xbrl": False,
                "period": None, "lines": {}}
        table = card.get("results")
        if card.get("xbrl") and isinstance(table, dict) and table.get("period"):
            info["xbrl"] = True
            info["period"] = table["period"]
            info["lines"] = {k: v["value"] for k, v in table.items()
                             if isinstance(v, dict) and isinstance(v.get("value"), (int, float))}
        out[row["news_id"]] = info
    return out


def load_cards(sink, scrips: set[str] | None = None) -> dict[str, dict]:
    """Every stored card's facts, one paged read of the cards (a card's JSON is only read here, not kept)."""
    out: dict[str, dict] = {}
    after = ["", ""]
    while True:
        rows = sink.query("export_cards", [after[0], after[1], PAGE])
        if not rows:
            break
        after = [rows[-1]["filed_at"], rows[-1]["news_id"]]
        out.update(card_facts(r for r in rows if not scrips or r.get("scrip_code") in scrips))
        if len(rows) < PAGE:
            break
    return out


class Labeller:
    """One company's labelling: ``run(dossier)`` labels it in place and returns ``(changed, new, had)``, the counts of
    items newly labelled and already labelled, per section and per label."""

    def __init__(self, cards: dict[str, dict] | None = None):
        self.cards = cards or {}
        self.events: dict[str, dict] = {}
        self.new: dict[str, dict[str, int]] = {}
        self.had: dict[str, dict[str, int]] = {}

    def _count(self, table: dict, section: str, by: str) -> None:
        row = table.setdefault(section, {})
        row[by] = row.get(by, 0) + 1

    def doc(self, news_id: str | None) -> str:
        """The kind of filing: from the card's, else the timeline's, event type, and the card's headline."""
        news_id = str(news_id or "")
        info = self.cards.get(news_id) or self.events.get(news_id)
        filing = SimpleNamespace(news_id=news_id, headline=(info or {}).get("headline") or "", subject="")
        return doc_kind((info or {}).get("event_type"), filing)

    def matches_card(self, news_id: str, metric: str, period: str | None, value) -> bool:
        info = self.cards.get(news_id)
        key = _KEY_OF.get(metric)
        if not info or not info["xbrl"] or not key or not isinstance(value, (int, float)) or period != info["period"]:
            return False
        shown = info["lines"].get(key)
        return shown is not None and abs(shown - value) <= 0.006

    def decide(self, news_id: str | None, metric: str | None = None, period: str | None = None, value=None,
               inputs: list[str] | None = None) -> tuple[str, str, list[str] | None]:
        """``(by, doc, from)`` for one item by the design's rules."""
        news_id = str(news_id or "")
        doc = self.doc(news_id)
        calc = metric in DERIVED
        if news_id.startswith(SCREENER_PREFIX):
            return "screener", "other", None   # the fill writes its own label; this only covers one stored without it
        if news_id.startswith(XBRL_SOURCE):
            doc = "results" if news_id.startswith(XBRL_SOURCE + "res") else doc
            return ("calc", doc, inputs) if calc else ("file", doc, None)
        if doc in ("call", "slides"):
            return "ai", doc, None
        if metric and news_id.startswith(NEWS_ID_PREFIX) and self.matches_card(news_id, metric, period, value):
            return ("calc", doc, inputs) if calc else ("file", doc, None)
        return "unknown", doc, None

    def put(self, section: str, item: dict, news_id, at, *, metric=None, period=None, value=None, basis=None,
            unit=None, inputs=None, target: dict | None = None) -> None:
        """Label ``item`` (or ``target``, where the label lives) unless it has one."""
        holder = item if target is None else target
        if holder.get("lab"):
            self._count(self.had, section, holder["lab"].get("by") or "unknown")
            return
        by, doc, src = self.decide(news_id, metric, period, value, inputs)
        if by == "unknown":
            holder["lab"] = {"by": "unknown", "doc": doc, "at": at}
        else:
            holder["lab"] = label(by, doc, at, basis=basis if metric else None, unit=unit if metric else None, src=src)
        self._count(self.new, section, by)

    def _inputs(self, metric: str, period: str, periods: dict[tuple[str, str], bool]) -> list[str] | None:
        if metric == "ebitda_margin":
            return [f"ebitda:{period}", f"revenue:{period}"]
        if metric == "revenue_net_excise":
            return [f"revenue:{period}", f"excise_duty:{period}"]
        if metric == "ebitda":
            return [f"{n}:{period}" for n in _EBITDA_PARTS if (n, period) in periods] or None
        return None

    def figures(self, section: str, rows: list[dict], basis_default: str | None = None) -> None:
        have = {(m.get("metric"), m.get("period")): True for m in rows}
        for m in rows:
            metric, period = m.get("metric"), m.get("period")
            inputs = self._inputs(metric, period, have) if metric in DERIVED else None
            if m.get("sources"):
                for s in m["sources"]:
                    self.put(section, s, s.get("news_id"), s.get("as_of") or m.get("as_of"), metric=metric, period=period,
                             value=s.get("value"), basis=s.get("basis") or m.get("basis") or basis_default,
                             unit=s.get("unit") or m.get("unit"), inputs=inputs)
            else:
                self.put(section, m, m.get("source_news_id"), m.get("as_of"), metric=metric, period=period,
                         value=m.get("value"), basis=m.get("basis") or basis_default, unit=m.get("unit"), inputs=inputs)

    def plain(self, section: str, rows, id_key: str = "source_news_id", at_keys: tuple[str, ...] = ("as_of",)) -> None:
        for item in rows or []:
            if isinstance(item, dict):
                at = next((item[k] for k in at_keys if item.get(k)), None)
                self.put(section, item, item.get(id_key), at)

    def feed(self, d: dict, section: str, present: bool, at: str | None, doc: str = "other") -> None:
        """A section only an exchange feed writes: one label for it, in ``section_lab``."""
        if not present:
            return
        known = d.setdefault("section_lab", {})
        if known.get(section):
            self._count(self.had, section, known[section].get("by") or "unknown")
            return
        known[section] = label("file", doc, at)
        self._count(self.new, section, "file")

    def run(self, d: dict) -> tuple[bool, dict, dict]:
        before = json.dumps(d, sort_keys=True)
        self.new, self.had = {}, {}
        # what each filing was, from the timeline (event type), for items whose card is not at hand
        self.events = {t["news_id"]: {"event_type": t.get("event_type"), "headline": ""}
                       for t in d.get("timeline", []) if isinstance(t, dict) and t.get("news_id")}
        self.figures("financial_metrics", d.get("financial_metrics", []))
        self.figures("screener_fill", d.get(SCREENER_KEY, []))
        standalone = d.get(STANDALONE_KEY) or {}
        self.figures("standalone_metrics", standalone.get("metrics", []), "STANDALONE")
        for name, rows in (("standalone_balance_sheet", standalone.get("balance_sheet", [])),
                           ("balance_sheet", d.get("balance_sheet", []))):
            self.plain(name, rows)
        self.plain("segment_mix", d.get("segment_mix"))
        self.plain("capital_actions", d.get("capital_actions"))
        self.plain("deals", d.get("deals"))
        self.plain("operating_notes", d.get("operating_notes"))
        self.plain("guidance", d.get("guidance"), at_keys=("given_on", "as_of"))
        self.plain("watchlist", d.get("watchlist"), at_keys=("created_on", "as_of"))
        self.plain("predictions", d.get("predictions"), at_keys=("created_on", "as_of"))
        self.plain("upcoming_events", d.get("upcoming_events"))
        self.plain("timeline", d.get("timeline"), id_key="news_id", at_keys=("date",))
        self.plain("entities", (d.get("identity") or {}).get("entities"))
        self.plain("ownership", d.get("ownership"))
        gov = d.get("governance") or {}
        self.plain("auditor", gov.get("auditor_history"))
        if isinstance(gov.get("auditor"), dict):   # the latest one is stored twice; the second is not counted again
            twin = next((a for a in gov.get("auditor_history", []) if a.get("source_news_id") == gov["auditor"].get("source_news_id")
                         and a.get("as_of") == gov["auditor"].get("as_of")), None)
            if twin is not None and twin.get("lab") and not gov["auditor"].get("lab"):
                gov["auditor"]["lab"] = dict(twin["lab"])
            elif not gov["auditor"].get("lab"):
                self.plain("auditor", [gov["auditor"]])
        if isinstance(d.get("business_summary"), dict):
            self.plain("business_summary", [d["business_summary"]])
        self.plain("call_points", d.get("call_points"), id_key="news_id", at_keys=("date",))

        def latest(rows, *keys):
            found = [str(r[k]) for r in rows or [] if isinstance(r, dict) for k in keys if r.get(k)]
            return max(found) if found else None

        events = lambda name: (d.get(name) or {}).get("events") or []  # noqa: E731
        self.feed(d, "corporate_actions", bool(d.get("corporate_actions")), latest(d.get("corporate_actions"), "as_of", "ex_date"))
        self.feed(d, "market_deals", bool(events("market_deals")), latest(events("market_deals"), "as_of", "date"))
        self.feed(d, "pledges", bool(events("pledges")), latest(events("pledges"), "as_of"))
        self.feed(d, "insider_trades", bool(events("insider_trades")), latest(events("insider_trades"), "as_of"))
        self.feed(d, "trade_remedies", bool(d.get("trade_remedies")), latest(d.get("trade_remedies"), "as_of"))
        self.feed(d, "governance_quarters", bool(gov.get("quarters")), latest(gov.get("quarters"), "as_of"))
        self.feed(d, "former_names", bool((d.get("identity") or {}).get("former_names")), None)
        if not d.get("section_lab"):
            d.pop("section_lab", None)
        return json.dumps(d, sort_keys=True) != before, self.new, self.had


def add_counts(total: dict, part: dict) -> None:
    for section, by in part.items():
        row = total.setdefault(section, {})
        for k, n in by.items():
            row[k] = row.get(k, 0) + n


def totals(table: dict) -> dict[str, int]:
    out = {k: 0 for k in LABELS}
    for by in table.values():
        for k, n in by.items():
            out[k] = out.get(k, 0) + n
    return out


def render(report: dict) -> str:
    rows = [f"memory labels ({'dry run, nothing written' if report['dry_run'] else 'written'}): "
            f"{report['companies']} companies read, {report['companies_changed']} {'would change' if report['dry_run'] else 'changed'}",
            f"{'section':26}{'file':>8}{'ai':>8}{'calc':>8}{'unknown':>9}{'had a label':>13}"]
    for section in SECTIONS:
        new, had = report["new"].get(section, {}), sum(report["had"].get(section, {}).values())
        if new or had:
            rows.append(f"{section:26}{new.get('file', 0):>8}{new.get('ai', 0):>8}{new.get('calc', 0):>8}"
                        f"{new.get('unknown', 0):>9}{had:>13}")
    t = totals(report["new"])
    rows.append(f"{'all newly labelled':26}{t['file']:>8}{t['ai']:>8}{t['calc']:>8}{t['unknown']:>9}"
                f"{sum(totals(report['had']).values()):>13}")
    return "\n".join(rows)


def label_all(sink, scrips: list[str], dry_run: bool, cards: dict[str, dict], restart: bool = False,
              time_budget: float | None = None, clock=time.monotonic) -> dict:
    """Label every company in ``scrips`` (key order). A real run writes each changed dossier back through a three-way
    merge (``keep_concurrent_writes``: what another job stored between the read and the write is kept) and saves the
    last company done, so a stopped run resumes after it (``restart`` begins again). ``more`` is true when the time budget
    ended the run with companies left."""
    scrips = sorted(scrips)
    done_through = "" if (dry_run or restart) else (sink.kv_get(RESUME_KEY) or "")
    todo = [s for s in scrips if s > done_through]
    new: dict = {}
    had: dict = {}
    report = {"dry_run": dry_run, "companies": 0, "companies_changed": 0, "skipped_resumed": len(scrips) - len(todo),
              "new": new, "had": had, "failed": [], "more": False, "last": done_through or None}
    deadline = clock() + time_budget if time_budget else None
    labeller = Labeller(cards)
    backup = None if dry_run else RunBackup(sink, "label-memory")   # each dossier is saved to R2 backup/ before its write
    with ThreadPoolExecutor(max_workers=READERS) as pool:
        for start in range(0, len(todo), READERS):
            if deadline is not None and clock() >= deadline:
                report["more"] = True
                break
            batch = todo[start:start + READERS]
            read = list(pool.map(lambda s: _read(sink, s), batch))   # reads in parallel; labels and writes in key order
            for scrip, dossier in zip(batch, read):
                if isinstance(dossier, Exception):
                    report["failed"].append(f"{scrip}: {type(dossier).__name__}: {dossier}"[:200])
                    continue
                report["companies"] += 1
                if dossier is None:
                    continue
                merged = json.loads(json.dumps(dossier))
                changed, got_new, got_had = labeller.run(merged)
                add_counts(new, got_new)
                add_counts(had, got_had)
                if changed:
                    report["companies_changed"] += 1
                    if not dry_run:
                        try:
                            keep_concurrent_writes(merged, dossier, sink.get_dossier(scrip))
                            backup.dossier(scrip, merged)
                            sink.put_dossier(scrip, merged)
                        except BackupError as exc:   # nothing more is written; the report so far is returned (and saved by the command)
                            report["failed"].append(f"{scrip}: {exc}"[:200])
                            report["error"] = f"{type(exc).__name__}: {exc}"[:300]
                            log.error("label-memory stopped: %s", exc)
                            break
                        except Exception as exc:   # noqa: BLE001 - one company's failed write must not stop the run
                            report["failed"].append(f"{scrip}: write {type(exc).__name__}: {exc}"[:200])
                            log.warning("label-memory %s write failed: %s", scrip, exc)
                            continue
                report["last"] = scrip
                if not dry_run and not report["failed"]:
                    sink.kv_set(RESUME_KEY, scrip, now_iso())   # only while nothing failed, so a failure is retried
            if report.get("error"):
                break
    return report


def _read(sink, scrip: str):
    try:
        return sink.get_dossier(scrip)
    except Exception as exc:   # noqa: BLE001
        return exc
