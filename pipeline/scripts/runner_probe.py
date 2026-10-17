"""Can the whole pipeline run from a GitHub-hosted runner? Read-only: every BSE and NSE address the
pipeline uses, through the pipeline's own clients, each step reported on its own so one refusal does
not hide the rest. Writes nothing and calls no AI model.

    python scripts/runner_probe.py [--report probe.md]

Exit status is 0 whatever BSE or NSE answer: the report is the result. Run by runner-probe.yml.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import timedelta

from bse_intel.bse import BseClient, fetch_scrip_list, industry_path
from bse_intel.extract import Document
from bse_intel.nse import NseClient
from bse_intel.timeutil import today_ist

# A large company, an NBFC (BSE's archive serves its template nothing), and a small company.
COMPANIES = [("500325", "RELIANCE"), ("500034", "BAJFINANCE"), ("506525", None)]

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report")
    args = parser.parse_args()
    today = today_ist()

    with BseClient() as bse:
        filings: list = []

        def announcements():
            for day in (today, today - timedelta(days=1), today - timedelta(days=3)):
                filings.extend(bse.announcements(day, max_pages=2))
            with_pdf = sum(1 for f in filings if f.pdf_url)
            return f"{len(filings)} announcements over 3 days, {with_pdf} with an attachment"

        step("BSE announcements (api.bseindia.com)", announcements)

        pdfs = [f for f in filings if f.pdf_url][:5]
        for f in pdfs:
            def attachment(f=f):
                body = bse.download(f.pdf_url)
                if not body:
                    return "no file (404 on AttachLive and AttachHis)"
                doc = Document(body)
                chars = sum(len(doc.page_text(i)) for i in range(doc.page_count))
                return f"{len(body):,} bytes, {doc.page_count} pages, {chars:,} characters of text"

            step(f"BSE attachment {f.news_id[:12]} ({f.filing_date})", attachment)

        def old_attachment():
            old = [f for f in bse.announcements(today - timedelta(days=200), max_pages=1) if f.pdf_url][:1]
            if not old:
                return "no attachment listed that day"
            body = bse.download(old[0].pdf_url)
            return f"{len(body or b''):,} bytes from {old[0].filing_date} (AttachHis path)"

        step("BSE attachment, 200 days old", old_attachment)

        for scrip, _ in COMPANIES:
            links = step(f"BSE results archive {scrip}", lambda s=scrip: bse.results_xbrl(s))
            if links:
                rows[-1] = rows[-1][:2] + (f"{len(links)} XBRL files, newest {links[0].period}",) + rows[-1][3:]
                step(f"BSE results XBRL {scrip} {links[0].period}",
                     lambda u=links[0].url: f"{len(bse.download(u, max_bytes=8_000_000) or b''):,} bytes")
            step(f"BSE quote header {scrip}",
                 lambda s=scrip: industry_path(bse.scrip_header(s)) or "answered, no industry")

        step("BSE scrip list (sync-companies)", lambda: f"{len(fetch_scrip_list(bse)):,} active equity scrips")

    with NseClient() as nse:
        def warm():
            r = nse._client.get("https://www.nseindia.com/", headers={"Accept": "text/html"})
            return f"HTTP {r.status_code} (the client treats the home page as optional)"

        step("NSE home page", warm)
        nse._warmed = True
        for _, symbol in COMPANIES:
            if not symbol:
                continue
            found = step(f"NSE Integrated Filing list {symbol}", lambda s=symbol: nse.integrated_filings(s))
            if found:
                rows[-1] = rows[-1][:2] + (f"{len(found)} quarters, newest filed {found[0].filed_at}",) + rows[-1][3:]
                step(f"NSE Integrated Filing XBRL {symbol}",
                     lambda u=found[0].xbrl_url: f"{len(nse.download(u) or b''):,} bytes of XML")
            step(f"NSE results list {symbol}", lambda s=symbol: f"{len(nse.financial_results(s))} filings")
            step(f"NSE shareholding {symbol}", lambda s=symbol: f"{len(nse.shareholding(s))} quarters")

    def yahoo():
        import yfinance as yf
        data = yf.download(["RELIANCE.BO", "BAJFINANCE.NS"], period="5d", progress=False, group_by="ticker")
        return f"{len(data)} days of prices"

    step("Yahoo prices", yahoo)

    failed = sum(1 for r in rows if r[1] != "ok")
    lines = [f"## Runner probe: {len(rows) - failed} of {len(rows)} steps answered", "",
             "| Step | Result | Detail | Seconds |", "|---|---|---|---|"]
    lines += [f"| {n} | {s} | {d.replace('|', '/')} | {t:.1f} |" for n, s, d, t in rows]
    report = "\n".join(lines) + "\n"
    print(report)
    if args.report:
        with open(args.report, "a", encoding="utf-8") as fh:
            fh.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
