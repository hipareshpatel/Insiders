"""AI usage of one run: provider_usage is a running total per day, so snapshot it before and diff after.
  usage.py snap FILE          write today's totals (and the clock) to FILE
  usage.py diff FILE FILINGS  requests, tokens, failures and 429s since FILE, per provider and per filing"""
import collections
import datetime
import glob
import json
import sqlite3
import sys

db = [p for p in glob.glob(r"D:\Insiders\data\wrangler\v3\d1\miniflare-D1DatabaseObject\*.sqlite") if "metadata" not in p][0]


def totals():
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out = {}
    for day, provider, model, req, tin, tout, fail, rl in c.execute(
            "select day, provider, model, requests, input_tokens, output_tokens, failures, rate_limited from provider_usage"):
        out[f"{day}|{provider}|{model}"] = [req or 0, tin or 0, tout or 0, fail or 0, rl or 0]
    return out


if sys.argv[1] == "snap":
    json.dump({"at": datetime.datetime.now().isoformat(), "totals": totals()}, open(sys.argv[2], "w"))
else:
    before = json.load(open(sys.argv[2]))
    filings = int(sys.argv[3])
    hours = (datetime.datetime.now() - datetime.datetime.fromisoformat(before["at"])).total_seconds() / 3600
    now = totals()
    per = collections.defaultdict(lambda: [0, 0, 0, 0, 0])
    for key, vals in now.items():
        old = before["totals"].get(key, [0, 0, 0, 0, 0])
        _, provider, model = key.split("|")
        for i in range(5):
            per[f"{provider}/{model}"][i] += vals[i] - old[i]
    total = [sum(v[i] for v in per.values()) for i in range(5)]
    print(f"{filings} filings in {hours:.2f} h = {filings / max(hours, 1e-9):.0f} filings/hour")
    print(f"requests {total[0]} ({total[0] / max(filings, 1):.2f} a filing), tokens in {total[1]:,} out {total[2]:,}, "
          f"failures {total[3]}, rate-limited {total[4]}")
    for name, v in sorted(per.items(), key=lambda kv: -kv[1][0]):
        if v[0]:
            print(f"  {name[:60]:60} {v[0]:>5} req  {v[3]:>4} fail  {v[4]:>4} 429  {v[1]:>10,} in")
