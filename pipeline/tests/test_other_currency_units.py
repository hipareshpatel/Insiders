# Another currency's unit line is never a rupee unit (29 Oct 2026): the lost-sign rules took "US$", "USD", "$", "€" or "£" before
# "in million" for a mangled rupee sign, so a USD figure was read as rupees, 10x or more off. Every reader of unit lines is checked.
import pytest

from bse_intel import grounding, pdf_numbers_first as nf, pdf_referee as pr, xbrl_key as xk

OTHER = ["(US$ in million)", "(USD in millions)", "x ($ in million)", "(in US$ million, except per share data)",
         "(€ in million)", "(£ in million)", "(US$ millions)",
         # the review: codes glued to "in", OCR's forms of US$, currencies written as words or other codes
         "(USDin million)", "(USin million)", "(EURin million)", "(USS in million)", "(US8 in million)", "(USD8 in million)",
         "(Euro in million)", "(Yen in million)", "(RMB in million)", "(LKR in million)", "(BDT in million)", "($ in thousands)"]
RUPEE = [("(₹ in million)", 10), ("(< in crores)", 1), ("(in lakhs)", 100), ("(Rs. in lakhs except EPS)", 100),
         ("(XLakhs)", 100), ("(ཪ in million)", 10), ("(INR Million)", 10), ("{ in Lakhs)", 100), ("t in crore", 1),
         # a mangled rupee sign that holds a currency symbol, before lakh or crore: no other currency is written in those (bench)
         ("(?£in Lacs)", 100), ("($ in Lakhs)", 100), ("(€ in lakhs)", 100), ("(US in crores)", 1)]


def test_a_rupee_unit_line_that_mentions_another_currency_after_it_keeps_its_unit():
    line = "(in ₹ million, except USD per share)"
    assert nf.scan_units([line]) == {10} and xk._declared_unit(line) == 10


@pytest.mark.parametrize("line", OTHER)
def test_a_unit_line_of_another_currency_is_no_rupee_unit(line):
    assert not list(grounding._DECLARED_UNIT.finditer(line))
    assert pr._bare_unit([line], 0) is None and pr._garbled_unit([line], 0) is None
    assert xk._declared_unit(line) is None
    assert nf.scan_units([line]) == set()
    assert nf.unit_of(["Particulars"], [line]) is None


@pytest.mark.parametrize("line,per_crore", RUPEE)
def test_a_rupee_unit_line_is_still_read(line, per_crore):
    assert nf.unit_of(["Particulars"], [line]) == per_crore
    assert xk._declared_unit(line) == per_crore


@pytest.mark.parametrize("line", ["(Amount in millions of US dollars)", "(Amount in millions of USD unless otherwise stated)",
                                  "(Amount in thousands of USD unless otherwise stated)", "(Amount in millions of €)"])
def test_an_amount_in_millions_of_another_currency_is_no_rupee_unit(line):
    assert not list(grounding._DECLARED_UNIT.finditer(line)) and xk._declared_unit(line) is None


@pytest.mark.parametrize("line,per_crore", [("(Amount in millions of ₹ unless otherwise stated)", 10),
                                            ("(,\\mount in millions of Z unless otherwise stated)", 10),   # Heritage's scans
                                            ("(Amount 111 millions of Z unless otherwise stated)", 10), ("(Amount in lakhs of Rupees)", 100)])
def test_an_amount_in_rupee_units_is_still_read(line, per_crore):
    words = [next(g for g in m.groups() if g) for m in grounding._DECLARED_UNIT.finditer(line)]
    assert words and grounding._PER_CRORE.get(words[0].lower().rstrip("s")) == per_crore
