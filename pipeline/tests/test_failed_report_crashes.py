"""Two crashes the failed-filings report of 25 Oct 2026 named: each failed a filing outright."""
from __future__ import annotations

from bse_intel.dossier import merge, new_dossier
from bse_intel.grounding import SourceIndex
from test_memory import Q2, filing, output


def test_a_first_business_summary_is_written_with_its_label():
    # JSWENERGY's call (11 May): the summary used text_lab before it was defined (UnboundLocalError)
    f = filing("nse-200", Q2)
    d = merge(new_dossier(f), output(business_summary="Makes power"), f, "HIGH", Q2)
    assert d["business_summary"]["text"] == "Makes power"
    assert d["business_summary"]["lab"]


def test_a_huge_digit_run_does_not_crash_the_crore_check():
    # LTF's deck (24 Apr): a 400-digit run read as infinity, and int(inf) raised OverflowError
    ix = SourceIndex("Total income 1,234.00 crore; ref " + "9" * 400)
    assert ix.stated_crore(1234.0, 2)
    assert not ix.stated_crore(1500.25, 2)
