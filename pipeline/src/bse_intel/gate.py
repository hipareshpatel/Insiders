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

def deal_is_company_figure(amount_cr: float | None, dossier: dict | None, tolerance: float = 0.002) -> str | None:
    """The deal amount equals the company's own revenue, net worth or paid-up capital within `tolerance`
    (turnover, net worth and share capital are never the size of an order or a raise). The tolerance is a
    rounding (0.2%): SML's computed ₹554.65 Cr deal sat 0.9% from a quarter's revenue of ₹549.71 Cr by chance.
    Returns the figure's name, else None."""
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


# --- a claim must be the filing's own words -------------------------------------------------------------------------

_SOFT = {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " ",
         # ligature glyphs a PDF's text layer keeps ("quick-seƫng", "EﬀecƟve"; audit round 2, dropped_facts.md)
         "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "Ɵ": "ti", "ƫ": "tti"}
_PAGE_BREAK = re.compile(r"-{3}\s*page \d+(?: of \d+)?\s*-{3}")
_LINE_HYPHEN = re.compile(r"(?<=[a-z])- (?=[a-z])")


def _flat(text: str) -> str:
    """Lower case, straight quotes and dashes, one space between words: a PDF's line breaks and double
    spaces must not decide whether a quote is in the filing, nor a word broken at a line end ("Long- term")
    or a sentence running across a page break."""
    for bad, good in _SOFT.items():
        text = text.replace(bad, good)
    flat = _PAGE_BREAK.sub(" ", " ".join(text.lower().split()))
    return " ".join(_LINE_HYPHEN.sub("-", flat).split())


_ELISION = re.compile(r"\[\s*(?:\.\.\.|…)\s*\]|\.\.\.|…")


def quote_found(quote: str | None, text: str, *readings: str) -> bool:
    """The quote appears in the filing, ignoring case, spacing and smart punctuation. A quote joined
    with "..." or "[...]" must have every part present, in order.

    `readings` are the same pages read another way. A page set in two columns, or as a table whose cells
    run to several lines, is read line by line across all of them, so the left cell's words land inside
    the right cell's sentence ("...SPA 1 Sale Shares from the agreement (in brief). Seller 1 to the
    Purchaser..."); the model quotes the sentence the page prints and it is not in that reading (SML's
    share purchase agreements, loop rounds 3a-3b, 2026-10-17). Read block by block, the cell is whole.
    A quote must still be one reading's own words, contiguous: nothing is skipped to make it fit."""
    if not quote:
        return False
    parts = [p for p in _ELISION.split(quote) if p.strip()]
    for haystack in (_flat(t) for t in (text, *readings) if t):
        at = 0
        for part in parts:
            found = haystack.find(_flat(part), at)
            if found == -1:
                break
            at = found + 1
        else:
            return bool(parts)
    return False


NEAR_QUOTE = 0.9   # share of a quote's words that must stand in order in one place of the filing


def quote_near(quote: str | None, text: str, *readings: str) -> str | None:
    """The filing's own sentence a quote copies with small differences, or None.

    Models quote with a word dropped or changed: "Twenty Eight Thousand Fifty Six" for the PDF's "Twenty
    Eight Thousand and Fifty Six", "Lakhs" for "Lakh", "the provisions of the SEBI" for "the SEBI (LODR)"
    (Novartis's and SML's offer letters, loop round 3a). Held as quotes "not in the filing", their cards were
    kept out of the feed with every figure right. Here at least 90% of the quote's words (and at least six)
    must stand in order in one place of one reading; the span they cover is returned, so a figure can still
    be asked to be in that one sentence rather than anywhere in the filing.

    What may differ is wording only. Not a word that turns the sentence round ("has not approved"), not a
    figure (a quote carrying 5,349 where the filing has none, or leaving out the figures between - a table's
    "8.0% 9.2%"), and not more than a few of the filing's words left out: an elision is marked with "...".
    The same number written two ways (92,72,997 and 9272997), a lost rupee sign and a margin's line number
    are not differences (all seen on the loop's cards, 2026-10-18)."""
    import difflib

    words = _norm(_flat(_ELISION.sub(" ", quote or "")).split())[0]
    if len(words) < 6:
        return None
    need = NEAR_QUOTE * len(words)
    for reading in (t for t in (text, *readings) if t):
        printed = _flat(reading).split()
        hay, where = _norm(printed)
        starts = {i for i in range(len(hay) - 2) if hay[i:i + 3] == words[:3]}
        ends = {i for i in range(len(hay) - 2) if hay[i:i + 3] == words[-3:]}
        anchors = sorted(starts | {max(0, e - len(words)) for e in ends})
        for a in anchors[:50]:
            low = max(0, a - 3)
            window = hay[low:a + int(len(words) * 1.3) + 3]
            blocks = difflib.SequenceMatcher(None, words, window, autojunk=False).get_matching_blocks()
            if sum(b.size for b in blocks) < need:
                continue
            used = [b for b in blocks if b.size]
            span = window[used[0].b:used[-1].b + used[-1].size]
            in_quote = {i for b in used for i in range(b.a, b.a + b.size)}
            in_span = {i for b in used for i in range(b.b - used[0].b, b.b - used[0].b + b.size)}
            dropped = [w for i, w in enumerate(words) if i not in in_quote]      # the quote's, not the filing's
            skipped = [w for i, w in enumerate(span) if i not in in_span]       # the filing's, left out
            if set(dropped + skipped) & _TURNING:
                continue
            if any(_has_digit(w) for w in dropped) or any(_has_digit(w) and not (w.isdigit() and len(w) <= 2)
                                                          for w in skipped):
                continue
            if len(skipped) > max(3, 0.15 * len(words)):
                continue
            first, last = where[low + used[0].b], where[low + used[-1].b + used[-1].size - 1]
            return " ".join(printed[first:last + 1])
    return None


SCATTERED_SHARE = 0.95   # of a quote's words that must stand inside one short window of the page


def quote_scattered(quote: str | None, text: str, *readings: str) -> str | None:
    """The stretch of a page whose words a quote uses in another order, or None.

    In a two-column disclosure table (a SEBI annexure, a rating table, an NCD listing) the text layer wraps the label
    cell and the value cell over several lines and interleaves them, and the model quotes the cell unwrapped, as a
    clean sentence: every word is on the page, in a different order. 117 of 157 quotes held as "not in the filing"
    had all their words in it (held-card analysis, 2026-10-20: HomeFirst's NCD listing, Hester's "INR 10.50 million",
    Balaji Amines's rating table, Newgen's "3 Years"). Here 95% of the quote's words (at least six), and every figure in
    it as an exact token, must fall inside a window of the page at most twice the quote's length; that window is
    returned, so a card's figure is still asked to be in it. A turning word ("not") the window lacks fails it."""
    from collections import Counter

    words = _norm(_flat(_ELISION.sub(" ", quote or "")).split())[0]
    if len(words) < 6:
        return None
    want = Counter(words)
    figures = {w for w in words if _has_digit(w)}
    turning = {w for w in words if w in _TURNING}
    size = 2 * len(words)
    for reading in (t for t in (text, *readings) if t):
        printed = _flat(reading).split()
        hay, where = _norm(printed)
        have = Counter()
        for i, w in enumerate(hay):
            have[w] += 1
            if i >= size:
                have[hay[i - size]] -= 1
            if w not in want or i + 1 < min(size, len(words)):
                continue
            covered = sum(min(n, have[k]) for k, n in want.items())
            if covered < SCATTERED_SHARE * len(words):
                continue
            if any(have[f] < 1 for f in figures) or any(have[t] < 1 for t in turning):
                continue
            low = max(0, i - size + 1)
            # The order of a table's figures carries its period or its row: "5.93 5.53" for the page's "5.53 5.93"
            # made FY26 a Q1FY26, and "61.5% from 59.6%" took a chart's bars for quarters (independent check of
            # 24 figures this rule accepted, 2026-10-20: 3 wrong, all this). The quote's figures keep the page's order.
            if not _in_order([w for w in words if _has_digit(w)], [w for w in hay[low:i + 1] if _has_digit(w)]):
                continue
            return " ".join(printed[where[low]:where[i] + 1])
    return None


def _in_order(seq: list[str], hay: list[str]) -> bool:
    """Whether `seq` is a subsequence of `hay` (each in turn, later than the one before)."""
    it = iter(hay)
    return all(any(x == y for y in it) for x in seq)


def _has_digit(word: str) -> bool:
    return any(c.isdigit() for c in word)


def _norm(words: list[str]) -> tuple[list[str], list[int]]:
    """Words compared as words: without the punctuation around them ("only)." is "only"), a number without
    its grouping commas (92,72,997 is 9272997), a rupee sign left out. With each one's place in `words`."""
    out, where = [], []
    for i, w in enumerate(words):
        t = w.strip(".,;:()[]'\"_")
        if not t or t in ("₹", "`"):
            continue
        out.append(t.replace(",", "") if _has_digit(t) else t)
        where.append(i)
    return out, where


_TURNING = {"not", "no", "nil", "never", "neither", "nor", "none", "without", "except", "excluding", "unless",
            "subject", "cannot", "can't", "won't", "didn't", "doesn't", "isn't", "wasn't", "shall", "may",
            "might", "proposed", "intends", "approved", "rejected", "withdrawn", "terminated", "cancelled"}


_CLAIM_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_PERIOD_LABEL = re.compile(r"\b(?:q[1-4]|h[12]|9m)?fy\s?'?\d{2,4}\b|\b(?:19|20)\d{2}\b|\bq[1-4]\b", re.I)
# A date written out in figures (16.12.2025, 05/01/26): with the year taken off as a period label the day and month
# were left as an amount, 16.12 (SML Mahindra's ROC order, 2026-10-18).
_WRITTEN_DATE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-](?:\d{4}|\d{2})\b")


