"""An annual report's own XBRL, as a table in front of its text (to-do item 4, F57).

An annual report runs to 300 pages with its statements in lakh or million and the standalone and
consolidated sets side by side. Read from the PDF alone, 12 of the 31 smoke-test annual-report cards were
held in round 3d: lakh figures quoted as crore, a borrowings total the model added up and no sentence
printed, the consolidated revenue called standalone (Kanoria's "standalone revenue ₹1,536.71 Cr").

Companies file the same statements with MCA as XBRL, and NSE publishes the files:

    GET /api/annual-reports-xbrl?index=equities&symbol=<SYMBOL>
        -> {"data": [{"fromYr": "2024", "toYr": "2025", "report_type": "IND-AS",
                      "submission_type": "Standalone" | "Consolidated", "broadcast_dttm": "22-DEC-2025 12:22:28",
                      "fileName": "https://nsearchives.nseindia.com/corporate/xbrl/AR_XBRL_<SYMBOL>_<stamp>.xml"}]}

One instance per year and basis, on the MCA Ind-AS taxonomy: amounts in rupees, the basis in
NatureOfReportStandaloneConsolidated, each related party, key managerial person and consolidated entity a
typed member of its own. The standalone instance alone carries the board's report and the auditor's CARO
clauses. Read from real files (Kanoria FY25, Prism FY26, Shivam FY25; 2026-10-18), two things decide how:

* Filing software writes 0 for a field left empty. Kanoria's ContingentLiabilities is 0 beside
  WhetherThereAreAnyContingentLiabilities "true" and ₹6.82 Cr listed by class; its ManagerialRemuneration
  is 0 while its board's report pays the managing director ₹3.15 Cr. A zero is never shown as a nil: it is
  left out, so the table cannot tell a card that something is absent.
* "Qualified Opinion" in an auditor's report can head the report on internal financial controls while the
  opinion on the statements is unmodified (Shivam FY25). The opinion is read from its "Basis for ... Opinion"
  heading, which SA 700/705 put under the opinion it explains.

The file is filed weeks to months after the PDF (Kanoria FY25: the report in September, its XBRL in
December), so a report read the day it is filed usually has none yet and is read from its PDF as before.
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date

from .xbrl import _change, _local, _num, _units, appears_in, as_utf8

# (metric, wording, element names in order of preference): non-dimensional facts, in ₹ crore unless per share
FLOWS = (
    ("revenue", "revenue from operations", ("RevenueFromOperations",)),
    ("other_income", "other income", ("OtherIncome",)),
    ("total_income", "total income", ("Income",)),
    ("total_expenses", "total expenses", ("Expenses",)),
    ("finance_cost", "finance costs", ("FinanceCosts",)),
    ("depreciation", "depreciation and amortisation", ("DepreciationDepletionAndAmortisationExpense",
                                                        "DepreciationAndAmortisationExpense")),
    ("exceptional_items", "exceptional items", ("ExceptionalItemsBeforeTax", "ExceptionalItems")),
    ("pbt", "profit before tax", ("ProfitBeforeTax",)),
    ("tax_expense", "tax expense", ("TaxExpense", "IncomeTaxExpenseContinuingOperations")),
    ("pat", "profit for the year", ("ProfitLossForPeriod",)),
    ("pat_owners", "profit attributable to owners of the parent", ("ProfitOrLossAttributableToOwnersOfParent",)),
    ("eps", "basic EPS", ("BasicEarningsLossPerShare",)),
    ("cfo", "cash from operating activities", ("CashFlowsFromUsedInOperatingActivities",)),
    ("managerial_remuneration", "managerial remuneration", ("ManagerialRemuneration", "RemunerationToDirectors")),
)
STOCKS = (
    ("net_worth", "equity attributable to owners of the parent", ("EquityAttributableToOwnersOfParent",)),
    ("equity", "total equity", ("Equity",)),
    ("total_assets", "total assets", ("Assets",)),
    ("borrowings_noncurrent", "non-current borrowings", ("BorrowingsNoncurrent",)),
    ("borrowings_current", "current borrowings", ("BorrowingsCurrent",)),
    ("cash", "cash and cash equivalents", ("CashAndCashEquivalents",)),
    ("contingent_liabilities", "contingent liabilities", ("ContingentLiabilities",)),
)
PER_SHARE = {"eps"}
# Looked for in the PDF before the file is trusted. Large figures only: a 300-page report prints nearly every
# small number somewhere, so a profit of ₹30 Cr would be "found" whatever file it came from.
CONFIRM = ("revenue", "total_assets", "equity")
# Loans, advances and receivables due from directors or the firms they are partners or directors in
DIRECTOR_DUES = ("LoansDueByDirectors", "AdvanceDueByDirectors", "TradeReceivablesDueByDirectors",
                 "LoansDueByFirmsOrCompaniesInWhichAnyDirectorIsPartnerOrDirector",
                 "AdvanceDueByFirmsOrCompaniesInWhichAnyDirectorIsPartnerOrDirector",
                 "TradeReceivablesDueByFirmsOrCompaniesInWhichAnyDirectorIsPartnerOrDirector")
# The CARO clauses the annual-report focus names, by the start of their element names (the names run on)
CARO = (("DisclosureInAuditorsReportRelatingToStatutoryDues", "statutory dues (CARO vii)"),
        ("DisclosureInAuditorsReportRelatingToDefaultInRepayment", "defaults in repaying lenders (CARO ix)"),
        ("DisclosureInAuditorsReportRelatingToFraud", "fraud (CARO xi)"))
_OPINION_BASIS = re.compile(r"basis\s+for\s+(qualified\s+|adverse\s+|disclaimer\s+of\s+)?opinion", re.I)
_HEADINGS = (("emphasis of matter", re.compile(r"emphasis\s+of\s+matters?\b", re.I)),
             ("material uncertainty related to going concern",
              re.compile(r"material\s+uncertainty\s+related\s+to\s+going\s+concern", re.I)),
             ("qualified opinion", re.compile(r"(?<!basis for )(?<!un)\b(?:qualified|adverse)\s+opinion|"
                                              r"disclaimer\s+of\s+opinion", re.I)))
MAX_LINE_ITEMS = 6
EXCERPT = 320


@dataclass
class AnnualReport:
    basis: str | None                  # CONSOLIDATED or STANDALONE
    period_end: date                   # the year the report closes
    rounding: str | None = None        # how the PDF prints its statements: "Millions", "Lakhs", "Crores"
    current: dict[str, float] = field(default_factory=dict)   # metric -> ₹ Cr (EPS ₹/share), zeros left out
    prior: dict[str, float] = field(default_factory=dict)     # the same for the year before
    auditors: list[str] = field(default_factory=list)
    qualified_flag: bool | None = None  # WhetherAuditorsReportHasBeenQualifiedOrHasAnyReservationsOrContainsAdverseRemarks
    opinion: str | None = None         # unmodified / qualified / adverse / disclaimer, from the report's own heading
    report_notes: list[tuple[str, str]] = field(default_factory=list)   # (heading, the words under it)
    contingent: list[tuple[str, float]] = field(default_factory=list)   # (class as described, ₹ Cr)
    related_flows: list[tuple[str, str, str, float]] = field(default_factory=list)     # (party, kind, nature, ₹ Cr)
    related_balances: list[tuple[str, str, str, float]] = field(default_factory=list)  # (party, kind, payable/receivable, ₹ Cr)
    related_gross: float | None = None
    kmp_pay: list[tuple[str, str, float]] = field(default_factory=list)   # (name, designation, ₹ Cr)
    director_dues: float | None = None
    loss_entities: list[tuple[str, str, float]] = field(default_factory=list)  # (entity, type, share of group P&L ₹ Cr)
    caro: list[tuple[str, str]] = field(default_factory=list)                   # (clause, the auditor's words)

    @property
    def fy(self) -> str:
        return fy_label(self.period_end)

    def figures(self) -> int:
        return len(self.current) + len(self.prior) + len(self.contingent) + len(self.related_flows) \
            + len(self.related_balances) + len(self.kmp_pay) + len(self.loss_entities)


_FY_SPAN = re.compile(r"\b(20\d\d)\s*[-–/]\s*(\d\d)\b(?![-/]\d)")
_YEAR_END = re.compile(r"\b31(?:st)?\s*(?:march|mar)\b[,.]?\s*(20\d\d)|\bmarch\s*31(?:st)?,?\s*(20\d\d)", re.I)


def report_year(headline: str, subject: str, filed_at: str) -> int:
    """The year the report's financial year ends in (2025 for 2024-25): from the headline ("Annual Report for
    the financial year 2024-25", "F.Y.E. 31st March 2026"), else from when it was filed - a report filed from
    April on is the year just closed. A year read from the filing, never "the newest file NSE has": Kanoria's
    FY26 report was filed in August 2026, when the only file listed was FY25's."""
    words = f"{headline} {subject}"
    span = _FY_SPAN.search(words)
    if span and int(span.group(2)) == (int(span.group(1)) + 1) % 100:
        return int(span.group(1)) + 1
    end = _YEAR_END.search(words)
    if end:
        return int(end.group(1) or end.group(2))
    filed = date.fromisoformat(filed_at[:10])
    return filed.year if filed.month >= 4 else filed.year - 1


