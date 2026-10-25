"""The one list of foreign currencies the filings write amounts in (F156). Before it, grounding, gate and pipeline each
kept their own list, and SEK and THB were in none ("SEK 86.4 Mn" became Rs 8.64 Cr, KPIL)."""

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
TAIL_PATTERN = rf"(?:{'|'.join(c.lower() for c in CODES)}|{'|'.join(WORDS)}|us\$|[{SYMBOLS}])\s*$"