def numbers_in_quote(claim: str, quote: str, unit: int | None = None) -> list[str]:
    """Numbers written in the claim that its own quote does not carry (4.5 never matches 45), so a fact
    cannot borrow a figure from elsewhere in the filing. A figure rounded to the card's own last digit is the
    quote's ("952" of "951.96"); a prefix is not ("95" of "951.96" is a tenth of it).

    `unit` is what the filing says its figures are in, as a divisor to crore (100 for lakh, 10 for
    million); plain rupees are always tried too, since a notice writes the amount out in full. A card writes crore and an Indian statement writes lakh, so without it a right reading was
    reported as missing: "16.53 Cr" is the quoted row's own "1,653". Dividing by the stated unit also
    keeps the check that matters - "458 Cr" of a row reading 457.86 million is the ten-times misreading
    and is still refused, because 45.79 is what that row says.

    Period labels are not figures either, nor are percentages: a row prints the two amounts, not the
    change between them, which grounding checks against the whole filing anyway. "FY25 revenue rose
    6.3% YoY to Rs 356.27 Cr" was reported as stating 25, 6.3 and 356.27 - none of them wrong - and on
    2026-10-17 this was the commonest single reason a card was held back from the feed.
    """
    if not quote:
        return []
    flat_quote = _SPACED_THOUSANDS.sub(r"\1\2", _DECIMAL_COMMA.sub(r"\1.\2", _flat(quote)))
    found = [m.group(0).replace(",", "") for m in _CLAIM_NUMBER.finditer(flat_quote)]
    digits = set(found)
    # Each quoted figure in crore at every unit it may be in: the unit written after it ("Rs. 1.09 lakh"),
    # else the unit the filing declares, and plain rupees, because a notice writes the amount out in full
    # ("Rs.50,10,05,632") where the card writes Rs 50.10 Cr. `as_printed` keeps the figure as it stands, for
    # a card figure with no money unit (a per-share amount, a count) and for a filing that declares none.
    # Each quoted figure also carries its own rounding, in crore: a presentation's "2,123" is the tagged ₹2,122.50
    # Cr rounded (Jubilant, 2026-10-18). Only for a figure of three or more digits - a note number ("23") is not
    # a rounded amount.
    in_crore, as_printed = [], []
    for m in _CLAIM_NUMBER.finditer(flat_quote):
        raw = m.group(0).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        rounding = 0.5 * 10 ** -len(raw.partition(".")[2]) if len(raw.replace(".", "").lstrip("0")) >= 3 else 0.0
        # its own unit: written after it ("1.09 lakh"), or in the name before it, as the XBRL table's
        # balance-sheet line writes crore ("net_debt_cr 1348.6")
        own = _unit_after(flat_quote, m.end()) or (1 if re.search(r"_cr\s*:?\s*$", flat_quote[:m.start()]) else None)
        in_crore += [(value / s, rounding / s) for s in ([own] if own else [s for s in (unit, 1e7) if s and s > 1])]
        if own is None and not (unit and unit > 1):
            in_crore.append((value, rounding))
        as_printed.append((value, rounding))
    missing = []
    flat_claim = _PERIOD_LABEL.sub(" ", _WRITTEN_DATE.sub(" ", _flat(claim)))
    for m in _CLAIM_NUMBER.finditer(flat_claim):
        after = flat_claim[m.end():m.end() + 14].lstrip()
        if after.startswith(("bps", "bp ", "bp,", "bp.", "pp", "basis point", "percentage point")):
            continue  # a change in a ratio, not a figure the row prints: "+56 bps" off 9.78% and 9.22%
        if after.startswith("%"):
            continue  # a percentage follows from the row's own figures rather than being printed in it,
            # and grounding already checks one against the whole filing, stated or derived
        value = m.group(0).replace(",", "")
        card_unit = _unit_after(flat_claim, m.end())
        if card_unit is not None and _FOREIGN.search(flat_claim[max(0, m.start() - 8):m.start()]):
            card_unit = None   # "EUR 9.7 million" is the euro amount as written, not rupees (eMudhra's Cryptas)
        # The same digits only count when the card wrote no unit: "₹3,595 Cr" is not the 3,595 of a statement
        # in million, and "458 Cr" is not "4583" (Jubilant FY25, loop round 3c).
        if card_unit is None and (value in digits or any(d.startswith(value) or value.startswith(d) for d in digits)):
            continue
        try:
            number = float(value)
        except ValueError:
            continue
        decimals = len(value.partition(".")[2])
        if not decimals and number <= 31:
            continue  # a day of the month, a count of directors: grounding leaves these alone too
        # A figure rounded to the card's own last digit is that figure: "₹952 Cr" of a row reading 951.96,
        # "₹1.1 lakh" of a demand of 1.09 lakh. Only a prefix used to count ("95" of "951.96"), so a figure
        # rounded up was held as missing. The unit still has to be right: a card amount in crore, lakh or
        # million is compared in crore, and "458 Cr" of a row reading 457.86 million is still refused.
        # And a figure cut at the card's last digit is that figure too: "₹554 Cr" of ₹554.65 Cr, "₹79 Cr" of
        # 796 million (2026-10-18). Not one rounded the wrong way by more than half a digit.
        tolerance, step = 0.5 * 10 ** -decimals, 10 ** -decimals
        scale = card_unit or 1
        candidates = in_crore if card_unit is not None else in_crore + as_printed
        target = number / scale
        if any(abs(c - target) <= max(tolerance / scale, r) + 1e-12 or 0 <= abs(c) - abs(target) < step / scale
               for c, r in candidates):
            continue
        missing.append(m.group(0))
    return missing


