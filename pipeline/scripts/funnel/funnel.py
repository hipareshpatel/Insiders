"""Stage-by-stage funnel of announcements for the smoke-test companies (read-only analysis).

Inputs (none of them is modified):
  - d1.sqlite: a byte copy of the local D1 database (copy_db() makes it from data/wrangler/v3/d1/...)
  - noise/*.json: the noise/ objects of local R2, fetched by fetch_noise.py through the local site's API
  - logs_summary.json: from parse_logs.py (run logs' stats blocks and discovery lines)
  - docs/audit/card-audit-2026-10-16.json (round 0) and docs/audit/round-1.json (round 1): audit verdicts
  - data/text_cache: the pipeline's cached filing text, for the held-card number check
Output: data/funnel/funnel.md and funnel_data.json (data/ is not committed).
Run from the repository root, the local site running: fetch_noise.py, parse_logs.py, then funnel.py.
"""
from __future__ import annotations

import bisect
import collections
import glob
import gzip
import json
import pathlib
import random
import re
import shutil
import sqlite3

HERE = pathlib.Path(__file__).resolve().parents[3] / "data" / "funnel"   # outputs and fetched inputs; data/ is not committed
HERE.mkdir(parents=True, exist_ok=True)
D1_DIR = pathlib.Path(r"D:\Insiders\data\wrangler\v3\d1\miniflare-D1DatabaseObject")
TEXT_CACHE = pathlib.Path(r"D:\Insiders\data\text_cache")
AUDIT0 = pathlib.Path(r"D:\Insiders\docs\audit\card-audit-2026-10-16.json")
AUDIT1 = pathlib.Path(r"D:\Insiders\docs\audit\round-1.json")
NAMED = ["506525", "532776", "505192", "500672", "530019"]
CALENDAR_RULES = {"board meeting intimation", "AGM notice", "record date / book closure"}
RNG = random.Random(20261018)


def copy_db() -> pathlib.Path:
    src = [p for p in D1_DIR.glob("*.sqlite") if p.name != "metadata.sqlite"]
    assert len(src) == 1, src
    dst = HERE / "d1.sqlite"
    shutil.copyfile(src[0], dst)
    return dst


# ---------------------------------------------------------------- classification

def dup_kind(reason: str) -> str:
    r = reason or ""
    if "(exact match)" in r:
        return "exact text repeat"
    if "(near match)" in r:
        return "near text repeat"
    if "same results quarter" in r:
        return "same results quarter (D20)"
    if "pass 1 named" in r:
        return "same event, another document (pass 1 named it)"
    if "checked before pass 2" in r:
        return "same event, another document (repeat check before pass 2)"
    if "in other words" in r:
        return "same event, in other words (after pass 2)"
    if "same timeline event" in r:
        return "same timeline event"
    return "other duplicate"


def dup_target(reason: str) -> str | None:
    m = re.search(r"duplicate of ([0-9a-f-]{36})", reason or "")
    return m[1] if m else None


PASS1_CLASSES = [
    ("analyst / investor meet, media interview", r"analyst|investor (meet|conference|briefing)|conference|interaction with|media appearance|panel|investor outreach|institutional visit|industry discussion"),
    ("trading window / insider-trading code", r"trading window|insider trading|pit\b"),
    ("BRSR / ESG rating", r"brsr|esg"),
    ("AGM / EGM / postal ballot procedure", r"\bagm\b|\begm\b|postal ballot|annual general|voting result"),
    ("auditor / director / KMP / SMP change", r"auditor|director|\bwtd\b|\bmd\b|ceo|cfo|ciro|chro|smp|senior management|kmp|key managerial|committee|company secretary|tenure|avp|head|management"),
    ("award, recognition, press release", r"award|honou?r|recognition|certification|anniversary|foundation day|exhibition|press release|advocacy|campaign"),
    ("tax / GST / penalty / regulatory order", r"gst|tax|penalty|regulatory|order|labeling"),
    ("RTA / address / name / website change, share transfer admin", r"rta|registrar|address|name|website|domain|re-?lodg|transfer request|physical shares|symbol"),
    ("compliance report / certificate / disclosure", r"complian|certificate|report|disclosure|deviation|large corporate|intimation|notice|procedur|dissemination|reminder|communication"),
]


def pass1_class(reason: str, headline: str) -> str:
    text = f"{reason} || {headline}".lower()
    for name, pat in PASS1_CLASSES:
        if re.search(pat, text):
            return name
    return "other"


HOLD_CLASSES = [
    ("headline figure not found", "Headline figures not found"),
    ("number not found in filing or memory", "Numbers not found in the filing text"),
    ("quantified-impact math mismatch", "Quantified impact"),
    ("claim not supported", "Claim not supported"),
    ("figure out of scale / wrong column", "Figures that do not fit"),
    ("quote does not carry the figure", "Give each fact the filing's own sentence"),
    ("garbled scan", "text layer is garbled"),
    ("human hold", "Held after review"),
]


def hold_classes(issues: list[str]) -> list[str]:
    out = []
    for issue in issues or []:
        for name, prefix in HOLD_CLASSES:
            if prefix in issue:
                out.append(name)
                break
        else:
            out.append("other")
    return out


def ungrounded_tokens(issues: list[str]) -> list[str]:
    toks = []
    for issue in issues or []:
        if issue.startswith("Numbers not found in the filing text or company memory:"):
            body = issue.split(":", 1)[1]
            toks += [t.strip() for t in re.split(r",\s(?=\S)", body) if t.strip()]
    # "1,000" is split above only where a comma is followed by a space: keep Indian digit groups whole
    return toks


# ---------------------------------------------------------------- number checks on held cards

NUM = re.compile(r"(?<![\w.])\(?-?\d{1,3}(?:,\d{2,3})*(?:\.\d+)?\)?(?![\w])|(?<![\w.])\(?-?\d+(?:\.\d+)?\)?(?![\w])")