def pick(listing, year: int) -> list:
    """The files for that year, one per basis (the list keeps the latest of each), consolidated first."""
    return sorted((f for f in listing if f.to_year == year), key=lambda f: f.basis != "CONSOLIDATED")


def fy_label(end: date) -> str:
    return f"FY{end.year % 100:02d}" if end.month == 3 else f"the year to {end.day} {end:%B %Y}"


def _day(d: date) -> str:
    return f"{d.day} {d:%B %Y}"


def _cr(value: float) -> str:
    return f"{value:,.2f} Cr"


def _words(member: str) -> str:
    """"JointControlOrSignificantInfluenceMember" -> "joint control or significant influence"."""
    name = re.sub(r"Member$", "", member.rsplit(":", 1)[-1])
    name = re.sub(r"OfEntityOrParent$", "", name)
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name).lower().strip()


def _clean(text: str) -> str:
    """An XBRL text block as plain words: tags, entities and runs of space removed."""
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    return re.sub(r"\s+", " ", text.replace(" ", " ")).strip()


def _excerpt(text: str, limit: int = EXCERPT) -> str:
    """The opening of a passage, cut at a sentence end where one falls late enough."""
    if len(text) <= limit:
        return text
    cut = text.rfind(". ", 0, limit)
    return text[:cut + 1] if cut >= limit // 3 else text[:limit].rsplit(" ", 1)[0] + " ..."