# How OCR and a press release write a figure: "95028,10" for 95,028.10 (a last group of two digits is no
# thousands group), "INR 1 885.6 million" for 1,885.6 (Ahluwalia's segment row, eMudhra's cash; 2026-10-18)
_DECIMAL_COMMA = re.compile(r"(?<![\d,])(\d{3,}),(\d{2})(?![\d,.])")
_SPACED_THOUSANDS = re.compile(r"((?:inr|rs\.?|₹|usd|us\$|eur|€)\s*\d{1,3}) (\d{3})(?=[.,]\d|\b)")
_FOREIGN = re.compile(r"(?:eur|euro|euros|usd|us\$|\$|€|gbp|£|jpy|¥|chf|aed|sgd)\s*$")


_UNIT_WORD = re.compile(r"\s*(crores?|cr\b|lakhs?|lacs?|millions?|mn\b|billions?|bn\b|thousands?)")
_PER_CRORE = {"crore": 1, "cr": 1, "lakh": 100, "lac": 100, "million": 10, "mn": 10, "billion": 0.01, "bn": 0.01,
              "thousand": 10_000}


def _unit_after(flat: str, end: int) -> float | None:
    """The money unit written right after a figure in lower-cased text, as figures per ₹ crore."""
    m = _UNIT_WORD.match(flat, end)
    if not m:
        return None
    word = m.group(1)
    return _PER_CRORE.get(word, _PER_CRORE.get(word[:-1]))


