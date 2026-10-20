"""A deal stage the filing's words support (live review 3, 2026-10-20: 4 of the 7 WRONG cards had a stage the filing
did not state)."""

from bse_intel.gate import supported_stage


def test_a_shareholders_approval_needs_the_votes_result():
    notice = ("The meeting of the equity shareholders was held today through video conferencing. The combined results "
              "of the remote e-voting and e-voting at the meeting will be duly announced.")
    assert supported_stage("SHAREHOLDER_APPROVED", notice) == "PROPOSED"
    convening = "Notice convening the meeting of the unsecured creditors to be held on September 5, 2026 is enclosed."
    assert supported_stage("SHAREHOLDER_APPROVED", convening) == "PROPOSED"
    result = "The resolution for the scheme was approved by the equity shareholders with the requisite majority."
    assert supported_stage("SHAREHOLDER_APPROVED", result) == "SHAREHOLDER_APPROVED"


def test_a_board_approval_needs_the_board():
    speech = "Your Company has proposed a capex of Rs 20,000 crore over the medium term across the Group."
    assert supported_stage("BOARD_APPROVED", speech) == "PROPOSED"
    outcome = "The Board of Directors at its meeting held today approved the acquisition of 100% stake."
    assert supported_stage("BOARD_APPROVED", outcome) == "BOARD_APPROVED"
    assert supported_stage("COMPLETED", speech) == "COMPLETED"     # other stages are left as they are
    assert supported_stage("BOARD_APPROVED", "") == "BOARD_APPROVED"  # no text, no judgement
