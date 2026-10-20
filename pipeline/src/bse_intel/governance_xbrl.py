"""The quarterly governance filing's XBRL (NSE "Integrated Filing- Governance", SEBI circular of 31 Dec 2024).

Every listed company files it each quarter (measured 2026-10-18: 21,021 files on NSE's list, 727 for the September
2026 quarter by 18 Oct; `/api/integrated-filing-results?type=Integrated Filing- Governance`, all companies, newest
first, up to 1,000 rows a page). The PDF is routine and stays on the drop list; the XBRL is memory: who sits on the
board and its committees, whether their composition and meetings meet SEBI's rules, investor complaints, and the
annexure's parts that matter to an investor - C (shares or voting rights bought in unlisted companies), D (fines and
penalties imposed in the quarter), E (updates on ongoing tax litigation), F (loans, guarantees, comfort letters and
security given to promoters, directors or KMP) - and whether there was a cyber-security incident (Reg 27(2)(ba)).

Measured on 40 September-quarter files drawn by seed (2026-10-18): fines or penalties in 6 (an income-tax penalty
order at Zydus, RBI compounding at Carysil, exchange fines at Chennai Petroleum and Sarveshwar), tax-litigation updates
in 14, Part F filled in 13, a board or committee composition not in terms of SEBI's rules in 1 (Chennai Petroleum: board,
audit and nomination committees), no cyber incident, no disqualified director.

The file's contexts: `MainD`/`MainI` for the company, `D_CompBOD<n>`/`CompBOD<n>` for a director (text and numbers of
the same director), `D_CompComit<n>` for a committee member, `MeetingBOD<n>`/`MeetingComit<n>` for a meeting,
`I_ImpositionOfFineOrPenalty<n>` and `I_OngoingTaxLitigationsOrDisputes<n>` for the annexure's rows. Amounts are in
rupees (unit INR).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import date

# Longest gap allowed between two meetings, in days (SEBI LODR): the board, Reg 17(2); the audit committee, Reg
# 18(2)(a); the risk-management committee, Reg 21(3C). The other committees need only meet once a year.
MAX_GAP_DAYS = {"board": 120, "audit committee": 120, "risk management committee": 210}
_COMPLIANCE = (
    ("board", "TheCompositionOfBoardOfDirectorsIsInTermsOfSebiRegulations2015"),
    ("audit committee", "TheCompositionOfAuditCommitteeIsInTermsOfSebiRegulations2015"),
    ("nomination and remuneration committee", "TheCompositionOfTheNominationAndRemunerationCommitteeIsInTermsOfSebiRegulations2015"),
    ("stakeholders relationship committee", "TheCompositionOfTheStakeholdersRelationshipCommitteeCommitteeIsInTermsOfSebiRegulations2015"),
    ("risk management committee", "TheCompositionOfTheRiskManagementCommitteeIsInTermsOfSebiRegulations2015"),
    ("meetings", "TheMeetingsOfTheBoardOfDirectorsAndTheAboveCommitteesHaveBeenConductedInTheMannerAsSpecifiedInSebiRegulations2015"),
)
_CYBER = "WhetherAsPerSubRegulation2baOfRegulation27OfSEBILODRThereHasBeenCyberSecurityIncidentsDuringTheQuarter"
# Part F: (who, what) from the field's own words
_PARTY = (("PromoterGroup", "promoter group"), ("Promoter", "promoter"), ("Directors", "directors and relatives"),
          ("KMPs", "KMP"))
_EMPTY = {"", "na", "n.a.", "nil", "none", "not applicable", "-"}
# Raised when what is read changes, so memory files a quarter again (dossier.merge_governance). 2: a penalty's amount
# only beside its own words (2026-10-19)
PARSER_VERSION = 4   # 3: money below a share of annual profit is not raised; 4: that share is 5% (owner, 2026-10-19)
# A penalty below this is kept in memory but raised as no exception (Harsha's ₹648 GST penalty, measured 2026-10-18)
MINOR_PENALTY_RUPEES = 100_000
MATERIAL_SHARE_OF_PROFIT = 0.05   # owner, 2026-10-19: a governance issue under 5% of annual profit is dropped
_RUPEES = re.compile(r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*(crores?|cr\.?|lakhs?|lacs?|million|mn\b)?", re.I)


_PENALTY_WORDS = re.compile(r"penalt|\bfines?\b|levied|levy|imposed|compound|monetary|award", re.I)


def _rupees(m) -> float:
    value = float(m.group(1).replace(",", "") or 0)
    unit = (m.group(2) or "").lower()
    return value * (1e7 if unit.startswith("cr") else 1e5 if unit.startswith(("lakh", "lac")) else 1e6 if unit in ("million", "mn") else 1)


def penalty_rupees(impact: str | None, *details: str | None) -> float | None:
    """The penalty's amount in rupees: one written beside "penalty", "fine", "levied", "imposed", "compounding" in the
    impact or the details ("Fine of Rs. 9,66,420/- imposed", "Amount of penalty imposed is Rs. 0.30 million",
    "Rs.200/- Monetary Penalty"), else the
    impact field when it is just an amount ("Rs. 2,250/-"). Any other amount in the details is something else: a
    ₹16.85 Cr cash remittance (IndusInd), a ₹3 Cr tax demand the authority dropped (JK Cement), measured 2026-10-19.
    None when no amount can be told for the penalty."""
    for text in (impact, *details):
        for m in _RUPEES.finditer(text or ""):
            if _PENALTY_WORDS.search(text[max(0, m.start() - 80):m.start()] + " " + text[m.end():m.end() + 30]):
                return _rupees(m)
    m = _RUPEES.search(impact or "")
    if m and len(re.sub(r"[\W_]+", "", (impact or "")[:m.start()] + (impact or "")[m.end():])) <= 12:
        return _rupees(m)
    return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _bool(value: str | None) -> bool | None:
    v = (value or "").strip().lower()
    return True if v in ("true", "yes") else False if v in ("false", "no") else None


def _num(value: str | None) -> float | None:
    try:
        return float((value or "").replace(",", ""))
    except ValueError:
        return None


@dataclass
class Director:
    name: str
    category: str = ""            # "Non-Executive - Independent Director", "Executive Director"...
    role: str = ""                # "Chairperson related to Promoter", "Not Applicable"...
    din: str = ""
    appointed: str | None = None
    ceased: str | None = None
    cessation_reason: str | None = None
    tenure_months: float | None = None
    disqualified: bool | None = None
    listed_directorships: float | None = None


@dataclass
class GovernanceReport:
    symbol: str = ""
    scrip_code: str = ""
    company: str = ""
    quarter_end: str | None = None      # ISO date
    board: list[Director] = field(default_factory=list)
    committees: dict[str, list[str]] = field(default_factory=dict)   # committee -> members
    compliance: dict[str, bool] = field(default_factory=dict)        # body -> composition in terms of SEBI's rules
    gaps: dict[str, float] = field(default_factory=dict)             # body -> longest gap between meetings, days
    meetings: dict[str, int] = field(default_factory=dict)           # body -> meetings in the quarter
    quorum_missed: list[str] = field(default_factory=list)
    chair_related_to_md: bool | None = None
    regular_chair: bool | None = None
    cyber_incident: bool | None = None
    complaints: dict[str, float] = field(default_factory=dict)       # received, disposed, pending
    penalties: list[dict] = field(default_factory=list)              # Part D
    tax_litigation: list[dict] = field(default_factory=list)         # Part E
    related_finance: list[dict] = field(default_factory=list)        # Part F, non-zero lines only
    unlisted_acquisitions: bool | None = None                        # Part C applies

    def floor_rupees(self, annual_profit_cr: float | None = None) -> float:
        """Below this a fine, or money lent, guaranteed or secured for insiders, is not raised (owner, 2026-10-19: a
        governance issue under 5% of annual profit is dropped). For a loss-making company, or one whose profit memory
        does not hold, the ₹1 lakh floor."""
        if annual_profit_cr and annual_profit_cr > 0:
            return max(MINOR_PENALTY_RUPEES, annual_profit_cr * 1e7 * MATERIAL_SHARE_OF_PROFIT)
        return MINOR_PENALTY_RUPEES

    def exceptions(self, annual_profit_cr: float | None = None) -> list[str]:
        """What an investor would want to hear about, in plain words; empty for a clean quarter. Money below
        floor_rupees() stays in memory without a line of its own; a penalty with no stated amount is raised."""
        floor = self.floor_rupees(annual_profit_cr)
        out = [f"{body} composition not in terms of SEBI's rules" if body != "meetings"
               else "board and committee meetings not held as SEBI's rules specify"
               for body, ok in self.compliance.items() if ok is False]
        for body, gap in self.gaps.items():
            limit = MAX_GAP_DAYS.get(body)
            if limit and gap > limit:
                out.append(f"{body}: {gap:g} days between meetings (limit {limit})")
        out += [f"quorum not met: {b}" for b in self.quorum_missed]
        out += [f"director disqualified: {d.name}" for d in self.board if d.disqualified]
        if self.cyber_incident:
            out.append("cyber-security incident in the quarter")
        for p in self.penalties:
            if p.get("amount_rupees") is not None and p["amount_rupees"] < floor:
                continue   # kept in memory; not worth a line of its own
            amount = f" ₹{p['amount_rupees'] / 1e5:,.2f} lakh" if p.get("amount_rupees") is not None else ""
            out.append(f"fine or penalty{amount}: {p.get('authority') or 'authority not named'}"
                       + (f" ({p['details'][:120]})" if p.get("details") else ""))
        for f in self.related_finance:
            if max(f["given_cr"], f["outstanding_cr"]) * 1e7 < floor:
                continue
            out.append(f"{f['kind']} to {f['party']}: ₹{f['outstanding_cr']:g} Cr outstanding")
        return out

    def memory(self, annual_profit_cr: float | None = None) -> dict:
        """The quarter's entry for the company's memory (dossier), without the board's personal fields."""
        return {"parser": PARSER_VERSION, "quarter_end": self.quarter_end,
                "material_floor_cr": round(self.floor_rupees(annual_profit_cr) / 1e7, 4),
                "board": [{"name": d.name, "category": d.category, "role": d.role if d.role != "Not Applicable" else None,
                           "appointed": d.appointed, "ceased": d.ceased, "cessation_reason": d.cessation_reason,
                           "tenure_months": d.tenure_months} for d in self.board],
                "independent_directors": sum(1 for d in self.board if "independent" in d.category.lower() and not d.ceased),
                "board_size": sum(1 for d in self.board if not d.ceased),
                "committees": self.committees, "compliance": self.compliance, "gaps": self.gaps,
                "chair_related_to_md": self.chair_related_to_md, "cyber_incident": self.cyber_incident,
                "complaints": self.complaints, "penalties": self.penalties, "tax_litigation": self.tax_litigation,
                "related_finance": self.related_finance, "exceptions": self.exceptions(annual_profit_cr)}

    def as_dict(self) -> dict:
        return asdict(self)


