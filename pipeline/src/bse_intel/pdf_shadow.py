"""The shadow check of live results cards with the numbers-first PDF reader (TODO 121, owner 29 Oct 2026).

For each results card published in the last hours, the card's headline figures (revenue or total income, PBT, profit, as the
card states them, in crore, for the card's period) are compared with what the filing's PDF proves (``pdf_numbers_first``).
One row a figure: agrees / disagrees / unknown, with both values and the reason. Read only: no card, memory or site change,
no AI, no D1 write. The rows go to R2 (``meta/pdf-shadow/<day>.csv``) every few cards, so a run stopped by its time budget or a
lost runner keeps what it did, and the next run skips the cards already in the file.

Where a card keeps its figures (measured in the code, pipeline.py / dossier.results_snapshot, 29 Oct 2026): ``card_json["results"]``
is ``{"period": "Q2FY27", "revenue": {"value": cr, ...}, "pbt": {...}, "pat": {...}, "lines": [{"key", "label"}, ...]}``; the
revenue line is named "Total income" in ``lines`` when it is that line; the basis is ``card_json["xbrl"]["basis"]`` when the
card was made from a tagged file, else not stored (assumption: then the group's CONSOLIDATED statement, as memory prefers it;
the STANDALONE one is tried before a disagreement is reported). The filing's PDF is the ``pdf_url`` column of the card's row.

PBT is compared like with like (``pbt_verdict``). The card's PBT is memory's ``pbt`` for the quarter (dossier.results_snapshot):
today the file's ProfitBeforeTax (xbrl.py, before the associates' share as the taxonomy defines it), or that plus the share where
the statement prints the sum (``xbrl.settle_pbt``); STATUS item 9 makes it screener's PBT (ProfitBeforeTax + the associates' share +
regulatory deferral + discontinued profit, docs/design/screener-row-rules.md). The reader gives the printed "Profit before tax"
line, which holds the share when the statement prints the share above it. So the printed line is taken to each definition with
the quarter's own parts from memory's screener-rule statements (``statements.py``: "Profit before tax", "PBT as filed",
"Associates' share", read once a card from the dossier, no NSE call), and the card agrees when it is one of them. Without those
parts a PBT that differs from the printed line is "unknown", never "disagrees".
"""
from __future__ import annotations

import csv
import io
import logging
import re
import time
from datetime import datetime, timedelta

from .timeutil import IST, now_ist

log = logging.getLogger(__name__)

PROGRESS_PREFIX = "meta/pdf-shadow/"
CSV_HEADER = ["run_at", "card_id", "symbol", "filed_at", "period", "basis", "metric", "card_value", "pdf_value", "verdict", "reason",
              "pdf_page", "pdf_seconds", "pdf_url"]
SAVE_EVERY_CARDS = 3
SAVE_EVERY_SECONDS = 120.0
FLOOR = 0.005                      # crore: half a unit of two printed decimals
PAGE = 100
DEFAULT_PROFIT_LABELS = ("Net profit", "PAT", "Net loss")
_TRANSIENT = re.compile(r"^(?:download failed)")


def progress_key(day: str) -> str:
    return f"{PROGRESS_PREFIX}{day}.csv"


