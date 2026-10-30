"""NUMFIRST_STOP_EARLY on the stored results PDFs (docs/bench/stop-early-live.md), as the live path reads them (no OCR cache, no NSE): for each PDF, analyse
with the switch off then on, the seconds of each, and every reading the key asks of it (revenue, total income, PBT, PAT on
each basis and period the out-of-sample keys hold for that PDF) compared off against on.

usage: PYTHONPATH=src python scripts/bench_stop_early_live.py <out.json> <key.csv> [<key.csv> ...] -- <pdf dir> [<pdf dir> ...]
"""
import csv
import json
import os
import sys
import time

os.environ.pop("PDF_BENCH", None)


def main(argv):
    out = argv[0]
    cut = argv.index("--")
    keys, dirs = argv[1:cut], argv[cut + 1:]
    from bse_intel import pdf_numbers_first as nf
    from bse_intel.pdf_readers import pdf_key
    asks = {}
    for k in keys:
        for r in csv.DictReader(open(k)):
            asks.setdefault(pdf_key(r["pdf_url"]), set()).add((r["period"], r["metric"], r["basis"].upper()))
    files = {}
    for d in dirs:
        for f in sorted(os.listdir(d)):
            if f.endswith(".pdf"):
                files.setdefault(f[:-4], os.path.join(d, f))
    rows = json.load(open(out)) if os.path.exists(out) else []     # resume after a container restart
    done = {r["pdf"] for r in rows}
    for key, path in files.items():
        if key in done:
            continue
        data = open(path, "rb").read()
        res = {}
        for flag in ("0", "1"):
            os.environ["NUMFIRST_STOP_EARLY"] = flag
            t0 = time.perf_counter()
            try:
                tables = nf.analyse(data, ocr_garbled=True)
            except Exception as exc:   # noqa: BLE001
                tables = []
                print("failed", key, type(exc).__name__)
            secs = time.perf_counter() - t0
            readings = {}
            for period, metric, basis in sorted(asks.get(key, ())):
                r = nf.reading_from_tables(tables, period, metric, basis)
                readings[f"{period}|{metric}|{basis}"] = (r.status, None if r.value is None else round(r.value, 6))
            res[flag] = (round(secs, 2), readings)
        changed = [k for k in res["0"][1] if res["0"][1][k] != res["1"][1][k]]
        rows.append({"pdf": key, "off_s": res["0"][0], "on_s": res["1"][0], "asks": len(res["0"][1]), "changed": changed})
        json.dump(rows, open(out, "w"), indent=1)
    off = sum(r["off_s"] for r in rows)
    on = sum(r["on_s"] for r in rows)
    print(json.dumps({"pdfs": len(rows), "off_s": round(off, 1), "on_s": round(on, 1),
                      "saved_per_pdf_s": round((off - on) / max(1, len(rows)), 1),
                      "asks": sum(r["asks"] for r in rows), "changed": sum(len(r["changed"]) for r in rows)}))


if __name__ == "__main__":
    main(sys.argv[1:])
