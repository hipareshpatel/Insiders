"""CARD_OTHER_ISSUER (blind audit 1 Nov 2026, HEGAM nse-106837190): HEG Advanced Materials (formerly HEG Limited) filed the
results of HEG Limited (formerly HEG Graphite Limited), the demerged graphite company, and the card headlined them as its own.
The statement texts below follow the layout of Indian results filings; HEG's own text was not read (assumption)."""

from bse_intel.models import Filing
from bse_intel.pipeline import other_issuer_results, subsidiary_results

HEGAM_FORMER = ["HEG Limited", "Hindustan Electro Graphites Limited"]


def f(name):
    return Filing(news_id="n", scrip_code="1", company_name=name, headline="", subject="", filed_at="2026-10-30",
                  filing_date="2026-10-30")


HEG_FILING = (
    "HEG Advanced Materials Limited\nThe Manager, Listing Department, National Stock Exchange of India Limited\n"
    "Sub: Financial Results of HEG Limited (formerly known as HEG Graphite Limited)\n"
    "Pursuant to the Scheme of Arrangement, please find enclosed the unaudited financial results for the quarter and half "
    "year ended 30 September 2026 as approved by its Board.\n"
    "HEG LIMITED (Formerly known as HEG Graphite Limited)\nRegd. Office: Mandideep (Near Bhopal) Distt. Raisen\n"
    "Statement of Unaudited Financial Results for the quarter and half year ended 30th September, 2026\n"
    "Revenue from operations 740.40 680.91 696.85 1,421.31 1,309.63 2,568.50\n")


def test_another_companys_results_under_the_listed_companys_former_name_are_not_its_own():
    assert other_issuer_results(f("HEG Advanced Materials Limited"), HEG_FILING, HEGAM_FORMER) == "HEG Limited"
    # the subsidiary rule does not see it: the letter never says "subsidiary" (why the card went out)
    assert subsidiary_results(f("HEG Advanced Materials Limited"), HEG_FILING) is None


def test_the_listed_companys_own_statement_is_its_own():
    own = ("HEG ADVANCED MATERIALS LIMITED\nStatement of Unaudited Standalone Financial Results for the quarter ended "
           "30 September 2026\nRevenue from operations 12.10")
    assert other_issuer_results(f("HEG Advanced Materials Limited"), own, HEGAM_FORMER) is None
    # one of its statements in its own name is enough, whatever else the filing names
    assert other_issuer_results(f("HEG Advanced Materials Limited"), HEG_FILING + own, HEGAM_FORMER) is None


def test_a_filing_from_before_the_rename_under_the_former_name_is_its_own():
    before = ("HEG LIMITED\nRegd. Office: Mandideep\nStatement of Audited Financial Results for the quarter and year ended "
              "31st March, 2025\nRevenue from operations 2,100.00")
    assert other_issuer_results(f("HEG Advanced Materials Limited"), before, HEGAM_FORMER) is None


def test_no_name_or_a_name_with_ltd_and_the_words_dropped_is_never_another_company():
    bank = "STATE BANK OF INDIA\nStatement of Reviewed Financial Results for the quarter ended 30.09.2026"
    assert other_issuer_results(f("State Bank of India"), bank) is None    # no "Limited" printed: nothing named
    abbrev = "Tata Consultancy Services Ltd.\nStatement of Audited Consolidated Financial Results for the quarter ended"
    assert other_issuer_results(f("Tata Consultancy Services Limited"), abbrev) is None
    the = "THE INDIAN HOTELS COMPANY LIMITED\nStatement of Unaudited Financial Results for the quarter ended"
    assert other_issuer_results(f("Indian Hotels Co. Ltd."), the) is None


def test_another_companys_statement_with_no_former_names_known():
    other = ("We enclose the results of Alpha Graphite Limited for the quarter.\nALPHA GRAPHITE LIMITED\n"
             "Statement of Unaudited Financial Results for the quarter ended 30 September 2026")
    assert other_issuer_results(f("Beta Holdings Limited"), other) == "Alpha Graphite Limited"   # the letter's spelling


def test_the_switch_is_off_by_default(monkeypatch):
    from bse_intel.settings import card_other_issuer
    monkeypatch.delenv("CARD_OTHER_ISSUER", raising=False)
    monkeypatch.delenv("REPO_VARS", raising=False)
    assert card_other_issuer() is False