SAME_BLOCK = 2000  # characters either side of the quote: about one statement table, not the document


def figures_in_same_block(missing: list[str], quote: str, text: str, unit: int | None = None,
                          claim: str = "", window: int = SAME_BLOCK) -> tuple[list[str], list[str]]:
    """Split figures a quote does not carry into those the same table does, and the rest.

    A card sentence naturally draws on more than one row - revenue and the profit below it, this
    quarter beside last - while it quotes the row it is mainly about. Holding the card for the second
    figure was the commonest complaint left on 2026-10-17, and almost every one was right.

    The window is the table around the quote, not the whole filing: document-wide is the weak test the
    quote contract was written to replace, where an invented whole-crore figure lands on an unrelated
    line 40% of the time (test_cards.py). A figure from a sibling row is reported, not held; one that
    is nowhere near the quote is still a hold.
    """
    if not missing or not text or not quote:
        return list(missing), []
    flat = _flat(text)
    first = _flat(re.split(r"\.\.\.|…", quote)[0].strip())
    at = flat.find(first) if first else -1
    if at == -1:
        return list(missing), []
    block = flat[max(0, at - window):at + len(first) + window]
    # Each figure with the unit the card wrote after it, so it is compared in crore: Jubilant's "₹3,595 Cr"
    # passed against a statement's 3,595 million (₹359.5 Cr) while the digits alone were compared.
    still, siblings = [], []
    for raw in missing:
        (still if numbers_in_quote(_with_unit(claim, raw), block, unit) else siblings).append(raw)
    return still, siblings


def _with_unit(claim: str, raw: str) -> str:
    """A figure as the card wrote it, with the money unit after it ("3,595 cr")."""
    said = _flat(_PERIOD_LABEL.sub(" ", claim or ""))
    at = said.find(raw.lower())
    word = _UNIT_WORD.match(said, at + len(raw)) if at != -1 else None
    return f"{raw} {word.group(1)}" if word else raw


def quote_unit(quote: str, text: str, unit: float | None = None) -> float | None:
    """The unit the quote's own table declares, where the document as a whole declares several (a deck in "Rs. In
    Mn." beside crore pages, an annual report in lakh beside crore notes); else the document's `unit`."""
    from .grounding import unit_before  # local: grounding does not import the gate

    words = re.findall(r"[^\W_]+|\d[\d,.]*", quote or "")[:8]
    if len(words) < 3 or not text:
        return unit
    m = re.search(r"\W+".join(re.escape(w) for w in words), text, re.I)
    here = unit_before(text, m.start()) if m else None
    return here if here is not None else unit


# A figure a fact sets its own against: "5.1% of the ₹7,794 Cr order book", "vs -₹0.44 Cr YoY", "narrowed from ₹50.19 Cr"
_COMPARED = re.compile(r"\b(?:vs|versus|against|compared (?:with|to)|from|over)\b|%\s*of\b|\bx\s+of\b|\btimes\b")


def compared_figures(missing: list[str], claim: str, memory: str, text: str, unit: float | None = None) -> list[str]:
    """The figures a fact compares its own with, where they are not in its quote but are the company's own known
    figures: in memory or the scale block the prompt gave (the order book, last year's loss, net worth), or in the
    filing to two decimals. A key number "5.1% of ₹7,794 Cr" quoting the order letter, or "EBITDA ₹19.88 Cr vs
    -₹0.44 Cr YoY" quoting the XBRL line, was held as stating a figure its quote does not (2026-10-18). Only a
    figure the fact itself marks as the comparison: "revenue of ₹845.89 Cr" stays held, since a wrong period's
    figure is in memory too."""
    flat = _flat(claim)
    out = []
    for raw in missing:
        at = flat.find(raw.lower())
        if at < 0 or not _COMPARED.search(flat[max(0, at - 35):at]):
            continue
        said = _with_unit(claim, raw)
        precise = len(raw.replace(",", "").partition(".")[2]) >= 2
        if (memory and not numbers_in_quote(said, memory)) or (precise and not numbers_in_quote(said, text, unit)):
            out.append(raw)
    return out


