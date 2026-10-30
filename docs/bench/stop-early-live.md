# NUMFIRST_STOP_EARLY on the live path (30 Oct 2026)

The lead asked (30 Oct): before any switch-on, the seconds saved per results filing and whether any card's figures
change, read-only over stored PDFs, no NSE download.

**How:** `pipeline/scripts/bench_stop_early_live.py` on the stored out-of-sample PDFs (`data/oos/pdfs`,
`data/oos3/pdfs`, 140 unique). Each PDF is read twice by `analyse(ocr_garbled=True)`, once with the switch off and once
on. There is no OCR cache (as on live) and no time cap. Each read is timed, and every key figure (revenue, total income,
PBT, PAT, each basis and period the two out-of-sample keys hold) is compared off against on. Results:
`stop-early-live-66.json`.

**Stopped at 66 of 140** (this session's 2-hour cap on background jobs, after two container restarts). Rows 10-21 were
timed while a second copy ran by mistake, so their seconds are inflated, both off and on. The lead: don't finish now.
Re-time all 140 with one copy once the PBT question below is settled.

## Result on 66 PDFs

- **Seconds:** off 4,523, on 3,667. That is 856 s saved, 13 s a filing (19%). Rough, because of rows 10-21.
- **Figures changed:** 0 of 285 key figures.
- **The live 60 s cap** (`SLIP_CHECK_NUMFIRST_SECONDS`). Past the cap the reader gives no answer and the text-layer
  reader decides. 29 of 66 PDFs run past 60 s with the switch off, 23 with it on. So on live most of the saving is capped
  away. What changes is **who decides**: 6 filings fall under the cap only with the switch on, and 0 the other way. Their
  readings, with the switch on, against the key:

  | Filing | Right | Wrong | No answer |
  |---|---|---|---|
  | MANORAMA | 7 | 0 | 1 |
  | ACI | 8 | 0 | 0 |
  | AHLUCONT | 2 | 0 | 6 |
  | ERIS | 7 | **1** | 0 |
  | two PDFs with no key rows | - | - | - |

  ERIS Q1FY27 consolidated PBT: the reader gives 179.49 against the XBRL key's 179.89. The switch off reads the same,
  so the stop does not cause it. It is the known PBT definition gap (STATUS §3 item 14: the XBRL tag and the printed
  PBT differ by the associates' share). **Correction (30 Oct, later):** the slip check is never asked for PBT, so this
  gap cannot reach it (see the end of this page).

## Group filers (the lead's case)

The worry: does the stop end the scanned-page reads before the consolidated statement is read? 21 of the 66 PDFs have
consolidated rows in the key and saved more than 3 s with the switch on. None changed a figure. 8 of them were re-read
with a spy on the stop test. On every one the stop fired only after both bases were stated (the rule: the consolidated
basis is wanted whenever the filing names one).

| Filing | Consolidated pages read | Right | Wrong | No answer |
|---|---|---|---|---|
| YUKEN | 5, 6 | 3 | 1 (PBT 6.94 vs 7.25, same with the switch off) | 0 |
| MANORAMA | 4 | 4 | 0 | 0 |
| HITECHGEAR | 3 | 3 | 0 | 1 |
| DOLATALGO | 4 | 3 | 0 | 1 |
| PACEDIGITK | 8 | 4 | 0 | 0 |
| ZENSARTECH | 6 | 4 | 0 | 0 |
| FIEMIND | 5, 6 | 4 | 0 | 0 |
| LAURUSLABS | 2 | 2 | 0 | 2 |

No consolidated answer was lost to the stop. Both wrongs are PBT, are the same with the switch off, and are the
definition gap above.

## What the two PBT gaps are

Both are the joint ventures' or associates' share. The file tags PBT before the share, and the statement prints the
line before the share too. Numbers-first answers the "Profit before tax" line after the share:

- ERIS: 179.89 before the share; the JV share is a 0.40 loss; 179.49 after it.
- YUKEN: 724.60 lakh before the share; the associates' share is -30.34 lakh; 694.26 lakh after it.

Neither filing prints any exceptional items.

## Decision (lead, 30 Oct 2026)

Option (b): numbers-first's PBT follows the definition of the slip check's corrected figure (TODO 143). Until that
lands, NUMFIRST_STOP_EARLY stays off. Then all 140 stored PDFs are re-timed with one copy running.

## Correction (30 Oct 2026, after #253 merged)

The live slip check never asks the reader for PBT. All three callers (pipeline.py ~3091 and ~3581, seed.py ~200) go
through `xbrl.fix_scale`. It checks one figure: the first of `_SCALE_REFERENCE` = revenue, total income, interest earned
(xbrl.py 1179 and 1319). So the PBT definition gap above cannot produce a slip-check False, on live today or with the
switch on. The figures that matter are revenue and total income. On the 66 PDFs none of them changed, and the 6 filings
that cross the cap have no wrong revenue or total income figure (their only wrong is ERIS's PBT). So TODO 143 is not
what blocks NUMFIRST_STOP_EARLY. The switch-on call goes back to the lead on these figures.

## The clean sample: 72 PDFs, one copy (30 Oct 2026, lead: take the 72)

The re-time of all 140 (`stop-early-live-72.json`) ran with one copy throughout and stopped at this session's 2-hour cap
on background jobs after 72 PDFs. Lead: the 72 are the sample.

- **Seconds:** off 3,961, on 3,148. That is 813 s saved, **11.3 s a filing**.
- **Figures changed:** **0 of 341** key figures (revenue, total income, PBT, PAT).
- **The live 60 s cap:** 28 of 72 run past 60 s with the switch off, 23 with it on. **5 filings drop under the cap only
  with the switch on**, and 0 go the other way. On those 5, numbers-first would then decide the slip check, which asks
  for revenue / total income / interest earned. Their readings against the key, switch on:
  - ERIS: revenue and total income right.
  - ACI: right.
  - SHIVAUM: revenue 1 right, 1 no answer; total income 1 right, 1 no answer.
  - MAHLOG: revenue 4 right, total income 4 right.
  - One PDF has no key rows.

  **No wrong revenue or total income figure.** The only wrongs are PBT, which the slip check never asks for: MAHLOG
  consolidated Q2FY27 40.30 vs 40.36 and H1FY27 79.36 vs 79.47.

The lead takes the switch-on call to the owner on these figures.
