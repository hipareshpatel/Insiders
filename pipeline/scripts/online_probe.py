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
10. the event XBRL lag: each file against its company's nearest earlier announcement flagged hasXbrl;
11. NSE's SAST Reg 31 encumbrance feed (promoter pledges, module 42).

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
            flagged: dict[str, list[datetime]] = collections.defaultdict(list)
            for r in found.get("ann", []):
                if r.get("hasXbrl") and r.get("an_dt"):
                    flagged[r.get("symbol")].append(datetime.strptime(r["an_dt"], _WHEN))
            gaps = []
            for r in found["xbrl"]:
                try:
                    at = datetime.strptime(r["broadcastDateTime"], _WHEN)
                except (KeyError, ValueError):
                    continue
                before = [t for t in flagged.get(r.get("symbol"), []) if t <= at]
                if before:
                    gaps.append((at - max(before)).total_seconds() / 60)
            if not gaps:
                return "no file matched"
            gaps.sort()
            share = lambda m: sum(1 for g in gaps if g <= m)
            return (f"{len(gaps)} of {len(found['xbrl'])} matched; median {gaps[len(gaps) // 2]:.0f} min; "
                    f"<=1 min {share(1)}, <=15 min {share(15)}, <=1 h {share(60)}, <=4 h {share(240)}; "
                    f"max {gaps[-1] / 60:.1f} h")

        step("event XBRL lag after its hasXbrl announcement", lag)

        def pledges():
            got = _list(nse._get(f"{SITE}/api/corporate-pledgedata-sast3132",
                                 {"from_date": week_ago, "to_date": to_day}).json())
            keys = sorted(got[0])[:12] if got else []
            return f"{len(got)} rows over 7 days; fields: {', '.join(keys)}"

        step("SAST Reg 31 encumbrance feed (pledges)", pledges)

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
