"""Module 8: DGTR trade-remedy cases, parsed from the site's own markup (measured 2026-10-19) and linked to companies
only when the initiation notice names them."""

import json
from pathlib import Path
from types import SimpleNamespace

from bse_intel import dgtr
from bse_intel.dossier import dossier_as_of

FIXTURES = Path(__file__).parent / "fixtures"

LIST_PAGE = """
<div class="investigation">
                <span class="status">1 - Ongoing Investigation</span>
                <p><a href="/en/anti-dumping-cases/initiation-anti-dumping-investigation-concerning-imports-caprolactam-originating" hreflang="en">Initiation of an anti-dumping investigation concerning imports of "Caprolactam" originating in or exported from China PR, Russia, Thailand and United States of America.</a></p>
                <div class="details">
                                        <span class="country"><i class="fas fa-map-marker-alt"></i>Country: China PR, Russia, Thailand and United States of America</span>                    <span class="proceeding">Type of Investigation: Anti-dumping Investigation</span>                    <span class="proceeding">Type of Proceeding: Original Investigation</span>                </div>
            </div>
<div class="investigation">
                <span class="status">4 - Ongoing Investigation</span>
                <p><a href="/en/anti-dumping-cases/anti-dumping-investigation-concerning-imports-para-tert-octyl-phenol-ptop" hreflang="en">Anti-dumping investigation concerning imports of Para-tert-Octyl Phenol (&ldquo;PTOP&rdquo;) Formaldehyde Tackifier Resin from China PR.</a></p>
                <div class="details">
                                        <span class="country"><i class="fas fa-map-marker-alt"></i>Country: China PR</span>                    <span class="proceeding">Type of Investigation: Anti-dumping Investigation</span>                    <span class="proceeding">Type of Proceeding: Original Investigation</span>                </div>
            </div>
<li class="pager__item pager__item--last">
          <a href="?page=41" title="Go to last page">
"""

CASE_PAGE = """
<table><tr>
                        <th scope="col">S.no</th>
                        <th scope="col">Timeline for completion of investigation</th>
                        <th scope="col">Details</th>
                        <th scope="col">Publish Date</th>
                    </tr>
<tr>
                    <td>1</td>
                    <td id="9314">Initiation Notification</td>
                    <td><a href="https://dgtr.gov.in/sites/default/files/2026-09/Initiation%20English.pdf" target="_blank"><img
                    src="/themes/custom/dgtr/images/pdf.png"> Download (202.69 KB)</a></td>
                    <td>29/09/2026</td>
                    </tr>
<tr>
                    <td>2</td>
                    <td id="9400">Extension of time for submission of questionnaire response</td>
                    <td><a href="https://dgtr.gov.in/sites/default/files/2026-10/Extension.pdf">Download</a></td>
                    <td>10/10/2026</td>
                    </tr>
<tr>
                    <td>3</td>
                    <td id="9500">Preliminary Findings</td>
                    <td><a href="https://dgtr.gov.in/sites/default/files/2026-12/PF.pdf">Download</a></td>
                    <td>15/12/2026</td>
                    </tr></table>
"""


def test_case_list_reads_each_case_and_the_last_page():
    cases = dgtr.parse_case_list(LIST_PAGE)
    assert [c["product"] for c in cases] == ["Caprolactam", "Para-tert-Octyl Phenol (“PTOP”) Formaldehyde Tackifier Resin"]
    first = cases[0]
    assert first["url"].startswith("https://www.dgtr.gov.in/en/anti-dumping-cases/initiation-")
    assert first["status"] == "Ongoing Investigation"
    assert first["countries"] == "China PR, Russia, Thailand and United States of America"
    assert (first["investigation"], first["proceeding"]) == ("Anti-dumping Investigation", "Original Investigation")
    assert dgtr._product_from_title("Initiation of Safeguard (Quantitative Restrictions) investigation concerning imports "
                                    "of Soda Ash into India") == "Soda Ash"
    assert dgtr.last_page(LIST_PAGE) == 41 and dgtr.last_page("<p>no pager</p>") == 0