def to_csv(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for r in rows:
        writer.writerow(["" if r.get(k) is None else repr(round(r[k], 4)) if isinstance(r.get(k), float) else r.get(k) for k in CSV_HEADER])
    return buffer.getvalue()


def load_csv(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def load_rows(sink, day: str) -> list[dict]:
    # get_object gives None when nothing is saved yet; any other failure stops the run, because the run ends by rewriting the
    # whole day file from what it holds and would replace the day's saved rows with its own (review of 0739dcf)
    body = sink.get_object(progress_key(day))
    return load_csv(body.decode("utf-8")) if body else []


def save_rows(sink, day: str, rows: list[dict]) -> bool:
    try:
        sink.put_object(progress_key(day), to_csv(rows).encode("utf-8"), "text/csv")
        return True
    except Exception as exc:   # noqa: BLE001 - a failed save is never a stop
        log.warning("pdf-shadow: rows not saved (%s: %s)", type(exc).__name__, exc)
        return False


def decimals_of(value: float, cap: int = 2) -> int:
    text = repr(float(value))
    return min(cap, len(text.split(".")[1].rstrip("0")) if "." in text and "e" not in text else 0)


def verdict(card_value: float, reading) -> tuple[str, str]:
    """(agrees | disagrees | unknown, reason). Agrees when |card - pdf| <= max(the reader's tolerance, 0.005) + half a unit of the
    card's own shown decimals; unknown when the reader gives no "ok"."""
    if reading is None or reading.status != "ok" or reading.value is None:
        status = getattr(reading, "status", "none")
        return "unknown", f"{status}: {getattr(reading, 'note', '')}"[:300]
    allowed = max(float(reading.tol or 0), FLOOR) + 0.5 * 10 ** -decimals_of(card_value)
    gap = abs(card_value - reading.value)
    if gap <= allowed:
        return "agrees", f"PDF p{reading.page} prints {reading.value:g} Cr ({reading.label}; {reading.source})"[:300]
    return "disagrees", f"PDF p{reading.page} prints {reading.value:g} Cr ({reading.label}; {reading.source}), gap {gap:.2f} > {allowed:.3f}"[:300]


def pbt_parts(dossier: dict | None, period: str, basis: str | None) -> dict | None:
    """The parts that take a printed PBT to the card's definitions, from memory's screener-rule statements of the quarter and
    basis (``statements.py``, table "quarters"): ``share`` the associates' and JVs' share screener adds, ``add`` all screener adds
    to the filed ProfitBeforeTax (the share, regulatory deferral, discontinued profit). None when memory holds no such entry."""
    from . import screener_view as sv

    for e in (dossier or {}).get("statements") or []:
        if not isinstance(e, dict) or (e.get("period"), e.get("basis"), e.get("table")) != (period, basis, "quarters"):
            continue
        rows = e.get("rows") or {}
        screener = rows.get("Profit before tax")
        if not isinstance(screener, (int, float)):
            return None
        filed = rows.get("PBT as filed", screener)
        add = float(screener) - float(filed)
        family = e.get("family")
        # what of ``add`` is the share: the corporate recipe has its own row; the NBFC recipe adds the share alone; a lender's
        # and an insurer's PBT stay as filed
        share = float(rows.get("Associates' share") or 0.0) if family in (None, sv.CORPORATE) else add if family == sv.NBFC else 0.0
        return {"share": share, "add": add, "screener": float(screener), "filed": float(filed)}
    return None


def pbt_definitions(parts: dict) -> list[tuple[str, float]]:
    """(definition, what to add to the printed PBT line) for each definition a card's PBT may be on: as printed; the filed PBT
    where the statement prints the line after the share; screener's PBT from a line printed before the share, or after it."""
    share, add = parts["share"], parts["add"]
    out = [("as printed", 0.0)]
    if share:
        out.append(("the filed PBT before the associates' share (the PDF's line is after it)", -share))
    if add:
        out.append(("screener's PBT (the PDF's line before the associates' share)", add))
        if share:
            out.append(("screener's PBT (the PDF's line after the associates' share)", add - share))
    seen: set[float] = set()
    return [(name, d) for name, d in out if round(d, 6) not in seen and not seen.add(round(d, 6))]


def pbt_verdict(card_value: float, reading, parts: dict | None) -> tuple[str, str]:
    """The PBT verdict like with like: agrees when the card is the printed line taken to one of ``pbt_definitions``; unknown when
    it is not the printed line and memory has no parts to build the other definitions."""
    word, why = verdict(card_value, reading)
    if word != "disagrees":
        return word, why
    if parts is None:
        return "unknown", f"the card's PBT may be another definition (associates' share, screener's additions) and memory holds no parts for it; {why}"[:300]
    from dataclasses import replace

    for name, delta in pbt_definitions(parts)[1:]:
        shifted = replace(reading, value=reading.value + delta)
        if verdict(card_value, shifted)[0] == "agrees":
            return "agrees", (f"on {name}: PDF p{reading.page} prints {reading.value:g} Cr ({reading.label}; {reading.source}), "
                              f"{delta:+g} from memory's parts = {shifted.value:g}")[:300]
    tried = ", ".join(f"{reading.value + d:g}" for _, d in pbt_definitions(parts))
    return "disagrees", f"no PBT definition fits (tried {tried}); {why}"[:300]


def figures_of(card_json: dict) -> tuple[str | None, str | None, list[tuple[str, float, str]]]:
    """(period, basis or None, [(metric, card value in crore, profit line label)]) of a results card: revenue (total income when
    the card's line is named so), PBT and profit, those the card states."""
    results = card_json.get("results") or {}
    period = results.get("period")
    basis = (card_json.get("xbrl") or {}).get("basis")
    labels = {s.get("key"): s.get("label") or "" for s in results.get("lines") or [] if isinstance(s, dict)}
    out = []
    for key, metric in (("revenue", "revenue"), ("pbt", "pbt"), ("pat", "pat")):
        row = results.get(key)
        value = row.get("value") if isinstance(row, dict) else None
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        label = labels.get(key, "")
        if key == "revenue" and label.lower().startswith("total income"):
            metric = "total_income"
        out.append((metric, float(value), label))
    return period, basis, out


def _read(tables, period: str, metric: str, basis: str | None):
    from . import pdf_numbers_first as nf

    return nf.reading_from_tables(tables, period, metric, basis)


def check_card(tables, period: str, basis: str | None, figures, dossier: dict | None = None) -> list[dict]:
    """One result per figure: metric, card value, verdict, reason, PDF value, page, the basis used. ``dossier`` is the company's
    memory, whose statements give the parts PBT is compared with (``pbt_verdict``)."""
    from .metrics import CONSOLIDATED, STANDALONE

    out = []
    for metric, value, label in figures:
        def judge(reading, b, metric=metric, value=value):
            return pbt_verdict(value, reading, pbt_parts(dossier, period, b)) if metric == "pbt" else verdict(value, reading)

        used = basis or CONSOLIDATED
        reading = _read(tables, period, metric, used)
        word, why = judge(reading, used)
        if not basis and word != "agrees":
            other = _read(tables, period, metric, STANDALONE)      # the card's basis is not stored: the other one may be its own
            alt_word, alt_why = judge(other, STANDALONE)
            if alt_word == "agrees" or (word == "unknown" and alt_word != "unknown"):
                reading, word, why, used = other, alt_word, alt_why, STANDALONE
        if basis and word == "disagrees":
            # the card's stored basis is the tagged file's; its figures may come from memory's other basis (review of 0739dcf)
            alt = STANDALONE if basis == CONSOLIDATED else CONSOLIDATED
            other = _read(tables, period, metric, alt)
            if judge(other, alt)[0] == "agrees":
                reading, used = other, alt
                word, why = "basis_mismatch", f"agrees with the {alt} figure, not the stored {basis} basis; {why}"
        if not basis:
            why = f"basis assumed, the card does not store it; {why}"
        if word == "disagrees" and metric == "pat" and label and label not in DEFAULT_PROFIT_LABELS:
            word, why = "unknown", f"the card's profit line is '{label}' (not necessarily the total profit the reader gives); {why}"
        if word == "disagrees" and metric == "pat" and used == CONSOLIDATED:
            # a card's consolidated profit may be the owners' share (dossier prefers pat_owners); the reader gives the total
            word, why = "unclear", f"consolidated profit: the card may show the owners' share, the reader the total; {why}"
        out.append({"metric": metric, "card_value": value, "verdict": word, "reason": why, "basis": used,
                    "pdf_value": reading.value if reading is not None and reading.status == "ok" else None,
                    "pdf_page": reading.page if reading is not None and reading.status == "ok" else None})
    agreed = {r["basis"] for r in out if r["verdict"] == "agrees"}
    if not basis and len(agreed) > 1:
        # each figure found on the basis that fits it hides a card that mixes the two (the 26 Oct audit's mixed-bases class)
        for r in out:
            if r["verdict"] == "agrees":
                r["verdict"] = "mixed_bases"
                r["reason"] = f"the card's figures agree on different bases ({', '.join(sorted(agreed))}): mixed bases; {r['reason']}"
    return out


def _memory(sink, card: dict) -> dict | None:
    """The company's memory (the PBT parts), or None when it cannot be read: PBT is then unknown rather than disagrees."""
    get = getattr(sink, "get_dossier", None)
    if get is None or not card.get("scrip_code"):
        return None
    try:
        return get(str(card["scrip_code"]))
    except Exception as exc:   # noqa: BLE001 - a failed read only costs the PBT parts
        log.info("pdf-shadow: memory of %s not read (%s)", card.get("scrip_code"), type(exc).__name__)
        return None


def cards_since(sink, since_iso: str):
    """The stored cards filed after ``since_iso``, oldest first (``export_cards``, keyset-paged from the cutoff)."""
    after = [since_iso, ""]
    while True:
        rows = sink.query("export_cards", [after[0], after[1], PAGE])
        if not rows:
            return
        after = [rows[-1]["filed_at"], rows[-1]["news_id"]]
        yield from rows
        if len(rows) < PAGE:
            return


def tuned_symbols(bench=None) -> set[str]:
    """The companies the reader was tuned on: those in the two answer keys (docs/bench/{normal,hard}pdf/key.csv) that are not on
    the held-out list (docs/bench/heldout.csv). Every other company's figures are held out (the lead's ask, 29 Oct 2026)."""
    import csv
    from pathlib import Path

    bench = Path(bench) if bench else Path(__file__).resolve().parents[3] / "docs" / "bench"
    seen: set[str] = set()
    for key in ("normal", "hard"):
        try:
            with open(bench / f"{key}pdf" / "key.csv", encoding="utf-8") as fh:
                seen |= {r["symbol"] for r in csv.DictReader(fh)}
        except FileNotFoundError:
            pass
    try:
        with open(bench / "heldout.csv", encoding="utf-8") as fh:
            seen -= {r["symbol"] for r in csv.DictReader(fh)}
    except FileNotFoundError:
        pass
    return seen


def summary(rows: list[dict], tuned: set[str] | None = None) -> dict:
    """Per group (``held_out``: companies the reader was never tuned on; ``tuned``), the count of each verdict and the cards read,
    and the PDF minutes the rows took (each card's seconds counted once): the runner time a day."""
    tuned = tuned_symbols() if tuned is None else tuned
    out: dict = {"held_out": {}, "tuned": {}}
    cards: dict[str, set] = {"held_out": set(), "tuned": set()}
    seconds: dict[str, float] = {}
    for r in rows:
        group = "tuned" if r.get("symbol") in tuned else "held_out"
        out[group][r["verdict"]] = out[group].get(r["verdict"], 0) + 1
        cards[group].add(r["card_id"])
        try:
            seconds[r["card_id"]] = float(r.get("pdf_seconds") or 0)
        except ValueError:
            pass
    for group in ("held_out", "tuned"):
        out[group]["cards"] = len(cards[group])
    out["pdf_minutes"] = round(sum(seconds.values()) / 60, 1)
    return out


def run(nse, sink, since_hours: float = 3.0, limit: int | None = None, time_budget: float | None = None, clock=time.monotonic,
        src=None, analyse=None, now=None, every: int = SAVE_EVERY_CARDS, every_seconds: float = SAVE_EVERY_SECONDS) -> dict:
    """Read the recent results cards' PDFs one after the other. ``limit`` is cards read this run (a skipped card is not counted)."""
    import json

    from .nse import SourceBlockedError
    from .pdf_referee import Sources

    now = now or now_ist()
    day = now.date().isoformat()
    cutoff = (now - timedelta(hours=since_hours)).astimezone(IST).isoformat(timespec="seconds")
    src = src or Sources(nse, ocr=False)
    if analyse is None:
        from . import pdf_numbers_first as nf

        def analyse(data):   # noqa: E306
            return nf.analyse(data, ocr_garbled=True)
    rows = load_rows(sink, day)
    previous = load_rows(sink, (now - timedelta(days=1)).date().isoformat())
    done = {r["card_id"] for r in rows} | {r["card_id"] for r in previous}
    stats = {"cards_read": 0, "skipped_done": 0, "no_results_table": 0, "fetch_failed": 0, "blocked": False, "out_of_time": False}
    started, last_save, since = clock(), clock(), 0

    def save() -> None:
        nonlocal last_save, since
        save_rows(sink, day, rows)
        last_save, since = clock(), 0

    for card in cards_since(sink, cutoff):
        if card.get("event_category") != "RESULTS" or card.get("held"):
            continue
        card_id = card["news_id"]
        if card_id in done:
            stats["skipped_done"] += 1
            continue
        if limit is not None and stats["cards_read"] >= limit:
            break
        if time_budget is not None and clock() - started > time_budget:
            stats["out_of_time"] = True
            break
        try:
            card_json = json.loads(card["card_json"]) if isinstance(card["card_json"], str) else card["card_json"]
        except ValueError:
            continue
        period, basis, figures = figures_of(card_json)
        if not period or not figures or not card.get("pdf_url"):
            stats["no_results_table"] += 1
            continue
        t0 = clock()
        base = {"run_at": now.isoformat(timespec="seconds"), "card_id": card_id, "symbol": card.get("symbol"),
                "filed_at": card.get("filed_at"), "period": period, "pdf_url": card["pdf_url"]}
        try:
            data, why = src.payload(card["pdf_url"])
        except SourceBlockedError as exc:
            stats["blocked"] = True
            log.warning("NSE refused (%s): stopping the PDF shadow check", exc)
            break
        if data is None and _TRANSIENT.match(why or ""):
            stats["fetch_failed"] += 1                       # not finished: the next run reads the card again
            log.info("pdf-shadow: %s: %s", card_id, why)
            continue
        results: list[dict]
        if data is None:
            results = [{"metric": m, "card_value": v, "verdict": "unknown", "reason": f"no PDF: {why}", "basis": basis or "",
                        "pdf_value": None, "pdf_page": None} for m, v, _ in figures]
        else:
            try:
                results = check_card(analyse(data), period, basis, figures, dossier=_memory(sink, card))
            except SourceBlockedError:
                raise
            except Exception as exc:   # noqa: BLE001 - one PDF failing is a reason, not a stop
                log.warning("pdf-shadow: %s: reader failed (%s)", card_id, type(exc).__name__)
                results = [{"metric": m, "card_value": v, "verdict": "unknown", "reason": f"reader failed ({type(exc).__name__})",
                            "basis": basis or "", "pdf_value": None, "pdf_page": None} for m, v, _ in figures]
        seconds = round(clock() - t0, 1)
        for r in results:
            rows.append({**base, "basis": r["basis"], "metric": r["metric"], "card_value": r["card_value"], "pdf_value": r["pdf_value"],
                         "verdict": r["verdict"], "reason": r["reason"], "pdf_page": r["pdf_page"], "pdf_seconds": seconds})
        done.add(card_id)
        stats["cards_read"] += 1
        since += 1
        src.release()
        if since >= every or clock() - last_save >= every_seconds:
            save()
    save()
    mine = [r for r in rows if r.get("run_at") == now.isoformat(timespec="seconds")]
    counts: dict[str, int] = {}
    for r in mine:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    return {"rows": rows, "day": day, "verdicts": counts, "summary": summary(rows), **stats}
