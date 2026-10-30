"""What a results or annual-report XBRL says that memory never kept, read by code from the stored facts (owner, 30 Oct 2026: YES to
TODO 138's topics and the annual-report extras of TODO 132, first group). No model, no download: the facts document is
``xbrl_facts.parse_facts`` / ``parse_annual_facts`` (dimensional facts keep their axis and member), as segments.py and statements.py
read it. Four dossier keys, each a list of entries labelled ``lab.by = "file"``, one entry per period and basis (and kind for the
audit key), a revised file replacing the same period and basis, the newest ``MAX_ENTRIES[key]`` kept:

``audit``  (quarter, kind "results"): ``audited`` (WhetherResultsAreAuditedOrUnaudited at the quarter), ``audited_ytd`` (at the
    half, nine months or year ending then), ``opinion`` (DeclarationOfUnmodifiedOpinionOrStatementOnImpactOfAuditQualification:
    "Declaration of unmodified opinion" or "Not applicable"), ``qualification_status``
    (WhetherResultsAreAuditedOrUnauditedForImpactOfAuditQualification), ``auditors`` [{name (AuditorsFirmName), peer_review_valid
    (WhetherTheFirmHoldsAValidPeerReviewCertificateIssuedByPeerReviewBoardOfICAI), certificate_valid_until (ValidityDateOfCertificate)}]
    (the capmkt taxonomy's AuditorAxis; two auditors give two rows). (year, kind "annual", the MCA taxonomy): ``qualified``
    (WhetherAuditorsReportHasBeenQualifiedOrHasAnyReservationsOrContainsAdverseRemarks), ``auditors`` [{name (NameOfAuditFirm),
    signing_partner, signed_on, firm_registration_no}] and ``clauses`` {default_in_repayment, fraud, statutory_dues}: {text, remark
    (the AuditorsQualificationsReservationsOrAdverseRemarks member, e.g. AuditorsFavourableRemark, ClauseNotApplicable)}.
``cash_flow_detail``: every cash-flow line (adjustments, working capital, tax, interest, dividends, capex, proceeds and repayments
    of borrowings, lease payments ...) in crore, the half year of a Q2 file (``span`` "H1", period "Q2FY27") and the year of a Q4
    file or an annual report (``span`` "FY", period "FY26").
``related_parties``: quarter (kind "results"): ``items`` one per RelatedPartyTransactionAxis member: counterparty, relationship, type,
    other_details, entity, amount_cr, approved_cr, remarks, opening_cr and closing_cr (the balances at the period's start and end), and
    ``other`` for any further element a filer tags (a loan's rate or tenure). Year (kind "annual"): ``parties`` one per related party:
    name, category, ``flows`` (element: crore for the year) and ``balances`` (element: crore at the year end).
``fin_ratios``: the ratios the file states for the quarter: CET1 and additional tier 1, debt-equity, debt and interest service coverage,
    gross and net NPAs (amounts in crore, percentages), the insurer's solvency, persistency (13/25/37/49/61 months), conservation and
    shareholders' fund NPAs, and the ones xbrl.RATIO_TAGS reads for cards. Values are AS FILED: fractions stay fractions (0.1973 is
    19.73%), the solvency ratio is as the filer wrote it (1.8 is 180%; filers disagree on its scale), money is in crore.

The second group (owner, 30 Oct 2026: yes), the same way (one entry per period and basis, a template's all-zero filler never stored):

``oci`` (quarter): ``oci_net_cr`` (OtherComprehensiveIncomeNetOfTaxes, else OtherComprehensiveIncome), ``not_reclassified_cr`` /
    ``reclassified_cr`` (AmountOfItemThatWill[Not]BeReclassifiedToProfitAndLoss) and their tax (IncomeTaxRelatingToIt[em]sThatWill[Not]
    BeReclassifiedToProfitOrLoss; older taxonomies misspell it "Itmes"), ``profit_cr`` (ProfitLossForPeriod), ``total_comprehensive_cr``
    (ComprehensiveIncomeForThePeriod) with the owners' and minorities' parts, and ``items`` one per ItemsThat[Will|WillNot]BeReclassified
    ToProfitAndLossAxis member (group, description, amount_cr).
``discontinued`` (quarter): ProfitLossFromDiscontinuedOperationsBeforeTax, TaxExpenseOfDiscontinuedOperations,
    ProfitLossFromDiscontinuedOperationsAfterTax, with ProfitLossForPeriodFromContinuingOperations (continuing PAT) and ProfitLossForPeriod;
    stored only when a discontinued figure is not 0.
``segment_balance`` (quarter): the segment note's assets and liabilities, one row per ReportableSegmentAssetsAxis /
    ReportableSegmentLiabilitiesAxis member (SegmentAssets, SegmentLiabilities, named by its DescriptionOfReportableSegment, so the row
    matches segments.py's revenue rows by name), and the file's totals (SegmentAssets, SegmentLiabilities, NetSegmentAssets,
    NetSegmentLiabilities).
``dividends`` (quarter): ``face_value`` (FaceValueOfEquityShareCapital, rupees a share) and the amounts of FinalDividend and InterimDividend
    (crore) where a filer tags them (an insurer's template; the fixtures hold them as 0, which is never stored).
``kmp_pay`` (annual report): one row per KeyManagerialPersonnelsAndDirectorsAxis member: name, designation, pay_cr
    (KeyManagerialPersonnelOrDirectorRemuneration, else GrossSalaryToKeyManagerialPersonnelOrDirector); the totals ManagerialRemuneration
    and RemunerationToDirectors when not 0 (Kanoria files them as 0 beside real rows).
``contingent_liabilities`` (annual report): ``has_contingent`` (WhetherThereAreAnyContingentLiabilities), ``total_cr`` (ContingentLiabilities,
    when not 0) and ``classes`` one per ClassesOfContingentLiabilitiesAxis member with a description and an amount at the year end
    (DescriptionOfNatureOfObligationContingentLiabilities, EstimatedFinancialEffectOfContingentLiabilities); a class with no description
    of its own is a subtotal, as annual_xbrl reads it, and is left out.

Nothing here changes a figure the cards read. A failure never fails a filing (statements.from_file)."""

