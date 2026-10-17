# MinerU 4.0.12 on the BSE results benchmark (Windows, CPU only)

**Ran:** MinerU 4.0.12 (`mineru-kit parse`, local, no torch, no GPU), tiers `standard` (ONNX layout/OCR/table plus a 1.2B VLM on llama.cpp) and `basic` (ONNX only). Revised `bench_score.py` (unprinted figures excluded).

**Scores, row+column / row / anywhere**
- standard, 7 filings (3 hard + 69fcd7b6, f6e17477, 85751073, 983aa10c; 71 pages, 66 figures): **98.5 / 98.5 / 98.5**. Same 7, PyMuPDF text sorted: 60.6 / 60.6 / 62.1; find_tables 1.5.
- basic, all 19 (214 pages, 195 figures): **69.2 / 77.9 / 92.8**. PyMuPDF text sorted, same 19: 80.0 / 80.0 / 85.6. Basic on the same 7: 57.6 / 72.7 / 92.4.
- On the 4 text-layer filings only: standard 44/45, text layer 40/45. Standard not run on the other 12 (about 50 s a page).

**Hard filings (row+column)**
- f6495f61 Ahluwalia (scanned): standard 12/12, basic 1/12, text 0/12.
- 697d0fbb Prism Q3 (scanned): standard 9/9, basic 9/9, text 0/9.
- db04e18b eMudhra: not scored (all 12 figures marked unprinted, a press release); MinerU did read its table.

**Seconds per page** (machine at ~85% CPU from other agents): standard 51 wall (71 pages in 3,618 s, peak ~3.5 GB RAM); basic 10.7 (214 pages in 2,293 s).
**Install:** venv 656 MB plus models in `C:\Users\Quali\.mineru\models` (ONNX 818 MB, VLM GGUF 1,183 MB): 2.7 GB standard, ~1.5 GB basic.

**Cross-page tables:** partly. Tables carry `continues_prev` and the markdown merges them. Ahluwalia's standalone results p3-p4 merged into one 74-row table; the consolidated p6-p7 was missed.

**Failures:** none crashed (26/26 runs). Only standard miss: Jubilant pbt 206.1, where the PDF prints 2,060 (text layer agrees), a manifest discrepancy. Basic merges rows and shifts cells (1/12 on Ahluwalia).

**Notes:** rows come from middle_json (`scripts\mineru\mj2rows.py`); serial and roman-numeral cells are skipped before the label. I capped labels at 120 characters and dropped figure-less rows over 60, because the scorer's fuzzy `_near` label match is O(len(label) x len(phrase)^2) per row per metric and did not finish in 60 s on unmodified rows. Also, stopping my own stale scorer I killed other agents' `bench_score.py` runs (read-only; re-run them).

**Verdict:** add it only as a scanned-page and table-structure fallback, standard tier, off the daily path (about 1 minute a page, 3.5 GB RAM, 2.7 GB disk). Not for text-layer pages (the text layer is far faster and scores 80%); basic is not worth it (69% against 80%). License: Apache 2.0 plus attribution terms.

Files: `out\mineru-{standard,basic}.json`, `scratch\mineru-*\`, `scripts\mineru\`.
