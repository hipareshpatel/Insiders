"""Earnings calls by quarter in the company summary (O13/O4): grouping, caps, dedupe, boilerplate dropped."""

import json

from bse_intel import card_refresh
from bse_intel.call_summary import (CARD_PER_CATEGORY, CARD_TOTAL, CATEGORIES, PER_CATEGORY, PER_QUARTER, boilerplate,
                                    call_filings, card_takeaways, category, quarter_of, summarize_calls)
from bse_intel.models import Filing
from bse_intel.radar import summarize

T1, T2, T3, P3, R1 = "call-q1fy27", "call-q4fy26", "call-q3fy26", "deck-q3fy26", "results-q1fy27"


def _tl(news_id, when, event_type, summary, **extra):
    return {"id": "t_" + news_id, "date": when, "event_type": event_type, "impact_level": "MODERATE", "summary": summary,
            "news_id": news_id, **extra}


def dossier():
    """A mid-cap cement maker's memory after three calls, one deck and a results filing."""
    return {
        "scrip_code": "CEMX",
        "timeline": [
            _tl(R1, "2026-08-08T16:10:00+05:30", "RESULTS", "Q1FY27 revenue +12% YoY"),
            _tl(T1, "2026-08-14T19:00:00+05:30", "CONCALL_PRESENTATION", "Q1FY27 call: volumes +9%, capex on track",
                pdf_url="https://nsearchives.nseindia.com/corporate/CEMX_14082026.pdf"),
            _tl(T2, "2026-05-20T19:00:00+05:30", "CONCALL_PRESENTATION", "Q4 and FY26 earnings call transcript"),
            _tl(T3, "2026-02-05T19:00:00+05:30", "CONCALL_PRESENTATION", "Q3FY26 call transcript"),
            _tl(P3, "2026-02-03T19:00:00+05:30", "CONCALL_PRESENTATION", "Investor presentation Q3FY26"),
        ],
        "guidance": [
            {"id": "g1", "statement": "Volume growth of 10-12% in FY27", "metric": "volume", "target": "10-12%", "due": "FY27",
             "source_type": "CONCALL", "given_on": "2026-05-20T19:00:00+05:30", "source_news_id": T2, "status": "OPEN",
             "status_history": [], "repeated": [{"as_of": "2026-08-14T19:00:00+05:30", "source_news_id": T1}]},
            {"id": "g2", "statement": "Commission 2 MTPA grinding unit at Jajpur", "target": "₹650 Cr capex", "due": "Q4FY27",
             "source_type": "CONCALL", "given_on": "2026-08-14T19:00:00+05:30", "source_news_id": T1, "status": "OPEN",
             "status_history": []},
            {"id": "g3", "statement": "EBITDA per tonne of ₹1,000 by FY28", "due": "FY28", "source_type": "CONCALL",
             "given_on": "2026-08-14T19:00:00+05:30", "source_news_id": T1, "status": "OPEN", "status_history": []},
            {"id": "g4", "statement": "Revenue of ₹5,000 Cr in FY27", "due": "FY27", "source_type": "PRESS",
             "given_on": "2026-08-08T16:10:00+05:30", "source_news_id": R1, "status": "OPEN", "status_history": []},
            # a call the timeline no longer holds: its guidance still marks it as a call
            {"id": "g5", "statement": "Net debt to EBITDA below 1.5x by FY26", "due": "FY26", "source_type": "CONCALL",
             "given_on": "2025-11-10T19:00:00+05:30", "source_news_id": "call-q2fy26", "status": "OPEN", "status_history": []},
        ],
        "operating_notes": [
            {"text": "Thank you for joining us on the Q1FY27 earnings call", "as_of": "2026-08-14T19:00:00+05:30", "source_news_id": T1},
            {"text": "Good morning everyone and welcome", "as_of": "2026-08-14T19:00:00+05:30", "source_news_id": T1},
            {"text": "The earnings conference call was held on 14 August 2026 with the management", "as_of": "2026-08-14T19:00:00+05:30", "source_news_id": T1},
            {"text": "Cement volumes up 9% YoY to 3.1 MT; trade share 68%", "as_of": "2026-08-14T19:00:00+05:30", "source_news_id": T1},
            {"text": "Power and fuel cost down ₹110 per tonne on cheaper pet coke", "as_of": "2026-08-14T19:00:00+05:30", "source_news_id": T1},
            {"text": "Cement volumes rose 9% YoY to 3.1 MT, trade share at 68%", "as_of": "2026-08-14T19:00:00+05:30", "source_news_id": T1},
            {"text": "Fuel mix shifted to 40% pet coke", "as_of": "2026-05-20T19:00:00+05:30", "source_news_id": T2},
            {"text": "Results revenue note from the press release", "as_of": "2026-08-08T16:10:00+05:30", "source_news_id": R1},
            {"text": "Slides show East region share at 55%", "as_of": "2026-02-03T19:00:00+05:30", "source_news_id": P3},
        ],
        "watchlist": [
            {"id": "w1", "kind": "CONCERN", "text": "Why did receivables rise in Q1?", "response": "Government projects; collections due in Q2",
             "created_on": "2026-08-14T19:00:00+05:30", "source_news_id": T1, "status": "OPEN", "status_history": []},
            {"id": "w2", "kind": "CONCERN", "text": "Pricing in the East", "created_on": "2026-08-14T19:00:00+05:30",
             "source_news_id": T1, "status": "OPEN", "status_history": []},   # no answer: not a takeaway
        ],
        "deals": [{"id": "d1", "kind": "CAPEX", "expansion": "Clinker line 2 at Rajgangpur", "stage": "IN_PROGRESS",
                   "amount_cr": 1200.0, "as_of": "2026-02-05T19:00:00+05:30", "source_news_id": T3,
                   "history": [{"stage": "ANNOUNCED", "amount_cr": 1200.0, "as_of": "2026-02-05T19:00:00+05:30", "source_news_id": T3},
                               {"stage": "IN_PROGRESS", "amount_cr": 1200.0, "progress": "60% complete",
                                "as_of": "2026-08-14T19:00:00+05:30", "source_news_id": T1}]}],
        "capital_actions": [],
        "balance_sheet": [{"gross_debt_cr": 2100.0, "net_debt_cr": 1400.0, "as_of": "2026-05-20T19:00:00+05:30", "source_news_id": T2}],
    }


