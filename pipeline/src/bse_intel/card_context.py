"""Structured blocks for the card's face, made by code from memory and the card (owner, 2026-10-19: "cards dynamic
by event", "how past memory works"). The website draws each one in the event's own shape; none of them is model text.

* ``rating_change``: the credit rating before and after this filing, on the agency's long-term scale.
* ``case_stage``: where a regulatory or legal case stands (USFDA: Form 483 -> warning letter -> import alert ->
  closed; other cases: notice -> order -> appeal -> resolved), from the card's headline and first point.
* ``guidance_recall``: what management last said it would deliver, from memory before this filing, with when and
  where it was said (EquiSense's "Management expects ₹1,500-1,700 Cr sales for the year" on an order card).
"""

from __future__ import annotations

import re

from .dossier import third_party_view

# Long-term scale shared by CRISIL, ICRA, CARE, India Ratings, Acuite, Brickwork and Infomerics, best first
LONG_TERM = ("AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
             "B+", "B", "B-", "C+", "C", "C-", "D")
_GRADE = re.compile(r"(?<![A-Z0-9])(AAA|AA|A|BBB|BB|B|C|D)([+-])?(?![A-Z0-9+])")
_AGENCY = re.compile(r"\b(CRISIL|ICRA|CARE|IND(?:IA)?\s*RA(?:TINGS)?|IND-?RA|ACUITE|BWR|BRICKWORK|INFOMERICS|IVR)\b", re.I)


def long_term_grade(rating: str | None) -> str | None:
    """'CARE A- (Negative)' -> 'A-'; '[ICRA]AA(Stable)' -> 'AA'; a short-term 'A1+' alone -> None."""
    if not rating:
        return None
    text = _AGENCY.sub(" ", rating.upper().replace("[", " ").replace("]", " "))
    text = re.sub(r"\((?:CE|SO)\)", " ", text)
    m = _GRADE.search(text)
    if not m:
        return None
    grade = m[1] + (m[2] or "")
    return grade if grade in LONG_TERM else None


_AGENCY_KEYS = (("CRISIL", "CRISIL"), ("ICRA", "ICRA"), ("CARE", "CARE"), ("INDIA RATINGS", "IND-RA"), ("IND-RA", "IND-RA"),
                ("IND RA", "IND-RA"), ("ACUITE", "ACUITE"), ("ACUITÉ", "ACUITE"), ("BRICKWORK", "BWR"), ("BWR", "BWR"),
                ("INFOMERICS", "IVR"), ("IVR", "IVR"))


def agency_of(sheet: dict) -> str | None:
    """The agency of a stored rating, from its agency field or the rating text ("CARE A-")."""
    text = f"{sheet.get('rating_agency') or ''} {sheet.get('credit_rating') or ''}".upper()
    if re.search(r"\bIND\s+[A-D]", text):
        return "IND-RA"
    return next((key for word, key in _AGENCY_KEYS if re.search(rf"(?<![A-Z]){re.escape(word)}(?![A-Z])", text)), None)


# "upgraded the long-term rating to [ICRA]AAA (Stable) from [ICRA]AA+ (Stable)": the earlier grade in the filing's words
_FROM_GRADE = re.compile(r"\b(?:upgrad|downgrad|revis|reaffirm|migrat|chang)\w*\b[^.;]{0,200}?\bfrom\s+([^.;,]{1,40})", re.I)


def grade_before_in_text(text: str | None) -> str | None:
    """The long-term grade a rating filing says it moved from, when it says so."""
    for m in _FROM_GRADE.finditer(text or ""):
        grade = long_term_grade(m[1])
        if grade:
            return grade
    return None


