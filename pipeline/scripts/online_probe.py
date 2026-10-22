"""Can an online-only pipeline (GitHub + Cloudflare, NSE as the source) get what it needs? Read-only checks of
the NSE addresses an NSE-first pipeline would use, from a GitHub-hosted runner, each reported on its own so one
refusal does not hide the rest. Writes nothing, calls no AI model, needs no secrets.

    python scripts/online_probe.py [--report probe.md]

Checks (docs/SOURCES.md "Event XBRL" and "Timing checked live"):
1. NSE's announcement list, and how many rows carry hasXbrl and a PDF;
2. the event XBRL list (/api/XBRL-announcements) by type, and one order's XBRL read field by field;
3. how many event XBRL files can be joined to their announcement (same symbol, broadcast within 10 minutes);
4. results XBRL (integrated filing): the gap after the board-meeting outcome for a few companies;
5. annual-report XBRL lists, and shareholding XBRL read with the pipeline's own parser;
6. an announcement PDF downloaded and read with the pipeline's own reader;
7. BSE's announcement XBRL page (CorpXbrlGen), which answered a non-Indian cloud address once;
8. a BSE results file on www.bseindia.com/XBRLFILES, BSE's file host rather than its refused API;
9. the two calls BSE's Financial Results page makes for its table (NSTodayResults_ng, Result_Arch_ng);
10. the event XBRL lag: each file against its company's nearest earlier announcement of the same subject;
11. NSE's SAST Reg 31 encumbrance feed (promoter pledges, module 42);
12. where a company's industry can come from on NSE (quote page, announcement rows, index constituent lists);
13. the missing sources (data chain audit §6): bulk and block deals, insider trades (PIT) and where they moved.

Exit status is 0 whatever NSE answers: the report is the result. Run by online-probe.yml.
"""

from __future__ import annotations

import argparse
import collections
import re
import time
from datetime import datetime, timedelta

import httpx

from bse_intel.extract import Document
from bse_intel.nse import SITE, USER_AGENT, NseClient
from bse_intel.timeutil import today_ist
from bse_intel.xbrl import parse as xbrl_parse

# A large IT company, a bank, an NBFC and a PSU: round 3's companies, all on NSE
COMPANIES = ["LTM", "MAHABANK", "CGCL", "NTPC"]
EVENT_TYPES = ["announcements", "para-b", "action"]
BSE_XBRL = ("https://www.bseindia.com/Msource/90D/CorpXbrlGen.aspx"
            "?Bsenewid=8911e55c-f499-4973-9e33-c13c680640b4&Scripcode=503804")
# A results file the owner opened (Cupid Breweries, Q2FY27): BSE's file host, not its api.bseindia.com
BSE_RESULTS_FILE = ("https://www.bseindia.com/XBRLFILES/IFIndasDuplicateUploadDocument/"
                    "Integrated_Finance_Ind_As_512361_17102026233627_IFIndAs.html")
_FACT = re.compile(r"<(in-capmkt:\w+)[^>]*>([^<]{1,200})</")
_WHEN = "%d-%b-%Y %H:%M:%S"

rows: list[tuple[str, str, str, float]] = []


def step(name: str, fn):
    start = time.monotonic()
    try:
        detail = fn()
        rows.append((name, "ok", str(detail), time.monotonic() - start))
        return detail
    except Exception as exc:  # the probe reports every failure and carries on
        rows.append((name, "FAILED", f"{type(exc).__name__}: {exc}"[:300], time.monotonic() - start))
        return None


def _subject(text: str) -> str:
    return " ".join(str(text).lower().replace("&amp;", "&").split())[:30]


# Event XBRL subjects whose announcement goes under other words (measured 11-18 Oct 2026, nearest announcement of
# the symbol): a director change is filed as "Appointment", "Change in Management", "Resignation", "Cessation"...
_SAME_EVENT = {
    "change in directors/kmp/smp/au": ("appointment", "change in management", "resignation", "cessation",
                                       "change in director", "change in company secretary", "change in auditor",
                                       "change in registrar"),
    "pendency of any litigation(s) ": ("pendency of litigation",),
    "key licenses/regulatory approv": ("granting/withdrawal/surrender",),
    "commencement or postponement (": ("commencement",),
}


def _same_event(xbrl_subject: str, announcement_subject: str) -> bool:
    if announcement_subject and xbrl_subject.startswith(announcement_subject):
        return True
    return any(announcement_subject.startswith(a) for a in _SAME_EVENT.get(xbrl_subject, ()))


