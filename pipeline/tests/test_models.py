

def test_a_buyback_is_never_a_fundraise():
    # MEDIASSIST nse-106837158 (audit of 1 Nov 2026): its Rs 49.27 Cr buyback was typed FUNDRAISE ("raise" on the scale line)
    from bse_intel.models import DealValue
    assert DealValue(kind="FUNDRAISE", segment="Share Buyback", amount_cr=49.27).kind == "OTHER"
    assert DealValue(kind="BUYBACK").kind == "OTHER"
    assert DealValue(kind="FUNDRAISE", segment="QIP").kind == "FUNDRAISE"