def test_quarter_discussed_from_the_summary_else_the_filing_date():
    assert quarter_of("2026-08-14T19:00:00+05:30", "Q1FY27 call") == "Q1FY27"
    assert quarter_of("2026-08-14", "Q2FY27 guidance raised") == "Q1FY27"   # a quarter not yet ended is not the call's
    assert quarter_of("2026-05-20") == "Q4FY26"
    assert quarter_of("2026-02-05") == "Q3FY26"
    assert quarter_of("2025-11-10") == "Q2FY26"
    assert quarter_of("2026-07-28", "Q4FY26 and Q1FY27 compared") == "Q1FY27"


def test_call_filings_by_timeline_event_or_guidance_source():
    calls = call_filings(dossier())
    assert set(calls) == {T1, T2, T3, P3, "call-q2fy26"}   # the results filing is not a call
    assert calls[T1]["pdf_url"].endswith(".pdf") and calls["call-q2fy26"]["quarter"] == "Q2FY26"


def test_boilerplate_and_categories():
    assert boilerplate("Thank you for joining us on the Q1FY27 earnings call")
    assert boilerplate("Good morning everyone and welcome")
    assert boilerplate("The earnings conference call was held on 14 August 2026 with the management")
    assert boilerplate("This presentation contains forward-looking statements")
    assert boilerplate("Strong quarter")   # too short to say anything
    assert not boilerplate("Cement volumes up 9% YoY to 3.1 MT; trade share 68%")
    assert category("Volume growth of 10-12% in FY27", "guidance") == "Guidance"
    assert category("Commission 2 MTPA grinding unit", "guidance") == "Capex & capacity"
    assert category("Power and fuel cost down ₹110 per tonne", "note") == "Margins & costs"
    assert category("Order book at ₹4,000 Cr, 2.5x sales", "note") == "Demand & orders"
    assert category("Why did receivables rise: government projects", "concern") == "Balance sheet & funding"
    assert category("New CFO appointed from within", "note") == "Other"


