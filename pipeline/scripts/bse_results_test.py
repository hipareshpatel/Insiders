"""Owner's test, 25 Oct 2026: BSE results XBRL through the ported adapter (adapters/bse.py) for 8 dual-listed companies,
against NSE's file for the same quarter and basis. Read-only, no AI. Run by hand or from Maintenance (bse-results-test):

    python scripts/bse_results_test.py <out.json>

Every call's status, size and time is printed at the end."""
import json, subprocess, sys, time, logging
logging.basicConfig(level=logging.WARNING)
from bse_intel.adapters import bse as A
from bse_intel.bse import parse_results_archive
from bse_intel import xbrl

class Rec:   # records every call the adapter makes: status, size, time
    def __init__(self, session): self.s, self.log = session, []
    def get(self, url, params=None, timeout=None):
        t = time.time(); r = self.s.get(url, params=params, timeout=timeout)
        self.log.append({"url": url.split("?")[0][-60:], "status": r.status_code, "bytes": len(r.content), "secs": round(time.time()-t, 2)})
        return r
    @property
    def headers(self): return self.s.headers
    def close(self): self.s.close()

import requests
rec = Rec(requests.Session())
c = A.BSEClient(session=rec)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
CK = "/tmp/nse.ck"
def nse(url):
    return subprocess.run(["curl","-s","-b",CK,"-c",CK,"-A",UA,"-H","Referer: https://www.nseindia.com/","--max-time","60",url],capture_output=True).stdout
subprocess.run(["curl","-s","-c",CK,"-A",UA,"-o","/dev/null","https://www.nseindia.com/"])
COS = [("532540","TCS"),("500209","INFY"),("500325","RELIANCE"),("507685","WIPRO"),("500180","HDFCBANK"),("500696","HINDUNILVR"),("532174","ICICIBANK"),("500570","TATAMOTORS")]
KEY = ("revenue","total_income","pbt","pat","eps","interest_earned")
out = []
for scrip, sym in COS:
    row = {"scrip": scrip, "symbol": sym}
    try:
        data = c.get("Result_Arch_ng/w", {"scrip_cd": scrip}, "results_archive", {"scrip": scrip})
        table = json.loads(data).get("Table") or []
        links = parse_results_archive(table)
        row["archive_rows"] = len(table); row["links"] = len(links)
        link = next((l for l in links if l.basis == "CONSOLIDATED"), links[0] if links else None)
        if not link: out.append(row); continue
        row.update(period=link.period, basis=link.basis, url=link.url)
        body = c.fetch_url(link.url, {}, "results_xbrl", file=True)
        res = xbrl.parse(body)
        b = {m.metric: m.value for m in res.metrics if m.period == res.period and m.metric in KEY} if res else {}
        row["bse"] = b; row["bse_period"] = res.period if res else None
    except Exception as e:
        row["error"] = f"{type(e).__name__}: {e}"[:200]; out.append(row); print(json.dumps(row), flush=True)
        if isinstance(e, A.Blocked):
            break   # a refusal is not worked round: stop
        continue
    # NSE: the same quarter and basis
    time.sleep(2)
    lst = json.loads(nse(f"https://www.nseindia.com/api/integrated-filing-results?index=equities&symbol={sym}&type=Integrated%20Filing-%20Financials") or b"{}")
    lst = lst.get("data", []) if isinstance(lst, dict) else lst
    want = "Consolidated" if row.get("basis") == "CONSOLIDATED" else "Standalone"
    n = None
    for r in lst:
        if r.get("consolidated") == want and r.get("xbrl"):
            time.sleep(2); res2 = xbrl.parse(nse(r["xbrl"]))
            if res2 and res2.period == row.get("bse_period"):
                n = {m.metric: m.value for m in res2.metrics if m.period == res2.period and m.metric in KEY}; break
    row["nse"] = n
    row["same"] = None if n is None else all(abs(b[k] - n[k]) < 0.011 for k in b if k in n) and bool(set(b) & set(n))
    out.append(row); print(json.dumps(row), flush=True)
    if row.get("error", "").startswith("Blocked"):
        break   # a refusal is not worked round: stop
json.dump({"companies": out, "calls": rec.log}, open(sys.argv[1], "w"), indent=1)
st = {}
for l in rec.log: st[l["status"]] = st.get(l["status"], 0) + 1
print(json.dumps({"calls": len(rec.log), "status": st, "max_secs": max((l["secs"] for l in rec.log), default=0)}))