def _contexts(root) -> dict[str, dict]:
    """id -> {"start", "end", "instant", "dims": {axis: member}}. A typed member's value is its child's text
    (a related party's or a person's own key), which xbrl._contexts does not read."""
    out = {}
    for ctx in root.iter():
        if _local(ctx.tag) != "context":
            continue
        info: dict = {"dims": {}}
        for el in ctx.iter():
            name = _local(el.tag)
            if name in ("startDate", "endDate", "instant") and el.text:
                try:
                    info[name] = date.fromisoformat(el.text.strip()[:10])
                except ValueError:
                    pass
            elif name in ("explicitMember", "typedMember"):
                value = "".join(el.itertext()).strip()
                # the axis is a QName ("ind-as:RelatedPartyAxis"), and the prefix is the filer's choice
                info["dims"][el.get("dimension", "").rsplit(":", 1)[-1]] = value.rsplit(":", 1)[-1]
        info["end"] = info.get("endDate") or info.get("instant")
        out[ctx.get("id")] = info
    return out


def parse(data: bytes) -> AnnualReport | None:
    """One annual-report instance; None when it is not one (no year's revenue, profit or assets in it)."""
    data = as_utf8(data)
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    contexts, units = _contexts(root), _units(root)
    facts = []   # (name, context info, MONEY / PER_SHARE / SHARES / PURE or TEXT, raw text)
    for el in root.iter():
        ref, unit = el.get("contextRef"), el.get("unitRef")
        if ref is None or el.text is None or ref not in contexts:
            continue
        facts.append((_local(el.tag), contexts[ref], units.get(unit, "PURE") if unit else "TEXT", el.text.strip()))
    years = [c["endDate"] for c in contexts.values() if "startDate" in c and "endDate" in c and not c["dims"]
             and 11 <= round(((c["endDate"] - c["startDate"]).days + 1) / 30.44) <= 13]
    if not years:
        return None
    end = max(years)
    prior_end = max((d for d in years if d < end), default=None)
    text: dict[str, str] = {}   # the company-level text facts, the year's own where both years carry one
    for name, info, kind, value in facts:
        if kind == "TEXT" and not info["dims"] and value and (name not in text or info["end"] == end):
            text[name] = value
    nature = text.get("NatureOfReportStandaloneConsolidated", "").lower()
    report = AnnualReport(basis="CONSOLIDATED" if "consolidated" in nature else "STANDALONE" if "standalone" in nature else None,
                          period_end=end, rounding=text.get("LevelOfRoundingUsedInFinancialStatements") or None)

    def amount(value: str, kind: str, per_share: bool = False) -> float | None:
        number = _num(value)
        if number is None or number == 0:
            return None
        if per_share:
            return number if kind in ("PER_SHARE", "PURE") else None
        return number / 1e7 if kind == "MONEY" else None

    plain: dict[tuple[str, date], tuple[float, str]] = {}   # (name, period end) -> first non-dimensional value
    share_class: dict[tuple[str, date], tuple[float, str]] = {}
    for name, info, kind, value in facts:
        if info["end"] is None or kind == "TEXT":
            continue
        if not info["dims"]:
            plain.setdefault((name, info["end"]), (value, kind))
        elif set(info["dims"]) == {"ClassesOfEquityShareCapitalAxis"}:
            share_class.setdefault((name, info["end"]), (value, kind))
    for metric, _, names in FLOWS + STOCKS:
        for when, into in ((end, report.current), (prior_end, report.prior)):
            for name in names:
                found = plain.get((name, when)) or (share_class.get((name, when)) if metric in PER_SHARE else None)
                value = amount(*found, per_share=metric in PER_SHARE) if found else None
                if value is not None:
                    into[metric] = value
                    break
    if not any(m in report.current for m in CONFIRM):
        return None

    _auditor(report, facts, text)
    _contingent(report, facts)
    _related(report, facts)
    _people(report, facts)
    _entities(report, facts)
    return report


