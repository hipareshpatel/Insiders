# Sampling re-run, 24 Oct 2026 (owner's go)

12 filings of Apollo Micro Systems, Shakti Pumps and BlueStone (4 announcement types each) re-run on production with
the merged #100 code (`RESULTS_FACTS`, `RESULTS_RICH` on, the F118 prompts). Old cards: `before.json`; new:
`after_raw.json`; the pairs given to two independent blind reviewers: `pairs_*.json`; their verdicts: `review_*.json`.
Every re-run was processed by the merged code (run 208, head 9233007; the old-code run 206 processed none).

| Filing | Old | New | New vs old |
|---|---|---|---|
| Apollo results (574) | MINOR, THIN | MINOR, PARTIAL | better |
| Apollo investor deck (613) | RIGHT, THIN | RIGHT, THIN | better |
| Apollo IDL silo, capex (471) | MINOR (reading), FULL | RIGHT, FULL | better |
| Apollo warrant allotment (827) | MINOR, FULL | no card | **wrong drop**: a distinct capital action |
| Shakti results (837) | RIGHT, THIN | RIGHT, PARTIAL | better |
| Shakti investor deck (969) | RIGHT, THIN | WRONG (reading only), THIN | worse: "expanding order book" when it halved |
| Shakti EV subsidiary, M&A (721) | RIGHT, FULL | MINOR, THIN | worse: impact rated too high, details dropped |
| Shakti order win (175) | RIGHT, FULL | RIGHT, FULL | better |
| BlueStone results (286) | MINOR, THIN | not processed yet | - |
| BlueStone NCD (336) | MINOR (reading), FULL | RIGHT, PARTIAL | same |
| BlueStone monthly update (337) | MINOR, THIN | no card | right: it repeats the results filing's pages |
| BlueStone NSE fine (418) | RIGHT, FULL | RIGHT, PARTIAL | worse: corrective steps dropped |

Both results cards are richer (cash flow, cost ratios, receivables, borrowings, dividend); they repeated two code lines,
fixed in 28edc2c. Of the three worse cards, two were written by DeepSeek before (its paid window closed 23 Oct) and
Gemini 3.5 Flash-Lite now; the third by Flash-Lite both times. Literal `**` in the stored text is the bold the site
renders (`RichText.tsx`), not shown to readers.
