"""Read every run log (read-only) and pull out the final JSON stats block and the per-day discovery lines.

Writes data/funnel/logs_summary.json. Re-runs overlap (a filing deferred in one run is analysed
in the next, and a company reset re-queues filings), so the per-run counters are reported side by side
and only the discovery counters are summed: discovery skips any news_id already in the ledger or in the
day's noise file, so a filing is counted as discovered once unless its ledger row was deleted (a reset).
"""
import json
import pathlib
import re

LOGS = [*sorted(pathlib.Path(r"D:\Insiders\data\logs").glob("*.log"))]
if pathlib.Path(r"D:\backfill.log").exists():
    LOGS.append(pathlib.Path(r"D:\backfill.log"))
DISC = re.compile(r"discovered (\d{4}-\d{2}-\d{2}): (\d+) new filings \((\d+) queued, (\d+) noise\)")


def last_json(text: str) -> dict | None:
    end = text.rfind("}")
    while end != -1:
        start = text.rfind("\n{", 0, end)
        if start == -1:
            return None
        try:
            return json.loads(text[start + 1:end + 1])
        except json.JSONDecodeError:
            end = text.rfind("}", 0, start)
    return None


def main() -> None:
    runs = []
    for path in LOGS:
        text = path.read_text(encoding="utf-8", errors="replace")
        stats = last_json(text)
        disc = DISC.findall(text)
        runs.append({
            "log": path.name,
            "stats": stats if isinstance(stats, dict) and "discovered" in stats else None,
            "disc_lines": len(disc),
            "disc_new": sum(int(d[1]) for d in disc),
            "disc_queued": sum(int(d[2]) for d in disc),
            "disc_noise": sum(int(d[3]) for d in disc),
        })
    out = pathlib.Path(__file__).resolve().parents[3] / "data" / "funnel" / "logs_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(runs, indent=1), encoding="utf-8")
    keys = ["discovered", "dropped_rule", "outside_universe", "pending_new", "pass1_rejected", "timeline_only",
            "analyzed", "not_material", "failed", "deferred", "duplicates", "needs_review", "second_opinions",
            "corrected"]
    print("log".ljust(42), " ".join(k[:8].rjust(8) for k in keys), "disc_new disc_q disc_noise")
    tot = {k: 0 for k in keys}
    for r in runs:
        s = r["stats"]
        if not s:
            continue
        for k in keys:
            tot[k] += s.get(k, 0) or 0
        print(r["log"].ljust(42), " ".join(str(s.get(k, "")).rjust(8) for k in keys),
              r["disc_new"], r["disc_queued"], r["disc_noise"])
    print("SUM".ljust(42), " ".join(str(tot[k]).rjust(8) for k in keys),
          sum(r["disc_new"] for r in runs), sum(r["disc_queued"] for r in runs), sum(r["disc_noise"] for r in runs))


if __name__ == "__main__":
    main()
