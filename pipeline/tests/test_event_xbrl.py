"""Event XBRL (PLAN 18 part 3): NSE's structured Reg 30 files, read field by field, joined to their announcement
and put in front of the card's text; an order's exact figures go on the card's deal. Fixtures are NSE's own files
of 17-18 Oct 2026 (RailTel's ₹167.52 Cr order, ACME Solar's PPA with a Windows-1252 byte, MedPlus's two licence
suspensions, Camlin's director retirement)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from bse_intel import event_xbrl as ex
from bse_intel.models import Card, DealValue, Filing
from bse_intel.timeutil import IST

FIX = Path(__file__).parent / "fixtures"


def _facts(name: str) -> ex.EventFacts:
    return ex.parse((FIX / f"nse_event_{name}.xml").read_bytes(), name)


def _file(app_id="18826", symbol="RAILTEL", when="2026-10-18 10:38", family_type="Bagging/Receiving of orders/contracts  (Sub-para 4-Para B)",
          attachment=None, size=None, xbrl="https://nsearchives.nseindia.com/corporate/xbrl/X.xml", prev=None):
    return ex.EventFile(app_id, symbol, "para-b", family_type, datetime.strptime(when, "%Y-%m-%d %H:%M").replace(tzinfo=IST),
                        xbrl, attachment, size, "Original", prev)


def _filing(subject="Bagging/Receiving of orders/contracts", when="2026-10-17T13:37:56+05:30", pdf="https://nsearchives.nseindia.com/corporate/R.pdf",
            size="324.10 KB", symbol="RAILTEL"):
    return Filing(news_id="nse-1", scrip_code="543265", company_name="RailTel", symbol=symbol, headline="x", subject=subject,
                  category="", subcategory=subject, filed_at=when, filing_date=when[:10], pdf_url=pdf, attachment_size=size)


def test_order_fields_are_read_exactly():
    f = _facts("railtel_order_20261018")
    assert (f.symbol, f.scrip_code, f.isin) == ("RAILTEL", "543265", "INE0DD101019")
    assert f.event_type == "Bagging/Receiving of orders/contracts"
    assert f.amounts_cr() == [167.52]
    (order,) = ex.orders([ex.Match(_file(), f, "same file")])
    assert order.amount_cr == 167.52 and order.counterparty == "Railway Recruitment Board Secunderabad"
    assert order.received and order.announcement == "New" and order.dated == "2026-10-16"
    assert order.includes_gst is False            # "Rs.1,67,52,00,000/-(ExcludingTax)"
    assert order.related_party is False and order.execution_by == "15-Oct-2031"
    table = ex.table([ex.Match(_file(), f, "same file")])
    assert "₹167.52 crore (₹1675200000)" in table and "type of announcement: New" in table


def test_a_file_with_bytes_outside_its_encoding_is_still_read():
    f = _facts("acmesolar_order_20261017")
    assert f is not None and f.amounts_cr() == [2415.0]
    assert ex.orders([ex.Match(_file(symbol="ACMESOLAR"), f, "content")])[0].counterparty == "Solar Energy Corporation of India Limited"


def test_several_actions_are_items_and_one_event_spread_over_contexts_is_one_header():
    medplus = _facts("medplus_action_20261018")
    assert medplus.event_type == "Action(s) taken or orders passed (sub-para 20)"
    actions = [i for i in medplus.items if "TypeOfActionsTakenOrOrdersPassed" in i]
    assert [a["PeriodForWhichCommunicationWouldBeApplicableForActionsTakenOrOrdersPassed"] for a in actions] == ["02 days", "01 day"]
    camlin = _facts("camlin_director_20261018")
    assert camlin.items == [] and camlin.main["NameOfDesignatedPerson"] == "Pradip Kanakia"
    assert camlin.main["TypeOfChange"] == "Tenure completion"


def test_same_file_by_url_by_size_and_by_the_pdf_in_the_zip():
    pdf = "https://nsearchives.nseindia.com/corporate/REFEX_17102026124640_RIL_order.pdf"
    assert ex.same_file(_file(attachment=pdf), pdf, None)
    # The company re-attaches the PDF to the XBRL form: a new name, the same size to the hundredth of a KB
    other = "https://nsearchives.nseindia.com/corporate/REG30PARAB_532884_17102026132023.pdf"
    assert ex.same_file(_file(attachment=other, size="409.89 KB"), pdf, "409.89 KB")
    assert not ex.same_file(_file(attachment=other, size="409.88 KB"), pdf, "409.89 KB")
    zipped = ex.EventFacts(pdf_size=394_537)       # 385.29 KB
    assert ex.same_file(_file(attachment="https://x/KMP_Doc.zip"), pdf, "385.29 KB", zipped)


def test_confirm_needs_the_amount_with_three_digits_or_a_name():
    order = _facts("railtel_order_20261018")
    assert ex.confirm(order, "RailTel has received a Letter of Acceptance worth Rs. 167.52 Crore from RRB")
    assert ex.confirm(order, "Order value: ₹ 1,67,52,00,000 (excluding taxes)")
    assert ex.confirm(order, "Value of the order: Rs 16,752.00 lakh")
    # Another order of the same client: the name is there, the amount is not
    assert not ex.confirm(order, "Railway Recruitment Board Secunderabad has awarded an order of Rs 18.99 Crore. Dated 16.10.2026, ref 167")
    director = _facts("camlin_director_20261018")
    assert ex.confirm(director, "Mr. Pradip Kanakia, Independent Director, completes his second term today")
    assert not ex.confirm(director, "Appointment of Ms. Asha Rao as Company Secretary")
    # The company's own name is in every filing of the company: it pairs nothing (round 5, Dabur's court-stay file
    # with its FDA letter of the day before)
    stay = ex.EventFacts(company="Dabur India Limited",
                         main={"NameOfTheAuthority": "Hon'ble Delhi High Court", "NameOfTheListedEntity": "Dabur India Limited"})
    assert stay.names() == ["Hon'ble Delhi High Court"]
    assert not ex.confirm(stay, "Dabur India Limited: US FDA warning letter for the Silvassa plant")
    assert ex.confirm(stay, "Dabur India Limited: stay granted today by the Hon'ble Delhi High Court")


def test_match_takes_the_same_file_then_content_within_the_window(settings):
    f = _facts("railtel_order_20261018")
    filing = _filing()
    same = _file(attachment="https://nsearchives.nseindia.com/corporate/REG30PARAB_543265.pdf", size="324.10 KB")
    later = _file(app_id="18827", when="2026-10-18 10:39")
    too_late = _file(app_id="18828", when="2026-10-23 10:00")
    elsewhere = _file(app_id="18829", symbol="IRCON")
    read = lambda file: f
    got, checked = ex.match(filing, [same, later, too_late, elsewhere], read, "an order worth Rs 167.52 crore")
    assert [(m.file.app_id, m.how) for m in got] == [("18826", "same file")] and set(checked) == {"18826", "18827"}
    got, _ = ex.match(filing, [later], read, "an order worth Rs 167.52 crore")
    assert [(m.file.app_id, m.how) for m in got] == [("18827", "content")]
    assert ex.match(filing, [later], read, "an order worth Rs 18.99 crore")[0] == []
    # A revision replaces the file it revises
    revised = _file(app_id="18830", when="2026-10-18 11:00", prev="18827")
    assert [m.file.app_id for m in ex.match(filing, [later, revised], read, "Rs 167.52 crore")[0]] == ["18830"]
    # A file of another event is not looked at, unless the filing went under a generic subject
    licence = _file(app_id="9", family_type="Key licenses/regulatory approvals (Sub-para 12-Para B)")
    assert ex.match(filing, [licence], read, "Rs 167.52 crore")[0] == []   # another event, and the subject is not generic
    assert ex.match(_filing(subject="General Updates"), [licence], read, "Rs 167.52 crore")[0]
    # Director changes get no card (owner, 2026-10-18), so their files are never read
    kmp = _file(app_id="7", family_type="Change in Directors/KMP/SMP/Auditor/RTA")
    assert ex.match(_filing(subject="General Updates"), [kmp], read, "Rs 167.52 crore") == ([], [])


def test_a_file_may_come_minutes_before_its_pdf():
    filing = _filing(when="2026-10-18T11:03:58+05:30")
    early = _file(when="2026-10-18 10:59")
    assert ex.candidates([early], "RAILTEL", datetime.fromisoformat(filing.filed_at)) == [early]
    assert ex.candidates([_file(when="2026-10-18 04:00")], "RAILTEL", datetime.fromisoformat(filing.filed_at)) == []


def test_the_file_sets_the_deal_and_the_model_keeps_the_words():
    (order,) = ex.orders([ex.Match(_file(), _facts("railtel_order_20261018"), "same file")])
    card = Card.model_validate({"impact_level": "MODERATE", "headline": "RailTel wins RRB exam services order",
                                "what_happened": [{"text": "LoA from RRB"}],
                                "deal_value": {"kind": "OTHER", "amount_cr": 1675.2, "counterparty": "RRB", "includes_gst": True}})
    notes = ex.apply_orders(card, [order])
    assert card.deal_value.amount_cr == 167.52 and card.deal_value.counterparty == "Railway Recruitment Board Secunderabad"
    assert card.deal_value.includes_gst is False and card.deal_value.kind == "ORDER" and card.deal_value.execution_by == "15-Oct-2031"
    assert len(notes) == 3 and card.headline == "RailTel wins RRB exam services order"
    empty = Card.model_validate({"impact_level": "MODERATE", "headline": "RailTel wins RRB exam services order",
                                 "what_happened": [{"text": "LoA from RRB"}]})
    ex.apply_orders(empty, [order])
    assert isinstance(empty.deal_value, DealValue) and empty.deal_value.amount_cr == 167.52
    # Two orders in the files: which one the card's deal is cannot be told, so it is left alone
    assert ex.apply_orders(card, [order, order]) == []


def test_parse_list_reads_both_row_shapes():
    rows = [{"appId": 100780, "symbol": "CYIENT", "eventType": "Resignation of Director/KMP/SMP", "broadcastDateTime": "18-Oct-2026 11:09:18",
             "attachment": "https://nsearchives.nseindia.com/corporate/CYIENT_ROID_100780_KMP_Doc.zip", "typeOfAnn": "Original"},
            {"appId": "202183", "symbol": "SBICARD", "eventType": "Options to purchase securities ESOPS (Sub-para 10-Para B)",
             "broadcastDateTime": "18-Oct-2026 11:40:30", "attachment": "https://nsearchives.nseindia.com/corporate/REG30PARAB_543066.pdf",
             "attachfileSize": "186.38 KB", "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/R.xml", "prevAppId": None},
            {"appId": "1", "symbol": "X", "broadcastDateTime": "not a time"}]
    zipped, esop = ex.parse_list(rows[:1], "announcements") + ex.parse_list(rows[1:], "para-b")
    assert zipped.xbrl_url.endswith(".zip") and zipped.family == "management"
    assert esop.attachment_size == "186.38 KB" and esop.family == "esop" and esop.prev_app_id is None
    assert esop.broadcast_at == datetime(2026, 10, 18, 11, 40, 30, tzinfo=IST)


class EventNse:
    """NSE's event XBRL list and files, as the pipeline asks for them."""

    def __init__(self, files, body):
        self.files, self.body, self.calls = files, body, []

    def event_xbrl(self, kind, day_from, day_to=None, symbol=None):
        self.calls.append((kind, day_from, day_to))
        return [f for f in self.files if f.kind == kind]

    def download(self, url, max_bytes=None):
        return self.body


