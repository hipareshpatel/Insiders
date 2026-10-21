"""Do figures cards wrote into memory agree with the company's own XBRL? No AI, read from the live site.

Usage: python -I scripts/memory_xbrl_agree.py OUT_DIR [COMPANIES]
Fetches the memory of up to COMPANIES (default 250) companies on the live feed into OUT_DIR/dossiers, then compares
each card source of a figure with each XBRL source of the same metric and period, grouped by basis
(deep audit C2 and D1, 21 Oct 2026).
"""
import collections
import json
import pathlib
import sys
import urllib.request

SITE = "https://insiders.reply-bd3.workers.dev/api"
UA = {"User-Agent": "Mozilla/5.0"}


def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))


def fetch(out: pathlib.Path, limit: int) -> None:
    scrips, cursor = [], None
    while len(scrips) < limit:
        page = get(f"{SITE}/feed?range=all&limit=100" + (f"&cursor={cursor}" if cursor else ""))
        scrips += [c["scrip_code"] for c in page["cards"] if c["scrip_code"] not in scrips]
        cursor = page.get("next_cursor")
        if not cursor:
            break
    out.mkdir(parents=True, exist_ok=True)
    for scrip in scrips[:limit]:
        path = out / f"{scrip}.json"
        if not path.exists():
            path.write_text(json.dumps(get(f"{SITE}/companies/{scrip}").get("dossier")))


def xbrl(source: dict) -> bool:
    return str(source.get("news_id", "")).startswith("xbrl:")


def compare(folder: pathlib.Path) -> None:
    counts, differ = collections.Counter(), []
    for path in sorted(folder.glob("*.json")):
        dossier = json.loads(path.read_text() or "null") or {}
        for entry in dossier.get("financial_metrics", []):
            sources = entry.get("sources") or []
            if (entry.get("unit") or "INR_CR") != "INR_CR":
                continue
            for card in (s for s in sources if not xbrl(s) and s.get("value") is not None):
                for tagged in (s for s in sources if xbrl(s) and s.get("value") is not None):
                    kind = ("xbrl basis not stated" if not tagged.get("basis") else "card basis not stated"
                            if not card.get("basis") else "same basis" if card["basis"] == tagged["basis"] else "other basis")
                    ok = abs(card["value"] - tagged["value"]) <= max(0.06, abs(tagged["value"]) * 0.01)
                    counts[(kind, "agree" if ok else "differ")] += 1
                    if kind == "same basis" and not ok:
                        differ.append((path.stem, entry["metric"], entry["period"], card["value"], tagged["value"], card["news_id"]))
    for key in sorted(counts):
        print(*key, counts[key], sep="\t")
    for row in differ:
        print(*row, sep="\t")


if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1]) / "dossiers"
    fetch(root, int(sys.argv[2]) if len(sys.argv) > 2 else 250)
    compare(root)
