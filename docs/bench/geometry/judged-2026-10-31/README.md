# Call-memory deck points, judged blind (31 Oct 2026, ~00:30 IST)

The 293 points call memory's v2 prompt kept from the 9 decks of docs/bench/geometry/decks.csv (maintenance run 41031796024,
artifact `call-memory`), judged RIGHT / WRONG against the slide itself by three independent agents (no rule shown to them):
266 RIGHT, 27 WRONG (9.2%), 0 UNSURE. WRONG by deck: ESAF 9 of 71, MTAR 7 of 33, Welspun 7 of 32, Thyrocare 3 of 32,
GK Energy 1 of 51, BlackBuck, Firstsource, Shaily, Huhtamaki 0. Nearly all are a chart or pie figure paired with another bar,
year or segment's label. The 30 Oct set this replaces (6 of 146 WRONG) was lost with that session's scratchpad.

Files: `points/<news_id>.json` (the kept points as stored), `verdicts.json` ({id, verdict, why}), `to_judge.jsonl` (what the
judges saw). The PDFs are the `deck-pdfs` artifact of run 41069401462 (named by news id in this set); page texts are rebuilt
from them with PyMuPDF, a page under 20 words marked `[ocr]`.

    python scripts/measure_slide_geometry.py --pdf-dir PDFS --texts TEXTS --points docs/bench/geometry/judged-2026-10-31/points \
        --verdicts docs/bench/geometry/judged-2026-10-31/verdicts.json

Measured: rules on main (30 Oct) WRONG 23 of 27 dropped, RIGHT 64 dropped (25.2%); the 31 Oct rules (units and filler never
labels, prose left alone) WRONG 23 of 27, RIGHT 57 (22.4%). The bar is all WRONG out and at most 3% RIGHT dropped.
