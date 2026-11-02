"""CARD_COMPARATIVE_MATCHES_MEMORY: a PDF-read results card whose earlier-quarter figures contradict memory (settings.
card_comparative_matches_memory; off by default, then nothing here runs). Blind audit 1 Nov 2026, MASKINVEST nse-106838206: a
scanned statement read with its columns out of order. The card said "net loss of ₹0.02 Cr in Q2FY27 versus ₹0.04 Cr in Q1FY27"
and "revenue ₹0.04 Cr against ₹0.03 Cr in Q1FY27"; memory, from the exchange's own files, holds Q1FY27 at a ₹0.02 Cr loss and
₹0.02 Cr revenue (₹0.04 Cr and ₹0.03 Cr are the year-ago quarter's). When the comparatives are read from the wrong column, so is
the quarter itself.

A figure the card gives for a named quarter ("₹0.04 Cr in Q1FY27") of a metric memory holds for that quarter (revenue, total
income, EBITDA, PBT, PAT; a loss by its size) is compared with memory's; one off by more than rounding (2% and ₹0.005 Cr) is a
contradiction. Only cards without the exchange's file, whose figures are the PDF's reading."""

from __future__ import annotations

import re

from .periods import canonical_period
from .settings import card_comparative_matches_memory

_METRICS = (("revenue", r"revenue|sales|top[- ]?line"), ("total_income", r"total income"), ("ebitda", r"EBITDA"),
            ("pbt", r"PBT|profit before tax"),
            ("pat", r"PAT|net (?:profit|loss)|profit after tax|(?<!operating )(?<!gross )(?:profit|loss)(?!\s+before)"))
_AMOUNT_PERIOD = re.compile(r"₹\s?(-?[\d,]+(?:\.\d+)?)\s*(?:cr|crore)\b[^.;₹]{0,20}?\b(?:in|for|during|of)\s+"
                            r"(Q[1-4]\s?FY\s?'?\d{2}|[1-4]Q\s?FY\s?\d{2})", re.I)


_QUARTER = re.compile(r"\bQ[1-4]\s?FY\s?'?\d{2}\b|\b[1-4]Q\s?FY\s?\d{2}\b", re.I)


def _metric_before(text: str, at: int) -> str | None:
    clause = re.split(r";|\b(?:while|whereas|but)\b", text[:at])[-1]
    best = None
    for key, pattern in _METRICS:
        for m in re.finditer(rf"\b(?:{pattern})\b", clause, re.I):
            if best is None or m.start() >= best[1]:
                best = (key, m.start())
    return best[0] if best else None


_BASIS_WORD = re.compile(r"\b(standalone|consolidated)\b", re.I)
# a company's own measure, not the file's revenue line: net sales value and revenue net of excise (UNITDSPR's NSV 3,054 against the
# file's 6,855; TI's "net revenue" 384 against 881.18 gross; blind read of 41369856320)
_OWN_MEASURE = re.compile(r"\b(?:net\s+sales\s+value|NSV|net\s+revenue|net\s+of\s+excise|excluding\s+excise)\b", re.I)
# another company's figures in the parent's card: a subsidiary's, a joint venture's or an associate's results (VEDL's card on
# HZL: HZL's Q4FY25 PAT 3,003 against Vedanta's own 4,961; blind read of 41369856320), or another name's own figures ("HZL's")
_OTHER_ENTITY = re.compile(r"\b(?:subsidiar(?:y|ies)|joint\s+venture|JV|associate\s+compan(?:y|ies))\b")
_POSSESSIVE = re.compile(r"\b([A-Z][A-Za-z&.]{1,30})['’]s\b")
_CORPORATE = {"ltd", "limited", "the", "india", "industries", "company", "co", "corporation", "corp", "of", "and", "&"}


def _own_names(names) -> set[str]:
    """The card's own company in the forms a card may write it: its symbol, its name's words (corporate words aside) and their
    initials ("Infosys Limited" -> infosys; "Hindustan Zinc Limited" -> hindustan, zinc, hz, hzl)."""
    own: set[str] = {"company", "group", "firm", "bank", "insurer", "lender", "management", "board"}   # "The Company's revenue"
    for name in names or ():
        words = [w for w in re.findall(r"[A-Za-z&]+", str(name or "")) if w]
        if len(words) == 1 and words[0].isupper():
            own.add(words[0].lower())   # a symbol ("TCS", "HINDZINC")
        kept = [w for w in words if w.lower() not in _CORPORATE]
        own |= {w.lower() for w in kept}
        if len(kept) > 1:
            own.add("".join(w[0] for w in kept).lower())
            own.add("".join(w[0] for w in words if w.lower() not in {"the", "of", "and", "&"}).lower())
    return own


def _another_company(sentence: str, own: set[str]) -> bool:
    """The sentence speaks of another company's figures: a subsidiary, joint venture or associate, or a possessive name that is
    not the card's own company ("HZL's" on Vedanta's card; "Infosys's" on Infosys's card is its own; lead, 2 Nov 2026)."""
    if _OTHER_ENTITY.search(sentence):
        return True
    return any(m.group(1).lower().rstrip(".") not in own for m in _POSSESSIVE.finditer(sentence))
# an adjusted or non-GAAP figure is no reported line (BLUESTONE's adjusted EBITDA 147.4 against 125.74: blind read of 41345924894)
_ADJUSTED = re.compile(r"\b(?:adjusted|underlying|normali[sz]ed|non[- ]?gaap|core|recurring|pre[- ]?ind[- ]?as|excluding|"
                       r"before\s+exceptional|ex[- ]exceptional)\b", re.I)