def _at(info: dict, end: date) -> bool:
    return info["end"] == end


def _auditor(report: AnnualReport, facts, text: dict) -> None:
    firms: dict[str, list[str]] = {}
    for name, info, kind, value in facts:
        if kind != "TEXT" or "AuditorsAxis" not in info["dims"] or not value:
            continue
        firms.setdefault(info["dims"]["AuditorsAxis"], []).append(f"{name}={value}")
    for member in sorted(firms):
        fields = dict(item.split("=", 1) for item in firms[member])
        firm = fields.get("NameOfAuditFirm")
        if not firm:
            continue
        parts = [firm + (f" (firm registration {fields['FirmsRegistrationNumberOfAuditFirm']})"
                         if fields.get("FirmsRegistrationNumberOfAuditFirm") else "")]
        if fields.get("NameOfAuditorSigningReport"):
            parts.append(f"signed by {fields['NameOfAuditorSigningReport']}")
        signed = fields.get("DateOfSigningAuditReportByAuditors", "")
        try:
            parts.append(f"on {_day(date.fromisoformat(signed[:10]))}")
        except ValueError:
            pass
        report.auditors.append(" ".join(parts))
    flag = next((v for k, v in text.items() if k.startswith("WhetherAuditorsReportHasBeenQualified")), "").lower()
    report.qualified_flag = True if flag == "true" else False if flag == "false" else None
    body = _clean(text.get("DisclosureInAuditorsReportExplanatory", ""))
    basis = _OPINION_BASIS.search(body)
    if basis:
        kind = (basis.group(1) or "").strip().lower()
        report.opinion = {"": "unmodified", "qualified": "qualified", "adverse": "adverse"}.get(kind, "disclaimer")
        if report.opinion != "unmodified":  # what the auditor qualified, in its own words
            report.report_notes.append((basis.group(0), _excerpt(body[basis.start():])))
    for heading, pattern in _HEADINGS:
        for m in pattern.finditer(body):
            if heading == "qualified opinion" and basis and report.opinion != "unmodified" and m.start() < basis.start():
                continue  # the opinion on the statements itself, already stated
            words = _excerpt(body[m.start():])
            if len(words) > len(m.group(0)) + 20:
                report.report_notes.append((heading, words))
            break
    for prefix, label in CARO:
        value = next((_clean(v) for name, info, kind, v in facts if kind == "TEXT" and name.startswith(prefix)
                      and _at(info, report.period_end)), "")
        if len(value) >= 40:
            report.caro.append((label, _excerpt(value)))