def test_case_documents_dated_and_staged_hearings_and_extensions_unstaged():
    docs = dgtr.parse_case_documents(CASE_PAGE)
    assert [(d["stage"], d["date"]) for d in docs] == [
        ("INITIATION", "2026-09-29"), (None, "2026-10-10"), ("PRELIMINARY_FINDING", "2026-12-15")]
    assert docs[0]["url"].endswith("Initiation%20English.pdf")
    assert dgtr.stage_of("Final Findings") == "FINAL_FINDING"
    assert dgtr.stage_of("Customs Notification") == "CUSTOMS_NOTIFICATION"
    assert dgtr.stage_of("Termination Notification") == "TERMINATED"
    assert dgtr.stage_of("Corrigendum to Initiation Notification") is None
    assert dgtr.stage_of("Oral hearing notice") is None


def _sentences(key_start: str) -> str:
    data = json.loads((FIXTURES / "dgtr_initiation_sentences.json").read_text(encoding="utf-8"))
    return " ".join(next(v for k, v in data.items() if k.startswith(key_start)))


def test_applicants_from_both_forms_of_the_notice():
    # "X (hereinafter referred to as the applicant) has filed" and "The application has been filed by X"
    assert dgtr.named_companies(_sentences("Caprolactam")) == {"Gujarat State Fertilizers & Chemicals Limited": "APPLICANT"}
    pty = dgtr.named_companies(_sentences("Polyester"))
    # "Reliance Industries Limited" is one name, not "Reliance Industries" and "Limited and Wellknown ..."
    assert pty["Reliance Industries Limited"] == "APPLICANT"
    assert {"Wellknown Polyester Limited", "Wellknown Polyesters Ltd"} <= set(pty)
    assert not any(n.startswith(("Limited", "and")) for n in pty)


def test_supporters_kept_apart_and_exporters_not_named():
    text = ("N4/s DCW Limited (hereinafter refened to as the \"applicant\") has filed an application. The application has "
            "been filed by M/s DCW Limited. Apart from the applicant, there is another producer Epigral Limited (formerly "
            "known as Meghmani Finechem Limited) which commenced production. Epigral Limited has supported the "
            "application. Imports from M/s EBC Corporation from Japan, and M/s Sekisui Specialty Chemicals (Thailand) Co.")
    assert dgtr.named_companies(text) == {"DCW Limited": "APPLICANT", "Epigral Limited": "SUPPORTER"}


def test_scanned_name_cut_at_a_sentence_start_still_whole_where_the_notice_repeats_it():
    text = ("Rules, 1995, Laxmi Organic Industries Limited (hereinafter referred to as the 'Applicant') has filed an "
            "application before the Designated Authority")
    assert dgtr.named_companies(text) == {"Laxmi Organic Industries Limited": "APPLICANT"}
    assert dgtr.named_companies("The Fertilisers And Chemicals Travancore Limited (hereinafter referred to as the "
                                "'Applicant') has filed an application.") == {
        "Fertilisers And Chemicals Travancore Limited": "APPLICANT"}


def test_match_is_exact_by_name_key():
    companies = {dgtr.name_key("DCW Limited"): "500117", dgtr.name_key("Epigral Ltd."): "543952",
                 dgtr.name_key("Laxmi Organic Industries Limited"): "540222"}
    names = {"M/s DCW Ltd": "APPLICANT", "Epigral Limited": "SUPPORTER", "Laxmi Organic Industries": "APPLICANT",
             "DCW Chemicals Limited": "APPLICANT", "DCW": "APPLICANT"}
    assert dgtr.match_companies(names, companies) == {"500117": "APPLICANT", "543952": "SUPPORTER", "540222": "APPLICANT"}


def _case():
    return dgtr.parse_case_list(LIST_PAGE)[0]