# an insurer's Indian-GAAP results file (the GI/LI templates until FY26): from Q1FY27 insurers file under Ind AS 117, and a later
# card's FY26 comparatives are restated under it (STARHEALTH Q4FY26: the GI file's ProfitLossAfterTax 111.33 Cr, the Q1FY27
# filing's restated loss (5,540) lakh; facts-dump 41383638958)
_IGAAP_INSURER = re.compile(r"INTEGRATED_FILING_(?:GI|LI)_", re.I)
_IND_AS_INSURERS_FROM = "Q1FY27"


def _igaap_insurer_keys(dossier: dict | None) -> set[tuple[str, str, str]]:
    """(metric, period, basis) whose exchange-file figure in memory comes from an insurer's Indian-GAAP template."""
    from .watch_code import _sources_of, _src_basis

    keys = set()
    for m in (dossier or {}).get("financial_metrics") or []:
        if not isinstance(m, dict) or not m.get("period") or not m.get("metric"):
            continue
        for src in _sources_of(m):
            lab = src.get("lab") if isinstance(src.get("lab"), dict) else {}
            basis = _src_basis(src, m)
            if lab.get("by") == "file" and basis and _IGAAP_INSURER.search(str(lab.get("file_url") or "")):
                keys.add((m["metric"], m["period"], basis.upper()))
    return keys


def _file_figures(dossier: dict | None) -> dict[tuple[str, str, str], float]:
    """{(metric, period, basis): value} of memory's figures the exchange's own results file gave (a source labelled ``file``, on a
    named basis); a calculated or a model-read figure, or one with no basis, is none (blind read of 41345924894: IOB's 1,962.67
    and STARHEALTH's 111.33 were not in their filings)."""
    from .dossier import inr_crore
    from .watch_code import _sources_of, _src_basis

    out: dict[tuple[str, str, str], float] = {}
    for m in (dossier or {}).get("financial_metrics") or []:
        if not isinstance(m, dict) or not m.get("period") or not m.get("metric"):
            continue
        for src in _sources_of(m):
            lab = src.get("lab") if isinstance(src.get("lab"), dict) else {}
            basis = _src_basis(src, m)
            # in crore, whatever rupee unit the source was stored in (lead's review of #369: a lakh source of 500 is ₹5 Cr); a rate,
            # a per-share figure, dollars or shares are no crore amount to set a card's "₹X Cr" against (review of #370: USD_MN)
            crore = inr_crore(src.get("value"), src.get("unit") or m.get("unit"))
            if lab.get("by") != "file" or not basis or crore is None:
                continue
            out.setdefault((m["metric"], m["period"], basis.upper()), crore)
    return out


def _decimals(raw: str) -> int:
    return len(raw.split(".")[1]) if "." in raw else 0


def contradictions(texts: list[str], dossier: dict | None, basis: str | None = None, names=()) -> list[str]:
    """Each "metric period: card X vs memory Y" the card's words state against memory, when the switch is on (blind read of release
    check 41345924894, 9 of 20 holds wrong): only on the card's own basis (the figure's clause names it, else the card's
    ``basis``; none known, no hold), only against a figure the exchange's own file gave for that quarter and basis, at the card's
    printed precision ("₹3 Cr" is 3.11), and never for an adjusted figure. Never for the card's own quarter (the latest it names),
    a company's own measure (NSV, net revenue), or another company's figures (``names``: the card's own company, its symbol and
    name, so its own possessive still counts)."""
    if not card_comparative_matches_memory():
        return []
    memory = _file_figures(dossier)
    if not memory:
        return []
    from .periods import quarter_index

    # the card's own quarter, the latest it names: only an earlier quarter's figure is a comparative (blind read of 41369856320:
    # ABCAPITAL's own Q4FY26 PAT 1,124 and UNITDSPR's own NSV were held as comparatives)
    named = [canonical_period(re.sub(r"\s|'", "", m.group(0)).upper()) or m.group(0)
             for text in texts for m in _QUARTER.finditer((text or "").replace("**", ""))]
    own = max((p for p in named if quarter_index(p) is not None), key=quarter_index, default=None)
    own_names = _own_names(names)
    # a card from Q1FY27 on sets no figure against an insurer's Indian-GAAP file: its comparatives are restated under Ind AS 117
    # (lead, 2 Nov 2026: by the file's template, not the industry, which would also take insurers already on Ind AS)
    igaap = _igaap_insurer_keys(dossier) if own and quarter_index(own) >= quarter_index(_IND_AS_INSURERS_FROM) else set()
    found = []
    for text in texts:
        flat = (text or "").replace("**", "")
        for m in _AMOUNT_PERIOD.finditer(flat):
            metric = _metric_before(flat, m.start())
            period = canonical_period(re.sub(r"\s|'", "", m.group(2)).upper()) or m.group(2)
            clause = re.split(r";|\.\s", flat[:m.start()])[-1]
            sentence = re.split(r"[.;]\s", flat[:m.start()])[-1]
            if not metric or _ADJUSTED.search(clause) or period == own or _OWN_MEASURE.search(clause) \
                    or _another_company(sentence, own_names):
                continue
            word = _BASIS_WORD.findall(clause)
            on = (word[-1] if word else basis or "").upper()
            if not on:
                continue
            key = (metric, period, on)
            if key not in memory and metric == "pat":
                key = ("pat_owners", period, on)
            if key in igaap:
                continue
            held = memory.get(key)
            if held is None:
                continue
            raw = m.group(1).replace(",", "")
            said = abs(float(raw))
            if abs(said - abs(held)) > max(0.005, 0.5 * 10 ** -_decimals(raw), 0.02 * abs(held)):
                found.append(f"{metric} {period}: the card says ₹{said:g} Cr, memory (the exchange's file) ₹{abs(held):g} Cr")
    return list(dict.fromkeys(found))
