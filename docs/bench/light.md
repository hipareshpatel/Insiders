# Light engines vs PyMuPDF sort=True

Baseline (corrected): PyMuPDF sort=True = **64.0 / 64.0 / 78.1** (row+column / row / anywhere). All engines share one row splitter that keeps leading serial numbers in the label, so scores compare. Code: `data/bench/scripts/light/`, outputs `data/bench/out/`.

| engine / config | row+col | row | any | s/page* |
|---|---|---|---|---|
| plumber-lines (default `extract_tables`) | 14.0 | 15.4 | 30.3 | 0.30 |
| plumber-text (text/text) | 44.3 | 44.3 | 77.6 | 0.4-0.5 |
| plumber-text-tuned | 42.5 | 43.0 | 77.2 | 0.3-0.5 |
| plumber-words (`extract_words`) | 61.4 | 61.8 | 77.2 | 0.14 |
| plumber-words-merge (+ orphan label rows) | **62.3** | 62.7 | 77.2 | 0.15-0.35 |
| p4llm-legacy (find_tables lines) | 40.8 | 40.8 | 72.8 | 0.6 |
| p4llm-legacy-text | 28.9 | 28.9 | 69.7 | 3.3 |
| p4llm-layout (pymupdf-layout, OCR off) | 43.0 | 43.0 | 73.7 | 2.6 |
| per-page best-of sorted+words / sorted+layout | 63.2 / 64.0 | | | |
| union sorted+words (ceiling only) | 64.5 | 64.9 | 78.1 | |

*Noisy, CPU shared; PyMuPDF text is 0.05.

**Per-filing: nothing beats 64.0% anywhere.** words-merge loses Jubilant f6e17477 12->10, Heritage daee44c8 5->4, Novartis 983aa10c 10->9. plumber-text loses Shivam 2531d7cc 9->2 (splits words: "fr om"). Layout loses Jubilant 139e9236 11->3, Novartis e4a61c7f 7->0 (drops a 2,092-character text layer over an image). Legacy loses Jubilant 139e9236 11->0, Shivam e9ae2c81 9->0 (a whole column packed into one cell).

**pdfplumber:** pdfminer emits the space glyph as literal "(cid:3)" in the Jubilant filings; I map it (+4.8 points, raw 56.6). It also splits "1,007" and "9.71" mid-number at any `x_tolerance` (1.5/2/3 gave 62.3/62.3/61.4).

**Install:** pdfplumber stack 46 MB; pymupdf4llm +1 MB; layout +171 MB (onnxruntime, numpy, networkx, pymupdf-layout). Venv 293 MB.

**eMudhra Q4 scores 0:** the PDF is a 5-page press-release letter, not a results statement. Ten of the 12 XBRL items are not in it. The two that are sit under labels the scorer misses: "PAT" 243.4 million = 24.34 crore, and "Revenue from operation" 1,492.6 = total_income 149.26.

**Scorer:** `revenue` is plural-only, so Shivam "Revenue from Operation" misses (2 figures). `other_expenses` misses banks' "Operating expenses" (CSB x2). `pat` misses "PAT". Widening all three adds 5 figures to PyMuPDF and words-merge, 3 to layout; ranking unchanged.

**Recommendation:** add none. The best (words-merge, 62.3%) is below PyMuPDF sort=True at 3-7x the time plus 46 MB, and layout is 43.0% at 2.6 s/page plus 171 MB; the remaining misses are garbled or scanned text layers and labels, not extraction.