def rating_change(before: dict | None, after: dict, news_id: str, text: str = "") -> dict | None:
    """The rating this filing set, beside the same agency's last one in memory, else the grade the filing says it
    moved from (memory often has no earlier rating: Hind Copper's ICRA AA+ -> AAA, laptop re-check 2026-10-19)."""
    sheets = [s for s in after.get("balance_sheet", []) if s.get("credit_rating")]
    if not sheets or sheets[-1].get("source_news_id") != news_id:
        return None
    now = sheets[-1]
    agency = agency_of(now)
    # the last rating by the same agency: CRISIL AA beside ICRA AA- is two opinions, not a downgrade
    prev = next((s for s in reversed((before or {}).get("balance_sheet", []))
                 if s.get("credit_rating") and (agency is None or agency_of(s) in (agency, None))), None)
    grade, was = long_term_grade(now.get("credit_rating")), long_term_grade((prev or {}).get("credit_rating"))
    if grade is None:
        return None
    if was is None:
        was = grade_before_in_text(text)
        prev = {"as_of": None, "rating_outlook": None} if was else prev
    notches = LONG_TERM.index(was) - LONG_TERM.index(grade) if was else None   # positive: an upgrade
    return {
        "agency": now.get("rating_agency"), "after": grade, "after_outlook": now.get("rating_outlook"),
        "before": was, "before_outlook": (prev or {}).get("rating_outlook") if was else None,
        "notches": notches, "as_of_before": ((prev or {}).get("as_of") or "")[:10] or None if was else None,
    }


_UPGRADE_WORD = re.compile(r"\bupgrad\w*", re.I)
_DOWNGRADE_WORD = re.compile(r"\bdowngrad\w*", re.I)


def rating_word_mismatch(words: str, new_rating: str | None, new_agency: str | None, before: dict | None,
                         text: str = "") -> list[str]:
    """A card that calls a rating an upgrade or a downgrade when its grade did not move, or the other way round.

    eMudhra's ICRA A reaffirmed was published as "upgraded to A (Stable)" (live review 2, 2026-10-20): the earlier
    grade, from the same agency in memory or in the filing's own "from ..." words, is the test. `words` is the card's
    headline and first points; nothing is said when the earlier grade is not known."""
    grade = long_term_grade(new_rating)
    if grade is None:
        return []
    agency = agency_of({"rating_agency": new_agency, "credit_rating": new_rating})
    prev = next((s for s in reversed((before or {}).get("balance_sheet", []))
                 if s.get("credit_rating") and (agency is None or agency_of(s) in (agency, None))), None)
    was = long_term_grade((prev or {}).get("credit_rating")) or grade_before_in_text(text)
    if was is None:
        return []
    up, down = bool(_UPGRADE_WORD.search(words)), bool(_DOWNGRADE_WORD.search(words))
    if was == grade and (up or down):
        return [f"The card calls the rating {'an upgrade' if up else 'a downgrade'}, but the long-term grade is {grade} "
                f"before and after: a reaffirmation"]
    moved = LONG_TERM.index(was) - LONG_TERM.index(grade)
    if (moved > 0 and down and not up) or (moved < 0 and up and not down):
        return [f"The card calls the rating {'a downgrade' if down else 'an upgrade'}, but it moved from {was} to {grade}"]
    return []


_USFDA = (("Form 483", r"\b(?:form\s*)?483\b|observations?\b"), ("Warning letter", r"\bwarning\s+letter\b"),
          ("Import alert", r"\bimport\s+alert\b"),
          ("Closed", r"\b(?:establishment\s+inspection\s+report|eir|close[- ]?out\s+letter|nai|vai)\b|\bclosed\b"))
_CASE = (("Notice", r"\bnotices?\b|\bshow[- ]cause\b|\bsummons\b|\bsearch\b|\binspection\b"),
         ("Order", r"\b(?<!in )order\b(?!\s+(?:book|inflow|win|to)\b)|\bdemand\b|\bpenalt(?:y|ies)\b|\bimposed\b|\blevied\b"
                   r"|\bfined?\b|\bconvicted\b"),
         ("Appeal", r"\b(?:filed|preferred|filing)\s+(?:an?\s+)?appeal\b|\bappeal\s+(?:filed|admitted)\b|\bappealed\b"
                    r"|\bstay\s+(?:order|granted)\b|\bgranted\s+(?:a\s+)?stay\b"),
         # an appeal "dismissed" ends the case against the company as often as for it: not a resolution here
         ("Resolved", r"\bsettled\b|\bquashed\b|\bset\s+aside\b|\bin\s+(?:its|the\s+company'?s)\s+favou?r\b"
                      r"|\b(?:notice|demand|order|case)\s+(?:was\s+|has\s+been\s+)?withdrawn\b"))