def _nse_order(when, subject="Bagging/Receiving of orders/contracts"):
    from test_pipeline import _filing as bse_filing

    f = bse_filing("nse-106821056", "RailTel has informed the Exchange about Bagging/Receiving of orders/contracts", when)
    return f.model_copy(update={"subject": subject, "subcategory": subject, "symbol": "RAILTEL", "route": "FAST_TRACK",
                                "event_type": "ORDER_WIN"})


def test_an_order_card_takes_its_amount_and_client_from_the_file(settings):
    import json

    from bse_intel.timeutil import now_ist
    from test_pipeline import PASS2, _pdf, build

    filed = now_ist() - timedelta(hours=3)
    filing = _nse_order(filed)
    out = json.loads(json.dumps(PASS2))
    out["event_type"] = "ORDER_WIN"
    out["card"] = {"impact_level": "MODERATE", "headline": "RailTel bags an RRB exam-services order",
                   "what_happened": ["Letter of Acceptance from RRB Secunderabad"],
                   "deal_value": {"kind": "ORDER", "amount_cr": 1675.2, "counterparty": "RRB"}}
    out["dossier_delta"] = {}
    out["timeline_entry"] = "RailTel received an LoA from RRB Secunderabad."
    text = "RailTel has received a Letter of Acceptance from Railway Recruitment Board Secunderabad worth Rs. 167.52 Crore (excluding taxes)."
    pipeline, sink, fake = build(settings, [filing], {filing.pdf_url: _pdf(text)},
                                 {"nvidia/nemotron-3-super-120b-a12b": [json.dumps(out)] * 3}, env={"NVIDIA_API_KEY": "n"})
    file = ex.EventFile("18826", "RAILTEL", "para-b", "Bagging/Receiving of orders/contracts  (Sub-para 4-Para B)",
                        (filed + timedelta(minutes=50)).astimezone(IST), "https://nsearchives.nseindia.com/corporate/xbrl/R.xml", None, None)
    pipeline.nse = EventNse([file], (FIX / "nse_event_railtel_order_20261018.xml").read_bytes())
    result = pipeline.analyze(filing)
    card = result.card["card"]
    assert card["deal_value"]["amount_cr"] == 167.52
    assert card["deal_value"]["counterparty"] == "Railway Recruitment Board Secunderabad"
    assert card["deal_value"]["includes_gst"] is False
    assert card["event_xbrl"]["files"][0]["app_id"] == "18826" and card["event_xbrl"]["files"][0]["how"] == "content"
    assert card["event_xbrl"]["orders"][0]["related_party"] is False