from __future__ import annotations

import logging
import re
from datetime import date

from . import xbrl_facts
from .memory_gaps import quarter_end
from .periods import quarter_index

log = logging.getLogger(__name__)

AUDIT, CASH_FLOW, RELATED, RATIOS = "audit", "cash_flow_detail", "related_parties", "fin_ratios"
OCI, DISCONTINUED, SEGMENT_BALANCE, DIVIDENDS, KMP_PAY, CONTINGENT = (
    "oci", "discontinued", "segment_balance", "dividends", "kmp_pay", "contingent_liabilities")
KEYS = (AUDIT, CASH_FLOW, RELATED, RATIOS, OCI, DISCONTINUED, SEGMENT_BALANCE, DIVIDENDS, KMP_PAY, CONTINGENT)
MAX_ENTRIES = {AUDIT: 60, CASH_FLOW: 16, RELATED: 24, RATIOS: 60, OCI: 60, DISCONTINUED: 60, SEGMENT_BALANCE: 60, DIVIDENDS: 60,
               KMP_PAY: 16, CONTINGENT: 16}   # cash flow ~6 KB an entry: 8 years of half and full years, one basis
MAX_ITEMS = 60          # related-party transactions of one quarter; the largest first
MAX_PARTIES = 80        # related parties of one annual report
CLAUSE_MAX = 3000       # characters of an auditor's clause kept in the dossier (the facts doc holds up to xbrl_facts.FULL_TEXT_MAX)
MONEY_KEYS = (CASH_FLOW, RELATED, RATIOS, OCI, DISCONTINUED, SEGMENT_BALANCE, DIVIDENDS, KMP_PAY, CONTINGENT)    # a quarter memory holds as unit-slipped (scale_held) gets none of these

# a line of the cash-flow statement, by how the taxonomies name it (Ind AS results, banks, insurers; the annual report's file)
CASH_FLOW_NAME = re.compile(
    r"^(Adjustments|OtherAdjustments|OtherCash|Repayments|ShareOfProfitAndLossFromPartnership|CashFlows|CashReceipts|CashPayment|CashAdvances|Dividends"
    r"(Received|Paid)Classified|Interest(Paid|Received)Classified|IncomeTaxesPaidRefundClassified|OtherInflowsOutflows|Proceeds|Purchase|"
    r"Payments?(Of|For|From|To)|IncreaseDecreaseInCashAndCashEquivalents|EffectOfExchangeRateChangesOnCashAndCashEquivalents|"
    r"CashAndCashEquivalentsCashFlowStatement)")
# the P&L's purchases share the Purchase prefix and the 6- and 12-month contexts (blind review)
CASH_FLOW_NOT = re.compile(r"^(AmountOfItem|IncomeTaxRelating|Purchases$|PurchasesOfStockInTrade$)")

RATIO_ELEMENTS = (
    "CET1Ratio", "AdditionalTier1Ratio", "DebtEquityRatio", "DebtServiceCoverageRatio", "InterestServiceCoverageRatio",
    "GrossNonPerformingAssets", "NonPerformingAssets", "PercentageOfGrossNpa", "PercentageOfNpa", "ReturnOnAssets",
    "SolvencyRatio", "PersistencyRatio13ThMonth", "PersistencyRatio25ThMonth", "PersistencyRatio37ThMonth",
    "PersistencyRatio49ThMonth", "PersistencyRatio61ThMonth", "ConservationRatio", "CombinedRatio", "IncurredClaimRatio",
    "NetRetentionRatio", "ExpensesOfManagementRatio", "GrossNPAsShareholdersFund", "NetNPAsShareholdersFund",
    "PercentageOfGrossNPAsShareholdersFund", "PercentageOfNetNPAsShareholdersFund")