def stated_precisely(missing: list[str], claim: str, text: str, unit: int | None = None) -> list[str]:
    """The figures a sentence takes from another part of the filing that the filing states to their last digit.

    A sentence quotes the row it is about and leans on others: CSB's "provisions rose to ₹16.53 Cr (from a
    negative ₹4.54 Cr)" quotes the XBRL line, and the year-ago ₹4.54 Cr is the statement's (454) lakh, far
    down the page - a right card held (loop round 3c, 2026-10-18). Looked for in the whole filing, an invented
    figure lands on an unrelated line 40% of the time when it is a whole number but 3% at two decimals, and
    that was measured on a 563,458-character annual report (test_cards.py). So a figure written to two or more
    decimals and found at the right unit is reported, not held. Not for a key number or a notable change,
    whose figure must be on its own row."""
    found = []
    for raw in missing:
        if len(raw.replace(",", "").partition(".")[2]) >= 2 and not numbers_in_quote(_with_unit(claim, raw), text, unit):
            found.append(raw)
    return found


# --- a fact whose quote is not the filing's own words -----------------------------------------------------------------

_MONTHS = {m: i for i, names in enumerate(("jan january", "feb february", "mar march", "apr april", "may", "jun june",
                                            "jul july", "aug august", "sep sept september", "oct october",
                                            "nov november", "dec december"), 1) for m in names.split()}
_MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_DATE_DMY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:day of\s+)?" + _MONTH + r"\.?,?\s*(\d{4})\b", re.I)
_DATE_MDY = re.compile(r"\b" + _MONTH + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})\b", re.I)
_DATE_NUM = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b")
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_RATING = re.compile(r"\b(crisil|icra|care|ind|acuite|bwr|brickwork|ivr|infomerics)\s*\)?\s*(?:pp-?)?"
                     r"(a1\+?|a[2-4]\+?|aaa|aa[+-]?|a[+-]?|bbb[+-]?|bb[+-]?|b[+-]?|c|d)(?![\w+-])", re.I)