def test_merge_then_point_in_time_view_and_signals():
    dossier = {"scrip_code": "500690"}
    docs = dgtr.parse_case_documents(CASE_PAGE)
    assert dgtr.merge(dossier, _case(), docs, "APPLICANT") is True
    assert dgtr.merge(dossier, _case(), docs, "APPLICANT") is False   # nothing new: memory not rewritten
    entry = dossier["trade_remedies"][0]
    assert (entry["stage"], entry["stage_on"], entry["as_of"][:10]) == ("PRELIMINARY_FINDING", "2026-12-15", "2026-09-29")
    assert len(entry["documents"]) == 2   # the extension notice is not a step

    # a card filed in October sees the initiation only; one filed before the case began sees no case
    october = dossier_as_of(dossier | {"financial_metrics": []}, "2026-10-20T10:00:00+05:30")
    assert october["trade_remedies"][0]["stage"] == "INITIATION"
    assert dgtr.signals(october, "2026-10-20T10:00:00+05:30") == [
        ("INFO", "DGTR started the anti-dumping investigation on Caprolactam (China PR, Russia, Thailand and United States "
                 "of America) on 2026-09-29; the company applied.")]
    assert dossier_as_of(dossier | {"financial_metrics": []}, "2026-09-01T10:00:00+05:30")["trade_remedies"] == []
    later = dgtr.signals(dossier, "2026-12-20T10:00:00+05:30")
    assert later[0][0] == "POSITIVE" and "preliminary finding" in later[0][1]
    assert dgtr.signals(dossier, "2027-09-01T10:00:00+05:30") == []   # older than six months


def test_sync_reads_each_notice_once_and_links_only_named_universe_companies(monkeypatch):
    pages = {
        f"{dgtr.BASE}{dgtr.LIST_PATHS['ANTI_DUMPING']}?page=0": LIST_PAGE.encode(),
        _case()["url"]: CASE_PAGE.encode(),
        "https://www.dgtr.gov.in/en/anti-dumping-cases/anti-dumping-investigation-concerning-imports-para-tert-octyl-phenol-ptop":
            b"<table></table>",
        "https://dgtr.gov.in/sites/default/files/2026-09/Initiation%20English.pdf": b"%PDF capro",
    }
    calls: list[str] = []

    def fetch(url):
        calls.append(url)
        if url not in pages:
            raise RuntimeError("HTTP 404")
        return pages[url]

    monkeypatch.setattr(dgtr, "notice_text", lambda pdf: _sentences("Caprolactam"))
    monkeypatch.setattr(dgtr, "LIST_PATHS", {"ANTI_DUMPING": dgtr.LIST_PATHS["ANTI_DUMPING"]})
    import bse_intel.universe as universe

    monkeypatch.setattr(universe, "load_nse", lambda sink: SimpleNamespace(built=True, included={"500690"}))

    class Sink:
        def __init__(self):
            self.objects, self.dossiers = {}, {}

        def query(self, name, params):
            assert name == "export_companies"
            return [] if params[0] else [
                {"scrip_code": "500690", "company_name": "Gujarat State Fertilizers & Chemicals Ltd", "former_names_json": "[]"},
                {"scrip_code": "999999", "company_name": "Another Company Limited", "former_names_json": "[]"}]

        def get_object(self, key):
            return self.objects.get(key)

        def put_object(self, key, body, content_type="application/json"):
            self.objects[key] = body

        def get_dossier(self, scrip):
            return self.dossiers.get(scrip)

        def put_dossier(self, scrip, dossier):
            self.dossiers[scrip] = dossier

        def company(self, scrip):
            return {"company_name": "Gujarat State Fertilizers & Chemicals Ltd", "symbol": "GSFC"}

    sink = Sink()
    report = dgtr.sync(SimpleNamespace(sink=sink), deadline=1e12, fetch=fetch)
    assert (report["cases"], report["notices_read"], report["linked"], report["companies"]) == (2, 1, 1, 1)
    assert sink.dossiers["500690"]["trade_remedies"][0]["role"] == "APPLICANT"
    assert len(sink.dossiers) == 1
    # the same day again: case pages and notices are not read again; memory is unchanged
    calls.clear()
    report = dgtr.sync(SimpleNamespace(sink=sink), deadline=1e12, fetch=fetch)
    assert all("Initiation" not in c for c in calls) and report["companies"] == 0
    assert calls == [f"{dgtr.BASE}{dgtr.LIST_PATHS['ANTI_DUMPING']}?page=0"]