def _contingent(report: AnnualReport, facts) -> None:
    described = {tuple(sorted(info["dims"].items())): _clean(value) for name, info, kind, value in facts
                 if name == "DescriptionOfNatureOfObligationContingentLiabilities" and _at(info, report.period_end)}
    for name, info, kind, value in facts:
        if name != "EstimatedFinancialEffectOfContingentLiabilities" or kind != "MONEY" or not _at(info, report.period_end):
            continue
        what = described.get(tuple(sorted(info["dims"].items())))
        number = _num(value)
        # A class with no description of its own, or one pointing at its children ("Refer to child member",
        # Prism FY26: the 565.52 its three classes add to), is a subtotal of the others.
        if what and number and not re.match(r"(refer\b|na$|nil$|-)", what, re.I):
            report.contingent.append((_excerpt(what, 120), number / 1e7))
    report.contingent.sort(key=lambda c: -abs(c[1]))


def _related(report: AnnualReport, facts) -> None:
    names: dict[tuple[str, str], str] = {}
    for name, info, kind, value in facts:
        party = info["dims"].get("RelatedPartyAxis")
        if name == "NameOfRelatedParty" and party and value:
            names.setdefault((info["dims"].get("CategoriesOfRelatedPartiesAxis", ""), party), _clean(value))
    for name, info, kind, value in facts:
        party = info["dims"].get("RelatedPartyAxis")
        number = _num(value)
        if not party or kind != "MONEY" or not number or not _at(info, report.period_end):
            continue
        category = info["dims"].get("CategoriesOfRelatedPartiesAxis", "")
        who = names.get((category, party))
        if not who:
            continue
        if name in ("AmountsPayableRelatedPartyTransactions", "AmountsReceivableRelatedPartyTransactions"):
            side = "payable to" if "Payable" in name else "receivable from"
            report.related_balances.append((who, _words(category), side, number / 1e7))
        elif "RelatedPartyTransactions" in name or name == "BadDebtsOfRelatedParties":
            # "PurchasesOfGoodsRelatedPartyTransactions" -> "purchases of goods",
            # "OtherRelatedPartyTransactionsContributionReceived" -> "other transactions, contribution received"
            head, _, tail = name.partition("RelatedPartyTransactions")
            nature = f"{_words(head)} transactions, {_words(tail)}" if tail else _words(head)
            report.related_flows.append((who, _words(category), nature, number / 1e7))
    report.related_flows.sort(key=lambda r: -abs(r[3]))
    report.related_balances.sort(key=lambda r: -abs(r[3]))
    gross = next((_num(v) for n, info, kind, v in facts if n == "GrossValueOfTransactionsWithRelatedParties"
                  and not info["dims"] and kind == "MONEY" and _at(info, report.period_end)), None)
    report.related_gross = gross / 1e7 if gross else None


def _people(report: AnnualReport, facts) -> None:
    """Key managerial personnel's pay from the board's report, and what directors owe the company."""
    pay: dict[str, dict[str, float]] = {}
    who: dict[str, dict[str, str]] = {}
    for name, info, kind, value in facts:
        person = info["dims"].get("KeyManagerialPersonnelsAndDirectorsAxis")
        if not person or not _at(info, report.period_end):
            continue
        if kind == "MONEY" and _num(value):
            pay.setdefault(person, {})[name] = _num(value) / 1e7
        elif kind == "TEXT" and value:
            who.setdefault(person, {})[name] = _clean(value)
    for person, amounts in pay.items():
        # the whole remuneration where it is tagged; a director paid only sitting fees has no gross salary
        value = amounts.get("KeyManagerialPersonnelOrDirectorRemuneration") or amounts.get("GrossSalaryToKeyManagerialPersonnelOrDirector")
        if value:
            details = who.get(person, {})
            report.kmp_pay.append((details.get("NameOfKeyManagerialPersonnelOrDirector", person),
                                   details.get("DesignationOfKeyManagerialPersonnelOrDirector", ""), value))
    report.kmp_pay.sort(key=lambda k: -k[2])
    dues = 0.0
    for wanted in DIRECTOR_DUES:
        # the item's total where it is tagged, else its current and non-current parts
        parts = [(bool(info["dims"]), _num(v) or 0) for n, info, kind, v in facts if n == wanted and kind == "MONEY"
                 and _at(info, report.period_end) and set(info["dims"]) <= {"ClassificationBasedOnCurrentNoncurrentAxis"}]
        total = [v for dimensional, v in parts if not dimensional]
        dues += total[0] if total else sum(v for _, v in parts)
    report.director_dues = dues / 1e7 if dues > 0 else None


