"""The hard-PDF test set (F199): every PDF reader and the ensemble scored against an answer key.

``docs/bench/hardpdf/key.csv`` holds public NSE figures (one row a figure the referee can ask: revenue or profit, a quarter or
a year, one basis) with the filing's PDF on NSE. ``pdf-referee-ensemble`` with ``ids`` = ``hardset`` reads that file instead of
a referee artifact: each key row becomes a pair the readers answer (no memory or screener value, the readers just read the
figure), ``pdf_readers.settle`` is applied unchanged, and this module scores each reader and the ensemble verdict against the
key. A reading is right when it is within half a unit of the printed decimals (at least 0.005 crore) of ``expected_cr``.

    python -m bse_intel.pdf_bench --collect <key.csv> <pdf dir> [limit]       download the key's PDFs (NSE)
    python -m bse_intel.pdf_bench --run <key.csv> <pdf dir> <out dir> [limit]  read, settle, score; writes hardset-score.json/.md
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
from collections import defaultdict

MIN_TOL = 0.005       # crore: half a unit of two printed decimals
VERDICT_KEEP = ("settled", "scanned_lead", "disagree", "unsure", "none")


def load_key(text: str) -> list[dict]:
    """The key rows with a figure, a period, a metric, a basis and a PDF; others are skipped."""
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            expected = float(r.get("expected_cr", ""))
        except ValueError:
            continue
        if not (r.get("symbol") and r.get("period") and r.get("metric") and r.get("basis") and r.get("pdf_url")):
            continue
        out.append({**r, "expected_cr": expected, "basis": r["basis"].upper(),
                    "tags": [t for t in (r.get("tags") or "").split("|") if t]})
    return out


def pairs_of(key: list[dict], limit: int | None = None) -> list[dict]:
    """The pairs the readers answer, grouped by PDF (so each PDF is read once); ``limit`` keeps the first N PDFs."""
    urls = list(dict.fromkeys(r["pdf_url"] for r in key))
    if limit:
        urls = urls[:limit]
    order = {u: i for i, u in enumerate(urls)}
    return [{"symbol": r["symbol"], "scrip": r.get("scrip") or "", "period": r["period"], "metric": r["metric"],
             "basis": r["basis"], "pdf_url": r["pdf_url"], "expected": r["expected_cr"], "tags": r["tags"]}
            for r in sorted((r for r in key if r["pdf_url"] in order), key=lambda r: order[r["pdf_url"]])]


def outcome(status: str, value: float | None, expected: float, tol: float) -> str:
    """right | wrong | abstain for one reading (status ``ok``) or one settled verdict."""
    if status != "ok" or value is None:
        return "abstain"
    return "right" if abs(value - expected) <= max(tol, MIN_TOL) + 1e-9 else "wrong"


def answer_pair(ensemble, payload: bytes | None, pair: dict) -> dict:
    """One pair through the readers and the unchanged settle rule: {readers: {name: reading}, verdict: {...}}."""
    from .pdf_readers import Reading, settle
    if payload is None:
        readings = [Reading(n, "", "unavailable", note="PDF not downloaded") for n in ensemble.names]
    else:
        readings = ensemble.readings(pair["pdf_url"], payload, pair["period"], pair["metric"], pair["basis"])
    verdict = settle(readings)
    tol = max([r.tol for r in readings if r.reader in verdict.agreed] or [MIN_TOL])
    return {**{k: pair[k] for k in ("symbol", "period", "metric", "basis", "pdf_url", "expected", "tags")},
            "readers": {r.reader: {"status": r.status, "value": r.value, "tol": r.tol} for r in readings},
            "verdict": {"status": verdict.status, "value": verdict.value, "tol": tol, "agreed": verdict.agreed,
                        "disagreed": verdict.disagreed, "reason": verdict.reason}}


def _count() -> dict:
    return {"right": 0, "wrong": 0, "abstain": 0}


def score(records: list[dict]) -> dict:
    """Per reader and for the ensemble: right, wrong, abstain; the same per difficulty tag; the ensemble's false settlements.
    The ensemble answers only when the verdict is ``settled`` (the rule's own); a ``scanned_lead`` is counted on its own."""
    readers: dict[str, dict] = {}
    ensemble = {**_count(), "lead_right": 0, "lead_wrong": 0}
    by_tag: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(_count))
    false_settlements: list[dict] = []
    verdicts: dict[str, int] = defaultdict(int)
    for rec in records:
        exp = rec["expected"]
        for name, rd in rec["readers"].items():
            o = outcome(rd["status"], rd["value"], exp, rd["tol"])
            readers.setdefault(name, _count())[o] += 1
            for t in rec["tags"]:
                by_tag[t][name][o] += 1
        v = rec["verdict"]
        verdicts[v["status"]] += 1
        o = outcome("ok" if v["status"] == "settled" else "", v["value"], exp, v["tol"])
        ensemble[o] += 1
        for t in rec["tags"]:
            by_tag[t]["ENSEMBLE"][o] += 1
        if v["status"] == "scanned_lead":
            ensemble["lead_right" if outcome("ok", v["value"], exp, v["tol"]) == "right" else "lead_wrong"] += 1
        if o == "wrong":
            false_settlements.append({"symbol": rec["symbol"], "period": rec["period"], "metric": rec["metric"],
                                      "basis": rec["basis"], "settled": v["value"], "expected": exp,
                                      "agreed": v["agreed"], "tags": rec["tags"], "pdf_url": rec["pdf_url"]})
    return {"pairs": len(records), "readers": readers, "ensemble": ensemble, "verdicts": dict(verdicts),
            "by_tag": {t: {k: dict(c) for k, c in d.items()} for t, d in sorted(by_tag.items())},
            "false_settlements": false_settlements}