def test_calls_grouped_by_quarter_newest_first_with_headings_and_links():
    calls = summarize_calls(dossier())
    assert [c["quarter"] for c in calls] == ["Q1FY27", "Q4FY26", "Q3FY26", "Q2FY26"]
    q1 = calls[0]
    assert q1["date"] == "2026-08-14" and q1["sources"][0]["pdf_url"].endswith(".pdf")
    heads = {c["name"]: [p["text"] for p in c["points"]] for c in q1["categories"]}
    assert [c["name"] for c in q1["categories"]] == [c for c in CATEGORIES if c in heads]   # fixed order
    assert "Volume growth of 10-12% in FY27 · by FY27" not in heads.get("Guidance", [])
    assert any(t.startswith("Volume growth of 10-12% in FY27") for t in heads["Guidance"])   # reiterated on this call
    assert any("Jajpur" in t and "₹650 Cr" in t for t in heads["Capex & capacity"])
    assert any("Rajgangpur" in t and "60% complete" in t for t in heads["Capex & capacity"])   # the deal as this call put it
    assert heads["Margins & costs"][0].startswith("Power and fuel cost")
    assert any("receivables" in t and "collections due" in t for t in heads["Balance sheet & funding"])
    texts = [p["text"] for c in q1["categories"] for p in c["points"]]
    assert not any("Thank" in t or "welcome" in t or "conference call was held" in t for t in texts)
    assert sum("Cement volumes" in t for t in texts) == 1   # the same note in other words, once
    assert not any("press release" in t or "Pricing in the East" in t for t in texts)   # not from a call / no answer
    point = q1["categories"][0]["points"][0]
    assert point["news_id"] in (T1,) and point["date"] == "2026-08-14"
    reiterated = next(p for c in q1["categories"] for p in c["points"] if p["text"].startswith("Volume growth"))
    assert reiterated.get("reiterated") is True
    q3 = next(c for c in calls if c["quarter"] == "Q3FY26")
    assert {s["news_id"] for s in q3["sources"]} == {T3, P3}   # the transcript and the deck are one quarter
    q4 = next(c for c in calls if c["quarter"] == "Q4FY26")
    assert any("net debt ₹1,400 Cr" in p["text"] for c in q4["categories"] for p in c["points"])


def test_caps_per_heading_quarter_and_quarters():
    d = dossier()
    words = ["Odisha", "Bihar", "Jharkhand", "Bengal", "Assam", "Nepal", "Bhutan", "Sikkim"]
    kinds = ["Kiln", "Mill", "Silo", "Packer", "Crusher", "Dryer", "Grinder", "Depot"]
    d["operating_notes"] = [{"text": f"{k} capacity in {w} raised by {10 * (i + 1)} TPD", "source_news_id": T1,
                             "as_of": "2026-08-14T19:00:00+05:30"} for i, (k, w) in enumerate(zip(kinds, words))]
    d["operating_notes"] += [{"text": f"Demand from {w} {k.lower()} customers grew {i + 3}% this quarter", "source_news_id": T1,
                              "as_of": "2026-08-14T19:00:00+05:30"} for i, (k, w) in enumerate(zip(kinds, reversed(words)))]
    d["operating_notes"] += [{"text": t, "source_news_id": T1, "as_of": "2026-08-14T19:00:00+05:30"} for t in
                             ("Freight cost down ₹40 per tonne on rail share", "Power cost ₹1,150 per tonne after solar",
                              "EBITDA margin 18.5% on lower pet coke")]
    for i, (nid, when) in enumerate([("c-a", "2025-08-10"), ("c-b", "2025-05-10")]):
        d["timeline"].append(_tl(nid, f"{when}T19:00:00+05:30", "CONCALL_PRESENTATION", "call"))
        d["operating_notes"].append({"text": f"Old call note {i} with volumes up {i + 5}%", "as_of": when, "source_news_id": nid})
    calls = summarize_calls(d)
    assert [c["quarter"] for c in calls] == ["Q1FY27", "Q4FY26", "Q3FY26", "Q2FY26"]   # the last four only (not FY26's Q1)
    q1 = calls[0]
    assert all(len(c["points"]) <= PER_CATEGORY for c in q1["categories"])
    assert sum(len(c["points"]) for c in q1["categories"]) <= PER_QUARTER   # each heading capped, the quarter too


def test_company_summary_carries_the_calls_and_stays_json():
    s = summarize(dossier())["memory_summary_json"]
    assert s["calls"][0]["quarter"] == "Q1FY27"
    json.dumps(s, ensure_ascii=False)
    assert summarize({"timeline": [], "guidance": []})["memory_summary_json"]["calls"] == []


# --- the call card's own block: this filing's takeaways only ---

FILED_T1 = "2026-08-14T19:00:00+05:30"


def _texts(block):
    return [p["text"] for c in block for p in c["points"]]


