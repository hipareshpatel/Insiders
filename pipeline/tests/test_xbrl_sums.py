from __future__ import annotations

from bse_intel import xbrl_sums

HEAD = (b'<?xml version="1.0"?><xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" '
        b'xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink" '
        b'xmlns:in-capmkt="http://www.sebi.gov.in/xbrl/2026-01-31/in-capmkt">'
        b'<link:schemaRef xlink:href="in-capmkt-ent-2026-01-31.xsd" xlink:type="simple"/>'
        b'<!-- http://www.sebi.gov.in/xbrl/IntegratedFinance_IndAS/2026-01-31 -->'
        b'<xbrli:context id="D"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity>'
        b'<xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate>'
        b'</xbrli:period></xbrli:context><xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>')


def _file(**lines: int) -> bytes:
    body = b"".join(f'<in-capmkt:{k} contextRef="D" unitRef="INR" decimals="-5">{v}</in-capmkt:{k}>'.encode()
                    for k, v in lines.items())
    return HEAD + body + b"</xbrli:xbrl>"


def test_a_file_is_checked_against_the_official_sums_within_its_rounding():
    """Owner, 25 Oct 2026 (item 23): SEBI's taxonomy says income less expenses is the profit before exceptional items."""
    good = _file(RevenueFromOperations=1000_00000, OtherIncome=50_00000, Income=1050_00000, Expenses=800_00000,
                 ProfitBeforeExceptionalItemsAndTax=250_00000, ExceptionalItemsBeforeTax=0, ProfitBeforeTax=250_00000)
    report = xbrl_sums.check(good)
    assert report.template == "INDAS" and report.checked >= 3 and report.ok
    # off by one lakh, the printed precision: rounding, not a mistake
    assert xbrl_sums.check(_file(RevenueFromOperations=1000_00000, OtherIncome=50_00000, Income=1050_10000)).ok
    # profit before tax tagged with the associates' share in it (Orient Bell's kind of file) does not add up
    bad = xbrl_sums.check(_file(ProfitBeforeExceptionalItemsAndTax=250_00000, ExceptionalItemsBeforeTax=0,
                                ProfitBeforeTax=224_00000))
    assert bad.totals() == {"ProfitBeforeTax"} and bad.mismatches[0].gap == -26_00000


def test_every_results_template_has_its_sums():
    for key in ("INDAS", "OTHERTHANBANK", "BANKING", "NBFC", "GI", "LI", "LEGACY_INDAS", "LEGACY_BANKING", "LEGACY_NBFC"):
        assert xbrl_sums.sums_for(key), key
    assert xbrl_sums.sums_for("INDAS")["ProfitBeforeTax"] == [("ProfitBeforeExceptionalItemsAndTax", 1.0),
                                                               ("ExceptionalItemsBeforeTax", 1.0)]