def parse_num(s: str) -> float | None:
    s = s.strip()
    neg = s.startswith("(") and s.endswith(")") or s.startswith("-")
    s = s.strip("()").lstrip("-").replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def filing_numbers(news_id: str) -> list[float] | None:
    safe = "".join(ch for ch in news_id if ch.isalnum() or ch in "-_")[:80]
    path = TEXT_CACHE / safe[:2] / f"{safe}.json.gz"
    if not path.exists():
        return None
    data = json.loads(gzip.decompress(path.read_bytes()))
    texts: list[str] = []

    def walk(x):
        if isinstance(x, str):
            texts.append(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk({k: v for k, v in data.items() if k not in ("v", "error", "has_image")})
    nums = set()
    for t in texts:
        for m in NUM.finditer(t):
            v = parse_num(m[0])
            if v is not None and abs(v) >= 0.01:
                nums.add(abs(v))
    return sorted(nums)


def token_value(tok: str) -> tuple[float, int, str] | None:
    """(value, decimals, kind) of an ungrounded token."""
    t = tok.replace("₹", "").replace("Rs", "").strip()
    if "=" in t:
        t = t.split("=", 1)[1]
    kind = "percent" if t.endswith("%") else "bps" if t.endswith("bps") else "multiple" if re.search(r"\dx$", t) else "amount/count"
    t = re.sub(r"(%|bps|x|Cr|cr|crore|lakh)$", "", t).strip()
    m = re.fullmatch(r"-?[\d,]+(?:\.(\d+))?", t)
    if not m:
        return None
    v = parse_num(t)
    return (abs(v), len(m[1] or ""), kind) if v is not None else None


def any_in(sorted_vals: list[float], lo: float, hi: float) -> bool:
    i = bisect.bisect_left(sorted_vals, lo)
    return i < len(sorted_vals) and sorted_vals[i] <= hi


def explain(value: float, decimals: int, kind: str, nums: list[float]) -> str | None:
    """How a figure absent from the filing could still come from it: another unit, or a sum, difference,
    ratio or change of two of its figures (at the token's own rounding)."""
    h = 0.5 * 10 ** -decimals + 1e-9
    if kind in ("amount/count", "multiple"):
        for scale, label in ((0.01, "lakh->crore"), (0.1, "million->crore"), (1e-7, "rupees->crore"), (100, "crore->lakh"), (10, "crore->million")):
            if any_in(nums, (value - h) / scale, (value + h) / scale):
                return f"same figure in another unit ({label})"
        for a in nums:
            if a >= value + h:
                break
            if any_in(nums, value - h - a, value + h - a):
                return "sum of two filing figures"
        for a in nums:
            if any_in(nums, a - value - h, a - value + h) and a - value > 0:
                return "difference of two filing figures"
    if kind in ("percent", "bps", "multiple"):
        v = value / 100 if kind == "bps" else value
        hv = h / 100 if kind == "bps" else h
        for b in nums:
            if b < 0.5:
                continue
            if kind == "multiple":
                if any_in(nums, b * (v - hv), b * (v + hv)):
                    return "ratio of two filing figures"
                continue
            if any_in(nums, b * (v - hv) / 100, b * (v + hv) / 100):
                return "share of one filing figure in another"
            if any_in(nums, b * (1 + (v - hv) / 100), b * (1 + (v + hv) / 100)) or any_in(nums, b * (1 - (v + hv) / 100), b * (1 - (v - hv) / 100)):
                return "change between two filing figures"
            if kind == "percent" and any_in(nums, b - v - hv, b - v + hv):
                return "difference of two filing percentages (pp)"
            if kind == "bps" and any_in(nums, b - value / 100 - hv, b - value / 100 + hv):
                return "difference of two filing percentages (bps)"
    return None


CARD_FIELDS = ("headline", "takeaway", "core_catalyst", "what_happened", "why_it_matters", "key_numbers",
               "notable_changes", "deal_value", "results", "timeline_entry")


def card_grounded_numbers(card: dict, filing_nums: list[float], exclude: float) -> list[float]:
    """Figures the card itself states that are also in the filing (exact value), minus the token itself."""
    text = json.dumps({k: card.get(k) for k in CARD_FIELDS}, ensure_ascii=False)
    have = set(filing_nums)
    out = set()
    for m in NUM.finditer(text):
        v = parse_num(m[0])
        if v is not None and abs(v) >= 0.01 and abs(v) in have and abs(abs(v) - exclude) > 1e-9:
            out.add(abs(v))
    return sorted(out)


DENOMINATORS = (("market cap", r"market cap|m-?cap"), ("TTM / annual revenue", r"\bttm\b|trailing|annual revenue|fy\d\d revenue"),
                ("net worth", r"net worth|networth"), ("net debt / gross debt", r"net debt|gross debt|net cash|borrowings"),
                ("order book", r"order book"))


def figure_context(card: dict, token: str) -> str:
    """Which company-level denominator the card names next to an unfound figure: the scale block the Pass 2
    prompt is given (signals.scale_block: market cap, TTM revenue, net worth, net debt, order book)."""
    if "=" in token:
        key = token.split("=")[0]
        return "market cap" if "market_cap" in key else "formula input"
    text = json.dumps({k: card.get(k) for k in CARD_FIELDS + ("quantified_impact",)}, ensure_ascii=False).lower()
    t = token.lower()
    i = text.find(t)
    found = i >= 0
    while i >= 0:
        window = text[max(0, i - 80): i + len(t) + 40]
        for name, pat in DENOMINATORS:
            if re.search(pat, window):
                return name
        i = text.find(t, i + 1)
    return "elsewhere on the card" if found else "not located on the card"


# ---------------------------------------------------------------- report helpers

def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}%" if b else "-"


def md_table(header: list[str], rows: list[list]) -> str:
    def numeric(i):
        vals = [str(r[i]).replace("*", "").strip() for r in rows if i < len(r) and str(r[i]).strip()]
        return bool(vals) and all(re.fullmatch(r"-?[\d,.]+%?( of [\w ]+)?|-", v) for v in vals)
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---:" if i and numeric(i) else "---" for i in range(len(header))) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def clean(s: str | None, n: int = 110) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    s = re.sub(r"\s+", " ", s).strip().replace("|", "/")
    return s if len(s) <= n else s[: n - 1] + "…"


