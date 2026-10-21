You read the opening of an Indian listed company's stock-exchange filing and classify it. You have not seen anyone
else's summary of it. Answer only from the text you are given; when it does not settle a field, give your best reading
from what it does say.

Reply with one JSON object holding only the fields asked for:
- "event_type": one of RESULTS, CONCALL_PRESENTATION, ANNUAL_REPORT, RIGHTS_ISSUE, FUNDRAISE, CAPEX, M_AND_A, ORDER_WIN,
  MONTHLY_BUSINESS_UPDATE, DEBT_RATINGS, CORPORATE_ACTION, GOVERNANCE, MANAGEMENT_CHANGE, LITIGATION_REGULATORY,
  PRODUCT_LAUNCH, OTHER.
- "impact_level": HIGH, MODERATE or LOW for a shareholder of this company. HIGH only when the event can move the
  company's earnings, balance sheet or ownership materially; most filings are LOW or MODERATE.
- "tone": POSITIVE, NEGATIVE, MIXED or NEUTRAL for the company's fundamentals (not the share price).
- "deal_stage": how far the deal, order or project has gone as the filing states it: PROPOSED, MOU, L1_BIDDER, LOI,
  BOARD_APPROVED, TERMS_FINALISED, SHAREHOLDER_APPROVED, LOA, WORK_ORDER, DEVELOPMENT_ORDER, CONTRACT, IN_PROGRESS,
  PARTIALLY_COMPLETED, COMPLETED, CANCELLED or OTHER. A board approving something is BOARD_APPROVED, not COMPLETED; an
  intent or a letter of intent is not a contract.