def test_a_fresh_order_waits_for_its_file_without_spending_an_attempt(settings):
    from bse_intel.timeutil import now_ist
    from test_pipeline import _pdf, build

    filing = _nse_order(now_ist() - timedelta(minutes=12))
    pipeline, sink, fake = build(settings, [filing], {filing.pdf_url: _pdf("An order worth Rs. 167.52 Crore")}, {}, env={})
    pipeline.nse = EventNse([], b"")
    outcome = pipeline._process_one(filing, bulk=False, memory_complete=True)
    assert outcome.update["status"] == "PENDING" and "attempts" not in outcome.update
    assert outcome.update["last_error"].startswith("deferred: waiting for its event XBRL")
    # Older than the wait, it goes ahead from the PDF; a generic subject never waits
    assert ex.WAIT_MINUTES == 90
    late = _nse_order(now_ist() - timedelta(minutes=12), subject="General Updates")
    assert pipeline._event_xbrl(late, __import__("bse_intel.extract", fromlist=["Document"]).Document(_pdf("x")))[0] == []


def test_catch_up_reads_again_only_for_a_new_file_of_the_event(settings):
    from bse_intel import event_catchup
    from bse_intel.sinks.local import LocalSink

    row = {"news_id": "nse-1", "symbol": "RAILTEL", "filed_at": "2026-10-17T13:37:56+05:30",
           "subject": "Bagging/Receiving of orders/contracts", "checked": '["18825"]'}
    seen = _file(app_id="18825", when="2026-10-17 13:50")
    landed = _file(app_id="18826", when="2026-10-18 10:38")      # 21 hours later (RailTel, measured)
    licence = _file(app_id="9", when="2026-10-18 10:00", family_type="Key licenses/regulatory approvals (Sub-para 12-Para B)")
    assert [f.app_id for f in event_catchup.new_files(row, [seen, landed, licence])] == ["18826"]
    assert event_catchup.new_files(row, [seen, licence]) == []
    # Under a generic subject any event of the company's counts
    assert len(event_catchup.new_files(dict(row, subject="General Updates"), [seen, landed, licence])) == 2
    # The query runs on the local database
    assert LocalSink(settings).query("event_cards_without_xbrl", ["2026-10-01", 10]) == []


