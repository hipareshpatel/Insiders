"""RESULTS_NEEDS_STATEMENT (31 Oct 2026, TMB nse-106836238): a RESULTS-typed note with no results statement in its text."""
from bse_intel import pipeline as P

PAD = " The Board reviewed the business. " * 60      # enough words to judge (LACKS_RESULTS_MIN_CHARS)

NOTE = ("Tamilnad Mercantile Bank Limited. Disclosure under Regulation 30. The Bank has made an amount of Rs 304.24 crore provided "
        "towards the estimated ECL requirement of Rs 385 crore calculated on the basis of its advances portfolio as on September 30, "
        "2026." + PAD)


def test_a_note_about_a_provision_lacks_results():
    assert P.lacks_results(NOTE)


def test_a_results_statement_a_covering_letter_or_results_for_the_quarter_is_results():
    assert not P.lacks_results("STATEMENT OF UNAUDITED STANDALONE FINANCIAL RESULTS FOR THE QUARTER ENDED 30.09.2026" + PAD)
    assert not P.lacks_results("Dear Sir, we enclose the unaudited financial results of the Bank for the quarter ended "
                               "September 30, 2026." + PAD)
    assert not P.lacks_results("Reviewed financial results for the quarter and half year ended September 30, 2026" + PAD)
    assert not P.lacks_results("The financial results of the Bank for the quarter ended 30 September 2026 were approved." + PAD)


def test_too_little_text_is_never_judged():
    assert not P.lacks_results("Disclosure of a provision.")          # a scan OCR did not read
    assert not P.lacks_results("")


def test_the_switch_is_off_by_default(monkeypatch):
    from bse_intel.settings import results_needs_statement
    monkeypatch.delenv("RESULTS_NEEDS_STATEMENT", raising=False)
    assert results_needs_statement() is False
