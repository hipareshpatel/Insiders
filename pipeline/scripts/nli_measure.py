"""Would a small local NLI model catch the cards an audit found wrong? A measurement, not a pipeline step.

Each sentence a card states is paired with the filing text it rests on - its own quote where it carries
one (what_happened since D23; key_numbers, why_it_matters and notable_changes since the quote contract),
otherwise the three-sentence window of the filing that shares most words with it (the headline, the
takeaway) - and an NLI model says whether that text entails the sentence. A card is flagged when any of
its sentences is not entailed. The flags are then set against an audit round's verdicts.

It targets what the number checks cannot see: a stage read as done ("agreed to acquire, subject to CCI
approval" written as "acquired"), an open offer written as a fundraise, an invented party. On 20 pairs
built from those audit findings (2026-10-17, scratch test), MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli
caught 18 of 20 misreadings and flagged none of 20 faithful paraphrases at 0.15 s a pair; the xsmall
model the dissertation repo uses caught 11. Real card sentences are longer than those paraphrases, which
is what this script is for.

Decision rule, fixed before the run: worth wiring in if it flags at least 40% of the WRONG cards the code
did not already flag, while flagging at most 15% of the OK cards. Otherwise it is removed.

Setup (not a pipeline dependency; about 1 GB with CPU torch):
    pip install torch --index-url https://download.pytorch.org/whl/cpu
    pip install transformers sentencepiece protobuf
Usage, on an audit export (scripts/audit_export.py) and its round file:
    python -I -X utf8 scripts/nli_measure.py AUDIT_EXPORT_DIR ../docs/audit/round-1.json [--threshold 0.5]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict
from typing import Callable, Iterable

MODEL = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
QUOTED = ("what_happened", "why_it_matters", "key_numbers", "notable_changes")
UNQUOTED = ("headline", "takeaway", "core_catalyst")
_WORD = re.compile(r"[a-z0-9]+")
_SENT = re.compile(r"(?<=[.;:])\s+|\n{2,}")


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2}


def _claim(field: str, item) -> str | None:
    """The sentence a card states for one item of a field."""
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return None
    if field == "key_numbers":
        return " ".join(str(item.get(k) or "") for k in ("label", "value", "change")).strip() or None
    if field == "notable_changes":
        parts = [item.get("metric"), item.get("previous") and f"from {item['previous']}",
                 item.get("current") and f"to {item['current']}", item.get("why")]
        return " ".join(str(p) for p in parts if p) or None
    return item.get("text")


def window(text: str, claim: str, size: int = 3) -> str:
    """The run of `size` sentences in the filing that shares most words with the claim."""
    sentences = [s.strip() for s in _SENT.split(text) if s.strip()]
    if not sentences:
        return ""
    want = _words(claim)
    best, best_at = -1, 0
    for at in range(len(sentences)):
        got = len(want & _words(" ".join(sentences[at:at + size])))
        if got > best:
            best, best_at = got, at
    return " ".join(sentences[best_at:best_at + size])[:2000]


def pairs(card: dict, filing_text: str) -> list[tuple[str, str, str]]:
    """(field, premise, hypothesis) for every sentence the card states."""
    out = []
    for field in QUOTED:
        for item in card.get(field) or []:
            claim = _claim(field, item)
            if not claim:
                continue
            quote = item.get("quote") if isinstance(item, dict) else None
            out.append((field, quote or window(filing_text, claim), claim))
    for field in UNQUOTED:
        if card.get(field):
            out.append((field, window(filing_text, str(card[field])), str(card[field])))
    return [p for p in out if p[1]]


def code_flagged(card: dict) -> bool:
    """Whether the pipeline's own checks already marked the card (held, unresolved or needing review)."""
    review = card.get("review") or {}
    grounding = card.get("grounding") or {}
    return bool(review.get("status") in ("UNRESOLVED", "FAILED") or grounding.get("ungrounded")
                or grounding.get("unsupported_claims") or grounding.get("math_mismatches"))