def test_sync_waits_for_the_universe_and_survives_a_dead_site(monkeypatch):
    import bse_intel.universe as universe

    monkeypatch.setattr(universe, "load_nse", lambda sink: SimpleNamespace(built=False, included=set()))
    assert dgtr.sync(SimpleNamespace(sink=None), deadline=1e12, fetch=lambda u: b"")["stopped"] == "no NSE universe file yet"

    monkeypatch.setattr(universe, "load_nse", lambda sink: SimpleNamespace(built=True, included=set()))

    class Sink:
        objects: dict = {}

        def query(self, name, params):
            return []

        def get_object(self, key):
            return None

        def put_object(self, key, body, content_type="application/json"):
            self.objects[key] = body

    def dead(url):
        raise RuntimeError("DGTR request failed after 3 attempts")

    report = dgtr.sync(SimpleNamespace(sink=Sink()), deadline=1e12, fetch=dead)
    assert report["cases"] == 0 and len(report["errors"]) == 3 and not report["stopped"]


def test_live_run_classes_2026_10_19():
    # two applicants, the first ending in "Company"; a clause never becomes a name
    assert dgtr.named_companies("DGTR - An application has been filed by Hindusthan Chemical Company and United "
                                "Phosphorous Limited.") == {"Hindusthan Chemical Company": "APPLICANT",
                                                            "United Phosphorous Limited": "APPLICANT"}
    assert dgtr.named_companies("filed by UPL Limited and DGTR Superform Chemistries Limited.") == {
        "UPL Limited": "APPLICANT", "Superform Chemistries Limited": "APPLICANT"}
    # OCR reads "M/s" as "Mis"
    assert dgtr.named_companies("Mis Clean Science and Technology Private Limited (hereinafter referred to as the "
                                "applicant) has filed") == {"Clean Science and Technology Private Limited": "APPLICANT"}
    # the notice's plural slip still finds the one company; a private company is not its listed namesake
    companies = {dgtr.name_key("Laxmi Organic Industries Limited"): "540222",
                 dgtr.name_key("Clean Science and Technology Limited"): "543318"}
    assert dgtr.match_companies({"Laxmi Organics Industries Limited": "APPLICANT",
                                 "Clean Science and Technology Private Limited": "APPLICANT"}, companies) == {"540222": "APPLICANT"}
    # two companies one slip apart: no guess
    assert dgtr.match_companies({"Alpha Metal Limited": "APPLICANT"},
                                {"ALPHA METALS LIMITED": "1", "ALPHA METAL S LIMITED": "2", "ALPHAS METAL LIMITED": "3"}) == {}


def test_the_latest_initiation_names_the_applicant_and_the_stage_is_the_latest_by_date():
    docs = [{"label": "Final Findings", "stage": "FINAL_FINDING", "date": "2017-08-01", "url": "ff.pdf"},
            {"label": "Initiation Notification", "stage": "INITIATION", "date": "2026-09-30", "url": "new.pdf"},
            {"label": "Initiation Notification", "stage": "INITIATION", "date": "2016-10-05", "url": "old.pdf"}]
    assert dgtr._initiation(docs)["url"] == "new.pdf"
    dossier: dict = {}
    dgtr.merge(dossier, _case(), docs, "APPLICANT")
    entry = dossier["trade_remedies"][0]
    assert (entry["stage"], entry["stage_on"], entry["as_of"][:10]) == ("INITIATION", "2026-09-30", "2016-10-05")