# a ratio a real filer never reports as 0: its 0 is the template's filler (stock-page audit, 30 Oct 2026: SBI's CET1 0.0); a 0 NPA or
# a 0 debt-equity can be true and stays, unless every ratio of the quarter is 0 (then the whole block is filler)
NEVER_ZERO = frozenset({"CET1Ratio", "AdditionalTier1Ratio", "SolvencyRatio", "PersistencyRatio13ThMonth", "PersistencyRatio25ThMonth",
                        "PersistencyRatio37ThMonth", "PersistencyRatio49ThMonth", "PersistencyRatio61ThMonth", "ConservationRatio",
                        "CombinedRatio", "IncurredClaimRatio", "NetRetentionRatio", "ExpensesOfManagementRatio"})


def _real(values: dict) -> dict:
    """The ratios without the template's filler zeros: none when every one is 0, else the zeros of ``NEVER_ZERO`` out."""
    if not any(values.values()):
        return {}
    return {k: v for k, v in values.items() if v or k not in NEVER_ZERO}


CLAUSES = {"DisclosureInAuditorsReportRelatingToDefaultInRepaymentOfFinancialDues": "default_in_repayment",
           "DisclosureInAuditorsReportRelatingToFraudByTheCompanyOrOnTheCompanyByItsOfficersOrItsEmployeesReportedDuringPeriod": "fraud",
           "DisclosureInAuditorsReportRelatingToStatutoryDuesExplanatory": "statutory_dues"}
RPT_TEXT = {"NameOfCounterParty": "counterparty", "RelationshipOfTheCounterpartyWithTheListedEntityOrItsSubsidiary": "relationship",
            "TypeOfRelatedPartyTransaction": "type", "DetailsOfOtherRelatedPartyTransaction": "other_details",
            "NameOfListedEntityOrSubsidiaryEnteringIntoTheTransaction": "entity", "RemarksOnApprovalByAuditCommittee": "remarks"}
RPT_MONEY = {"AmountOfRelatedPartyTransactionDuringTheReportingPeriod": "amount_cr",
             "ValueOfTheRelatedPartyTransactionAsApprovedByTheAuditCommittee": "approved_cr"}
RPT_SKIP = re.compile(r"^PANOf")        # a masked tax number: no memory use
OTHER_TEXT_MAX = 300
RPT_TEXT_MAX = 500      # a counterparty's name, relationship or remark: the facts doc keeps the whole text


def _cr(value) -> float:
    return round(value / xbrl_facts.CRORE, 4)


def _bool(text):
    t = str(text).strip().lower()
    return True if t == "true" else False if t == "false" else None


def _order(period) -> int:
    p = str(period or "")
    return quarter_index(f"Q4{p}" if p.startswith("FY") else p) or 0


def _end(doc: dict) -> date | None:
    """The date the document's own period ends: a quarter's end, or an annual report's year end."""
    if doc.get("kind") == "annual":
        try:
            return date.fromisoformat(doc["year_end"])
        except (KeyError, ValueError):
            return None
    period = doc.get("period") or ""
    return quarter_end(period) if period.startswith("Q") else None


def _live(facts, ctx_id: str, end: date, months: int | None) -> bool:
    return facts._at(ctx_id, end, months, None)


# --- audit ----------------------------------------------------------------------------------------------------------

def _audit_results(doc: dict, end: date) -> dict | None:
    facts = xbrl_facts.Facts(doc)
    out: dict = {}
    auditors: dict[str, dict] = {}
    for el, ctx_id, _unit, value, _ in facts.rows:
        if not isinstance(value, str):
            continue
        ctx = facts.contexts.get(ctx_id) or {}
        dims = ctx.get("d") or {}
        if not dims:
            if el == "WhetherResultsAreAuditedOrUnaudited":
                if _live(facts, ctx_id, end, 3):
                    out.setdefault("audited", value)
                elif ctx.get("e") == end.isoformat() and ctx.get("m") in (6, 9, 12):
                    out.setdefault("audited_ytd", value)
            elif _live(facts, ctx_id, end, 3):
                if el == "DeclarationOfUnmodifiedOpinionOrStatementOnImpactOfAuditQualification":
                    out.setdefault("opinion", value)
                elif el == "WhetherResultsAreAuditedOrUnauditedForImpactOfAuditQualification":
                    out.setdefault("qualification_status", value)
        elif len(dims) == 1 and "Auditor" in next(iter(dims)) and ctx.get("e") == end.isoformat():
            row = auditors.setdefault(next(iter(dims.values())), {})
            if el == "AuditorsFirmName" and value.strip():
                row.setdefault("name", value.strip())
            elif el == "WhetherTheFirmHoldsAValidPeerReviewCertificateIssuedByPeerReviewBoardOfICAI":
                row.setdefault("peer_review_valid", _bool(value))
            elif el == "ValidityDateOfCertificate":
                row.setdefault("certificate_valid_until", value.strip())
    rows = [r for _, r in sorted(auditors.items()) if r.get("name")]
    if rows:
        out["auditors"] = rows
    return out or None