def _list(data) -> list:
    data = data.get("data", data) if isinstance(data, dict) else data
    return data if isinstance(data, list) else []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report")
    args = parser.parse_args()
    today = today_ist()
    week_ago = (today - timedelta(days=7)).strftime("%d-%m-%Y")
    to_day = today.strftime("%d-%m-%Y")
    found: dict[str, list] = {}

    with NseClient() as nse:
        def announcements():
            found["ann"] = _list(nse._get(f"{SITE}/api/corporate-announcements",
                                          {"index": "equities", "from_date": week_ago, "to_date": to_day}).json())
            ann = found["ann"]
            return (f"{len(ann)} rows over 7 days; hasXbrl {sum(1 for r in ann if r.get('hasXbrl'))}, "
                    f"PDF {sum(1 for r in ann if r.get('attchmntFile'))}")

        step("NSE announcements", announcements)

        found["xbrl"] = []
        for kind in EVENT_TYPES:
            def event_list(kind=kind):
                got = _list(nse._get(f"{SITE}/api/XBRL-announcements", {"index": "equities", "from_date": week_ago,
                                                                        "to_date": to_day, "type": kind}).json())
                found["xbrl"] += got
                top = collections.Counter(r.get("eventType") for r in got).most_common(4)
                return f"{len(got)} files; " + "; ".join(f"{k} {v}" for k, v in top)

            step(f"event XBRL list, type={kind}", event_list)

        def order_fields():
            order = next(r for r in found["xbrl"] if "orders" in str(r.get("eventType", "")).lower()
                         and str(r.get("xbrl") or r.get("attachment") or "").endswith(".xml"))
            body = nse._get(order.get("xbrl") or order["attachment"]).text
            facts = dict(_FACT.findall(body))
            keep = ("NameOfTheCompany", "AmountOfTheOrdersOrContracts", "NameOfTheEntityAwardingTheOrdersOrContracts",
                    "DateOfBaggingOrReceivingOfOrdersOrContracts", "TypeOfAnnouncementAsPerRegulation30ParaBOfPartAOfScheduleIII",
                    "WhetherTheOrderOrContractWouldFallWithinRelatedPartyTransactions")
            return "; ".join(f"{k}={facts.get('in-capmkt:' + k)}" for k in keep)

        step("one order's XBRL, field by field", order_fields)

        def joined():
            ann = [(r.get("symbol"), datetime.strptime(r["an_dt"], _WHEN)) for r in found.get("ann", []) if r.get("an_dt")]
            match = 0
            for r in found["xbrl"]:
                try:
                    at = datetime.strptime(r["broadcastDateTime"], _WHEN)
                except (KeyError, ValueError):
                    continue
                if any(s == r.get("symbol") and abs((t - at).total_seconds()) <= 600 for s, t in ann):
                    match += 1
            return f"{match} of {len(found['xbrl'])} event XBRL files have an announcement of the same symbol within 10 min"

        step("event XBRL joined to its announcement", joined)

        def lag():
            # NSE flags every announcement hasXbrl (515 of 515 on 16 Oct 2026), so the flag cannot pick the PDF an
            # XBRL file belongs to: match the same symbol and the same event (the XBRL's eventType starts with the
            # announcement's desc, e.g. "Bagging/Receiving of orders/contracts", or _SAME_EVENT), the nearest before it
            by_symbol: dict[str, list[tuple[datetime, str]]] = collections.defaultdict(list)
            for r in found.get("ann", []):
                if r.get("an_dt") and r.get("desc"):
                    by_symbol[r.get("symbol")].append((datetime.strptime(r["an_dt"], _WHEN),
                                                       _subject(r["desc"])))
            gaps, any_subject = [], 0
            for r in found["xbrl"]:
                try:
                    at = datetime.strptime(r["broadcastDateTime"], _WHEN)
                except (KeyError, ValueError):
                    continue
                kind = _subject(r.get("eventType") or "")
                before = [t for t, d in by_symbol.get(r.get("symbol"), []) if t <= at]
                any_subject += bool(before)
                same = [t for t, d in by_symbol.get(r.get("symbol"), []) if t <= at and _same_event(kind, d)]
                if same:
                    gaps.append((at - max(same)).total_seconds() / 60)
            if not gaps:
                return f"no file matched on subject ({any_subject} on symbol alone)"
            gaps.sort()
            share = lambda m: sum(1 for g in gaps if g <= m)
            return (f"{len(gaps)} of {len(found['xbrl'])} matched on symbol and subject ({any_subject} on symbol "
                    f"alone); median {gaps[len(gaps) // 2]:.0f} min; <=1 min {share(1)}, <=15 min {share(15)}, "
                    f"<=1 h {share(60)}, <=4 h {share(240)}; max {gaps[-1] / 60:.1f} h")

        step("event XBRL lag after its announcement of the same subject", lag)

        def subjects():
            ann = collections.Counter(_subject(r.get("desc") or "") for r in found.get("ann", []))
            xb = collections.Counter(_subject(r.get("eventType") or "") for r in found["xbrl"])
            missing = [k for k in xb if not any(_same_event(k, d) for d in ann)]
            return f"XBRL subjects with no announcement subject as prefix: {missing[:6]}"

        step("event XBRL subjects against announcement subjects", subjects)

        def pledges():
            got = _list(nse._get(f"{SITE}/api/corporate-pledgedata-sast3132",
                                 {"from_date": week_ago, "to_date": to_day}).json())
            keys = sorted(got[0])[:12] if got else []
            return f"{len(got)} rows over 7 days; fields: {', '.join(keys)}"

        step("SAST Reg 31 encumbrance feed (pledges)", pledges)

        # Missing sources (data chain audit §6, 22 Oct 2026): bulk and block deals returned NSE's bot page to a plain
        # cloud request; insider trades (PIT Reg 7) list nothing after 2 May 2026. Each address is tried on its own.
        for name, path, params in (
                ("bulk deals, 7 days (historical/bulk-deals)", "/api/historical/bulk-deals",
                 {"from": week_ago, "to": to_day}),
                ("block deals, 7 days (historical/block-deals)", "/api/historical/block-deals",
                 {"from": week_ago, "to": to_day}),
                ("large deals snapshot (snapshot-capital-market-largedeal)",
                 "/api/snapshot-capital-market-largedeal", {}),
                ("insider trades, 7 days (corporates-pit)", "/api/corporates-pit",
                 {"index": "equities", "from_date": week_ago, "to_date": to_day}),
                ("insider trades, one company (corporates-pit, RELIANCE)", "/api/corporates-pit",
                 {"index": "equities", "symbol": "RELIANCE"}),
                ("system-driven disclosures, 7 days (corporate-sdd, assumption)", "/api/corporate-sdd",
                 {"index": "equities", "from_date": week_ago, "to_date": to_day})):
            def source(path=path, params=params):
                r = nse._get(f"{SITE}{path}", params)
                if "json" not in r.headers.get("content-type", ""):
                    return f"HTTP {r.status_code} {r.headers.get('content-type', '')}: {r.text[:80]!r}"
                data = r.json()
                if isinstance(data, dict) and not isinstance(data.get("data"), list):
                    sizes = {k: len(v) for k, v in data.items() if isinstance(v, list)}
                    first = {k: v[0] for k, v in data.items() if isinstance(v, list) and v}
                    return f"HTTP 200, lists {sizes or sorted(data)[:8]}; first rows {str(first)[:900]}"
                got = _list(data)
                latest = max((str(x.get("date") or x.get("BD_DT_DATE") or x.get("acqtoDt") or x.get("intimDt") or "")
                              for x in got), default="")
                return f"HTTP 200, {len(got)} rows; fields {sorted(got[0])[:10] if got else []}; latest {latest[:20]}"

            step(f"Missing source: {name}", source)

        # The owner's note (22 Oct 2026): the insider-trading page sets the cookies its own API call expects, so open
        # it first, then ask for 1 Sep - today (equities, SME, and the CSV export)
        def pit_page():
            r = nse._client.get(f"{SITE}/companies-listing/corporate-filings-insider-trading",
                                headers={"Accept": "text/html"})
            return f"HTTP {r.status_code}, cookies now {sorted(nse._client.cookies.keys())[:8]}"

        step("PIT: the insider-trading page first", pit_page)
        for index, extra in (("equities", {}), ("sme", {}), ("equities", {"csv": "true"})):
            def pit_after_page(index=index, extra=extra):
                r = nse._client.get(f"{SITE}/api/corporates-pit", params={
                    "index": index, "from_date": "01-09-2026", "to_date": to_day, **extra},
                    headers={"Referer": f"{SITE}/companies-listing/corporate-filings-insider-trading"})
                kind = r.headers.get("content-type", "")
                if "json" in kind:
                    got = _list(r.json())
                    latest = max((str(x.get("intimDt") or x.get("date") or "") for x in got), default="")
                    return f"HTTP {r.status_code} JSON, {len(got)} rows; latest {latest[:20]}"
                lines = r.text.strip().splitlines()
                return f"HTTP {r.status_code} {kind}, {len(lines)} lines; first {lines[:2]!r:.200}"

            step(f"PIT after the page: {index}{' csv' if extra else ''}, 1 Sep - today", pit_after_page)

        for symbol in COMPANIES:
            def results_gap(symbol=symbol):
                filings = _list(nse._get(f"{SITE}/api/integrated-filing-results", {"index": "equities",
                                                                                   "symbol": symbol}).json())
                outcome = _list(nse._get(f"{SITE}/api/corporate-announcements", {
                    "index": "equities", "symbol": symbol,
                    "from_date": (today - timedelta(days=120)).strftime("%d-%m-%Y"), "to_date": to_day}).json())
                outs = [datetime.strptime(r["an_dt"], _WHEN) for r in outcome
                        if "outcome of board" in str(r.get("desc", "")).lower()]
                gaps = []
                for f in filings:
                    if "Financials" not in str(f.get("type", "")) or not f.get("broadcast_Date"):
                        continue
                    at = datetime.strptime(f["broadcast_Date"], _WHEN)
                    before = [o for o in outs if o <= at and at - o < timedelta(days=2)]
                    if before:
                        gaps.append(f"{f.get('qe_Date')} {f.get('consolidated')}: {at - max(before)}")
                return "; ".join(gaps[:4]) or f"{len(filings)} filings, none matched to an outcome"

            step(f"results XBRL after the outcome, {symbol}", results_gap)

        for symbol in COMPANIES[:2]:
            step(f"annual-report XBRL list, {symbol}", lambda symbol=symbol: "; ".join(
                f"FY{f.to_year} {f.basis} {f.filed_at}" for f in nse.annual_reports(symbol)[:4]))

        for symbol in COMPANIES[2:]:
            def shareholding(symbol=symbol):
                filings = nse.shareholding(symbol)[:1]
                data = nse.download(filings[0].xbrl_url) if filings else None
                parsed = xbrl_parse(data) if data else None
                return (f"{filings[0].period} filed {filings[0].filed_at[:10]}: {parsed.table()}" if parsed
                        else f"{len(filings)} filings, no XBRL read")

            step(f"shareholding XBRL read by the pipeline, {symbol}", shareholding)

        def pdf_read():
            row = next(r for r in found.get("ann", []) if str(r.get("attchmntFile", "")).endswith(".pdf"))
            body = nse._get(row["attchmntFile"]).content
            doc = Document(body)
            text = doc.select_text(4000, [])
            return f"{row.get('symbol')}: {len(body):,} bytes, {doc.page_count} pages, {len(text)} characters read"

        step("NSE announcement PDF read by the pipeline", pdf_read)

        # Company master from NSE (owner, 2026-10-19: everything on NSE): where a new listing's industry can come from
        def quote_industry():
            got = []
            for symbol in ("ITC", "TATATECH"):
                r = nse._get(f"{SITE}/api/quote-equity", {"symbol": symbol}).json()
                got.append(f"{symbol}: {r.get('industryInfo')} listed {(r.get('info') or {}).get('listingDate')} "
                           f"issued {(r.get('securityInfo') or {}).get('issuedSize')}")
            return "; ".join(got)

        step("NSE quote: industry of a company (/api/quote-equity)", quote_industry)

        def sm_industry():
            ann = found.get("ann", [])
            filled = collections.Counter(r.get("smIndustry") for r in ann if r.get("smIndustry"))
            return (f"{sum(filled.values())} of {len(ann)} announcements carry smIndustry; "
                    f"{len({r.get('symbol') for r in ann if r.get('smIndustry')})} companies; top {filled.most_common(4)}")

        step("announcement rows' own industry field (smIndustry)", sm_industry)

        for name in ("ind_niftytotalmarket_list.csv", "ind_niftymicrocap250_list.csv"):
            def index_list(name=name):
                text = nse._get(f"https://nsearchives.nseindia.com/content/indices/{name}").text
                lines = [l for l in text.splitlines() if l.strip()]
                return f"{len(lines) - 1} companies; header {lines[0][:120]!r}; first {lines[1][:120]!r}"

            step(f"NSE index constituents with industry ({name})", index_list)

    def bse_xbrl():
        r = httpx.get(BSE_XBRL, headers={"User-Agent": USER_AGENT}, timeout=30)
        tags = re.findall(r"<in-bse-co:(\w+)[ >]", r.text)
        return f"HTTP {r.status_code}, {len(r.content)} bytes, fields: {', '.join(tags[:8])}"

    step("BSE announcement XBRL page (CorpXbrlGen)", bse_xbrl)

    def bse_results_file():
        r = httpx.get(BSE_RESULTS_FILE, headers={"User-Agent": USER_AGENT}, timeout=40)
        figures = re.findall(r"<ix:nonfraction[^>]*?name=.([\w:-]+).[^>]*>([^<]*)<", r.text, re.I)
        names = dict(re.findall(r"<ix:nonnumeric[^>]*?name=.in-capmkt:(NameOfTheCompany|ScripCode).[^>]*>([^<]*)<",
                                r.text, re.I))
        cost = next((v for n, v in figures if n.endswith(":FinanceCosts")), None)
        return (f"HTTP {r.status_code}, {len(r.content):,} bytes, {len(figures)} tagged figures; "
                f"{names.get('NameOfTheCompany')} ({names.get('ScripCode')}), finance costs {cost}")

    step("BSE results file on www.bseindia.com/XBRLFILES (owner's link)", bse_results_file)

    # The Financial Results page (/corporates/comp_resultsnew) loads its table from these two calls (read from the
    # page's own JS, 2026-10-18): the recent list across companies, and one company's archive (?Code=)
    bse_headers = {"User-Agent": USER_AGENT, "Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com",
                   "Accept": "application/json, text/plain, */*"}
    # The page with the filter form (Segment, Industry, Broadcast Period, Submit; owner's screenshot) calls
    # Corp_FinanceResult_ng_new for the table and Corp_Archive_Wthxml_ng_new for the announcements beside it. The
    # page's defaults: FlagDur 1 = Today, segment C = Equity, every industry and result period.
    for name, url in (("filter form, today, all companies (Corp_FinanceResult_ng_new)",
                       "https://api.bseindia.com/BseIndiaAPI/api/Corp_FinanceResult_ng_new/w"
                       "?SCRIP_CD=&FlagDur=1&HFQ=&ISUBGROUP_CODE=&segment=C"),
                      ("filter form, last week, one company (Corp_FinanceResult_ng_new, 512361)",
                       "https://api.bseindia.com/BseIndiaAPI/api/Corp_FinanceResult_ng_new/w"
                       "?SCRIP_CD=512361&FlagDur=7&HFQ=&ISUBGROUP_CODE=&segment=C"),
                      ("announcements panel (Corp_Archive_Wthxml_ng_new)",
                       "https://api.bseindia.com/BseIndiaAPI/api/Corp_Archive_Wthxml_ng_new/w"
                       "?SCRIP_CD=&CATNAME=Result&FROMDT=&TODT=&PER=D&SEGMENT=A"),
                      ("recent results, all companies (NSTodayResults_ng)",
                       "https://api.bseindia.com/BseIndiaAPI/api/NSTodayResults_ng/w"),
                      ("one company's results archive (Result_Arch_ng, 512361)",
                       "https://api.bseindia.com/BseIndiaAPI/api/Result_Arch_ng/w?scrip_cd=512361")):
        def bse_results_list(url=url):
            r = httpx.get(url, headers=bse_headers, timeout=40)
            if r.status_code != 200 or "json" not in r.headers.get("content-type", ""):
                return f"HTTP {r.status_code} {r.headers.get('content-type', '')}: {r.text[:80]!r}"
            table = (r.json() or {}).get("Table") or []
            links = sum(1 for row in table if row.get("stand_xbrl_link") or row.get("conso_xbrl_link"))
            return f"HTTP 200, {len(table)} rows, {links} with an XBRL link; first: {str(table[:1])[:160]}"

        step(f"BSE Financial Results page: {name}", bse_results_list)

    lines = ["| check | result | detail | s |", "|---|---|---|---|"]
    lines += [f"| {n} | {s} | {d.replace('|', '/')} | {t:.1f} |" for n, s, d, t in rows]
    report = "## Online-only probe (NSE from a GitHub-hosted runner)\n\n" + "\n".join(lines) + "\n"
    print(report)
    if args.report:
        with open(args.report, "a", encoding="utf-8") as fh:
            fh.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
