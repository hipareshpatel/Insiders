"""The one list of foreign currencies the filings write amounts in (F156). Before it, grounding, gate and pipeline each
kept their own list, and SEK and THB were in none ("SEK 86.4 Mn" became Rs 8.64 Cr, KPIL)."""

import re


# ISO codes of the currencies Indian filings quote besides the rupee
CODES = ("USD", "EUR", "GBP", "JPY", "CHF", "AED", "SGD", "CAD", "AUD", "NZD", "SAR", "QAR", "OMR", "KWD", "BHD",
         "NGN", "KES", "ZAR", "SEK", "NOK", "DKK", "THB", "CNY", "RMB", "HKD", "MYR", "IDR", "PHP", "KRW", "TWD",
         "BRL", "MXN", "PLN", "CZK", "HUF", "TRY", "EGP", "BDT", "LKR", "MUR", "RUB", "ILS", "VND", "TZS", "UGX",
         "GHS", "COP", "CLP", "ARS", "PEN")
SYMBOLS = "$€£¥₦"
WORDS = ("euro", "euros", "baht", "krona", "kronor", "yen", "yuan", "dirham", "dirhams", "ringgit", "rand", "dollar",
         "dollars")

_codes = "|".join(CODES)
# the code or "US$" or a symbol, for the amount finders (case-insensitive use); grounding, deal checks
CODE_PATTERN = rf"(?:\b(?:{_codes}|US\$)|[{SYMBOLS}])"
# a currency right before a figure, on lower-cased text: gate
# a code or word only as a whole word: "country 120" is not TRY, "brand 5" not rand
TAIL_PATTERN = rf"(?:\b(?:{'|'.join(c.lower() for c in CODES)}|{'|'.join(WORDS)})|us\$|[{SYMBOLS}])\s*$"

# A unit line of another currency ("(US$ in million)", "(USDin millions)", OCR's "(USS in million)", "(€ millions)", "(Euro in
# million)"): a code glued to "in" counts, and so do OCR's US$ forms. Only a million, thousand or billion unit is another currency's:
# no currency but the rupee is written in lakh or crore, so "(?£in Lacs)" is a rupee sign OCR mangled (29 Oct 2026, review).
OTHER_UNIT_CURRENCY = rf"(?:\b(?:{_codes}|US[$S8]?|{'|'.join(WORDS)})(?=in\b|[^a-z]|$)|[{SYMBOLS}])"
_OTHER_UNIT = re.compile(OTHER_UNIT_CURRENCY, re.I)
_THOUSANDS_UNIT = re.compile(r"(?:millions?|mln|\bmn\b|mio|thousands?|'?000|billions?|\bbn\b)", re.I)
_RUPEE_MARK = re.compile(r"₹|\brs\.?|\binr\b|rupee", re.I)


def names_other_currency(line: str) -> bool:
    """Whether a unit line names another currency's million, thousand or billion and no rupee at all."""
    return bool(_THOUSANDS_UNIT.search(line) and not _RUPEE_MARK.search(line) and _OTHER_UNIT.search(line))