def examples(rows: list[dict], k: int = 3) -> list[dict]:
    """k rows, one per company where possible, chosen with a fixed seed."""
    rows = sorted(rows, key=lambda r: r["news_id"])
    RNG.shuffle(rows)
    picked, seen = [], set()
    for r in rows:
        if r.get("company_name") not in seen:
            picked.append(r)
            seen.add(r.get("company_name"))
        if len(picked) == k:
            return picked
    for r in rows:
        if r not in picked:
            picked.append(r)
        if len(picked) == k:
            break
    return picked


def ex_table(rows: list[dict], reason_key=lambda r: r.get("reason")) -> str:
    return md_table(["news_id", "company", "filed", "headline", "reason / detail"],
                    [[r["news_id"][:8], clean(r.get("company_name"), 28), (r.get("filed_at") or "")[:10],
                      clean(r.get("headline"), 95), clean(reason_key(r), 150)] for r in rows])


def logs_section() -> str:
    runs = json.load(open(HERE / "logs_summary.json", encoding="utf-8"))
    lines = ["\n## Appendix: run logs cross-check\n"]
    disc = [r for r in runs if r["disc_new"]]
    with_stats = [r for r in runs if r["stats"]]
    lines.append(f"{len(runs)} logs read ({sum(1 for r in runs if r['log'].startswith('backfill'))} backfill-companies, "
                 f"{sum(1 for r in runs if r['log'].startswith('process'))} process, the rest other commands); D:\\backfill.log is absent. "
                 f"Only {len(with_stats)} logs end with the JSON stats block: every backfill-companies run but the last was stopped "
                 "before it printed one, so the per-stage counters cannot be rebuilt from the logs. Discovery is logged per day "
                 "(\"discovered <day>: N new filings (Q queued, M noise)\"), and a news_id already in the ledger or the day's noise "
                 "file is skipped, so those lines can be summed:\n")
    lines.append(md_table(["log", "new", "queued", "noise"], [[r["log"], r["disc_new"], r["disc_queued"], r["disc_noise"]] for r in disc]
                          + [["**sum**", sum(r["disc_new"] for r in disc), sum(r["disc_queued"] for r in disc), sum(r["disc_noise"] for r in disc)]]))
    lines.append("\nThe first log (02:36) already found nothing new for the first five companies, so their discovery predates every "
                 "log here; the 03:16 run discovered the second five (1,038: 623 queued, 415 noise), and later runs added 81 (80 "
                 "noise - filings re-discovered after a reset or a rule change put them under a drop rule - and 1 new filing on "
                 "2026-10-16). The ledger itself is the de-duplicated count: 1,089 filing rows + 772 noise rows, no news_id in "
                 "both, and the 376 noise objects' rows equal the sum of the 376 `noise_count:<day>` keys in D1's kv table (772). "
                 "Per-run processing counters from the logs that have them:\n")
    keys = ["analyzed", "not_material", "pass1_rejected", "timeline_only", "duplicates", "failed", "deferred", "needs_review",
            "second_opinions", "corrected"]
    lines.append(md_table(["log", *keys, "stopped"], [[r["log"], *[r["stats"].get(k, 0) for k in keys],
                                                         clean(r["stats"].get("stopped_reason") or "", 60)] for r in with_stats]))
    lines.append("\nThese are re-runs of the 20-filing loop and small batches (the same filings read again), so they are not "
                 "added to the funnel: a filing's current row in D1 is its last outcome.")
    return "\n".join(lines)


# ---------------------------------------------------------------- main

