# Call-memory deck points with the v3 prompt, judged blind (31 Oct 2026, ~01:00 IST)

The same 9 decks, model (Gemini 3.5 Flash-Lite on key 3) and part size as ../judged-2026-10-31 (v2), read with
`config/prompts/call_memory_v3.md` (v2 plus: no figure off a chart, pie or diagram unless its own label, segment and period
are on its line), maintenance run 41103785967. Judged by three independent agents: 282 points, 255 RIGHT, **27 WRONG (9.6%)**
(v2: 27 of 293, 9.2%). ESAF 11 of 60, MTAR 5, Welspun 6, Thyrocare 3, Shaily 1, the other four 0. The prompt rule does not
change what this model does on chart slides.

Where the WRONG points are, both sets (quote_assembled = the quote was put together from words across the slide, not found
as one run of text): v2 all 27 WRONG assembled, RIGHT 113 assembled of 266; v3 25 of 27 WRONG assembled, RIGHT 99 of 255.
No WRONG point in either set has a quote found as one line of the page text. Dropping assembled slide quotes would remove
every WRONG but about 40% of RIGHT points; a second look (a vision read of the slide) would be needed only for them.