def _dates(text: str) -> set[tuple[int, int, int]]:
    found = set()
    for m in _DATE_DMY.finditer(text):
        found.add((int(m.group(3)), _MONTHS[m.group(2).lower()[:3] if m.group(2).lower()[:4] != "sept" else "sep"], int(m.group(1))))
    for m in _DATE_MDY.finditer(text):
        found.add((int(m.group(3)), _MONTHS[m.group(1).lower()[:3]], int(m.group(2))))
    for m in _DATE_NUM.finditer(text):
        found.add((int(m.group(3)), int(m.group(2)), int(m.group(1))))
    for m in _DATE_ISO.finditer(text):
        found.add((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    return {d for d in found if 1 <= d[1] <= 12 and 1 <= d[2] <= 31}


def _ratings(text: str) -> set[str]:
    return {f"{m.group(1).lower().replace('brickwork', 'bwr').replace('infomerics', 'ivr')} {m.group(2).lower()}"
            for m in _RATING.finditer(text)}


def unprinted_anchors(claim: str, text: str, unit: int | None = None, index=None) -> tuple[int, list[str]]:
    """The figures, dates and ratings a fact states, and those of them the filing does not print.

    When a fact's quote is not the filing's own words, its figures decide: audit round 2 found 50 of the 60
    facts the quote check dropped were true (dropped_facts.md). Their quotes were put together from a Reg 30
    table's cells, abbreviated, or copied from a damaged scan, and the old fallback looked only at amounts
    above 31, so a rating, a date, a percentage or a ₹6.98 Cr penalty could not save its fact. Each kind is
    checked here: a crore amount at the filing's declared unit, any other figure as printed, a date in any of
    the ways filings write one, a rating with its agency. Returns (how many there were, those not found)."""
    from .grounding import CRORE_SCALES, SourceIndex, _tokens   # local: grounding does not import the gate

    index = index or SourceIndex(text)
    claim = claim.replace("**", "")
    checked, missing = 0, []
    for value, decimals, pos, kind, raw in _tokens(claim):
        after = claim[pos + len(raw):pos + len(raw) + 8].lower()
        crore = re.match(r"\s*(?:cr\b|crores?\b)", after)
        if kind == "plain" and value <= 31 and decimals == 0:
            continue   # a count or a day of the month: dates are checked whole below
        checked += 1
        if crore:
            ok = index.stated_crore(value, decimals, plain_scales=(unit,) if unit else CRORE_SCALES)
        elif kind == "pct":
            ok = index.stated(value, decimals, scales=(1, 0.01))
        else:
            ok = index.stated(value, decimals, scales=(1,))
        if not ok:
            missing.append(raw)
    printed_dates = None
    for d in _dates(claim):
        checked += 1
        printed_dates = printed_dates if printed_dates is not None else _dates(text)
        if d not in printed_dates:
            missing.append(f"{d[2]:02d}.{d[1]:02d}.{d[0]}")
    said = _ratings(claim)
    if said:
        printed = _ratings(text)
        for r in said:
            checked += 1
            if r not in printed:
                missing.append(r.upper())
    return checked, missing


_NAME = re.compile(r"(?<![\w.&'-])([A-Z][\w&'.-]*[A-Za-z0-9])")
_NOT_NAMES = {"the", "this", "that", "these", "those", "its", "his", "her", "their", "company", "board", "bank", "order",
              "shareholders", "auditor", "director", "directors", "chairman", "managing", "independent", "non", "long",
              "short", "term", "rating", "ratings", "it", "he", "she", "they", "if", "on", "in", "of", "for", "and", "an",
              "pvt", "private", "ltd", "limited", "llp", "inc", "plc",
              "as", "at", "by", "with", "from", "under", "after", "before", "during", "post", "pre", "mr", "ms", "mrs", "dr"}


def unprinted_names(claim: str, text: str) -> tuple[int, list[str]]:
    """The names a fact with no figure gives - people, companies, places, agencies, instruments - and those the
    filing does not print. Of the 16 round-2 facts dropped with no figure, date or rating to check, 15 were true
    and their names were in the filing ("Dr. Muddana Sambasiva Rao", "Pierre Fabre", "Faridabad")."""
    flat = f" {_flat(text)} "
    names = []
    for m in _NAME.finditer(claim.replace("**", "")):
        word = m.group(1)
        if len(word) >= 3 and word.lower() not in _NOT_NAMES and (m.start() > 0 or word.isupper()):
            names.append(word)
    missing = [w for w in dict.fromkeys(names) if not re.search(r"(?<![a-z0-9])" + re.escape(_flat(w)) + r"(?![a-z0-9])", flat)]
    return len(names), missing


# --- a deal size taken from the wrong clause --------------------------------------------------------------------------

# Novartis India's SPA (Feb 2026) gave ₹660.09 Cr only as the instruments the seller subscribes to at Closing, set off
# against the price; the card called it the deal size. The real consideration (₹1,445.9 Cr) is the buyers' shares x price.
_SUB_AMOUNT = re.compile(r"\binstruments?\b|\bset[- ]?off\b|\bescrow\b|\bsubscribe\b|\bbank guarantee\b|\bsecurity deposit\b|"
                         r"\bearnest money\b|\bbreak fee\b|\btermination fee\b|\bindemnit", re.I)
_MAIN_AMOUNT = re.compile(r"\bconsideration\b|\bpurchase price\b|\bsale price\b|\btransaction value\b|\bdeal value\b|"
                          r"\benterprise value\b|\bvalued at\b|\bvaluation\b|\border value\b|\bcontract value\b|\bproject cost\b|"
                          r"\bissue size\b|\baggregating\b|\bworth\b", re.I)


def _sentence(text: str, start: int, end: int) -> str:
    left = max(text.rfind(". ", 0, start), text.rfind("\n\n", 0, start), text.rfind(";", 0, start))
    right_candidates = [i for i in (text.find(". ", end), text.find("\n\n", end), text.find(";", end)) if i != -1]
    return text[left + 1:(min(right_candidates) if right_candidates else len(text))]


def deal_amount_context(amount_cr: float | None, text: str | None) -> str | None:
    """Every place the deal amount appears in the filing sits in a sentence about instruments, set-off, escrow or
    a guarantee, and none says consideration, price or value: the amount is a sub-clause, not the deal size."""
    if not amount_cr or amount_cr <= 0 or not text:
        return None
    from .grounding import CRORE_SCALES, _tokens  # local: grounding does not import the gate

    found = []
    for value, _, pos, kind, raw in _tokens(text):
        if kind in ("pct", "bps", "pp", "x"):
            continue
        if any(abs(value / s - amount_cr) <= 0.005 * amount_cr for s in CRORE_SCALES):
            found.append(_sentence(text, pos, pos + len(raw)))
    if not found:
        return None
    if all(_SUB_AMOUNT.search(s) and not _MAIN_AMOUNT.search(s) for s in found):
        word = _SUB_AMOUNT.search(found[0]).group(0).lower()
        return f"₹{amount_cr:g} Cr appears in the filing only in a clause about {word}, not as the deal's consideration or value"
    return None


def tranche_total_cr(tranches: list, text: str | None) -> float | None:
    """Σ shares x price per share in ₹ crore, only when every tranche has both numbers and both are in the filing."""
    if not tranches or not text:
        return None
    from .grounding import SourceIndex

    index = SourceIndex(text)
    total = 0.0
    for t in tranches:
        if not t.shares or not t.price_per_share or not index.stated(float(t.shares), 0, (1,)) \
                or not index.stated(float(t.price_per_share), 2, (1,)):
            return None
        total += float(t.shares) * float(t.price_per_share) / 1e7
    return round(total, 2)


# --- a terminated deal is not a live one -----------------------------------------------------------------------------

_TERMINATED = re.compile(r"\b(?:terminat\w+|cancel\w*|withdr[ae]w\w*|rescind\w*|called off|abandon\w*|lapse[ds]?)\b", re.I)


def is_terminated(headline: str | None, subject: str | None = None) -> bool:
    return bool(_TERMINATED.search(f"{headline or ''} {subject or ''}"))


# --- a deal stage the filing's own words support (live review 3: 4 of 7 WRONG cards) ----------------------------------
_HOLDERS_APPROVED = re.compile(
    r"\b(?:approved|passed|assented|sanctioned)\b.{0,100}\b(?:shareholders?|members|equity\s+holders|creditors)\b"
    r"|\b(?:shareholders?|members)\b.{0,100}\b(?:approved|passed|assented)\b|requisite\s+majority", re.I | re.S)
_VOTE_TO_COME = re.compile(r"\b(?:will|shall)\s+be\s+(?:duly\s+)?(?:announced|declared|held|convened|placed)\b"
                           r"|\bto\s+be\s+(?:held|convened)\b|\bscheduled\s+(?:to\s+be\s+held|on|for)\b"
                           r"|\bnotice\s+(?:of|convening)\b.{0,60}\bmeeting\b", re.I | re.S)
_BOARD_APPROVED = re.compile(r"\bboard\b.{0,160}\b(?:approv\w*|accorded|consented|sanction\w*)\b"
                             r"|\b(?:approv\w*|sanction\w*)\b.{0,80}\bboard\b", re.I | re.S)


# A deal the filing says closes later: "the Scheme shall become effective and operative from November 01, 2026" (Dr.
# Agarwal's merger, filed 20 Oct, shown COMPLETED; live review 5). Measured on the 197 live COMPLETED deals of
# 14-20 Oct 2026: 3 match with no word of completion, all three not yet done (that merger, TVS Motor's NCLT-sanctioned
# merger "effective upon filing", ICICI Prudential Life's name change effective 23 Oct).
_CLOSES_LATER = re.compile(r"\b(?:shall|will)\s+(?:become|be)\s+(?:effective|operative|completed|consummated)\b|"
                           r"\b(?:is|are)\s+expected\s+to\s+(?:be\s+)?(?:complet|clos|consummat)\w*|"
                           r"\b(?:expected|likely|proposed)\s+(?:date\s+of\s+)?(?:completion|closing)\b", re.I)
_DONE = re.compile(r"\b(?:has|have)\s+(?:been\s+)?(?:completed|consummated|closed|become\s+effective)\b|"
                   r"\b(?:stands?|was|were|is)\s+(?:duly\s+)?(?:completed|consummated)\b|\bbecame\s+effective\b|"
                   r"\bcompletion\s+of\s+(?:the\s+)?(?:acquisition|transaction|sale|divestment|merger|amalgamation|allotment)\b|"
                   r"\b(?:allotted|acquired|commissioned)\b", re.I)


def supported_stage(stage: str | None, text: str) -> str | None:
    """The deal stage the filing's text supports: a shareholders' approval needs the vote's result, not its notice
    (Jubilant Agri's result "will be duly announced", JUBLCPL's meetings were weeks away); a board approval needs the
    board approving (ITC's chairman called a ₹20,000 Cr plan "proposed"). Steps down to what the text does say; with
    no text, the stage stands."""
    if not stage or not text:
        return stage
    if stage == "COMPLETED" and _CLOSES_LATER.search(text) and not _DONE.search(text):
        stage = "IN_PROGRESS"
    if stage == "SHAREHOLDER_APPROVED" and (not _HOLDERS_APPROVED.search(text) or _VOTE_TO_COME.search(text)):
        stage = "BOARD_APPROVED"
    if stage == "BOARD_APPROVED" and not _BOARD_APPROVED.search(text):
        stage = "PROPOSED"
    return stage


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


# --- a results statement that does not add up ----------------------------------------------------------------------------

# The names a reply uses for the lines a statement adds up, folded to one each.
_FOOTING_NAMES = {
    "revenue": "revenue", "revenue_from_operations": "revenue", "net_sales": "revenue", "sales": "revenue",
    "other_income": "other_income", "total_income": "total_income", "total_revenue": "total_income",
    "total_expenses": "total_expenses", "expenses": "total_expenses", "exceptional_items": "exceptional_items",
    "pbt": "pbt", "profit_before_tax": "pbt", "tax_expense": "tax_expense", "tax": "tax_expense",
    "total_tax": "tax_expense", "pat_continuing": "pat_continuing",
    "pat": "pat", "net_profit": "pat", "profit_after_tax": "pat", "profit_for_the_period": "pat",
}


def statement_footing(metrics) -> list[str]:
    """Results figures for one period that break the identities every results statement satisfies.

    A statement adds up by construction: total income is revenue plus other income, profit before tax
    is total income less total expenses (after any exceptional item), and profit after tax is that
    less tax. Figures read from a PDF that do not add up mean at least one was misread - a wrong
    column, a lakh read as crore, a dropped minus sign - and that needs no second document to see.

    Calibrated on 277 machine-tagged results files, figures known to be right: the three identities
    held 737 times out of 737 at this tolerance. The bank form (interest earned plus other income) was
    left out because it failed on 2 of 28 correct files.

    Reported, never corrected: which of the figures is wrong is not something the sum can say.
    """
    per: dict[str, dict[str, float]] = {}
    for m in metrics or []:
        name = _FOOTING_NAMES.get(str(getattr(m, "metric", "") or "").lower())
        if name and getattr(m, "value", None) is not None and getattr(m, "unit", "INR_CR") == "INR_CR":
            per.setdefault(m.period, {}).setdefault(name, float(m.value))
    problems = []
    for period, f in sorted(per.items()):
        def off(lhs: float, rhs: float) -> bool:
            # each printed line is rounded on its own, so a sum can miss by a little more than one line
            return abs(lhs - rhs) > max(0.06, 0.002 * max(abs(lhs), abs(rhs)))
        rev, oth, tot = f.get("revenue"), f.get("other_income"), f.get("total_income")
        if None not in (rev, oth, tot) and off(rev + oth, tot):
            problems.append(f"{period}: revenue {rev:,.2f} + other income {oth:,.2f} = {rev + oth:,.2f} Cr, "
                            f"but total income is given as {tot:,.2f} Cr")
        exp, pbt, ex = f.get("total_expenses"), f.get("pbt"), f.get("exceptional_items") or 0.0
        if None not in (tot, exp, pbt) and all(off(tot - exp + s * ex, pbt) for s in (1, -1, 0)):
            problems.append(f"{period}: total income {tot:,.2f} - total expenses {exp:,.2f} = {tot - exp:,.2f} Cr"
                            + (f" (exceptional {ex:,.2f})" if ex else "") + f", but PBT is given as {pbt:,.2f} Cr")
        pat = f.get("pat_continuing", f.get("pat"))
        tax = f.get("tax_expense")
        if None not in (pbt, tax, pat) and off(pbt - tax, pat):
            problems.append(f"{period}: PBT {pbt:,.2f} - tax {tax:,.2f} = {pbt - tax:,.2f} Cr, "
                            f"but PAT is given as {pat:,.2f} Cr")
    return problems


# --- a table's latest column, from its own YoY and QoQ columns -------------------------------------------------------

_NUM = r"\(?-?\d[\d,]*(?:\.\d+)?\)?"
_CHANGE_ROW = re.compile(r"(?m)^(?P<label>[^\n]*?[A-Za-z][^\n\d]*?)\s+(?P<a>" + _NUM + r")\s+(?P<b>" + _NUM + r")\s+(?P<c>"
                         + _NUM + r")\s+(?P<y>" + _NUM + r")\s*%\s+(?P<q>" + _NUM + r")\s*%\s*$")
_THREE = re.compile(r"(?m)^[^\n]*?[A-Za-z][^\n\d]*?\s+(" + _NUM + r")\s*%?\s+(" + _NUM + r")\s*%?\s+(" + _NUM + r")\s*%?\s*$")


def _num(raw: str) -> float:
    neg = raw.startswith("(") or raw.startswith("-")
    value = float(raw.strip("()-").replace(",", ""))
    return -value if neg else value


def table_columns(text: str) -> tuple[set[float], set[float]]:
    """(latest, stale) figures of the tables whose rows print a YoY and a QoQ change after three periods.

    A business update prints "Loans & Advances 140,041 155,555 158,335 13.1% 1.8%": the headers that would say
    which column is September 2026 came out garbled, and the card took the first column, a year old, and called a
    13.1% rise a 13.1% fall (Bandhan Bank's Q2FY27 update, round-2 re-run; memory stored the year-old figures as
    the quarter's). The changes say which column is the latest: here only the third column is 13.1% above one of
    the others and 1.8% above the third. Rows of the same table without change columns take the same order."""
    latest, stale, orders = set(), set(), []
    for m in _CHANGE_ROW.finditer(text or ""):
        cells = [_num(m.group(k)) for k in "abc"]
        yoy, qoq = _num(m.group("y")), _num(m.group("q"))
        found = set()
        for cur in range(3):
            for ya in range(3):
                qa = 3 - cur - ya
                if len({cur, ya, qa}) < 3 or not cells[ya] or not cells[qa]:
                    continue
                y, q = (cells[cur] / cells[ya] - 1) * 100, (cells[cur] / cells[qa] - 1) * 100
                if abs(abs(y) - abs(yoy)) <= 0.15 and abs(abs(q) - abs(qoq)) <= 0.15 \
                        and (yoy >= 0) == (y >= 0 or abs(y) < 0.05) and (qoq >= 0) == (q >= 0 or abs(q) < 0.05):
                    found.add(cur)
        if len(found) == 1:
            cur = found.pop()
            orders.append((m.start(), cur))
            latest.add(cells[cur])
            stale.update(c for i, c in enumerate(cells) if i != cur)
    if orders and all(cur != 0 for _, cur in orders):
        cur = orders[0][1]
        first, last = min(p for p, _ in orders) - 1500, max(p for p, _ in orders) + 1500
        for m in _THREE.finditer(text or ""):
            if first <= m.start() <= last:
                cells = [_num(g) for g in m.groups()]
                latest.add(cells[cur])
                stale.update(c for i, c in enumerate(cells) if i != cur)
    return latest, stale - latest


def stale_columns(texts: list[str], filed_text: str) -> list[str]:
    """Figures a card states that the table's own changes show are a year or a quarter old."""
    latest, stale = table_columns(filed_text)
    if not stale:
        return []
    from .grounding import _tokens   # local: grounding does not import the gate

    problems = []
    for text in texts:
        flat = text or ""
        for value, decimals, pos, kind, raw in _tokens(flat):
            if kind in ("bps", "pp", "x") or value < 1 or _COMPARED.search(flat[max(0, pos - 35):pos].lower()):
                continue  # "to 158,335 from 140,041": the comparison is meant to be the earlier figure
            tolerance = 0.5 * 10 ** -decimals + 1e-9
            if any(abs(abs(s) - value) <= tolerance for s in stale) and not any(abs(abs(v) - value) <= tolerance for v in latest):
                problems.append(f"states {raw} as current, but the table's YoY and QoQ columns show it is an earlier "
                                "period's figure; read the columns in the order the changes give")
    return list(dict.fromkeys(problems))
