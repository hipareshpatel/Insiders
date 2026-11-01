"""CARD_EVENT_REPEAT (STATUS S2, measured 1 Nov 2026: 47 repeat pairs in 30 days): ARIS's ₹250 Cr Transcon order filed as an
exchange intimation (nse-106830824, 18:40) and a press release (nse-106830842, 18:45) became two cards."""

from bse_intel import event_repeats as E

TIMELINE = [
    {"event_type": "ORDER_WIN", "date": "2026-10-27T18:36:04+05:30", "news_id": "nse-106830806",
     "summary": "Arisinfra Solutions announced that its subsidiary JS Infra Core secured a ₹9.85 Cr work order from S.P. Adke's Construction."},
    {"event_type": "ORDER_WIN", "date": "2026-10-27T18:40:37+05:30", "news_id": "nse-106830824",
     "summary": "Arisinfra Solutions announced that its subsidiary Arisunitern RE Solutions secured a ₹250 Cr DaaS service order from "
                "Transcon Iconica."},
]
RELEASE = "Arisinfra subsidiary wins ₹250 Cr DaaS mandate for Transcon Ramdev Plaza Phase II"


def on(monkeypatch):
    monkeypatch.setenv("CARD_EVENT_REPEAT", "1")


def test_the_press_release_of_an_order_already_on_file_is_a_repeat(monkeypatch):
    on(monkeypatch)
    found = E.match("ORDER_WIN", "2026-10-27T18:45:34+05:30", RELEASE, "Arisinfra Solutions Limited", TIMELINE, "nse-106830842")
    assert found and found[0] == "nse-106830824" and "250" in found[1] and "transcon" in found[1]


def test_another_amount_another_customer_another_kind_or_too_late_is_not(monkeypatch):
    on(monkeypatch)
    co = "Arisinfra Solutions Limited"
    assert E.match("ORDER_WIN", "2026-10-27T18:45:34+05:30", "Arisinfra wins ₹120 Cr order from Transcon", co, TIMELINE) is None
    assert E.match("ORDER_WIN", "2026-10-27T18:45:34+05:30", "Arisinfra wins ₹250 Cr order from Lodha Group", co, TIMELINE) is None
    assert E.match("M_AND_A", "2026-10-27T18:45:34+05:30", RELEASE, co, TIMELINE) is None
    assert E.match("ORDER_WIN", "2026-11-02T18:45:34+05:30", RELEASE, co, TIMELINE) is None       # more than 3 days later
    assert E.match("CONCALL_PRESENTATION", "2026-10-27T18:45:34+05:30", RELEASE, co, TIMELINE) is None   # the owner's call
    assert E.match("ORDER_WIN", "2026-10-27T18:40:37+05:30", RELEASE, co, TIMELINE, "nse-106830824") is None  # itself


def test_the_company_s_own_name_is_no_shared_name(monkeypatch):
    on(monkeypatch)
    tl = [{"event_type": "ORDER_WIN", "date": "2026-10-27T10:00:00+05:30", "news_id": "n1",
           "summary": "Arisinfra Solutions secured a ₹250 Cr order."}]
    assert E.match("ORDER_WIN", "2026-10-27T12:00:00+05:30", "Arisinfra wins ₹250 Cr order", "Arisinfra Solutions Limited", tl) is None


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("CARD_EVENT_REPEAT", raising=False)
    monkeypatch.delenv("REPO_VARS", raising=False)
    monkeypatch.setenv("BSE_INTEL_SWITCHES", "/no/such/file.toml")
    assert E.match("ORDER_WIN", "2026-10-27T18:45:34+05:30", RELEASE, "Arisinfra Solutions Limited", TIMELINE) is None


def test_an_order_book_total_is_no_order_amount(monkeypatch):
    """Lead's review of #329: two different orders whose cards both cite the order book must not match on it."""
    on(monkeypatch)
    tl = [{"event_type": "ORDER_WIN", "date": "2026-10-27T10:00:00+05:30", "news_id": "n1",
           "summary": "KEC wins a ₹410 Cr Powergrid line order; order book now ₹12,400 Cr."}]
    later = "KEC wins ₹220 Cr Powergrid substation order, taking its order book to ₹12,400 Cr"
    assert E.match("ORDER_WIN", "2026-10-28T10:00:00+05:30", later, "KEC International Limited", tl) is None
    same = "KEC wins ₹410 Cr Powergrid line order (press release); order book ₹12,400 Cr"
    assert E.match("ORDER_WIN", "2026-10-28T10:00:00+05:30", same, "KEC International Limited", tl)[0] == "n1"