def _audit_annual(doc: dict, end: date) -> dict | None:
    facts = xbrl_facts.Facts(doc)
    out: dict = {}
    auditors: dict[str, dict] = {}
    clauses: dict[str, dict] = {}
    for el, ctx_id, _unit, value, _ in facts.rows:
        if not isinstance(value, str) or not _live(facts, ctx_id, end, 12):
            continue
        dims = (facts.contexts.get(ctx_id) or {}).get("d") or {}
        if not dims:
            if el == "WhetherAuditorsReportHasBeenQualifiedOrHasAnyReservationsOrContainsAdverseRemarks" and _bool(value) is not None:
                out.setdefault("qualified", _bool(value))
            continue
        by_axis = {a.rsplit(":", 1)[-1]: m for a, m in dims.items()}
        if el in CLAUSES and len(dims) == 1:
            member = next(iter(by_axis.values()))
            clauses.setdefault(CLAUSES[el], {"text": value.strip()[:CLAUSE_MAX],
                                             "remark": re.sub(r"Member$", "", member) if "Axis" in next(iter(by_axis)) else None})
        elif "AuditorsAxis" in by_axis and len(dims) == 1:
            row = auditors.setdefault(by_axis["AuditorsAxis"], {})
            for name, field in (("NameOfAuditFirm", "name"), ("NameOfAuditorSigningReport", "signing_partner"),
                                ("DateOfSigningAuditReportByAuditors", "signed_on"), ("FirmsRegistrationNumberOfAuditFirm", "firm_registration_no")):
                if el == name and value.strip():
                    row.setdefault(field, value.strip())
    rows = [r for _, r in sorted(auditors.items()) if r.get("name")]
    if rows:
        out["auditors"] = rows
    if clauses:
        out["clauses"] = clauses
    return out or None


# --- cash flow ------------------------------------------------------------------------------------------------------

def _cash_flow(doc: dict, end: date) -> dict | None:
    months = 12 if doc.get("kind") == "annual" or (doc.get("period") or "").startswith("Q4") else 6 if (doc.get("period") or "").startswith("Q2") else None
    if months is None:
        return None
    facts = xbrl_facts.Facts(doc)
    rows: dict[str, float] = {}
    for el, ctx_id, unit, value, _ in facts.rows:
        if isinstance(value, str) or not facts._is_money(unit) or not CASH_FLOW_NAME.match(el) or CASH_FLOW_NOT.match(el):
            continue
        ctx = facts.contexts.get(ctx_id) or {}
        if ctx.get("d") or not (facts._at(ctx_id, end, months, None) or (el == "CashAndCashEquivalentsCashFlowStatement" and ctx.get("i") == end.isoformat())):
            continue
        rows.setdefault(el, _cr(value))
    if not rows:
        return None
    return {"span": "FY" if months == 12 else "H1", "months": months, "rows": rows}


# --- related parties ------------------------------------------------------------------------------------------------

def _related_results(doc: dict, end: date) -> dict | None:
    facts = xbrl_facts.Facts(doc)
    members: dict[str, dict] = {}
    entered = None
    for el, ctx_id, unit, value, _ in facts.rows:
        ctx = facts.contexts.get(ctx_id) or {}
        dims = ctx.get("d") or {}
        if not dims:
            if el == "WhetherTheCompanyHasEnteredIntoAnyRelatedPartyTransactionDuringThePeriod" and _live(facts, ctx_id, end, 3):
                entered = _bool(value)
            continue
        if len(dims) != 1 or not next(iter(dims)).endswith("RelatedPartyTransactionAxis") or RPT_SKIP.match(el):
            continue
        row = members.setdefault(next(iter(dims.values())), {})
        if el == "AmountOfRelatedPartyTransaction" and not isinstance(value, str) and facts._is_money(unit) and ctx.get("i"):
            row["closing_cr" if ctx["i"] == end.isoformat() else "opening_cr"] = _cr(value)
        elif not (ctx.get("e") == end.isoformat()):
            continue
        elif el in RPT_MONEY and not isinstance(value, str) and facts._is_money(unit):
            row.setdefault(RPT_MONEY[el], _cr(value))
        elif el in RPT_TEXT and isinstance(value, str):
            row.setdefault(RPT_TEXT[el], value.strip()[:RPT_TEXT_MAX])
        elif isinstance(value, str) and value.strip() and el not in RPT_TEXT:
            row.setdefault("other", {}).setdefault(el, value.strip()[:OTHER_TEXT_MAX])
        elif not isinstance(value, str) and el not in RPT_MONEY and el != "AmountOfRelatedPartyTransaction":
            row.setdefault("other", {}).setdefault(el, _cr(value) if facts._is_money(unit) else value)
    items = [r for r in members.values() if r.get("counterparty") or "amount_cr" in r]
    if not items and entered is None:
        return None
    items.sort(key=lambda r: -abs(r.get("amount_cr") or 0.0))
    out = {"n_items": len(items), "items": items[:MAX_ITEMS]}
    if entered is not None:
        out["entered"] = entered
    return out