def test_nse_results_rows_become_quarter_links_with_the_revision_first():
    from bse_intel.nse import parse_integrated_rows, results_links

    rows = [{"xbrl": "https://x/INTEGRATED_FILING_INDAS_1_17102026091927_WEB.xml", "qe_Date": "30-SEP-2026",
             "consolidated": "Consolidated", "type_Sub": "Original", "broadcast_Date": "17-Oct-2026 21:19:12"},
            # a revision has no broadcast time; its time is revised_Date (owner, from the page's columns)
            {"xbrl": "https://x/INTEGRATED_FILING_INDAS_2_18102026091927_WEB.xml", "qe_Date": "30-SEP-2026",
             "consolidated": "Consolidated", "type_Sub": "Revision", "revised_Date": "18-OCT-2026 21:27:17"},
            {"xbrl": "https://x/INTEGRATED_FILING_INDAS_3_01082026091927_WEB.xml", "qe_Date": "30-JUN-2026",
             "consolidated": "Non-Consolidated", "type_Sub": "Original", "broadcast_Date": "01-Aug-2026 10:00:00"}]
    links = results_links(parse_integrated_rows(rows))
    assert [(l.period, l.basis, l.url, l.filed_at) for l in links] == [
        ("Q2FY27", "CONSOLIDATED", rows[1]["xbrl"], "2026-10-18"), ("Q1FY27", "STANDALONE", rows[2]["xbrl"], "2026-08-01")]