def _root(data: bytes):
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        try:
            return ET.fromstring(re.sub(r"^\s*<\?xml[^>]*\?>", "", data.decode("utf-8", errors="replace")))
        except ET.ParseError:
            return None


def _body(name: str) -> str:
    name = " ".join(name.lower().split())
    return "nomination and remuneration committee" if "nomination" in name else \
        "stakeholders relationship committee" if "stakeholder" in name else name


def parse(data: bytes | None) -> GovernanceReport | None:
    root = _root(data) if data else None
    if root is None:
        return None
    by_ctx: dict[str, dict[str, list[str]]] = {}
    for el in root.iter():
        ctx = el.get("contextRef")
        if ctx is None or el.text is None:
            continue
        key = ctx[2:] if ctx.startswith("D_") else ctx   # D_CompBOD1 (text) and CompBOD1 (numbers): one director
        by_ctx.setdefault(key, {}).setdefault(_local(el.tag), []).append(" ".join(el.text.split()))
    main = {k: v[0] for ctx in ("MainI", "MainD") for k, v in by_ctx.get(ctx, {}).items()}
    if not main.get("Symbol") and not main.get("NameOfTheCompany"):
        return None
    r = GovernanceReport(main.get("Symbol", "").upper(), main.get("ScripCode", ""), main.get("NameOfTheCompany", ""),
                         main.get("DateOfEndOfReportingPeriod"))
    for name, field_ in _COMPLIANCE:
        ok = _bool(main.get(field_))
        if ok is not None:
            r.compliance[name] = ok
    r.chair_related_to_md = _bool(main.get("WhetherChairpersonIsRelatedToMDOrCEO"))
    r.regular_chair = _bool(main.get("WhetherTheListedEntityHasARegularChairperson"))
    r.cyber_incident = _bool(main.get(_CYBER))
    r.unlisted_acquisitions = _bool(next((v for k, v in main.items() if k.startswith("WhetherPartCOfAnnexure")), None))
    for k, label in (("NoOfInvestorComplaintsReceivedDuringThePeriod", "received"),
                     ("NoOfInvestorComplaintsDisposedOffDuringThePeriod", "disposed"),
                     ("NoOfInvestorComplaints", "pending")):
        n = _num(by_ctx.get("MainI", {}).get(k, [None])[0] if k == "NoOfInvestorComplaints" else main.get(k))
        if n is not None:
            r.complaints[label] = n

    for ctx in sorted(by_ctx, key=lambda c: (re.sub(r"\d+$", "", c), int(re.search(r"(\d+)$", c).group(1)) if re.search(r"\d+$", c) else 0)):
        f = {k: v[0] for k, v in by_ctx[ctx].items()}
        if ctx.startswith("CompBOD") and f.get("NameOftheDirector"):
            r.board.append(Director(f["NameOftheDirector"], f.get("PositionOfDirectorInBoardOne", ""),
                                    f.get("PositionOfDirectorInBoardTwo", ""), f.get("DirectorIdentificationNumberOfDirector", ""),
                                    f.get("DateOfAppointmentOfDirector"), f.get("DateOfCessationOfDirector"),
                                    f.get("ReasonForCessation"), _num(f.get("TenureOfDirector")),
                                    _bool(f.get("WhetherTheDirectorIsDisqualified")),
                                    _num(f.get("NumberOfDirectorshipInListedEntitiesIncludingThisListedEntity"))))
        elif ctx.startswith("CompComit") and f.get("NameOfCommittee"):
            members = r.committees.setdefault(_body(f["NameOfCommittee"]), [])
            if f.get("NameOfCommitteeMembers") and not f.get("DateOfCessationOfDirectorInCommittee"):
                members.append(f["NameOfCommitteeMembers"])
        elif ctx.startswith(("MeetingBOD", "MeetingComit")):
            body = "board" if ctx.startswith("MeetingBOD") else _body(f.get("NameOfCommittee", "committee"))
            if f.get("DatesOfMeetingIfAnyInTheRelevantQuarter") or f.get("DatesOfMeetingOfTheCommitteeInTheRelevantQuarter"):
                r.meetings[body] = r.meetings.get(body, 0) + 1
            gap = _num(f.get("MaximumGapBetweenAnyTwoConsecutiveMeetings"))
            if gap is not None:
                r.gaps[body] = max(r.gaps.get(body, 0), gap)
            if _bool(f.get("WhetherRequirementOfQuorumMet")) is False:
                r.quorum_missed.append(body)
        elif ctx.startswith("I_ImpositionOfFineOrPenalty") and f.get("NameOfTheAuthority"):
            details = f.get("NatureAndDetailsOfTheActionTakenOrOrderPassed")                 or f.get("DetailsOfTheViolationOrContraventionCommittedOrAllegedToBeCommitted")
            impact = f.get("ImpactOnFinancialOrOperationOrOtherActivitiesOfTheListedEntityQuantifiableInMonetaryTermsToTheExtentPossible")
            row = {"authority": f["NameOfTheAuthority"],
                   "received": f.get("DateOfReceiptOfDirectionOrOrderIncludingAnyAdInterimOrInterimOrdersOrAnyOtherCommunicationFromTheAuthority"),
                   "details": details, "impact": impact,
                   # the impact "in monetary terms" first: IndusInd's details name a ₹16.85 Cr cash remittance,
                   # its impact the ₹2,250 penalty (measured 2026-10-19)
                   "amount_rupees": penalty_rupees(impact, details)}
            if row not in r.penalties:   # Zydus filed the same order three times (measured 2026-10-18)
                r.penalties.append(row)
        elif ctx.startswith("I_OngoingTaxLitigationsOrDisputes") and f.get("NameOfTheOpposingParty"):
            r.tax_litigation.append({"opposing_party": f["NameOfTheOpposingParty"],
                                     "initiated": f.get("DateOfInitiationOfTheLitigationDispute"),
                                     "as_last_disclosed": f.get("StatusOfTheLitigationDisputeAsPerLastDisclosure"),
                                     "status": f.get("CurrentStatusOfTheLitigationOrDispute")})
    r.board = [d for d in r.board if d.name.lower() not in _EMPTY]
    _related_finance(r, main)
    return r