def _related_annual(doc: dict, end: date) -> dict | None:
    facts = xbrl_facts.Facts(doc)
    parties: dict[tuple[str, str], dict] = {}
    flag = None
    for el, ctx_id, unit, value, _ in facts.rows:
        ctx = facts.contexts.get(ctx_id) or {}
        dims = ctx.get("d") or {}
        if not dims:
            if el == "WhetherThereAreAnyRelatedPartyTransactionsDuringYear" and _live(facts, ctx_id, end, 12):
                flag = _bool(value)
            continue
        by_axis = {a.rsplit(":", 1)[-1]: m for a, m in dims.items()}
        if "RelatedPartyAxis" not in by_axis or set(by_axis) - {"RelatedPartyAxis", "CategoriesOfRelatedPartiesAxis"}:
            continue
        flow = ctx.get("e") == end.isoformat() and ctx.get("m") == 12
        balance = ctx.get("i") == end.isoformat()
        if not (flow or balance):
            continue
        category = re.sub(r"Member$", "", by_axis.get("CategoriesOfRelatedPartiesAxis", ""))
        row = parties.setdefault((category, by_axis["RelatedPartyAxis"]), {"category": category or None, "flows": {}, "balances": {}})
        if el == "NameOfRelatedParty" and isinstance(value, str):
            row.setdefault("party", value.strip())
        elif not isinstance(value, str) and facts._is_money(unit) and "RelatedParty" in el:
            (row["flows"] if flow else row["balances"]).setdefault(el, _cr(value))
    rows = [r for r in parties.values() if r.get("party") and (r["flows"] or r["balances"])]
    if not rows and flag is None:
        return None
    rows.sort(key=lambda r: -sum(abs(v) for v in r["flows"].values()))
    out = {"n_parties": len(rows), "parties": rows[:MAX_PARTIES]}
    if flag is not None:
        out["has_transactions"] = flag
    return out


# --- ratios ---------------------------------------------------------------------------------------------------------

def _ratios(doc: dict, end: date) -> dict | None:
    facts = xbrl_facts.Facts(doc)
    wanted = set(RATIO_ELEMENTS)
    values: dict[str, float] = {}
    fallback: dict[str, float] = {}
    for el, ctx_id, unit, value, _ in facts.rows:
        if el not in wanted or isinstance(value, str):
            continue
        ctx = facts.contexts.get(ctx_id) or {}
        if ctx.get("d") or ctx.get("e") != end.isoformat():
            continue
        v = _cr(value) if facts._is_money(unit) else value
        if ctx.get("m") == 3:
            values.setdefault(el, v)
        else:
            fallback.setdefault(el, v)     # a half-yearly filer states its ratios for the half year
    for el, v in fallback.items():
        values.setdefault(el, v)
    values = _real(values)
    return {"values": values} if values else None


# --- the second group: OCI, discontinued operations, segment balances, dividends, KMP pay, contingent liabilities ----------

OCI_ELEMENTS = {
    "OtherComprehensiveIncomeNetOfTaxes": "oci_net_cr", "OtherComprehensiveIncome": "oci_net_alt_cr",
    "AmountOfItemThatWillNotBeReclassifiedToProfitAndLoss": "not_reclassified_cr",
    "AmountOfItemThatWillBeReclassifiedToProfitAndLoss": "reclassified_cr",
    "IncomeTaxRelatingToItemsThatWillNotBeReclassifiedToProfitOrLoss": "tax_not_reclassified_cr",
    "IncomeTaxRelatingToItmesThatWillNotBeReclassifiedToProfitOrLoss": "tax_not_reclassified_cr",
    "IncomeTaxRelatingToItemsThatWillBeReclassifiedToProfitOrLoss": "tax_reclassified_cr",
    "IncomeTaxRelatingToItmesThatWillBeReclassifiedToProfitOrLoss": "tax_reclassified_cr",
    "ProfitLossForPeriod": "profit_cr", "ComprehensiveIncomeForThePeriod": "total_comprehensive_cr",
    "ComprehensiveIncomeForThePeriodAttributableToOwnersOfParent": "total_comprehensive_owners_cr",
    "ComprehensiveIncomeForThePeriodAttributableToOwnersOfParentNonControllingInterests": "total_comprehensive_nci_cr"}