def test_results_catch_up_reads_again_on_a_new_file_or_a_revision():
    from bse_intel import event_catchup
    from bse_intel.bse import XbrlLink

    first = XbrlLink("Q2FY27", "CONSOLIDATED", "https://x/1.xml", "2026-10-17")
    revised = XbrlLink("Q2FY27", "CONSOLIDATED", "https://x/2.xml", "2026-10-18")
    made_from_pdf = {"filed_at": "2026-10-17T16:05:00+05:30", "xbrl_url": None}
    assert event_catchup.results_due(made_from_pdf, [first])
    assert not event_catchup.results_due(made_from_pdf, [XbrlLink("Q4FY26", "CONSOLIDATED", "u", "2026-05-02")])
    # a file listed when the card was made, which it could not use, does not bring it back on every run
    assert not event_catchup.results_due(dict(made_from_pdf, seen=json.dumps([first.url])), [first])
    assert event_catchup.results_due(dict(made_from_pdf, seen=json.dumps([first.url])), [first, revised])
    made_from_first = {"filed_at": "2026-10-17T16:05:00+05:30", "xbrl_url": first.url, "period": "Q2FY27", "basis": "CONSOLIDATED"}
    assert event_catchup.results_due(made_from_first, [first, revised])
    assert not event_catchup.results_due(dict(made_from_first, xbrl_url=revised.url), [first, revised])


def test_a_fresh_nse_results_filing_waits_for_its_xbrl(settings):
    from bse_intel.timeutil import now_ist
    from test_pipeline import RESULT_TEXT, _pdf, build

    filing = _nse_order(now_ist() - timedelta(minutes=40)).model_copy(update={
        "subject": "Outcome of Board Meeting", "subcategory": "Outcome of Board Meeting", "event_type": "RESULTS"})
    pipeline, sink, fake = build(settings, [filing], {filing.pdf_url: _pdf(RESULT_TEXT)}, {}, env={})

    class NoResultsYet(EventNse):
        def financial_results(self, symbol, quarterly=True):
            self.calls.append(("results", symbol))
            return []

    pipeline.nse = NoResultsYet([], b"")
    outcome = pipeline._process_one(filing, bulk=False, memory_complete=True)
    assert outcome.update["status"] == "PENDING" and "attempts" not in outcome.update
    assert outcome.update["last_error"].startswith("deferred: waiting for its results XBRL")
    assert ("results", "RAILTEL") in pipeline.nse.calls and fake.calls == []   # no model was asked
