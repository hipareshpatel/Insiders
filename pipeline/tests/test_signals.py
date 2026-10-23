

def test_an_order_executed_in_a_named_year_is_not_spread_from_today():
    from bse_intel.signals import term_years

    assert term_years("FY29", "2026-10-23") is None            # Welspun: executed in FY29, not over 2.4 years from today
    assert term_years("During the financial year 2026-27", "2026-10-23") is None
    assert term_years("Q2 2027", "2026-10-23") is None
    assert term_years("36 months", "2026-10-23") == 3.0
    assert round(term_years("31 December 2028", "2026-10-23"), 1) == 2.2