def measure(cards: Iterable[tuple[str, dict, str]], verdicts: dict[str, dict],
            entail: Callable[[str, str], float], threshold: float) -> dict:
    """Card-level flags against the audit's verdicts. `entail(premise, hypothesis)` is P(entailment)."""
    by_verdict: dict[str, Counter] = defaultdict(Counter)
    by_class: dict[str, Counter] = defaultdict(Counter)
    worst: list[tuple[float, str, str, str, str]] = []
    for news_id, card, text in cards:
        audit = verdicts.get(news_id)
        if not audit:
            continue
        scored = [(entail(premise, claim), field, premise, claim) for field, premise, claim in pairs(card, text)]
        flagged = any(score < threshold for score, *_ in scored)
        verdict = audit["verdict"]
        tally = by_verdict[verdict]
        tally["cards"] += 1
        tally["flagged"] += flagged
        tally["pairs"] += len(scored)
        tally["pairs_flagged"] += sum(score < threshold for score, *_ in scored)
        if verdict == "WRONG" and not code_flagged(card):
            tally["missed_by_code"] += 1
            tally["missed_by_code_flagged"] += flagged
        for cls in {i.get("class") for i in audit.get("issues", [])}:
            by_class[cls]["cards"] += 1
            by_class[cls]["flagged"] += flagged
        worst += [(score, verdict, news_id, field, claim) for score, field, _, claim in scored if score < threshold]
    return {"by_verdict": by_verdict, "by_class": by_class, "worst": sorted(worst)[:25]}


def decide(result: dict) -> tuple[bool, str]:
    ok, wrong = result["by_verdict"].get("OK", Counter()), result["by_verdict"].get("WRONG", Counter())
    ok_rate = ok["flagged"] / ok["cards"] if ok["cards"] else 1.0
    missed = wrong["missed_by_code"]
    caught = wrong["missed_by_code_flagged"] / missed if missed else 0.0
    useful = caught >= 0.40 and ok_rate <= 0.15
    return useful, (f"flags {caught:.0%} of the {missed} WRONG cards the code missed and {ok_rate:.0%} of "
                    f"{ok['cards']} OK cards: {'worth wiring in' if useful else 'not worth it; remove'}")


def report(result: dict, threshold: float) -> str:
    lines = [f"## NLI measurement (flag when P(entailment) < {threshold})", "",
             "| Verdict | Cards | Flagged | Sentences | Sentences flagged |", "|---|---|---|---|---|"]
    for verdict in ("OK", "MINOR", "WRONG"):
        t = result["by_verdict"].get(verdict, Counter())
        if t["cards"]:
            lines.append(f"| {verdict} | {t['cards']} | {t['flagged']} ({t['flagged'] / t['cards']:.0%}) | "
                         f"{t['pairs']} | {t['pairs_flagged']} |")
    lines += ["", "| Issue class | Cards | Flagged |", "|---|---|---|"]
    for cls, t in sorted(result["by_class"].items(), key=lambda kv: -kv[1]["cards"]):
        lines.append(f"| {cls} | {t['cards']} | {t['flagged']} ({t['flagged'] / t['cards']:.0%}) |")
    lines += ["", f"Decision: {decide(result)[1]}", "", "Lowest-scoring sentences:"]
    lines += [f"- {score:.2f} {verdict} {news_id[:8]} {field}: {claim[:110]}"
              for score, verdict, news_id, field, claim in result["worst"]]
    return "\n".join(lines) + "\n"


def load_export(root: pathlib.Path) -> Iterable[tuple[str, dict, str]]:
    for card_file in sorted(root.rglob("*.card.json")):
        news_id = card_file.name[: -len(".card.json")]
        text_file = card_file.with_name(f"{news_id}.pdf.txt")
        text = text_file.read_text(encoding="utf-8") if text_file.exists() else ""
        yield news_id, json.loads(card_file.read_text(encoding="utf-8")), text


def model_scorer(name: str) -> Callable[[str, str], float]:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModelForSequenceClassification.from_pretrained(name).eval()
    entailment = {v.lower(): k for k, v in model.config.id2label.items()}["entailment"]

    def entail(premise: str, hypothesis: str) -> float:
        with torch.no_grad():
            logits = model(**tok(premise, hypothesis, return_tensors="pt", truncation=True, max_length=512)).logits
        return float(logits.softmax(-1)[0][entailment])

    return entail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("export_dir")
    ap.add_argument("round_file")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--report")
    args = ap.parse_args()
    verdicts = {row["news_id"]: row for row in json.loads(pathlib.Path(args.round_file).read_text(encoding="utf-8"))}
    result = measure(load_export(pathlib.Path(args.export_dir)), verdicts, model_scorer(args.model), args.threshold)
    text = report(result, args.threshold)
    print(text)
    if args.report:
        pathlib.Path(args.report).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
