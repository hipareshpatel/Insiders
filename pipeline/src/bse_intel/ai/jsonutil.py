"""Turn raw model output into a JSON object, tolerating the usual wrappers."""

from __future__ import annotations

import json
import re

_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def strip_reasoning(text: str) -> str:
    """Drop <think> blocks emitted by reasoning models (DeepSeek-R1 and similar)."""
    text = _THINK.sub("", text)
    lower = text.lower()
    if "</think>" in lower:  # the opening tag was part of the prompt template: keep only the answer
        text = text[lower.rindex("</think>") + len("</think>"):]
    elif "<think>" in lower:  # unterminated: the answer never started
        text = text[: lower.index("<think>")]
    return text.strip()


# UTF-8 read as cp1252 somewhere on a provider's side: "â‚¹519.4 Cr" for "₹519.4 Cr". It reached five cards and,
# through memory's timeline, the prompts of later filings, which copied it (2026-10-18). Only these sequences
# are put back: a reply may mix them with correct text, so the whole reply cannot be re-decoded.
_MOJIBAKE = {
    "â‚¹": "₹",   # ₹
    "â€™": "’", "â€˜": "‘",   # ’ ‘
    "â€œ": "“", "â€\u009d": "”", "â€\u009c": "“",   # “ ”
    "â€“": "–", "â€”": "—", "â€¦": "…",   # – — …
    "Â ": " ",
}
_MOJIBAKE_RE = re.compile("|".join(re.escape(k) for k in sorted(_MOJIBAKE, key=len, reverse=True)))


def repair_mojibake(text: str) -> str:
    return _MOJIBAKE_RE.sub(lambda m: _MOJIBAKE[m.group(0)], text) if "â" in text or "Â" in text else text


def extract_json_object(text: str) -> dict:
    """Return the first complete top-level JSON object found in ``text``."""
    if not text:
        raise ValueError("empty response")
    text = repair_mojibake(strip_reasoning(text))
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    while start != -1:
        end = _matching_brace(text, start)
        if end is None:
            break
        try:
            value = json.loads(text[start : end + 1])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
        start = text.find("{", start + 1)
    raise ValueError("no JSON object in response")


def _matching_brace(text: str, start: int) -> int | None:
    depth, in_string, escaped = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return None