def main() -> None:
    db = sqlite3.connect(copy_db())
    db.row_factory = sqlite3.Row
    F = {r["news_id"]: dict(r) for r in db.execute("SELECT * FROM filings")}
    C = {r["news_id"]: dict(r) for r in db.execute("SELECT * FROM cards")}
    for c in C.values():
        c["j"] = json.loads(c["card_json"])
    noise = []
    for f in sorted(glob.glob(str(HERE / "noise" / "*.json"))):
        j = json.load(open(f, encoding="utf-8"))
        noise += [dict(zip(j["fields"], r)) for r in j["rows"]]
    assert not set(F) & {n["news_id"] for n in noise}, "noise and ledger overlap"

    # The smoke-test set: the five named scrips plus the five others with the most filing rows.
    per_co = collections.Counter(f["scrip_code"] for f in F.values())
    others = [s for s, _ in per_co.most_common() if s not in NAMED][:5]
    SMOKE = NAMED + others
    names = {f["scrip_code"]: f["company_name"] for f in F.values()}
    names.update({n["scrip_code"]: n["company_name"] for n in noise})
    all_scrips = set(per_co) | {n["scrip_code"] for n in noise}

    data = {}
    report: list[str] = []

    def funnel(scope: set[str]) -> dict:
        nz = [n for n in noise if n["scrip_code"] in scope]
        fl = [f for f in F.values() if f["scrip_code"] in scope]
        st = collections.defaultdict(list)
        for n in nz:
            r = n["reason"] or ""
            if r.startswith("outside universe"):
                st["outside"].append(n)
            elif "(no XBRL file)" in r:
                st["xbrl_nofile"].append(n)
            else:
                st["rule"].append(n)
        for f in fl:
            s, r = f["status"], f["reason"] or ""
            if s == "DUPLICATE":
                st["dup"].append(f)
            elif s == "NOT_MATERIAL":
                st["nm_p1" if r.startswith("pass1:") else "nm_tl" if r.startswith("timeline only:") else
                   "nm_p2" if r.startswith("pass2:") else "nm_xbrl" if r.startswith("xbrl:") else "nm_other"].append(f)
            elif s == "FAILED":
                st["failed"].append(f)
            elif s == "PENDING":
                st["pending"].append(f)
            elif s == "ANALYZED":
                c = C.get(f["news_id"])
                if c is None:
                    st["analyzed_nocard"].append(f)
                else:
                    st["held" if c["held"] else "published"].append(f)
                    if c["needs_review"]:
                        st["needs_review"].append(f)
        st["_noise"], st["_filings"] = nz, fl
        return st

    S = funnel(set(SMOKE))
    A = funnel(all_scrips)
    data["smoke"] = SMOKE

    # ------------------------------------------------------------ A. funnel table
    def funnel_rows(st) -> list[list]:
        disc = len(st["_noise"]) + len(st["_filings"])
        rows = []
        remaining = disc
        rows.append(["**Announcements discovered** (R2 noise rows + D1 filing rows)", disc, "", ""])

        def loss(label, n, sub=False):
            nonlocal remaining
            rows.append([("&nbsp;&nbsp;&nbsp;- " if sub else "- ") + label, n, pct(n, remaining) if not sub else "", ""])

        by_rule = collections.Counter(n["reason"] for n in st["rule"])
        drop = sum(v for k, v in by_rule.items() if k not in CALENDAR_RULES)
        cal = sum(v for k, v in by_rule.items() if k in CALENDAR_RULES)
        rows.append([f"- dropped by rule (DROP {drop}, CALENDAR {cal})", len(st["rule"]), pct(len(st["rule"]), remaining), ""])
        for k, v in by_rule.most_common():
            rows.append([f"&nbsp;&nbsp;&nbsp;{'CALENDAR' if k in CALENDAR_RULES else 'DROP'}: {k}", v, pct(v, len(st["rule"])) + " of drops", ""])
        remaining -= len(st["rule"])
        rows.append(["- shareholding without an XBRL file", len(st["xbrl_nofile"]), pct(len(st["xbrl_nofile"]), remaining), ""])
        remaining -= len(st["xbrl_nofile"])
        rows.append(["- outside universe (market cap floor)", len(st["outside"]), pct(len(st["outside"]), remaining), ""])
        remaining -= len(st["outside"])
        nrows = len(st["_filings"])
        processed = nrows - len(st["pending"]) - len(st["failed"])
        rows.append([f"**Filing rows (D1 ledger)**", nrows, pct(nrows, disc) + " of discovered", "100% (of rows)"])
        remaining = nrows
        dups = st["dup"]
        rows.append(["- duplicates", len(dups), pct(len(dups), remaining), pct(len(dups), nrows)])
        for k, v in collections.Counter(dup_kind(f["reason"]) for f in dups).most_common():
            rows.append([f"&nbsp;&nbsp;&nbsp;{k}", v, pct(v, len(dups)) + " of dups", ""])
        remaining -= len(dups)
        for key, label in (("nm_p1", "pass 1: not material"), ("nm_tl", "timeline only (a line in memory, no card)"),
                           ("nm_p2", "pass 2: not material"), ("nm_xbrl", "XBRL shareholding to memory"),
                           ("nm_other", "not material, other reason")):
            if key in ("nm_xbrl", "nm_other") and not st[key]:
                continue
            rows.append([f"- {label}", len(st[key]), pct(len(st[key]), remaining), pct(len(st[key]), nrows)])
            remaining -= len(st[key])
        ff, pp = st["failed"], st["pending"]
        deferred = [f for f in pp if (f["last_error"] or "").startswith("deferred")]
        rows.append(["- failed (attempted, error)", len(ff), pct(len(ff), remaining), pct(len(ff), nrows)])
        remaining -= len(ff)
        rows.append([f"- still pending (never attempted {len(pp) - len(deferred)}, deferred {len(deferred)})", len(pp),
                     pct(len(pp), remaining), pct(len(pp), nrows)])
        remaining -= len(pp)
        if st["analyzed_nocard"]:
            rows.append(["- ANALYZED without a card row", len(st["analyzed_nocard"]), "", ""])
            remaining -= len(st["analyzed_nocard"])
        cards = len(st["held"]) + len(st["published"])
        rows.append(["**Cards written**", cards, pct(cards, nrows) + " of rows", pct(cards, processed) + " of processed rows"])
        nr = st["needs_review"]
        nr_held = sum(1 for f in nr if C[f["news_id"]]["held"])
        rows.append([f"- needs_review flag (a flag, not a gate: {nr_held} held, {len(nr) - nr_held} published)", len(nr), pct(len(nr), cards), ""])
        held = st["held"]
        rows.append(["- held out of the feed (`held = 1`)", len(held), pct(len(held), cards), ""])
        multi = collections.Counter()
        only = collections.Counter()
        for f in held:
            cl = set(hold_classes((C[f["news_id"]]["j"].get("review") or {}).get("issues")))
            for k in cl:
                multi[k] += 1
            only[next(iter(cl)) if len(cl) == 1 else ("(no issue listed)" if not cl else "(several kinds)")] += 1
        for k, v in multi.most_common():
            rows.append([f"&nbsp;&nbsp;&nbsp;has: {k}", v, pct(v, len(held)) + " of held", f"only this kind: {only.get(k, 0)}"])
        if only.get("(several kinds)"):
            rows.append(["&nbsp;&nbsp;&nbsp;held for several kinds at once", only["(several kinds)"], pct(only["(several kinds)"], len(held)) + " of held", ""])
        rows.append(["**Published (`held = 0`)**", len(st["published"]), pct(len(st["published"]), cards) + " of cards",
                     pct(len(st["published"]), disc) + " of discovered"])
        return rows

    hdr = ["Stage", "Count", "% of the stage above", "% of filing rows / note"]
    report.append("# Announcement funnel, smoke-test companies (local D1 + R2, read 2026-10-18)\n")
    smoke_names = ", ".join(f"{s} {names.get(s, '?')}" for s in SMOKE)
    same = set(SMOKE) == all_scrips
    report.append(f"**Scope.** Smoke-test set: {smoke_names}. The five beyond the named ones are the five other "
                  f"companies with the most filing rows. "
                  + ("The local database and R2 hold **only these ten companies**, so the smoke-test funnel and the "
                     "everything funnel are the same numbers; one table serves both." if same else
                     f"The database holds {len(all_scrips)} companies; totals for everything follow."))
    report.append("")
    stale = [f for f in F.values() if f["status"] == "ANALYZED" and (f["reason"] or "").startswith(("duplicate", "timeline only"))]
    report.append(f"**Sources.** A byte copy of the local D1 database (`data/wrangler/v3/d1/...sqlite`, last written "
                  f"{max(f['updated_at'] or '' for f in F.values())[:16]}); the {len(set(n['news_id'] for n in noise))} noise rows of the "
                  "local R2 `noise/` objects, read through `GET /api/internal/objects` on the local site (it answered 200); "
                  "the run logs in `data/logs` (D:\\backfill.log does not exist); the audit files `docs/audit/card-audit-2026-10-16.json` "
                  "(round 0) and `round-1.json`; the text cache for the held-card number checks. Nothing in the repository, "
                  f"database or R2 was changed. A filing is counted by its `status`; {len(stale)} ANALYZED rows still carry an "
                  "older duplicate or timeline reason because `filings_update.sql` coalesces `reason`, and they count as analysed.\n")
    report.append("## A. The funnel\n")
    report.append("**How to read it.** Each loss row's % is of the count entering that stage (what is left after the "
                  "rows above it); sub-rows are % of their parent. The order follows the brief, not the code: in the "
                  "pipeline the text-repeat check runs first, then pass 1 (PASS1 route only), then the fast-track repeat "
                  "check and D20 (before pass 2), then pass 2. Pending rows never reached any of those stages, so the "
                  "last column also gives each loss as a share of all filing rows. `needs_review` is a flag, not a gate: "
                  "what keeps a card out of the feed is `held` (the feed query is `WHERE c.held = 0`).\n")
    report.append(md_table(hdr, funnel_rows(S)))
    if not same:
        report.append("\n### Everything in the database\n")
        report.append(md_table(hdr, funnel_rows(A)))

    # Per company
    report.append("\n### Per company\n")
    prow = []
    for s in SMOKE:
        st = funnel({s})
        cards = len(st["held"]) + len(st["published"])
        nm = len(st["nm_p1"]) + len(st["nm_tl"]) + len(st["nm_p2"])
        prow.append([f"{s} {clean(names.get(s), 26)}", len(st["_noise"]) + len(st["_filings"]), len(st["rule"]),
                     len(st["_filings"]), len(st["dup"]), nm, len(st["failed"]) + len(st["pending"]), cards,
                     len(st["held"]), len(st["published"]), pct(len(st["held"]), cards)])
    tot = [sum(r[i] for r in prow) for i in range(1, 10)]
    prow.append(["**total**", *tot, pct(tot[7], tot[6])])
    report.append(md_table(["company", "discovered", "dropped by rule", "filing rows", "duplicates", "not material",
                            "failed + pending", "cards", "held", "published", "held %"], prow))

    # ------------------------------------------------------------ B. by event type
    report.append("\n## B. By event type\n")
    report.append("Event type is the one stored on the row at its last outcome: for a not-material or duplicate row "
                  "the type pass 1 / pass 2 / the rules gave it; for a card, the card's `event_category`; for a pending "
                  "row, the rule's type (blank = no rule matched, PASS1 route).\n")
    et = lambda f: f.get("event_type") or "(none)"
    stages = [("dup", "duplicates"), ("nm_p1", "pass 1 NM"), ("nm_tl", "timeline only"), ("nm_p2", "pass 2 NM"),
              ("pending", "pending"), ("failed", "failed")]
    types = collections.Counter()
    tab = collections.defaultdict(collections.Counter)
    for key, _ in stages:
        for f in S[key]:
            tab[key][et(f)] += 1
            types[et(f)] += 1
    for key in ("held", "published"):
        for f in S[key]:
            t = C[f["news_id"]]["event_category"]
            tab[key][t] += 1
            types[t] += 1
    rows = []
    for t, _ in types.most_common():
        cards = tab["held"][t] + tab["published"][t]
        rows.append([t, *[tab[k][t] for k, _ in stages], cards, tab["held"][t], tab["published"][t], pct(tab["held"][t], cards)])
    rows.append(["**total**", *[sum(tab[k].values()) for k, _ in stages], len(S["held"]) + len(S["published"]),
                 len(S["held"]), len(S["published"]), pct(len(S["held"]), len(S["held"]) + len(S["published"]))])
    report.append(md_table(["event type", *[l for _, l in stages], "cards", "held", "published", "held % of cards"], rows))

    report.append("\n### Duplicates by event type and sub-cause\n")
    kinds = [k for k, _ in collections.Counter(dup_kind(f["reason"]) for f in S["dup"]).most_common()]
    dt = collections.defaultdict(collections.Counter)
    for f in S["dup"]:
        dt[et(f)][dup_kind(f["reason"])] += 1
    report.append(md_table(["event type", *kinds, "total"],
                           [[t, *[dt[t][k] for k in kinds], sum(dt[t].values())] for t in sorted(dt, key=lambda t: -sum(dt[t].values()))]))

    report.append("\n### Pass 1 not material, by sub-cause (classified from pass 1's reason and the headline)\n")
    p1 = collections.Counter(pass1_class(f["reason"], f["headline"]) for f in S["nm_p1"])
    report.append(md_table(["sub-cause", "rows", "% of pass-1 NM"], [[k, v, pct(v, len(S["nm_p1"]))] for k, v in p1.most_common()]))

    report.append("\n### Pass 2 not material, by entry route and pass 2's event type\n")
    p2 = collections.Counter()
    for f in S["nm_p2"]:
        p2[(f["route"], et(f))] += 1
    report.append(md_table(["route", "event type (pass 2's)", "rows"], [[r, t, v] for (r, t), v in p2.most_common()]))

    report.append("\n### Held cards: hold kinds by event type (a card can have several)\n")
    ht = collections.defaultdict(collections.Counter)
    for f in S["held"]:
        c = C[f["news_id"]]
        for k in set(hold_classes((c["j"].get("review") or {}).get("issues"))):
            ht[c["event_category"]][k] += 1
    hk = [k for k, _ in HOLD_CLASSES if any(ht[t][k] for t in ht)]
    report.append(md_table(["event type", *hk, "held cards"],
                           [[t, *[ht[t][k] for k in hk], tab["held"][t]] for t in sorted(ht, key=lambda t: -tab["held"][t])]))

    # ------------------------------------------------------------ deeper checks used in D
    # 1. Where a duplicate's original ended
    def state(nid):
        f = F.get(nid)
        if not f:
            return "missing"
        if f["status"] == "ANALYZED":
            c = C.get(nid)
            return "card held" if c and c["held"] else "card published" if c else "analyzed, no card"
        return f["status"].lower().replace("_", " ")

    def root(nid, seen=()):
        f = F.get(nid)
        if f and f["status"] == "DUPLICATE":
            t = dup_target(f["reason"])
            if t and t not in seen:
                return root(t, seen + (nid,))
        return nid

    chain = collections.defaultdict(collections.Counter)
    chain_rows = collections.defaultdict(list)
    for f in S["dup"]:
        k = dup_kind(f["reason"])
        s = state(root(dup_target(f["reason"])))
        chain[k][s] += 1
        chain_rows[(k, s)].append(f)
    states = ["card published", "card held", "not material", "pending", "failed", "missing"]
    chain_tab = md_table(["duplicate sub-cause", *[f"original: {s}" for s in states], "total"],
                         [[k, *[chain[k][s] for s in states], sum(chain[k].values())] for k in kinds])
    # D20 quarters with no published card
    d20q = collections.defaultdict(set)
    for f in S["dup"]:
        if dup_kind(f["reason"]) == "same results quarter (D20)":
            q = re.search(r"quarter (\S+?),", f["reason"])[1]
            owner = root(dup_target(f["reason"]))
            d20q[(f["scrip_code"], q)].add(state(owner))
    d20_lost = {k: v for k, v in d20q.items() if "card published" not in v}

    # 2. Held cards: what the unfound numbers are
    tok_kind = collections.Counter()
    own_expl = collections.Counter()
    own_decoy = collections.Counter()
    nfig = collections.Counter()
    ctx_all = collections.Counter()
    scale_only_cards = []
    tok_expl = collections.Counter()
    decoy_expl = collections.Counter()
    held_detail = []
    mcap_cards = 0
    only_numbers_cards = 0
    explained_cards = 0
    for f in S["held"]:
        c = C[f["news_id"]]
        issues = (c["j"].get("review") or {}).get("issues") or []
        cl = set(hold_classes(issues))
        toks = ungrounded_tokens(issues)
        priced = c["j"].get("priced_at_filing") or {}
        nums = filing_numbers(f["news_id"])
        card_expl = []
        has_mcap = False
        for t in toks:
            tv = token_value(t)
            if "=" in t and "market_cap" not in t:
                tok_kind[f"formula input ({t.split('=')[0]}=...)"] += 1
                card_expl.append((t, "formula input"))
                continue
            mc = "market_cap" in t or (tv and priced.get("market_cap_cr") and abs(tv[0] - priced["market_cap_cr"]) <= 0.01 * priced["market_cap_cr"])
            if mc:
                tok_kind["market cap (from the price data, not the filing)"] += 1
                has_mcap = True
                card_expl.append((t, "market cap"))
                continue
            if tv is None:
                tok_kind["unparsed"] += 1
                continue
            tok_kind[tv[2]] += 1
            if nums is None:
                tok_expl["(no cached text)"] += 1
                continue
            e = explain(*tv, nums)
            tok_expl[e or "not explained"] += 1
            own = card_grounded_numbers(c["j"], nums, tv[0])
            e2 = explain(*tv, own) if own else None
            own_expl[e2 or "not explained"] += 1
            own_decoy["explained" if own and explain(round(tv[0] * 1.0731, tv[1]), tv[1], tv[2], own) else "not explained"] += 1
            card_expl.append((t, e or "not explained"))
            # decoy: the same figure 7.31% larger, rounded the same way - how often does chance explain it?
            dv = round(tv[0] * 1.0731, tv[1])
            decoy_expl["explained" if explain(dv, tv[1], tv[2], nums) else "not explained"] += 1
        mcap_cards += has_mcap
        ctxs = [figure_context(c["j"], t) for t in toks]
        for x in ctxs:
            ctx_all[x] += 1
        if cl == {"number not found in filing or memory"} and ctxs and all(
                x not in ("elsewhere on the card", "not located on the card") for x in ctxs):
            scale_only_cards.append(f)
        if cl == {"number not found in filing or memory"}:
            nfig[min(len(set(toks)), 4)] += 1
        if cl == {"number not found in filing or memory"}:
            only_numbers_cards += 1
            if card_expl and all(e != "not explained" for _, e in card_expl):
                explained_cards += 1
        held_detail.append({"news_id": f["news_id"], "company": f["company_name"], "headline": c["headline"],
                            "event": c["event_category"], "classes": sorted(cl), "tokens": card_expl})

    # 3. Audit verdicts (rounds 0 and 1) against today's outcome of the same filing
    def load_audit(p):
        try:
            return {r["news_id"]: r for r in json.load(open(p, encoding="utf-8"))}
        except OSError:
            return {}
    a0, a1 = load_audit(AUDIT0), load_audit(AUDIT1)
    noise_by_id = {n["news_id"]: n for n in noise}
    audit_tab = []
    audit_lost = []
    for label, aud in (("round 0 (2026-10-16, before the rebuild)", a0), ("round 1 (2026-10-16, after the rebuild)", a1)):
        tab_ = collections.defaultdict(collections.Counter)
        for nid, r in aud.items():
            s = state(nid)
            if F.get(nid) and F[nid]["status"] == "DUPLICATE":
                s = "duplicate: " + dup_kind(F[nid]["reason"])
            elif F.get(nid) and F[nid]["status"] == "NOT_MATERIAL":
                s = "not material: " + (F[nid]["reason"] or "").split(":")[0]
            elif s == "missing" and nid in noise_by_id:
                s = "dropped by rule: " + noise_by_id[nid]["reason"]
            tab_[r["verdict"]][s] += 1
            if r["verdict"] in ("OK", "MINOR") and not s.startswith("card"):
                audit_lost.append((label.split(" (")[0], r, s))
        audit_tab.append((label, tab_))

    data.update({"d20_lost": {f"{k[0]} {k[1]}": sorted(v) for k, v in d20_lost.items()},
                 "token_kinds": tok_kind, "token_explained": tok_expl, "decoy": decoy_expl,
                 "held_detail": held_detail})

    # ------------------------------------------------------------ C. examples
    report.append("\n## C. Examples at each loss stage (3 each, one company each where possible, fixed seed)\n")
    report.append("### Dropped by rule (before a filing row exists)\n")
    by_rule = collections.defaultdict(list)
    for n in S["rule"]:
        by_rule[n["reason"]].append(n)
    for rule, rows_ in sorted(by_rule.items(), key=lambda kv: -len(kv[1]))[:6]:
        report.append(f"\n**{('CALENDAR' if rule in CALENDAR_RULES else 'DROP')}: {rule}** ({len(rows_)})\n")
        report.append(ex_table(examples(rows_), lambda r: r.get("subcategory")))
    rest = sorted(by_rule.items(), key=lambda kv: -len(kv[1]))[6:]
    if rest:
        report.append("\n**The smaller rules** (one example each)\n")
        report.append(ex_table([examples(v, 1)[0] for _, v in rest], lambda r: f"{r['reason']} / {r.get('subcategory')}"))
    if S["outside"]:
        report.append("\n**Outside universe**\n")
        report.append(ex_table(examples(S["outside"])))
    report.append("\n### Duplicates\n")
    for k in kinds:
        rows_ = [f for f in S["dup"] if dup_kind(f["reason"]) == k]
        report.append(f"\n**{k}** ({len(rows_)})\n")
        report.append(ex_table(examples(rows_), lambda r: f"{r['reason'][:13]}…{r['reason'][49:]} -> original: {state(root(dup_target(r['reason'])))}"))
    for key, label in (("nm_p1", "Pass 1: not material"), ("nm_tl", "Timeline only"), ("nm_p2", "Pass 2: not material"),
                       ("failed", "Failed"), ("pending", "Still pending")):
        report.append(f"\n### {label} ({len(S[key])})\n")
        detail = (lambda r: f"{r['route']} / {r.get('event_type')} / attempts {r['attempts']} / {r.get('last_error') or 'never attempted'}") \
            if key in ("failed", "pending") else (lambda r: f"{r['route']} / {r.get('event_type')} / {r['reason']}")
        report.append(ex_table(examples(S[key]), detail))
    report.append("\n### Held out of the feed, by hold kind (cards held for that kind alone where there are three)\n")
    for name, _ in HOLD_CLASSES:
        rows_ = [f for f in S["held"] if name in hold_classes((C[f["news_id"]]["j"].get("review") or {}).get("issues"))]
        if not rows_:
            continue
        alone = [f for f in rows_ if set(hold_classes((C[f["news_id"]]["j"].get("review") or {}).get("issues"))) == {name}]
        pick = examples(alone if len(alone) >= 3 else rows_)
        report.append(f"\n**{name}** ({len(rows_)} cards, {len(alone)} held for it alone)\n")
        report.append(md_table(["news_id", "company", "card headline", "issues"],
                               [[f["news_id"][:8], clean(f["company_name"], 26), clean(C[f["news_id"]]["headline"], 90),
                                 clean("; ".join((C[f["news_id"]]["j"].get("review") or {}).get("issues") or []), 260)] for f in pick]))

    # ------------------------------------------------------------ D. reading
    report.append("\n## D. Where correct cards are most likely lost (my reading)\n")
    report.append("_This section is interpretation. The numbers under each point are measured; the judgement that a "
                  "card would have been correct is mine, from headlines and stored reasons, not from re-reading the PDFs._\n")
    report.append("\n### Evidence 1: where each duplicate's original ended\n")
    report.append(chain_tab)
    report.append(f"\nResults quarters (company x quarter) whose D20 duplicates point at an owner that has **no published card**: "
                  f"**{len(d20_lost)}** of {len(d20q)} quarters that had D20 duplicates: "
                  + ", ".join(f"{names.get(s, s)[:18]} {q} ({'/'.join(sorted(v))})" for (s, q), v in sorted(d20_lost.items())) + ".")
    report.append("\n### Evidence 2: what the 'number not found' figures on held cards are\n")
    report.append(md_table(["kind of figure", "figures"], [[k, v] for k, v in tok_kind.most_common()]))
    report.append("\nWhether each figure (other than market cap) can be made from the filing's own cached text: the same figure in "
                  "another unit, or a sum, difference, ratio or change of two of the filing's figures at the token's rounding:\n")
    report.append(md_table(["explanation", "figures"], [[k, v] for k, v in tok_expl.most_common()]))
    dn = sum(decoy_expl.values())
    report.append(f"\nControl: the same test on decoys (each figure x1.0731, same rounding) explains "
                  f"{decoy_expl['explained']} of {dn} ({pct(decoy_expl['explained'], dn)}), so an 'explained' figure is "
                  f"only evidence beyond that chance rate. Cards held for a number not found and nothing else: "
                  f"{only_numbers_cards}; of those, every figure explained (or market cap): {explained_cards}. Cards with a "
                  f"market-cap figure among their holds: {mcap_cards}.")
    report.append("\nWhere each unfound figure sits on the card: next to one of the company-level denominators the Pass 2 prompt "
                  "is handed by `signals.scale_block` (market cap, TTM revenue, net worth, net debt, order book), as a "
                  "quantified-impact formula input, or elsewhere:\n")
    report.append(md_table(["context of the unfound figure", "figures"], [[k, v] for k, v in ctx_all.most_common()]))
    report.append(f"\nCards held for a number not found and nothing else whose **every** unfound figure is a scale-block "
                  f"denominator, a share of one, or a formula input: **{len(scale_only_cards)}** of {only_numbers_cards} "
                  f"({', '.join(f['news_id'][:8] for f in scale_only_cards[:12])}{', ...' if len(scale_only_cards) > 12 else ''}).")
    on = sum(own_decoy.values())
    report.append("\nA stricter version of the same test, using only figures **the card itself states and the filing contains** "
                  "as the two operands (far fewer candidates, so far less chance):\n")
    report.append(md_table(["explanation (card's own grounded figures)", "figures"], [[k, v] for k, v in own_expl.most_common()]))
    report.append(f"\nControl: decoys explained {own_decoy['explained']} of {on} ({pct(own_decoy['explained'], on)}).")
    report.append("\nDistinct unfound figures on the cards held for a number not found and nothing else:\n")
    report.append(md_table(["distinct figures", "cards"], [[("4 or more" if k == 4 else k), v] for k, v in sorted(nfig.items())]))
    hx = collections.Counter()
    for f in S["held"]:
        c = C[f["news_id"]]
        cl = set(hold_classes((c["j"].get("review") or {}).get("issues")))
        hx[("needs_review = 1" if c["needs_review"] else "needs_review = 0",
            "number not found only" if cl == {"number not found in filing or memory"} else "other or several")] += 1
    report.append("\nHeld cards by the review flag (needs_review = 0 means every blueprint review rule passed: grounding score above "
                  "the threshold, no headline figure unfound, no math mismatch, no unsupported claim, nothing out of scale, no "
                  "quote problem; the hold comes from an unfound *amount* that the second opinion did not clear):\n")
    report.append(md_table(["", "number not found only", "other or several", "total"],
                           [[k, hx[(k, "number not found only")], hx[(k, "other or several")],
                             hx[(k, "number not found only")] + hx[(k, "other or several")]]
                            for k in ("needs_review = 0", "needs_review = 1")]))
    report.append("\n### Evidence 3: audit verdicts on the same filings against today's outcome\n")
    report.append("Rounds 0 and 1 audited older versions of these cards; a filing judged OK or MINOR then that has no card now "
                  "is a candidate correct card lost (or a deliberate merge, such as D20).\n")
    for label, tab_ in audit_tab:
        sts = sorted({s for v in tab_.values() for s in v})
        report.append(f"\n**{label}**\n")
        report.append(md_table(["verdict then", *sts], [[v, *[tab_[v][s] for s in sts]] for v in ("OK", "MINOR", "WRONG") if v in tab_]))
    hv = collections.defaultdict(collections.Counter)
    for f in S["held"]:
        r = a1.get(f["news_id"])
        if r:
            cl = set(hold_classes((C[f["news_id"]]["j"].get("review") or {}).get("issues")))
            hv["number not found only" if cl == {"number not found in filing or memory"} else "other or several"][r["verdict"]] += 1
    pv = collections.Counter(a1[f["news_id"]]["verdict"] for f in S["published"] if f["news_id"] in a1)
    report.append("\nToday's held and published cards whose filing was audited in round 1 (the audited card is an older version of "
                  "today's, so this is a pointer, not a measurement):\n")
    report.append(md_table(["today", "OK then", "MINOR then", "WRONG then", "OK + MINOR share"],
                           [[f"held: {k}", v["OK"], v["MINOR"], v["WRONG"], pct(v["OK"] + v["MINOR"], sum(v.values()))] for k, v in hv.items()]
                           + [["published", pv["OK"], pv["MINOR"], pv["WRONG"], pct(pv["OK"] + pv["MINOR"], sum(pv.values()))]]))
    if audit_lost:
        report.append("\nOK / MINOR then, no card now:\n")
        report.append(md_table(["round", "news_id", "verdict", "card headline then", "now"],
                               [[rnd, r["news_id"][:8], r["verdict"], clean(r["headline"], 90), s] for rnd, r, s in audit_lost]))

    yrows = []
    exp_cards = exp_pub = 0.0
    for route in ("FAST_TRACK", "PASS1", "TIMELINE"):
        done = [f for f in S["_filings"] if f["route"] == route and f["status"] in ("ANALYZED", "NOT_MATERIAL", "DUPLICATE", "FAILED")]
        cards_ = [f for f in done if f["status"] == "ANALYZED" and f["news_id"] in C]
        pub = [f for f in cards_ if not C[f["news_id"]]["held"]]
        pend = [f for f in S["pending"] if f["route"] == route]
        rc, rp = len(cards_) / len(done), len(pub) / len(done)
        exp_cards += rc * len(pend)
        exp_pub += rp * len(pend)
        yrows.append([route, len(done), pct(len(cards_), len(done)), pct(len(pub), len(done)), len(pend),
                      f"{rc * len(pend):.0f}", f"{rp * len(pend):.0f}"])
    yrows.append(["**total**", "", "", "", len(S["pending"]), f"{exp_cards:.0f}", f"{exp_pub:.0f}"])
    pend_tab = md_table(["route", "processed rows", "card rate", "published rate", "pending rows", "expected cards", "expected published"], yrows)
    pend_dates = sorted(f["filing_date"] for f in S["pending"])
    pend_cos = collections.Counter(f["company_name"] for f in S["pending"])

    reading = (HERE / "reading.md").read_text(encoding="utf-8") if (HERE / "reading.md").exists() else ""  # a reviewer's notes, optional
    i = next(k for k, line in enumerate(report) if "## D. Where correct cards" in line)
    report.insert(i + 2, reading)
    report.append("\n### Evidence 4: what the pending queue would yield at today's rates\n")
    report.append(f"Pending rows were filed {pend_dates[0]} to {pend_dates[-1]}; by company: "
                  + ", ".join(f"{k} {v}" for k, v in pend_cos.most_common()) + ".\n")
    report.append(pend_tab)
    report.append(logs_section())

    out = HERE / "funnel.md"
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    (HERE / "funnel_data.json").write_text(json.dumps(data, indent=1, ensure_ascii=False, default=list), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