def _pct(c: dict) -> str:
    answered = c["right"] + c["wrong"]
    return f"{100 * c['right'] / answered:.0f}%" if answered else "-"


def to_markdown(s: dict) -> str:
    out = ["# Hard-PDF test set: every reader against the answer key", "",
           f"{s['pairs']} key rows (revenue and profit, quarters and years). Right = within half a unit of the printed "
           f"decimals (at least {MIN_TOL} crore) of the printed figure; abstain = no figure given. Ensemble verdicts: "
           + ", ".join(f"{k} {v}" for k, v in sorted(s["verdicts"].items())) + ".", "",
           "| Reader | right | wrong | abstain | right of answered |", "|---|---|---|---|---|"]
    rows = sorted(s["readers"].items()) + [("ENSEMBLE (settled)", s["ensemble"])]
    out += [f"| {n} | {c['right']} | {c['wrong']} | {c['abstain']} | {_pct(c)} |" for n, c in rows]
    e = s["ensemble"]
    out += ["", f"Scanned lead (two OCR families agree, not a settlement): {e['lead_right']} right, {e['lead_wrong']} wrong.", "",
            "## Per difficulty tag (right/wrong/abstain)", ""]
    names = sorted(s["readers"]) + ["ENSEMBLE"]
    out += ["| Tag | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for tag, d in s["by_tag"].items():
        out.append(f"| {tag} | " + " | ".join(
            "{}/{}/{}".format(*(d.get(n, _count())[k] for k in ("right", "wrong", "abstain"))) for n in names) + " |")
    out += ["", f"## The ensemble's false settlements ({len(s['false_settlements'])})", ""]
    out += [f"- {f['symbol']} {f['period']} {f['basis']} {f['metric']}: settled {f['settled']:g}, printed {f['expected']:g} "
            f"(agreed: {'+'.join(f['agreed'])}; tags: {', '.join(f['tags'])})" for f in s["false_settlements"]] or ["None."]
    return "\n".join(out) + "\n"


def collect(key_csv: str, out_dir: str, limit: int | None = None) -> int:
    """Download the key's PDFs from NSE into ``out_dir`` (``<key>.pdf``, manifest.json, failed.json), as ``pdf_readers.collect``."""
    from .nse import NseClient
    from .pdf_readers import DEFAULT_READERS, fetch_with_retry, pdf_key
    from .pdf_referee import Sources
    os.environ["PDF_READERS"] = DEFAULT_READERS
    os.makedirs(out_dir, exist_ok=True)
    with open(key_csv, encoding="utf-8") as fh:
        pairs = pairs_of(load_key(fh.read()), limit)
    seen: dict[str, str] = {}
    failed: dict[str, str] = {}
    with NseClient() as nse:
        src = Sources(nse, ocr=False)
        for url in dict.fromkeys(p["pdf_url"] for p in pairs):
            data, why = fetch_with_retry(src, url)
            if data:
                with open(os.path.join(out_dir, f"{pdf_key(url)}.pdf"), "wb") as fh:
                    fh.write(data)
                seen[pdf_key(url)] = url
            else:
                failed[url] = why
                print(f"not collected: {url} ({why})")
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(seen, fh)
    with open(os.path.join(out_dir, "failed.json"), "w", encoding="utf-8") as fh:
        json.dump(failed, fh)
    print(f"collected {len(seen)} PDFs; {len(failed)} could not be downloaded")
    return 0


def run(key_csv: str, pdf_dir: str, out_dir: str, limit: int | None = None) -> int:
    """Read every key pair with the configured readers (env PDF_READERS, PDF_READER_TABLES_DIR) and write
    hardset-readings.json, hardset-score.json and hardset-score.md into ``out_dir``; the PDFs are those of ``pdf_dir``."""
    from . import pdf_readers
    from .pdf_referee import Sources, be_gentle
    be_gentle()
    os.environ["PDF_CACHE_DIR"] = pdf_dir
    os.makedirs(out_dir, exist_ok=True)
    with open(key_csv, encoding="utf-8") as fh:
        pairs = pairs_of(load_key(fh.read()), limit)
    ensemble = pdf_readers.Ensemble(pdf_readers.configured_readers())
    src = Sources(None, ocr=False)                       # the PDFs are in PDF_CACHE_DIR; no NSE session here
    records = []
    for pair in pairs:
        payload, _why = src.payload(pair["pdf_url"])
        records.append(answer_pair(ensemble, payload, pair))
    result = score(records)
    with open(os.path.join(out_dir, "hardset-readings.json"), "w", encoding="utf-8") as fh:
        json.dump(records, fh)
    with open(os.path.join(out_dir, "hardset-score.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    with open(os.path.join(out_dir, "hardset-score.md"), "w", encoding="utf-8") as fh:
        fh.write(to_markdown(result))
    print(to_markdown(result))
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if len(argv) in (3, 4) and argv[0] == "--collect":
        sys.exit(collect(argv[1], argv[2], int(argv[3]) if len(argv) == 4 else None))
    if len(argv) in (4, 5) and argv[0] == "--run":
        sys.exit(run(argv[1], argv[2], argv[3], int(argv[4]) if len(argv) == 5 else None))
    print("usage: python -m bse_intel.pdf_bench --collect <key.csv> <dir> [limit] | --run <key.csv> <pdf dir> <out dir> [limit]",
          file=sys.stderr)
    sys.exit(2)
