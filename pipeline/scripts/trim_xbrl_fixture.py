"""Cut a real XBRL instance down to a test fixture: the facts named, the contexts and units they use.

    python scripts/trim_xbrl_fixture.py AR_XBRL_KANORICHEM_22122025122259.xml tests/fixtures/nse_ar_kanorichem_fy25_consolidated.xml

Facts are kept by element name (annual_xbrl's own lists, plus a few it must ignore: company-level zeros,
foreign-currency subsidiary figures, equity-component splits), unchanged; a zero filed for one party or one
class is left out with the context only it used. Beyond that only trailing spaces at line ends are removed.
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from bse_intel import annual_xbrl

KEEP = {name for _, _, names in annual_xbrl.FLOWS + annual_xbrl.STOCKS for name in names} | set(annual_xbrl.DIRECTOR_DUES) | {
    "NatureOfReportStandaloneConsolidated", "LevelOfRoundingUsedInFinancialStatements", "DateOfEndOfReportingPeriod",
    "NameOfAuditFirm", "FirmsRegistrationNumberOfAuditFirm", "NameOfAuditorSigningReport",
    "DateOfSigningAuditReportByAuditors", "DisclosureInAuditorsReportExplanatory",
    "WhetherAuditorsReportHasBeenQualifiedOrHasAnyReservationsOrContainsAdverseRemarks",
    "DescriptionOfNatureOfObligationContingentLiabilities", "EstimatedFinancialEffectOfContingentLiabilities",
    "WhetherThereAreAnyContingentLiabilities", "NameOfRelatedParty", "GrossValueOfTransactionsWithRelatedParties",
    "NameOfKeyManagerialPersonnelOrDirector", "DesignationOfKeyManagerialPersonnelOrDirector",
    "KeyManagerialPersonnelOrDirectorRemuneration", "GrossSalaryToKeyManagerialPersonnelOrDirector",
    "NameOfEntityConsolidated", "TypeOfEntityConsolidated", "AmountOfShareInProfitOrLossOfEntityConsolidated",
    "NameOfSubsidiary", "TurnoverOfSubsidiary", "ProfitAfterTaxOfSubsidiary",
}
KEEP_PATTERN = re.compile(r"RelatedPartyTransactions|^DisclosureInAuditorsReportRelatingTo(StatutoryDues|DefaultInRepayment|Fraud)")


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def main(source: str, target: str) -> None:
    for _, (prefix, uri) in ET.iterparse(source, events=("start-ns",)):
        if prefix:
            ET.register_namespace(prefix, uri)
    tree = ET.parse(source)
    root = tree.getroot()
    dimensional = {el.get("id") for el in root if local(el.tag) == "context"
                   and any(local(m.tag) in ("explicitMember", "typedMember") for m in el.iter())}
    contexts, units = set(), set()
    for el in list(root):
        name = local(el.tag)
        if name in ("context", "unit", "schemaRef"):
            continue
        # a company-level zero stays (the filler annual_xbrl must not read as a nil); one per party or class goes
        filler = (el.text or "").strip() == "0" and el.get("contextRef") in dimensional
        if el.get("contextRef") and (name in KEEP or KEEP_PATTERN.search(name)) and not filler:
            contexts.add(el.get("contextRef"))
            if el.get("unitRef"):
                units.add(el.get("unitRef"))
        else:
            root.remove(el)
    for el in list(root):
        name = local(el.tag)
        if (name == "context" and el.get("id") not in contexts) or (name == "unit" and el.get("id") not in units):
            root.remove(el)
    tree.write(target, encoding="utf-8", xml_declaration=True)
    # trailing spaces at line ends, which the repository's whitespace check refuses (every reader strips them)
    lines = Path(target).read_bytes().split(b"\n")
    Path(target).write_bytes(b"\n".join(line.rstrip() for line in lines))
    print(f"{target}: {Path(target).stat().st_size:,} bytes, {len(contexts)} contexts")


if __name__ == "__main__":
    main(*sys.argv[1:3])
