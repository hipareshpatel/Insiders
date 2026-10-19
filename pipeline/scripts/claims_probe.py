"""Measure the cause/outcome/stage check (causes.py) on cards already reviewed blind, before wiring it in.

    pwsh: . C:\\Users\\Quali\\insiders-keys.ps1; Remove-Item env:DEEPSEEK_API_KEY
    python -I -X utf8 scripts/claims_probe.py ../data/audit/round4rerun/cards [--report OUT.json]

For each card in the reviewer folders: the claim sentences, the model's verdicts (free card route, pass2_bulk), what
would be cut, and how that lines up with the reviewers' findings (fields with an `invented` or `direction` issue).
Reports: claims found and cut; reviewer-flagged fields caught; cuts on cards the reviewers called OK. Writes nothing to
the platform; makes one AI request per card that has a claim.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from bse_intel import causes  # noqa: E402
from bse_intel.ai.gateway import AIGateway  # noqa: E402
from bse_intel.models import Pass2Output  # noqa: E402
from bse_intel.settings import get_settings  # noqa: E402

FIELD_OF = {"headline": "headline", "takeaway": "takeaway", "core_catalyst": "core_catalyst",
            "what_happened": "what_happened", "why_it_matters": "why_it_matters", "timeline_entry": "timeline",
            "timeline": "timeline"}


def _field(raw: str) -> str | None:
    head = (raw or "").split("[")[0].split(".")[0].strip()
    return FIELD_OF.get(head)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cards_dir")
    ap.add_argument("--report")
    ap.add_argument("--route", default="pass2_bulk")
    args = ap.parse_args()
    gateway = AIGateway(get_settings().load_toml("providers.toml"))
    stats = collections.Counter()
    rows = []
    for folder in sorted(pathlib.Path(args.cards_dir).glob("reviewer_*")):
        findings = {f["news_id"]: f for f in json.loads((folder / "findings.json").read_text(encoding="utf-8"))}
        for card_path in sorted(folder.glob("*.card.json")):
            nid = card_path.name[:-len(".card.json")]
            card = json.loads(card_path.read_text(encoding="utf-8"))
            text = (folder / f"{nid}.pdf.txt").read_text(encoding="utf-8")
            try:
                out = Pass2Output.model_validate({"is_material": True, "event_type": card.get("event_type") or "OTHER",
                                                  "timeline_entry": card.get("timeline_entry") or "",
                                                  "card": {k: v for k, v in card.items() if not k.startswith("_")}})
            except Exception as exc:  # a card that no longer validates is reported, not a stop
                print("skip", nid, type(exc).__name__, str(exc)[:100])
                continue
            found = causes.claims(out)
            verdict = findings.get(nid, {})
            flagged = {_field(i.get("field", "")) for i in verdict.get("issues", [])
                       if i.get("class") in ("invented", "direction")} - {None}
            stats["cards"] += 1
            stats["claims"] += len(found)
            stats["reviewer-flagged fields"] += len(flagged)
            if not found:
                stats["reviewer-flagged fields with no claim sentence"] += len(flagged)
                continue
            system, user = causes.prompt(found, text)
            try:
                result = gateway.complete_json(args.route, system, user, causes.ClaimCheck).value
            except Exception as exc:
                print("ai failed", nid, type(exc).__name__, str(exc)[:120])
                stats["ai failed"] += 1
                continue
            bad = causes.unsupported(found, result, text)
            cut_fields = {c["field"] for c in bad}
            stats["cut"] += len(bad)
            stats["reviewer-flagged fields caught"] += len(flagged & cut_fields)
            if verdict.get("verdict") == "OK":
                stats["cuts on OK cards"] += len(bad)
                stats["OK cards with a cut"] += bool(bad)
            if verdict.get("verdict") == "WRONG":
                stats["WRONG cards"] += 1
                stats["WRONG cards with a cut in a flagged field"] += bool(flagged & cut_fields)
            rows.append({"news_id": nid, "verdict": verdict.get("verdict"), "flagged": sorted(flagged),
                         "cut": [{"field": c["field"], "text": c["text"][:160]} for c in bad],
                         "kept": [c["text"][:120] for c in found if c not in bad]})
            print(f"{nid} {verdict.get('verdict')}: {len(found)} claims, {len(bad)} cut; flagged {sorted(flagged)} cut {sorted(cut_fields)}")
    print(json.dumps(stats, indent=1))
    if args.report:
        pathlib.Path(args.report).write_text(json.dumps({"stats": stats, "cards": rows}, ensure_ascii=False, indent=1),
                                             encoding="utf-8")


if __name__ == "__main__":
    main()
