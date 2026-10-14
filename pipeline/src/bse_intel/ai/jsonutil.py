"""Turn raw model output into a JSON object, tolerating the usual wrappers."""

from __future__ import annotations

import json
import re

_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def strip_reasoning(text: str) -> str:
    """Drop <think> blocks emitted by reasoning models (DeepSeek-R1 and similar)."""
    text = _THINK.sub("", text)
    if "<think>" in text.lower():  # unterminated: the answer never started
        text = text[: text.lower().index("<think>")]
    return text.strip()


def extract_json_object(text: str) -> dict:
    """Return the first complete top-level JSON object found in ``text``."""
    if not text:
        raise ValueError("empty response")
    text = strip_reasoning(text)
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
