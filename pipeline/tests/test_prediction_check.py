from bse_intel import prediction_check


class _Sink:
    def __init__(self, dossiers):
        self.dossiers = dossiers

    def get_dossier(self, scrip):
        return self.dossiers.get(scrip)


def test_lists_the_apl_apollo_verdict_and_the_per_share_tonne():
    apl = {"predictions": [{"metric": "volumes", "period": "Q2FY27", "value": 10.0, "comparison": ">=", "status": "MET",
                            "actual": 963143.0, "kpi": "Q2FY27 volume"},
                           {"metric": "revenue", "period": "Q2FY27", "value": 7000, "comparison": ">=", "status": "MET",
                            "actual": 7002, "kpi": "revenue"}],
           "financial_metrics": [{"metric": "ebitda_per_tonne", "period": "Q2FY27", "value": 5999, "unit": "INR_PER_SHARE"},
                                 {"metric": "eps", "period": "Q2FY27", "value": 12, "unit": "INR_PER_SHARE"}]}
    report = prediction_check.survey(_Sink({"APL": apl, "X": None}), ["APL", "X"], {"APL": "APLAPOLLO"})
    assert report["by_kind"] == {"verdict_withdrawn": 1, "per_share_unit": 1} and report["companies_affected"] == 1
    assert "APLAPOLLO" in prediction_check.render(report)