def _entities(report: AnnualReport, facts) -> None:
    """Group entities whose share of the consolidated result is a loss (Schedule III's additional information)."""
    named: dict[str, dict[str, str]] = {}
    shares: dict[str, float] = {}
    for name, info, kind, value in facts:
        entity = info["dims"].get("EntitiesConsolidatedAxis")
        if not entity or not _at(info, report.period_end):
            continue
        if name in ("NameOfEntityConsolidated", "TypeOfEntityConsolidated") and value:
            named.setdefault(entity, {})[name] = _clean(value)
        elif name == "AmountOfShareInProfitOrLossOfEntityConsolidated" and kind == "MONEY" and _num(value):
            shares[entity] = _num(value) / 1e7
    for entity, share in shares.items():
        kind = named.get(entity, {}).get("TypeOfEntityConsolidated", "")
        title = named.get(entity, {}).get("NameOfEntityConsolidated", entity)
        if share < 0 and "parent" not in kind.lower() and not title.lower().startswith("refer"):
            report.loss_entities.append((title, kind, share))
    report.loss_entities.sort(key=lambda e: e[2])


def confirm(report: AnnualReport, text: str) -> bool:
    """True when the year's revenue, profit, assets or equity appears in the PDF's text at a unit it may be printed
    in (or there is no text to look in): a file for another company or year, or in the wrong scale, has none."""
    if not (text or "").strip():
        return True
    return appears_in([report.current[m] for m in CONFIRM if m in report.current], text) is not False


# A CARO clause is mostly the auditor confirming nothing is wrong ("has been regular in depositing", "has not
# defaulted", "no fraud ... has been noticed"); only a remark that something is wrong is a red flag.
_CARO_CLEAN = re.compile(r"\b(?:has|have)\s+been\s+regular|(?<!not been )\bregular\s+in\s+depositing|\b(?:has|have)\s+not\s+defaulted|"
                         r"\bno\s+(?:fraud|default|material\s+fraud)|\bnot\s+applicable\b|\bno\s+such\b|\bnil\b", re.I)
_CARO_ADVERSE = re.compile(r"\bnot\s+(?:been\s+)?regular|\bhas\s+defaulted|\bdefaults?\s+in\s+(?:repayment|payment)|"
                           r"\bdelays?\s+in\s+(?:depositing|repayment)|\b(?:not|have\s+not)\s+been\s+deposited|"
                           r"\boutstanding\s+for\s+a\s+period\s+of\s+more\s+than\s+six\s+months|\bexcept\s+for\b|"
                           r"\bfraud\b[^.]{0,80}\b(?:has|was|were)\s+(?:been\s+)?(?:noticed|reported)(?![^.]{0,40}\bno\b)", re.I)


def caro_adverse(text: str) -> bool:
    """Whether the auditor's words under a CARO clause say something is wrong."""
    return bool(_CARO_ADVERSE.search(text or "")) and not (_CARO_CLEAN.search(text or "") and not re.search(r"\bexcept\b", text or "", re.I))


def card_block(reports: list[AnnualReport]) -> dict | None:
    """The annual report card's own block, made by code from the company's tagged file (owner, 22 Oct 2026: an annual
    report is read for its red flags, not as a results card): the auditor's opinion and the matters it raises, CARO
    remarks, contingent liabilities against net worth, related-party dealings against revenue, loss-making group
    entities and the best-paid KMP. Consolidated leads; the standalone file fills what it alone carries."""
    if not reports:
        return None
    reports = sorted(reports, key=lambda r: r.basis != "CONSOLIDATED")
    main = reports[0]
    first = lambda pick: next((v for r in reports if (v := pick(r))), None)
    opinion = main.opinion or first(lambda r: r.opinion)
    qualified = first(lambda r: r.qualified_flag)
    contingent = first(lambda r: r.contingent) or []
    flows = first(lambda r: r.related_flows) or []
    block = {
        "fy": main.fy, "basis": main.basis,
        "opinion": opinion or ("qualified or with reservations" if qualified else None),
        "auditors": (first(lambda r: r.auditors) or [])[:2],
        "matters": [heading for heading, _ in (first(lambda r: r.report_notes) or [])][:4],
        "caro": [{"clause": c, "text": t[:180]} for c, t in (first(lambda r: r.caro) or []) if caro_adverse(t)][:3],
        "caro_count": len(first(lambda r: r.caro) or []),
        "contingent_cr": round(sum(v for _, v in contingent), 2) if contingent else None,
        "contingent_top": [{"what": w[:80], "cr": round(v, 2)} for w, v in sorted(contingent, key=lambda x: -x[1])[:3]],
        "related_gross_cr": first(lambda r: r.related_gross),
        "related_top": [{"party": p[:60], "nature": n[:50], "cr": round(v, 2)}
                        for p, _, n, v in sorted(flows, key=lambda x: -abs(x[3]))[:3]],
        "loss_entities": len(first(lambda r: r.loss_entities) or []),
        "loss_entities_cr": round(sum(v for _, _, v in (first(lambda r: r.loss_entities) or []) if v < 0), 2) or None,
        "kmp_top": [{"name": n[:50], "role": d[:40], "cr": round(v, 2)}
                    for n, d, v in sorted(first(lambda r: r.kmp_pay) or [], key=lambda x: -x[2])[:2]],
        "revenue_cr": main.current.get("revenue"),
        "net_worth_cr": main.current.get("net_worth") or main.current.get("equity"),
    }
    return {k: v for k, v in block.items() if v not in (None, [], 0)} | {"fy": main.fy}