DISCONTINUED_ELEMENTS = {
    "ProfitLossFromDiscontinuedOperationsBeforeTax": "before_tax_cr", "TaxExpenseOfDiscontinuedOperations": "tax_cr",
    "ProfitLossFromDiscontinuedOperationsAfterTax": "after_tax_cr", "ProfitLossForPeriodFromContinuingOperations": "continuing_profit_cr",
    "ProfitLossForPeriod": "profit_cr"}
DIVIDEND_ELEMENTS = {"FaceValueOfEquityShareCapital": "face_value", "FinalDividend": "final_cr", "InterimDividend": "interim_cr"}
SEGMENT_TOTALS = {"SegmentAssets": "assets_cr", "SegmentLiabilities": "liabilities_cr", "NetSegmentAssets": "net_assets_cr",
                  "NetSegmentLiabilities": "net_liabilities_cr"}
MAX_OCI_ITEMS = 20
MAX_SEGMENTS = 40
MAX_KMP = 40
MAX_CLASSES = 40


def _quarter_values(facts, names: dict, end: date) -> dict:
    """The undimensioned numbers of ``names`` (element -> key) for the quarter ending ``end``: its 3-month fact, else (a half-yearly
    filer) the one ending then. Money in crore; other numbers (a face value) as filed."""
    quarter: dict[str, float] = {}
    other: dict[str, float] = {}
    for el, ctx_id, unit, value, _ in facts.rows:
        if el not in names or isinstance(value, str):
            continue
        ctx = facts.contexts.get(ctx_id) or {}
        if ctx.get("d") or ctx.get("e") != end.isoformat():
            continue
        (quarter if ctx.get("m") == 3 else other).setdefault(names[el], _cr(value) if facts._is_money(unit) else value)
    return {**other, **quarter}


def _current(members) -> set:
    """The members of the file's own column. A legacy results file (Titan Q2FY24) files a segment or an OCI item once for the quarter
    (member "OneReportableSegmentAssets01Member") and again under a "Four" prefix with another figure (the year-ago column) in a context
    of the same end date; the "One" members are the quarter's. A taxonomy with no such prefix keeps every member."""
    members = set(members)
    ones = {m for m in members if m.startswith("One")}
    return ones or members


def _oci(doc: dict, end: date) -> dict | None:
    facts = xbrl_facts.Facts(doc)
    values = _quarter_values(facts, OCI_ELEMENTS, end)
    alt = values.pop("oci_net_alt_cr", None)
    if "oci_net_cr" not in values and alt is not None:
        values["oci_net_cr"] = alt
    if not values.get("total_comprehensive_owners_cr"):    # a 0 beside a real total is the template's filler (Q3FY24): both parts go
        values.pop("total_comprehensive_owners_cr", None)
        values.pop("total_comprehensive_nci_cr", None)
    items: dict[str, dict] = {}
    for el, ctx_id, unit, value, _ in facts.rows:
        ctx = facts.contexts.get(ctx_id) or {}
        dims = ctx.get("d") or {}
        if len(dims) != 1 or ctx.get("e") != end.isoformat() or ctx.get("m") != 3:
            continue
        (axis, member), = dims.items()
        axis = axis.rsplit(":", 1)[-1]
        if axis == "ItemsThatWillNotBeReclassifiedToProfitAndLossAxis":
            group = "not_reclassified"
        elif axis == "ItemsThatWillBeReclassifiedToProfitAndLossAxis":
            group = "reclassified"
        else:
            continue
        row = items.setdefault(f"{group}:{member}", {"group": group})
        if el.startswith("DescriptionOfItemThatWill") and isinstance(value, str) and value.strip():
            row.setdefault("description", value.strip()[:RPT_TEXT_MAX])
        elif el.startswith("AmountOfItemThatWill") and not isinstance(value, str) and facts._is_money(unit):
            row.setdefault("amount_cr", _cr(value))
    keep = _current(k.split(":", 1)[1] for k in items)
    rows = [r for k, r in items.items() if r.get("amount_cr") and k.split(":", 1)[1] in keep]
    if not any(values.values()) and not rows:
        return None            # every figure 0: the template's filler
    out: dict = {"values": values}
    if rows:
        out["items"] = rows[:MAX_OCI_ITEMS]
    return out


def _discontinued(doc: dict, end: date) -> dict | None:
    values = _quarter_values(xbrl_facts.Facts(doc), DISCONTINUED_ELEMENTS, end)
    if not any(values.get(k) for k in ("before_tax_cr", "tax_cr", "after_tax_cr")):
        return None            # no discontinued operation: the template's 0 in every file
    return {"values": values}


