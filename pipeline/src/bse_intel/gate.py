"""The accuracy gate: cheap, deterministic checks that run on a card after the model and before it is
published. Each one answers a failure the card-vs-PDF audit found (docs/audit/), taken from the way a
reference repo keeps wrong figures off its cards (docs/REFERENCE_REVIEW.md): the model proposes, code
rejects. A failed check never hides a card; it marks it for review with the reason (D9).

Pure functions, so each has a regression test named after the real filing that failed.
"""

from __future__ import annotations

import re
from pathlib import Path

# --- garbled text (a bad scan or OCR layer): every figure read from it is suspect -------------------------------------

# A digit run with a stray letter inside or at its end ("2J9,51o", "1O5.4", "4,l35"): the letters an OCR mistakes for digits.
_GARBLED_TOKEN = re.compile(r"^\(?-?(?:\d[\d,.]*[oOIlJSB][\d,.]*\d|\d[\d,.]*\d[oOIlJ]|[oOIl]\d[\d,.]*\d)\)?$")
_DIGIT_TOKEN = re.compile(r"^\(?-?[\d,.oOIlJSB]*\d[\d,.oOIlJSB]*\)?$")
# Calibrated on the audited filings: every one with 3+ such tokens at 0.25% or more of its numbers had wrong
# figures (the reference repo's 25 tokens and 4% flags none of ours).
GARBLED_MIN_TOKENS = 3
GARBLED_SHARE = 0.0025


def text_is_garbled(text: str | None) -> bool:
    """At least GARBLED_MIN_TOKENS number-like tokens with letters inside, and at least GARBLED_SHARE of all
    number-like tokens: the text layer is unreliable, so figures read from its tables may be wrong."""
    tokens = [t.strip(".,;:") for t in (text or "").split()]
    numeric = [t for t in tokens if _DIGIT_TOKEN.match(t)]
    garbled = [t for t in numeric if _GARBLED_TOKEN.match(t)]
    return len(garbled) >= GARBLED_MIN_TOKENS and len(garbled) >= GARBLED_SHARE * max(len(numeric), 1)


# --- amounts that cannot be crore ------------------------------------------------------------------------------------

# ₹1 crore = 1e7 rupees; no listed company's single figure reaches 1e7 crore (₹10 trillion). A number that large
# followed by "Cr" is a rupee figure written in full ("299,99,99,852") that kept the word crore.
_CRORE_NUMBER = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(?:cr\b|crores?\b)", re.I)
MAX_CRORE = 1e7


def impossible_crore_amounts(texts: list[str]) -> list[str]:
    out = []
    for text in texts:
        for m in _CRORE_NUMBER.finditer(text or ""):
            try:
                value = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if value >= MAX_CRORE and m.group(1) not in out:
                out.append(m.group(1))
    return out


# --- a deal "size" that is really a company figure -------------------------------------------------------------------

def deal_is_company_figure(amount_cr: float | None, dossier: dict | None, tolerance: float = 0.01) -> str | None:
    """The deal amount equals the company's own revenue, net worth or paid-up capital within `tolerance`
    (turnover, net worth and share capital are never the size of an order or a raise). Returns the figure's
    name, else None."""
    if not amount_cr or amount_cr <= 0 or not dossier:
        return None

    def same(value) -> bool:
        return bool(value) and abs(float(value) - amount_cr) <= tolerance * amount_cr

    for m in dossier.get("financial_metrics", []):
        if m.get("metric") in ("revenue", "net_worth", "paid_up_capital", "total_income") and same(m.get("value")):
            return f"{m['metric']} {m.get('period', '')}".strip()
    for sheet in dossier.get("balance_sheet", []):
        if same(sheet.get("net_worth_cr")):
            return f"net worth {sheet.get('period', '')}".strip()
    return None


# --- a terminated deal is not a live one -----------------------------------------------------------------------------

_TERMINATED = re.compile(r"\b(?:terminat\w+|cancel\w*|withdr[ae]w\w*|rescind\w*|called off|abandon\w*|lapse[ds]?)\b", re.I)


def is_terminated(headline: str | None, subject: str | None = None) -> bool:
    return bool(_TERMINATED.search(f"{headline or ''} {subject or ''}"))


# --- an issue size that does not follow from its shares and price ----------------------------------------------------

def issue_size_mismatch(amount_cr: float | None, new_shares: float | None, issue_price: float | None,
                        low: float = 0.5, high: float = 2.0) -> str | None:
    """A fundraise's stated size against new shares x issue price (₹ crore). Outside 0.5x to 2x is a unit slip
    or a different quantity (a warrant's upfront 25%, a rights partly paid up), so it is flagged, never fixed."""
    if not amount_cr or not new_shares or not issue_price or amount_cr <= 0:
        return None
    implied = new_shares * issue_price / 1e7
    ratio = amount_cr / implied
    if low <= ratio <= high:
        return None
    return f"issue size ₹{amount_cr:,.2f} Cr but {new_shares:,.0f} shares at ₹{issue_price:,.2f} is ₹{implied:,.2f} Cr"


# --- the human hold list ---------------------------------------------------------------------------------------------

def load_holds(path: Path | None) -> dict[str, str]:
    """`news_id | reason` per line (`#` comments and blank lines ignored). A card named here is published with
    "held after review: <reason>" and marked for review; the stored analysis is untouched. A malformed line
    raises, so a typo cannot silently drop a hold."""
    holds: dict[str, str] = {}
    if not path or not Path(path).exists():
        return holds
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        news_id, sep, reason = (part.strip() for part in line.partition("|"))
        if not sep or not news_id or not reason:
            raise ValueError(f"{path}:{number}: expected 'news_id | reason', got {line!r}")
        holds[news_id] = reason
    return holds