def _related_finance(r: GovernanceReport, main: dict) -> None:
    """Part F, the lines with money in them: loans, guarantees or comfort, and security given to promoters,
    directors or KMP over the half-year, with what was outstanding at its end."""
    rows: dict[tuple[str, str], dict] = {}
    for name, value in main.items():
        amount = _num(value)
        if not amount or not name.startswith(("AggregateAmount", "AggregateValue", "BalanceOutstanding")):
            continue
        kind = "guarantee or comfort" if "Guarantee" in name else "security" if "Security" in name else "loan" if "Loan" in name else None
        party = next((label for key, label in _PARTY if f"To{key}" in name or f"By{key}" in name), None)
        if not kind or not party:
            continue
        row = rows.setdefault((kind, party), {"kind": kind, "party": party, "given_cr": 0.0, "outstanding_cr": 0.0})
        row["outstanding_cr" if name.startswith("BalanceOutstanding") else "given_cr"] = round(amount / 1e7, 4)
    r.related_finance = [row for row in rows.values() if row["given_cr"] or row["outstanding_cr"]]


def quarter_label(end: str | None) -> str | None:
    """"2026-09-30" -> "Q2FY27" (India's financial year ends in March)."""
    try:
        d = date.fromisoformat(end or "")
    except ValueError:
        return None
    fy = d.year + 1 if d.month > 3 else d.year
    return f"Q{((d.month - 4) % 12) // 3 + 1}FY{fy % 100:02d}"