def table(reports: list[AnnualReport]) -> str:
    """The reports (one per basis, the same year) as the lines put in front of the annual report's text. The
    consolidated instance leads; the standalone one adds its headline figures and what only it carries."""
    if not reports:
        return ""
    reports = sorted(reports, key=lambda r: r.basis != "CONSOLIDATED")
    main, others = reports[0], reports[1:]
    fy, prior_fy = main.fy, fy_label(date(main.period_end.year - 1, main.period_end.month, main.period_end.day))
    basis = (main.basis or "basis not stated").lower()
    printed = f"; the PDF prints its statements in {main.rounding.lower()}" if main.rounding else ""
    lines = [f"Machine-tagged annual report (XBRL the company filed with NSE, {fy}, {basis}, ₹ crore unless noted; "
             f"exact, prefer these over figures read from the PDF{printed}):"]
    for metric, wording, _ in FLOWS:
        if metric in main.current and metric not in ("managerial_remuneration", "eps"):   # no EPS for the model (owner rule 26 Oct 2026)
            lines.append(f"- {basis} {wording} {fy}: {_figure(main, metric, prior_fy)}")
    at = _day(main.period_end)
    # the company's own equity is its net worth; a group's net worth is the owners' share, without minorities
    same = main.current.get("net_worth") in (None, main.current.get("equity"))
    for metric, wording, _ in STOCKS:
        if metric in ("borrowings_noncurrent", "borrowings_current", "contingent_liabilities") or (metric == "net_worth" and same):
            continue
        if metric in main.current:
            wording = "total equity (net worth)" if metric == "equity" and same else wording
            lines.append(f"- {basis} {wording} at {at}: {_figure(main, metric, prior_fy)}")
    debt = [main.current.get(m) for m in ("borrowings_noncurrent", "borrowings_current")]
    if any(debt):
        parts = ", ".join(f"{label} {_cr(v)}" for label, v in zip(("non-current", "current"), debt) if v)
        # the year before too: Kanoria's card compared with FY24's ₹506.72 Cr, a sum no line printed (held)
        before = [main.prior.get(m) for m in ("borrowings_noncurrent", "borrowings_current")]
        parts += f"; {prior_fy}: {_cr(sum(v for v in before if v))}" if any(before) else ""
        lines.append(f"- {basis} borrowings at {at}: {_cr(sum(v for v in debt if v))} ({parts})")
    for other in others:
        figures = [f"{wording} {other.fy} {_cr(other.current[m])}" for m, wording, _ in FLOWS
                   if m in ("revenue", "pbt", "pat") and m in other.current]
        if "equity" in other.current:
            figures.append(f"total equity at {_day(other.period_end)} {_cr(other.current['equity'])}")
        if figures:
            lines.append(f"- {(other.basis or 'other basis').lower()} (the company alone): " + "; ".join(figures))
    if "managerial_remuneration" in main.current:
        lines.append(f"- {basis} managerial remuneration {fy}: {_cr(main.current['managerial_remuneration'])}")
    for report in reports:
        # The total and its classes on one line, so a card quoting either quotes both: Jubilant's card quoted the
        # by-class line for its ₹368.40 Cr total, printed on a line of its own, and was held. With no total tagged,
        # what the listed classes add to (a class with no description of its own is never among them).
        b = (report.basis or "").lower()
        total = report.current.get("contingent_liabilities")
        classes = "; ".join(f"{what} {_cr(v)}" for what, v in report.contingent[:MAX_LINE_ITEMS])
        if total and classes:
            lines.append(f"- {b} contingent liabilities at {at}: {_cr(total)}; by class: {classes}")
        elif total:
            lines.append(f"- {b} contingent liabilities at {at}: {_cr(total)}")
        elif classes:
            lines.append(f"- {b} contingent liabilities at {at}, by class: {classes}"
                         + (f"; all {len(report.contingent)} classes add to {_cr(sum(v for _, v in report.contingent))}"
                            if len(report.contingent) > 1 else ""))
        if total or classes:
            break   # one basis is enough; the consolidated set includes the company's own
    for report in reports:
        b = (report.basis or "").lower()
        if report.related_flows:
            total = sum(abs(v) for *_, v in report.related_flows)
            parties = len({party for party, *_ in report.related_flows})
            lines.append(f"- {b} related-party transactions {fy}, as tagged party by party: {parties} parties, "
                         f"{_cr(total)} summing every tagged flow both ways; largest: " + "; ".join(
                             f"{party} ({kind}) {nature} {_cr(v)}" for party, kind, nature, v in report.related_flows[:MAX_LINE_ITEMS]))
        if report.related_balances:
            lines.append(f"- {b} related-party balances at {at}: " + "; ".join(
                f"{side} {party} ({kind}) {_cr(v)}" for party, kind, side, v in report.related_balances[:4]))
        if report.related_gross:
            lines.append(f"- {b} gross value of related-party transactions {fy}, as the company states it: "
                         f"{_cr(report.related_gross)}")
        if report.related_flows or report.related_gross:
            break
    for report in reports:
        if report.kmp_pay:
            total = sum(v for *_, v in report.kmp_pay)
            lines.append(f"- remuneration of key managerial personnel and directors {fy} (board's report): "
                         f"{_cr(total)} in all; " + "; ".join(
                             f"{name}{f' ({role})' if role else ''} {_cr(v)}" for name, role, v in report.kmp_pay[:5]))
            break
    for report in reports:
        if report.director_dues:
            lines.append(f"- loans, advances and receivables due from directors or their firms at {at} "
                         f"({(report.basis or '').lower()}): {_cr(report.director_dues)}")
            break
    for report in reports:
        if report.loss_entities:
            lines.append(f"- group entities with a loss {fy}, by their share of the consolidated result: " + "; ".join(
                f"{title}{f' ({kind})' if kind else ''} {_cr(v)}" for title, kind, v in report.loss_entities[:5]))
            break
    # the lead report's: the same firm is spelt two ways across the two files (Prism FY26)
    firms = next((report.auditors for report in reports if report.auditors), [])
    if firms:
        lines.append("- statutory auditor: " + "; ".join(firms))
    opinions = [f"{(r.basis or '').lower()} {r.opinion}" for r in reports if r.opinion]
    if opinions:
        lines.append("- the auditor's opinion, read from its basis-for-opinion heading: " + "; ".join(opinions))
    flags = [f"{(r.basis or '').lower()} {'yes' if r.qualified_flag else 'no'}" for r in reports if r.qualified_flag is not None]
    if flags:
        lines.append("- the company's own XBRL answer to \"auditor's report qualified, with reservations or adverse "
                     "remarks\": " + "; ".join(flags))
    for report in reports:
        b = (report.basis or "").lower()
        for heading, words in report.report_notes:
            where = " (outside the opinion on the statements, such as the report on internal financial controls)" \
                if heading == "qualified opinion" else ""
            lines.append(f"- {heading} in the {b} auditor's report{where}: \"{words}\"")
        for label, words in report.caro:
            lines.append(f"- auditor on {label}: \"{words}\"")
    return "\n".join(lines)


def _figure(report: AnnualReport, metric: str, prior_fy: str) -> str:
    unit = " ₹/share" if metric in PER_SHARE else " Cr"
    now = report.current[metric]
    text = (f"{now:,.2f}{unit}")
    before = report.prior.get(metric)
    if before is not None:
        change = _change(now, before) if now > 0 else None
        text += f" ({prior_fy}: {before:,.2f}{unit}{f', {change:+.1f}%' if change is not None else ''})"
    return text