# A governance filing is a case only when a regulator, court or tax authority is in it (an AGM notice is not)
_CASE_CONTEXT = re.compile(r"\b(?:sebi|rbi|irdai|cci|court|tribunal|nclt|nclat|sat|penalt|show[- ]cause|demand|tax|gst|customs"
                           r"|enforcement|cbi|u?s?fda|inspection|search|summons|litigation|arbitration|adjudicat|compounding"
                           r"|regulator|ministry|dgtr|pollution|labour)", re.I)


def case_stage(event_type: str, headline: str, facts: list[str], context: list[str] = ()) -> dict | None:
    """Where a case stands. `at` is the step this filing is about (the furthest one its headline names, else its first
    point's); `reached` is every step the card names as having happened, each on its own: a USFDA import alert can
    come before the warning letter (Dabur, laptop re-check 2026-10-19), so the ladder is not filled up to `at`."""
    if event_type not in ("LITIGATION_REGULATORY", "GOVERNANCE"):
        return None
    lead = " ".join([headline, *facts[:1]]).lower()
    if not _CASE_CONTEXT.search(lead):
        return None
    track, steps = ("USFDA", _USFDA) if re.search(r"\b(?:us\s*)?fda\b", lead) else ("CASE", _CASE)

    def named(text: str) -> list[int]:
        return [i for i, (_, pattern) in enumerate(steps) if re.search(pattern, text.lower())]

    current = named(headline) or named(lead)
    if not current:
        return None
    reached = sorted(set(current) | set(named(" ".join([*facts, *context]))))
    return {"track": track, "steps": [name for name, _ in steps], "at": max(current), "reached": reached}


_RELEVANT = {
    "ORDER_WIN": ("revenue", "sales", "order", "turnover", "inflow", "pipeline", "bid"),
    "CAPEX": ("capex", "capacity", "investment", "plant", "commission", "revenue"),
    "RESULTS": ("revenue", "sales", "margin", "ebitda", "growth", "profit", "pat", "guidance"),
    "FUNDRAISE": ("capex", "investment", "debt", "fund", "plant"),
    "RIGHTS_ISSUE": ("capex", "investment", "debt", "fund", "plant"),
    "M_AND_A": ("acquisition", "inorganic", "revenue"),
    "MONTHLY_BUSINESS_UPDATE": ("volume", "sales", "revenue", "growth"),
}
_OPEN = {"OPEN", "ON_TRACK", "REVISED"}


def guidance_recall(before: dict | None, event_type: str, filed_at: str | None = None, limit: int = 2,
                    max_age_days: int = 540) -> list[dict]:
    """The latest open management guidance memory held before this filing that bears on this event. Guidance whose
    deadline has passed is left out (it is overdue, not a plan), and so is guidance more than 18 months old."""
    words = _RELEVANT.get(event_type)
    if not words:
        return []
    from datetime import date, timedelta

    try:
        today = date.fromisoformat((filed_at or "")[:10])
    except ValueError:
        today = None
    out = []
    for g in reversed((before or {}).get("guidance", [])):
        if g.get("status") not in _OPEN:
            continue
        # a commitment has a target or a deadline; an explanation from the call has neither (CSB's RoA remark)
        if not (g.get("target") or g.get("due") or g.get("due_date")):
            continue
        if today and g.get("due_date") and g["due_date"] < today.isoformat():
            continue
        if today and g.get("given_on") and g["given_on"][:10] < (today - timedelta(days=max_age_days)).isoformat():
            continue
        text = f"{g.get('statement', '')} {g.get('metric') or ''} {g.get('target') or ''}".lower()
        # an agency's or analyst's view is not the company's promise (laptop test, 2026-10-19: "Ind-Ra expects")
        if third_party_view(text):
            continue
        # whole words for the short ones ("pat" is not "patent"), a word start for the rest ("plants", "orders")
        if not any(re.search(rf"\b{w}\b" if len(w) <= 3 else rf"\b{w}", text) for w in words):
            continue
        out.append({"statement": g["statement"], "target": g.get("target"), "due": g.get("due"),
                    "given_on": (g.get("given_on") or "")[:10] or None, "source_type": g.get("source_type"),
                    "id": g.get("id")})
        if len(out) >= limit:
            break
    return out
