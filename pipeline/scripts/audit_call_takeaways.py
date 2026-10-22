"""On/off audit of the call-takeaway check (22 Oct 2026, owner's rule: a check that accepts more is measured first).

    python -I scripts/audit_call_takeaways.py OUT_DIR [OLD_REF]

Every published call card on the live site that has model takeaways: its transcript is fetched from NSE, read as the
pipeline reads it, and each takeaway is checked by the check at OLD_REF (default origin/main) and by the working
tree's. No AI is called and nothing is written to the platform. OUT_DIR gets accepted.json (the takeaways the new
check accepts and the old refused, for an independent reviewer), refused.json (the reverse, which should be empty)
and summary.json."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
import types
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bse_intel import call_summary as new_check  # noqa: E402
from bse_intel.extract import Document  # noqa: E402
from bse_intel.grounding import declared_unit  # noqa: E402
from bse_intel.models import Card  # noqa: E402

SITE = "https://insiders.reply-bd3.workers.dev"


def old_module(ref: str) -> types.ModuleType:
    source = subprocess.run(["git", "show", f"{ref}:pipeline/src/bse_intel/call_summary.py"], cwd=ROOT,
                            capture_output=True, text=True, check=True).stdout
    spec = importlib.util.spec_from_loader("bse_intel.call_summary_old", loader=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "bse_intel"
    exec(compile(source, "call_summary_old.py", "exec"), mod.__dict__)
    return mod


def get(url: str, binary: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
    return body if binary else json.loads(body)


def cards():
    page = 1
    while True:
        d = get(f"{SITE}/api/feed?range=all&category=CONCALL_PRESENTATION&limit=50&page={page}")
        yield from d["cards"]
        if page >= (d.get("pages") or 1):
            return
        page += 1


def verdicts(module, card_json: dict, text: str) -> list[tuple[bool, str | None]]:
    card = Card.model_validate({k: card_json[k] for k in ("impact_level", "headline", "what_happened", "call_takeaways")
                                if card_json.get(k) is not None})
    module.check_ai_takeaways(card, text, "", {}, declared_unit(text))
    return [(t.verified, t.issue) for t in card.call_takeaways]


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    pdfs = out / "pdf"
    pdfs.mkdir(exist_ok=True)
    old = old_module(sys.argv[2] if len(sys.argv) > 2 else "origin/main")
    accepted, refused, stats = [], [], {"cards": 0, "with_takeaways": 0, "read": 0, "takeaways": 0,
                                        "old_verified": 0, "new_verified": 0, "unreadable": []}
    for row in cards():
        stats["cards"] += 1
        cj = json.loads(row["card_json"])
        if not cj.get("call_takeaways") or not row.get("pdf_url"):
            continue
        stats["with_takeaways"] += 1
        path = pdfs / f"{row['news_id']}.pdf"
        try:
            if not path.exists():
                path.write_bytes(get(row["pdf_url"], binary=True))
                time.sleep(0.5)
            text = Document(path.read_bytes(), max_ocr_pages=0).select_text(10_000_000, [])
        except Exception as exc:  # noqa: BLE001 - one unreadable PDF is reported, the rest go on
            stats["unreadable"].append(f"{row['news_id']}: {exc}"[:200])
            continue
        stats["read"] += 1
        before, after = verdicts(old, cj, text), verdicts(new_check, cj, text)
        for item, (v0, i0), (v1, i1) in zip(cj["call_takeaways"], before, after):
            stats["takeaways"] += 1
            stats["old_verified"] += v0
            stats["new_verified"] += v1
            entry = {"news_id": row["news_id"], "symbol": row["symbol"], "pdf_url": row["pdf_url"],
                     "category": item.get("category"), "text": item.get("text"), "quote": item.get("quote"),
                     "versus_prior": item.get("versus_prior"), "old_issue": i0, "new_issue": i1}
            if v1 and not v0:
                accepted.append(entry)
            elif v0 and not v1:
                refused.append(entry)
    (out / "accepted.json").write_text(json.dumps(accepted, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "refused.json").write_text(json.dumps(refused, ensure_ascii=False, indent=1), encoding="utf-8")
    stats.update(accepted=len(accepted), refused=len(refused))
    (out / "summary.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k != "unreadable"} | {"unreadable": len(stats["unreadable"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
