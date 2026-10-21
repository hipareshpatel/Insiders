"""Institutional categories and named public holders from NSE's shareholding XBRL (owner, 2026-10-21: "people track
large institutional buys like FII, MF, DII ... significant changes in shareholding"). Measured on UltraTech's Q2FY27
file: MF 16.4%, insurers 4.05%, FPI 12.2%, LIC 3.72%, ICICI Prudential Nifty 50 Index Fund 2.9%."""

from bse_intel import xbrl

NS = ('xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
      'xmlns:in-bse-shp="http://www.bseindia.com/xbrl/shp" xmlns:iso4217="http://www.xbrl.org/2003/iso4217"')


def _ctx(cid, period, dims=""):
    when = (f"<xbrli:instant>{period}</xbrli:instant>" if len(period) == 10
            else f"<xbrli:startDate>{period[:10]}</xbrli:startDate><xbrli:endDate>{period[11:]}</xbrli:endDate>")
    return (f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="s">532538</xbrli:identifier></xbrli:entity>'
            f"<xbrli:period>{when}</xbrli:period>{f'<xbrli:scenario>{dims}</xbrli:scenario>' if dims else ''}</xbrli:context>")


def _explicit(axis, member):
    return f'<xbrldi:explicitMember dimension="in-bse-shp:{axis}">in-bse-shp:{member}</xbrldi:explicitMember>'


def _typed(axis, domain, value):
    return f'<xbrldi:typedMember dimension="in-bse-shp:{axis}"><in-bse-shp:{domain}>{value}</in-bse-shp:{domain}></xbrldi:typedMember>'


def _fact(name, ctx, value):
    return f'<in-bse-shp:{name} contextRef="{ctx}" unitRef="pure" decimals="2">{value}</in-bse-shp:{name}>'


def test_categories_and_named_holders():
    q, d = "2026-09-30", "2026-07-01/2026-09-30"
    mf_axis, mf_dom = "DetailsOfSharesHeldByMutualFundsOrUTIAxis", "MutualFundsOrUTIDomain"
    ind_axis, ind_dom = "DetailsSharesHeldByIndividualsOrHUFAxis", "IndividualsOrHUFDomain"
    parts = [
        _ctx("P", q, _explicit("ShareholdingPatternAxis", "ShareholdingOfPromoterAndPromoterGroupMember")),
        _ctx("MF", q, _explicit("ShareholdingPatternAxis", "MutualFundsOrUTIMember")),
        _ctx("FPI1", q, _explicit("ShareholdingPatternAxis", "InstitutionsForeignPortfolioInvestorCategoryOneMember")),
        _ctx("FPI2", q, _explicit("ShareholdingPatternAxis", "InstitutionsForeignPortfolioInvestorCategoryTwoMember")),
        _ctx("D_M1", d, _typed(mf_axis, mf_dom, "MutualFundsOrUTI_Context15")), _ctx("M1", q, _typed(mf_axis, mf_dom, "MutualFundsOrUTI_Context15")),
        _ctx("D_M2", d, _typed(mf_axis, mf_dom, "MutualFundsOrUTI_Context16")), _ctx("M2", q, _typed(mf_axis, mf_dom, "MutualFundsOrUTI_Context16")),
        _ctx("D_I1", d, _typed(ind_axis, ind_dom, "IndividualsOrHUF_Context15")), _ctx("I1", q, _typed(ind_axis, ind_dom, "IndividualsOrHUF_Context15")),
        _fact("ShareholdingAsAPercentageOfTotalNumberOfShares", "P", "0.5848"),
        _fact("ShareholdingAsAPercentageOfTotalNumberOfShares", "MF", "0.164"),
        _fact("ShareholdingAsAPercentageOfTotalNumberOfShares", "FPI1", "0.1178"),
        _fact("ShareholdingAsAPercentageOfTotalNumberOfShares", "FPI2", "0.0042"),
        _fact("NameOfTheShareholder", "D_M1", "ICICI PRUDENTIAL NIFTY 50 INDEX FUND"),
        _fact("ShareholdingAsAPercentageOfTotalNumberOfShares", "M1", "0.029"),
        _fact("NameOfTheShareholder", "D_M2", "A SMALL FUND"),
        _fact("ShareholdingAsAPercentageOfTotalNumberOfShares", "M2", "0.004"),     # under 1%: left out
        _fact("NameOfTheShareholder", "D_I1", "Promoter Person"),
        _fact("TypeOfPromoterShareholding", "D_I1", "Promoter"),
        _fact("ShareholdingAsAPercentageOfTotalNumberOfShares", "I1", "0.05"),      # promoter group: left out
    ]
    data = f'<xbrli:xbrl {NS}>{"".join(parts)}</xbrli:xbrl>'.encode()
    result = xbrl.parse(data)
    own = result.ownership
    assert result.kind == "SHAREHOLDING" and own.promoter_pct == 58.48
    assert own.mf_pct == 16.4 and own.fpi_pct == 12.2
    assert own.holders == [{"name": "ICICI PRUDENTIAL NIFTY 50 INDEX FUND", "category": "Mutual fund", "pct": 2.9}]