def _segment_balance(doc: dict, end: date) -> dict | None:
    facts = xbrl_facts.Facts(doc)
    iso = end.isoformat()
    names: dict[str, str] = {}
    amounts: dict[tuple[str, str], float] = {}      # (side, member) -> crore
    for el, ctx_id, unit, value, _ in facts.rows:
        ctx = facts.contexts.get(ctx_id) or {}
        dims = ctx.get("d") or {}
        if len(dims) != 1 or iso not in (ctx.get("i"), ctx.get("e")):
            continue
        (axis, member), = dims.items()
        axis = axis.rsplit(":", 1)[-1]
        side = "assets" if axis.endswith("ReportableSegmentAssetsAxis") else "liabilities" if axis.endswith("ReportableSegmentLiabilitiesAxis") else None
        if side is None:
            continue
        if el == "DescriptionOfReportableSegment" and isinstance(value, str) and value.strip():
            names.setdefault(f"{side}:{member}", value.strip())
        elif el == ("SegmentAssets" if side == "assets" else "SegmentLiabilities") and not isinstance(value, str) and facts._is_money(unit):
            amounts.setdefault((side, member), _cr(value))
    rows: dict[str, dict] = {}
    for side in ("assets", "liabilities"):
        keep = _current(m for s, m in amounts if s == side)
        amounts = {k: v for k, v in amounts.items() if k[0] != side or k[1] in keep}
    for (side, member), amount in amounts.items():
        name = names.get(f"{side}:{member}") or "Segment " + ("".join(ch for ch in member if ch.isdigit()) or "?")
        rows.setdefault(name, {"segment": name})[f"{side}_cr"] = amount
    rows = {n: r for n, r in rows.items() if r.get("assets_cr") or r.get("liabilities_cr")}
    totals: dict[str, float] = {}
    for el, ctx_id, unit, value, _ in facts.rows:
        ctx = facts.contexts.get(ctx_id) or {}
        if el in SEGMENT_TOTALS and not ctx.get("d") and not isinstance(value, str) and facts._is_money(unit) \
                and iso in (ctx.get("i"), ctx.get("e")):
            totals.setdefault(SEGMENT_TOTALS[el], _cr(value))
    if not rows and not any(totals.values()):
        return None
    out: dict = {"n_segments": len(rows), "segments": sorted(rows.values(), key=lambda r: -(r.get("assets_cr") or 0))[:MAX_SEGMENTS]}
    if any(totals.values()):
        out["totals"] = totals
    return out


def _dividends(doc: dict, end: date) -> dict | None:
    values = _quarter_values(xbrl_facts.Facts(doc), DIVIDEND_ELEMENTS, end)
    return {"values": values} if any(values.values()) else None


def _kmp_pay(doc: dict, end: date) -> dict | None:
    facts = xbrl_facts.Facts(doc)
    people: dict[str, dict] = {}
    totals: dict[str, float] = {}
    for el, ctx_id, unit, value, _ in facts.rows:
        ctx = facts.contexts.get(ctx_id) or {}
        if ctx.get("e") != end.isoformat() or ctx.get("m") != 12:
            continue
        dims = ctx.get("d") or {}
        if not dims:
            if el in ("ManagerialRemuneration", "RemunerationToDirectors") and not isinstance(value, str) and facts._is_money(unit) and value:
                totals.setdefault(el, _cr(value))
            continue
        if len(dims) != 1 or not next(iter(dims)).endswith("KeyManagerialPersonnelsAndDirectorsAxis"):
            continue
        row = people.setdefault(next(iter(dims.values())), {})
        if isinstance(value, str):
            if el == "NameOfKeyManagerialPersonnelOrDirector" and value.strip():
                row.setdefault("name", value.strip()[:RPT_TEXT_MAX])
            elif el == "DesignationOfKeyManagerialPersonnelOrDirector" and value.strip():
                row.setdefault("designation", value.strip()[:RPT_TEXT_MAX])
        elif facts._is_money(unit) and value:
            if el == "KeyManagerialPersonnelOrDirectorRemuneration":
                row["pay_cr"] = _cr(value)
            elif el == "GrossSalaryToKeyManagerialPersonnelOrDirector":
                row.setdefault("gross_salary_cr", _cr(value))
    rows = []
    for member, row in people.items():
        pay = row.get("pay_cr") or row.get("gross_salary_cr")
        if pay:
            rows.append({"name": row.get("name") or member, "designation": row.get("designation"), "pay_cr": pay})
    if not rows and not totals:
        return None
    rows.sort(key=lambda r: -r["pay_cr"])
    out: dict = {"n_people": len(rows), "people": rows[:MAX_KMP]}
    if totals:
        out["totals"] = totals
    return out


