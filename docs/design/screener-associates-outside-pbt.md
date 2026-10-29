# Companies whose associates' share screener keeps out of PBT (a separate list, not a rule)

Owner, 29 Oct 2026: "Make it separately, because we need to validate it for periods of 8-10 years" and "for right now no
company name specific rules". **No code reads this list.** It records which companies screener treats like Reliance (the
associates' and joint ventures' share left out of PBT and Other Income, kept in Net Profit), so the owner can decide later.

## How it is validated over 10–12 years without new requests

Screener's own page carries 10–12 years. When the share is inside screener's PBT, its Net Profit = PBT − Tax (Tax = Tax % ×
|PBT|). When the share is kept out, Net Profit is above PBT − Tax by about the share, every year. The residual below is Net
Profit − (PBT − Tax) in ₹ Cr from the stored pages (consolidated); `*` marks a year where it exceeds the tax-rate rounding
(max ₹1 Cr, 0.6 % of PBT). Measured 29 Oct 2026 on run 40793194881's rows (1,114 companies with 8+ years). The owner's DLF and
BEL Excel sheets confirm it for FY25–FY26 (PBT = the filed PBT exactly), and the XBRL years FY24–FY26 for the rest (the gap
equals the filed ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod).

Banks (SBI, Bank of Baroda, Canara, Indian Bank) and GIC Re show a residual too but file no associates' share the corporate
way: another cause (the bank template's share of associates and minority below PBT), not this list.

## Validated: the pattern in at least 80 % of 8–12 years, and the company files an associates' share

| Company | Years with the pattern | Residual by year (₹ Cr) |
|---|---|---|
| ADANIENT | 11 of 12 | FY15 7.8 FY16 17.9* FY17 115.8* FY18 219* FY19 193.9* FY20 243.4* FY21 296.7* FY22 312* FY23 214* FY24 34.6* FY25 469.5* FY26 213* |
| ALEMBICLTD | 12 of 12 | FY15 83.3* FY16 210.5* FY17 117.2* FY18 121.2* FY19 171.6* FY20 236* FY21 329.2* FY22 135.8* FY23 110.1* FY24 176.3* FY25 165.9* FY26 190.3* |
| ANANTRAJ | 10 of 12 | FY15 0.2 FY16 6.5* FY17 9.1* FY18 5.2* FY19 10.8* FY20 7.2* FY21 8.8* FY22 4* FY23 5.2* FY24 6.2* FY25 3.7* FY26 2.9 |
| AWL | 8 of 8 | FY19 18.8* FY20 59.1* FY21 79.7* FY22 30.9* FY23 29.7* FY24 -22.3* FY25 57.3* FY26 60.8* |
| DLF | 11 of 12 | FY15 -0.7 FY16 -156.7* FY17 -95.4* FY18 169.5* FY19 945.8* FY20 885.8* FY21 604.2* FY22 661.2* FY23 937.5* FY24 1089.2* FY25 1676.4* FY26 1805.5* |
| HUBTOWN | 12 of 12 | FY15 -1.4* FY16 -20.4* FY17 -9.3* FY18 -3.2* FY19 -16* FY20 -14.9* FY21 8* FY22 2.8* FY23 3* FY24 -10.2* FY25 -9.3* FY26 -3.3* |
| INDHOTEL | 11 of 12 | FY15 -1.3 FY16 -21.9* FY17 38.3* FY18 41.4* FY19 50.8* FY20 11.6* FY21 -99* FY22 -43.1* FY23 81.8* FY24 130.5* FY25 78.7* FY26 52.5* |
| KIRLOSBROS | 11 of 12 | FY15 -0.4 FY16 -11.8* FY17 5.8* FY18 4* FY19 8.3* FY20 4.2* FY21 6.3* FY22 13* FY23 10.2* FY24 8.5* FY25 16.5* FY26 15.4* |
| MARATHON | 9 of 11 | FY16 0 FY17 0.3 FY18 10.5* FY19 8* FY20 4.5* FY21 -7* FY22 15.6* FY23 11.7* FY24 35.8* FY25 28.8* FY26 18.3* |
| MAZDOCK | 12 of 12 | FY15 23.6* FY16 33.6* FY17 56.4* FY18 99.5* FY19 65.2* FY20 93* FY21 61* FY22 49.2* FY23 66.8* FY24 118.2* FY25 148.1* FY26 150.2* |
| NAHARPOLY | 12 of 12 | FY15 7.2* FY16 4.1* FY17 10.2* FY18 7* FY19 3.8* FY20 4.9* FY21 12* FY22 12.5* FY23 11.9* FY24 15.1* FY25 11.8* FY26 11.7* |
| ORIENTHOT | 10 of 12 | FY15 0.5 FY16 7.9* FY17 8.4* FY18 6.7* FY19 5* FY20 -1.8* FY21 -17* FY22 -7.2* FY23 -1.2* FY24 -0.3 FY25 -3.2* FY26 -3.8* |
| PILANIINVS | 11 of 12 | FY15 -59.2* FY16 -10.7* FY17 15.7* FY18 -0.2 FY19 2005.2* FY20 121* FY21 -9.4* FY22 55.8* FY23 90* FY24 16.5* FY25 -53* FY26 -34.5* |
| RAMCOIND | 12 of 12 | FY15 53.7* FY16 135* FY17 149.7* FY18 97.6* FY19 97.1* FY20 101* FY21 163.5* FY22 175.6* FY23 16.6* FY24 33* FY25 87.3* FY26 170* |
| RELINFRA | 11 of 12 | FY15 410.2* FY16 406.8* FY17 309.5* FY18 57.1* FY19 -1380.6* FY20 44.1* FY21 0.7 FY22 -192.3* FY23 -98* FY24 -500.6* FY25 693* FY26 -102.4* |
| REPCOHOME | 11 of 12 | FY15 2.2* FY16 4.5* FY17 6* FY18 1.4 FY19 15* FY20 17.2* FY21 11.4* FY22 1.6* FY23 19.3* FY24 21.5* FY25 23.3* FY26 26.9* |
| SUNDARMFIN | 12 of 12 | FY15 67.8* FY16 72.6* FY17 93.5* FY18 173.8* FY19 222.9* FY20 42.4* FY21 225.5* FY22 233.2* FY23 226.8* FY24 410.5* FY25 68.2* FY26 48.2* |
| TAJGVK | 11 of 12 | FY06 -0.2 FY16 -4.1* FY17 -6.6* FY18 -1.1* FY19 2.7* FY20 4.2* FY21 -13.7* FY22 -8.1* FY23 12.8* FY24 18.5* FY25 21.5* FY26 21.4* |
| TATACONSUM | 12 of 12 | FY15 -12* FY16 -6.4* FY17 -8.4* FY18 -8.8* FY19 -13.4* FY20 -73.9* FY21 -66.4* FY22 -62.4* FY23 -25.5* FY24 -90.9* FY25 -99.1* FY26 -82.8* |
| TEXINFRA | 11 of 12 | FY15 3.3* FY16 6.8* FY17 8.4* FY18 2.5* FY19 21.8* FY20 -15.7* FY21 3.5* FY22 4.9* FY23 -0 FY24 1.4* FY25 1.3* FY26 1.2* |
| TSFINV | 9 of 9 | FY18 112.1* FY19 106.8* FY20 48.6* FY21 64.5* FY22 143.6* FY23 206* FY24 339.4* FY25 334.8* FY26 364.2* |
| ZYDUSLIFE | 10 of 12 | FY15 2.3 FY16 32.9* FY17 34* FY18 52.9* FY19 41* FY20 23* FY21 37.1* FY22 42.4* FY23 101.6* FY24 107.4* FY25 32.2 FY26 92* |

## Most years, or the recent years only (a layout that changed, or a share that grew): check the years before

| Company | Years with the pattern | Residual by year (₹ Cr) |
|---|---|---|
| BEL | 9 of 12 | FY15 1.7 FY16 -3.6 FY17 15.9* FY18 22* FY19 47.4* FY20 40.8* FY21 40.6* FY22 57.2* FY23 43.8* FY24 35.5* FY25 69.7* FY26 22.2 |
| BALMLAWRIE | 8 of 12 | FY15 -0.6 FY16 0.8 FY17 -0.8 FY18 0.8 FY19 36.4* FY20 37.4* FY21 32.6* FY22 45.6* FY23 61.4* FY24 36* FY25 63* FY26 68.4* |
| GNFC | 8 of 12 | FY15 9* FY16 5.8* FY17 7* FY18 4.8 FY19 12.9* FY20 10.8* FY21 5 FY22 9.5 FY23 3.7 FY24 15.3* FY25 13.4* FY26 10.2* |
| MINDACORP | 8 of 12 | FY15 3.6* FY16 -0.2 FY17 -0.2 FY18 -0.2 FY19 -0.9 FY20 -1.3* FY21 4.2* FY22 9* FY23 -11* FY24 2.2* FY25 16.4* FY26 81.5* |
| PETRONET | 4 of 12 | FY15 2.8 FY16 5.4 FY17 10.8 FY18 10.2 FY19 14 FY20 -7.9 FY21 10.1 FY22 18.8 FY23 157.3* FY24 138.5* FY25 100.6* FY26 121.2* |
| TATACOMM | 7 of 12 | FY15 -0.7 FY16 0.3 FY17 2.7 FY18 -14.1* FY19 -148.6* FY20 1.8* FY21 -3 FY22 5 FY23 26.8* FY24 16.3* FY25 35* FY26 33.8* |
| SARDAEN | 5 of 12 | FY15 -0.5 FY16 0.5 FY17 -0.5 FY18 -0.8 FY19 -0.4 FY20 -8* FY21 -5.1* FY22 -1.8 FY23 -1.2 FY24 17.1* FY25 22.7* FY26 51.2* |
| HINDWAREAP | 4 of 8 | FY19 0.6 FY20 -0.1 FY21 0.7 FY22 -1.3 FY23 -9* FY24 -9* FY25 -17.8* FY26 -35.2* |

## Test too weak here (the share is under about 0.6 % of PBT, inside the tax-rate rounding): decided on the XBRL years (FY24–FY26) only

| Company | Years with the pattern | Residual by year (₹ Cr) |
|---|---|---|
| SUNPHARMA | 3 of 12 | FY15 -30.6 FY16 6.9 FY17 -25.8 FY18 -32.5* FY19 7.6 FY20 -36.4* FY21 -23.2* FY22 -16.6 FY23 -48.3 FY24 -36.6 FY25 -36.6 FY26 18.6 |
| RELIANCE | 2 of 12 | FY15 -6.6 FY16 33.5 FY17 -192.5 FY18 -1 FY19 73.6 FY20 211.6 FY21 -58.2 FY22 -45.1 FY23 406.1 FY24 765* FY25 736.1* FY26 -312.4 |
| SHRIRAMFIN | 1 of 12 | FY15 5 FY16 3.3 FY17 6.3 FY18 16.6 FY19 7 FY20 1.5 FY21 7.7 FY22 23.8* FY23 23.8 FY24 28.6 FY25 -33.4 FY26 49 |
| LT | 6 of 12 | FY15 -13.7 FY16 -1022* FY17 -357* FY18 -492.5* FY19 -82.6 FY20 47.8 FY21 63.3 FY22 127.5* FY23 -129.7* FY24 -45.9 FY25 -11.2 FY26 -268.2* |
| JKTYRE | 5 of 12 | FY15 4.4* FY16 11.6* FY17 1.1 FY18 -0.1 FY19 -4.5* FY20 -10.1* FY21 -0.1 FY22 0.1 FY23 -0 FY24 -5.4 FY25 -4.4* FY26 4.2 |
