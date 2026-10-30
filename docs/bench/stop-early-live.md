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
  PBT differ by the associates' share). On live today this filing runs past the cap and the text layer decides. With
  the switch on, numbers-first decides, and a 0.4 Cr gap is a "False" from the slip check, which removes stored figures.

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

## Decision (lead, 30 Oct 2026)

NUMFIRST_STOP_EARLY stays off until the slip check no longer acts on the PBT definition gap: either numbers-first PBT
is skipped in the slip check, or its PBT follows the definition the corrected figure uses.