def _contingent(doc: dict, end: date) -> dict | None:
    facts = xbrl_facts.Facts(doc)
    iso = end.isoformat()
    flag = total = None
    described: dict[str, str] = {}
    amounts: dict[str, float] = {}
    for el, ctx_id, unit, value, _ in facts.rows:
        ctx = facts.contexts.get(ctx_id) or {}
        dims = ctx.get("d") or {}
        if not dims:
            if el == "WhetherThereAreAnyContingentLiabilities" and _live(facts, ctx_id, end, 12):
                flag = _bool(value)
            elif el == "ContingentLiabilities" and ctx.get("i") == iso and not isinstance(value, str) and facts._is_money(unit) and value:
                total = _cr(value)
            continue
        if len(dims) != 1 or not next(iter(dims)).endswith("ClassesOfContingentLiabilitiesAxis"):
            continue
        member = next(iter(dims.values()))
        if el == "DescriptionOfNatureOfObligationContingentLiabilities" and isinstance(value, str) and ctx.get("e") == iso:
            described.setdefault(member, value.strip())
        elif el == "EstimatedFinancialEffectOfContingentLiabilities" and not isinstance(value, str) and facts._is_money(unit) \
                and ctx.get("i") == iso and value:
            amounts.setdefault(member, _cr(value))
    rows = [{"class": re.sub(r"Member$", "", m), "description": described[m][:RPT_TEXT_MAX], "amount_cr": a}
            for m, a in amounts.items()
            if described.get(m) and not re.match(r"(refer\b|na$|nil$|-)", described[m], re.I)]
    if flag is None and total is None and not rows:
        return None
    rows.sort(key=lambda r: -abs(r["amount_cr"]))
    out: dict = {"n_classes": len(rows), "classes": rows[:MAX_CLASSES]}
    if flag is not None:
        out["has_contingent"] = flag
    if total is not None:
        out["total_cr"] = total
    return out


# --- the dossier ----------------------------------------------------------------------------------------------------

def read(doc: dict) -> dict[str, tuple[str, dict]]:
    """{dossier key: (period column, payload)} the file gives. The column is the quarter ("Q2FY27") or, for a year, "FY26"."""
    end = _end(doc)
    if end is None:
        return {}
    annual = doc.get("kind") == "annual"
    period = doc.get("period") or ""
    year = period if annual else (period[2:] if period.startswith("Q4") else period)
    out: dict[str, tuple[str, dict]] = {}
    audit = (_audit_annual if annual else _audit_results)(doc, end)
    if audit:
        out[AUDIT] = (period, {"kind": "annual" if annual else "results", **audit})
    cash = _cash_flow(doc, end)
    if cash:
        out[CASH_FLOW] = (year if cash["span"] == "FY" else period, cash)
    related = (_related_annual if annual else _related_results)(doc, end)
    if related:
        out[RELATED] = (period, {"kind": "annual" if annual else "results", **related})
    ratios = None if annual else _ratios(doc, end)
    if ratios:
        out[RATIOS] = (period, ratios)
    readers = ((KMP_PAY, _kmp_pay), (CONTINGENT, _contingent)) if annual else \
        ((OCI, _oci), (DISCONTINUED, _discontinued), (SEGMENT_BALANCE, _segment_balance), (DIVIDENDS, _dividends))
    for key, reader in readers:
        found = reader(doc, end)
        if found:
            out[key] = (period, {"kind": "annual" if annual else "results", **found})
    return out


def remember(dossier: dict, doc: dict, news_id: str, as_of: str, at: str, replace: bool = True, source: str = "") -> int:
    """Put what the file gives into the dossier's four keys (in place); the number of entries written. An entry takes the place of
    one of the same period, basis and kind; ``replace`` False (the backfill) adds only where none is held. A quarter memory holds as
    unit-slipped (``scale_held``) gets no amounts."""
    period, basis = doc.get("period"), doc.get("basis")
    if not period:
        return 0
    held_slip = {str(h.get("period") if isinstance(h, dict) else h) for h in dossier.get("scale_held", [])}
    if any(isinstance(e, dict) and _real(e.get("values") or {}) != (e.get("values") or {}) for e in dossier.get(RATIOS, [])):
        # filler zeros written before 30 Oct 2026 go, and an entry left with none goes too; the file is read again below
        kept = [{**e, "values": _real(e.get("values") or {})} for e in dossier[RATIOS] if isinstance(e, dict)]
        dossier[RATIOS] = [e for e in kept if e["values"]]
    found = read(doc)
    written = 0
    for key, (column, payload) in found.items():
        if key in MONEY_KEYS and (column in held_slip or period in held_slip):
            continue
        kind = payload.get("kind")
        same = lambda e: (e.get("period"), e.get("basis"), e.get("kind")) == (column, basis, kind)      # noqa: E731
        held = [e for e in dossier.get(key, []) if isinstance(e, dict)]
        if not replace and any(same(e) for e in held):
            continue
        lab = {"by": "file", "doc": "annual_report" if doc.get("kind") == "annual" else "results", "basis": basis, "at": at,
               "rules": "xbrl_extras"}
        if source:
            lab["from"] = source
        entry = {"period": column, "basis": basis, **({"kind": kind} if kind else {}), **{k: v for k, v in payload.items() if k != "kind"},
                 "as_of": as_of, "source_news_id": news_id, "lab": lab}
        rest = [e for e in held if not same(e)]
        dossier[key] = sorted(rest + [entry], key=lambda e: _order(e.get("period")))[-MAX_ENTRIES[key]:]
        written += 1
    return written
