"""Build config/generic_words.txt for CARD_TEXT_SUPPORT (card_support.py): the stems of words of 6+ letters that appear in at
least K of the given filings' texts, so ordinary business English ("momentum", "expanding", "offset") is never read as a
name or a fact the sources must print. Words the check must keep (capacity, passengers ...) are left out.

    PYTHONPATH=src python scripts/build_generic_words.py K OUT.txt TEXTFILE [TEXTFILE ...]

Run over stored filing texts (a few dozen across sectors). Read-only on the inputs.
"""
import re
import sys
from collections import Counter

from bse_intel.card_support import KEEP_CHECKED, _stem

K, out, files = int(sys.argv[1]), sys.argv[2], sys.argv[3:]
df: Counter = Counter()
for path in files:
    text = open(path, errors="replace").read().lower()
    stems = {_stem(w) for part in re.findall(r"[a-z]{3,}(?:-[a-z]{3,})*", text) for w in part.split("-") if len(w) >= 6}
    df.update(stems)
keep = {_stem(w) for w in KEEP_CHECKED}
words = sorted(s for s, n in df.items() if n >= K and s not in keep)
open(out, "w").write("\n".join(words) + "\n")
print(len(words), "stems in", len(files), "filings, K =", K)