def test_card_block_holds_only_this_filings_takeaways_by_heading():
    block = card_takeaways(dossier(), T1, FILED_T1)
    texts = _texts(block)
    names = [c["name"] for c in block]
    assert names == [c for c in CATEGORIES if c in names]   # the company page's order
    assert any("2 MTPA" in t for t in texts) and any("receivables" in t for t in texts)
    assert any(p.get("reiterated") for c in block for p in c["points"])   # FY27 volume guidance said again on T1
    # other filings' points stay out: the Q4 call's fuel mix and balance sheet, the press release, the Q3 deck
    assert not any("40% pet coke" in t or "press release" in t or "East region" in t or "gross debt" in t for t in texts)
    # greetings, thanks and the call's logistics are dropped; the repeated volume note is kept once
    assert not any(t.lower().startswith(("thank", "good morning")) or "was held" in t for t in texts)
    assert sum("3.1 MT" in t for t in texts) == 1


def test_card_block_figures_first_and_capped():
    d = dossier()
    d["operating_notes"] += [{"text": f"Plant {i} at Jajpur running at {60 + i}% of capacity", "source_news_id": T1,
                              "as_of": FILED_T1} for i in range(6)]
    d["operating_notes"] += [{"text": f"Management remains focused on premium brand {w} in the north", "source_news_id": T1,
                              "as_of": FILED_T1} for w in ("Alpha", "Bravo", "Charlie", "Delta")]
    block = card_takeaways(d, T1, FILED_T1)
    assert all(len(c["points"]) <= CARD_PER_CATEGORY for c in block)
    assert len(_texts(block)) == CARD_TOTAL
    for c in block:   # within a heading a stated figure comes before words alone
        has = [any(ch.isdigit() for ch in p["text"]) for p in c["points"]]
        assert has == sorted(has, reverse=True)


def test_card_block_empty_when_memory_took_nothing_from_the_filing():
    assert card_takeaways(dossier(), "call-unknown", FILED_T1) is None
    assert card_takeaways(dossier(), None, FILED_T1) is None
    d = dossier()
    d["operating_notes"] = [n for n in d["operating_notes"]
                            if n["source_news_id"] != T1 or n["text"].startswith(("Thank", "Good morning", "The earnings"))]
    d["guidance"] = [g for g in d["guidance"] if g["source_news_id"] != T1 and not g.get("repeated")]
    d["watchlist"], d["deals"] = [], []
    assert card_takeaways(d, T1, FILED_T1) is None   # only greetings and logistics were left


def test_refresh_adds_the_block_to_a_stored_call_card():
    card = {"event_type": "CONCALL_PRESENTATION", "impact_level": "MODERATE", "headline": "CEMX Q1FY27 call",
            "what_happened": [{"text": "Volumes up 9% YoY", "quote": "volumes grew 9%"}], "signals": [],
            "timeline_entry": "Q1FY27 call"}
    filing = Filing(news_id=T1, scrip_code="CEMX", company_name="Cement X Ltd", headline="h", subject="",
                    filed_at=FILED_T1, filing_date=FILED_T1[:10])
    new, changed = card_refresh.refresh(card, dossier(), filing, None)
    assert "call_memory" in changed and new["call_memory"] == card_takeaways(dossier(), T1, FILED_T1)
    assert not card_refresh.refresh({**card, "event_type": "ORDER_WIN"}, dossier(), filing, None)[0].get("call_memory")


def test_no_eps_in_call_takeaways_on_cards_or_the_company_page():
    """Owner rule (26 Oct 2026): no EPS on cards or stock pages. Memory keeps a call's EPS points for its checks; the
    call card's takeaway block and the company page's call summary leave them out."""
    d = dossier()
    d["operating_notes"] += [{"text": "Diluted EPS for the quarter was Rs 12.40 against Rs 9.10", "source_news_id": T1,
                              "as_of": FILED_T1}]
    d.setdefault("call_points", []).append({"news_id": T1, "text": "Earnings per share rose to Rs 12.4 in Q1",
                                            "category": CATEGORIES[0]})
    texts = _texts(card_takeaways(d, T1, FILED_T1))
    assert texts and not any("EPS" in t or "per share" in t.lower() for t in texts)
    assert "EPS" not in str(summarize_calls(d)) and "Earnings per share" not in str(summarize_calls(d))


def test_a_trailing_eps_clause_is_cut_and_the_rest_of_the_point_kept():
    d = dossier()
    d.setdefault("call_points", []).append({"news_id": T1, "text": "Net profit rose to Rs 50 crore, EPS Rs 3",
                                            "category": CATEGORIES[0]})
    texts = _texts(card_takeaways(d, T1, FILED_T1))
    assert any("Rs 50 crore" in t for t in texts) and not any("EPS" in t for t in texts)
