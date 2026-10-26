"""The Tijori download (F189): JSON extraction, the slug map, the page check, 302 as "no page", the slow-back-then-stop rule,
resume."""

import json
from pathlib import Path

import httpx
import pytest

from bse_intel import tijori

FIXTURES = Path(__file__).parent / "fixtures"
DAY = "2026-10-27"


def fixture(name):
    return json.loads((FIXTURES / f"tijori_{name}.json").read_text(encoding="utf-8"))


def page_html(fx):
    """A financials page the way Tijori serves it: other JSON blocks, a bigger decoy, the identity and the tables."""
    return ("<html><head><title>x</title>"
            '<script type="application/ld+json">{"about": {"tickerSymbol": "%s", "name": "%s"}}</script></head><body>'
            '<script id="peersList" type="application/json">{"a": 1}</script>'
            '<script id="company_details" type="application/json">%s</script>'
            '<script id="%s" type="application/json">%s</script>'
            "<script src='https://www.google.com/recaptcha/api.js'></script></body></html>"
            % (fx["company_details"]["symbol"], fx["company_details"]["company"], json.dumps(fx["company_details"]),
               tijori.TABLES_ID, json.dumps(fx["fin_tables_data"])))


SITEMAP = ("<urlset>" + "".join(
    f"<url><loc>https://www.tijorifinance.com/company/{s}/</loc></url>"
    f"<url><loc>https://www.tijorifinance.com/company/{s}/financials/</loc></url>"
    for s in ("apar-industries-limited", "abb-india-limited", "the-anup-engineering-ltd", "sundaram-finance-limited",
              "twin-a-ltd", "twin-a-limited")) + "<url><loc>https://www.tijorifinance.com/features/</loc></url></urlset>")

COMPANIES = [("1", "ABB", "ABB India Ltd."), ("2", "APARINDS", "Apar Industries Limited"),
             ("3", "ANUPE", "The Anup Engineering Limited"), ("4", "TWINA", "Twin A Limited"),
             ("5", "NOSUCH", "No Such Company Ltd")]


SLUGS = ("apar-industries-limited", "abb-india-limited", "the-anup-engineering-ltd", "sundaram-finance-limited", "twin-a-ltd",
         "twin-a-limited")


class Sink:
    """``seed``: a saved slug map in which no page named a symbol, so a company is found by the name rule and fetched by slug (the
    run before the sweep existed); ``Sink(seed=False)`` is a first run with no map."""

    def __init__(self, seed=True):
        self.kv, self.objects = {}, {}
        if seed:
            self.kv[tijori.SLUGS_KEY] = json.dumps({"built": "x", "slugs": {s: "" for s in SLUGS}})

    def kv_get(self, key):
        return self.kv.get(key)

    def kv_set(self, key, value, now):
        self.kv[key] = value

    def list_objects(self, prefix):
        return sorted(k for k in self.objects if k.startswith(prefix))

    def put_object(self, key, body, content_type="application/json"):
        self.objects[key] = body

    def get_object(self, key):
        return self.objects.get(key)


def client_for(answers, seen, **kw):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen.append(url)
        status, body = answers(url)
        return httpx.Response(status, text=body, headers={"location": "/"} if status == 302 else {})
    naps = []
    return tijori.TijoriClient(transport=httpx.MockTransport(handler), sleep=naps.append, clock=lambda: 0.0, **kw), naps


def site(url):
    if url.endswith("/sitemap.xml"):
        return 200, SITEMAP
    if "/abb-india-limited/" in url:
        return 200, page_html(fixture("abb"))
    if "/apar-industries-limited/" in url:
        return 200, page_html(fixture("apar"))
    return 302, ""


# --- the page ----------------------------------------------------------------------------------------------------

def test_the_tables_are_taken_from_the_named_block_and_hold_the_known_rows():
    tables = tijori.extract_tables(page_html(fixture("apar")))
    assert set(tables) >= {"qt_c", "qt_s", "pl_c_s", "pl_s_s"}
    row = next(r for r in tables["qt_c"]["data"] if r["name"] == "Net Profit")
    assert dict(zip(tables["qt_c"]["report_dates"], row["value"]))["Jun 2026"] == 467.45


def test_without_the_id_the_largest_json_block_that_holds_the_tables_is_taken():
    fx = fixture("abb")
    body = page_html(fx).replace(f'id="{tijori.TABLES_ID}"', 'id="renamed"')
    assert tijori.extract_tables(body)["qt_c"]["report_dates"] == fx["fin_tables_data"]["qt_c"]["report_dates"]
    assert tijori.extract_tables("<html>no data</html>") is None


def test_the_page_names_its_company():
    assert tijori.identity(page_html(fixture("apar"))) == {"symbol": "APARINDS", "name": "Apar Industries Ltd.",
                                                          "slug": "apar-industries-limited"}
    assert tijori.verifies({"symbol": "APARINDS", "name": "x", "slug": ""}, "aparinds", "Anything")
    assert tijori.verifies({"symbol": "", "name": "Apar Industries Ltd.", "slug": ""}, "APARINDS", "Apar Industries Limited")
    assert not tijori.verifies({"symbol": "OTHER", "name": "Other Ltd.", "slug": ""}, "APARINDS", "Apar Industries Limited")


# --- the slug map ------------------------------------------------------------------------------------------------

def test_names_and_slugs_meet_after_ltd_limited_the_and_punctuation():
    assert tijori.normalise("The Anup Engineering Ltd.") == tijori.normalise("the-anup-engineering-limited".replace("-", " "))
    assert tijori.normalise("Mahindra & Mahindra Limited") == "mahindra and mahindra"
    assert tijori.normalise("Dolphin Offshore Enterprises (India) Ltd.") == "dolphin offshore enterprises india"
    assert tijori.normalise("Bajaj Auto's Ltd") == "bajaj autos"


def test_slugs_are_the_company_level_urls_only():
    assert tijori.sitemap_slugs(SITEMAP) == ["apar-industries-limited", "abb-india-limited", "the-anup-engineering-ltd",
                                             "sundaram-finance-limited", "twin-a-ltd", "twin-a-limited"]


def test_matched_ambiguous_and_unmatched_are_told_apart():
    got = tijori.map_slugs(COMPANIES, tijori.sitemap_slugs(SITEMAP))
    assert got["matched"] == {"ABB": "abb-india-limited", "APARINDS": "apar-industries-limited",
                              "ANUPE": "the-anup-engineering-ltd"}
    assert got["ambiguous"] == {"TWINA": ["twin-a-limited", "twin-a-ltd"]}
    assert got["unmatched"] == ["NOSUCH"]


# --- the run -----------------------------------------------------------------------------------------------------

def test_a_verified_page_is_stored_as_gzipped_tables_and_a_302_is_no_page():
    sink, seen = Sink(), []
    client, _ = client_for(site, seen)
    with client:
        out = tijori.run(sink, COMPANIES, client, DAY)
    assert sorted(sink.objects) == [f"raw/tijori/{DAY}/ABB.json.gz", f"raw/tijori/{DAY}/APARINDS.json.gz"]
    stored = json.loads(tijori.unpack(sink.objects[f"raw/tijori/{DAY}/APARINDS.json.gz"]))
    assert stored == fixture("apar")["fin_tables_data"]
    assert out["pages_stored"] == 2 and out["pages_no_page"] == 2 and out["matched"] == 3 and out["unmatched"] == ["NOSUCH"]
    assert "TWINA" in out["ambiguous"] and sum("twin-a" in u for u in seen) == 2   # both candidates tried, none has a page
    assert sum("/sitemap.xml" in u for u in seen) == 1 and out["requests_made"] == 6 and not out["more"] and not out["slowed"]


def test_a_page_of_another_company_is_discarded_and_listed():
    sink = Sink()

    def answers(url):
        return (200, page_html(fixture("apar"))) if "/abb-india-limited/" in url else site(url)
    client, _ = client_for(answers, [])
    with client:
        out = tijori.run(sink, COMPANIES[:1], client, DAY)
    assert not sink.objects and out["pages_not_verified"] == 1 and "ABB -> abb-india-limited" in out["not_verified"][0]
    assert json.loads(sink.kv[f"tijoridl:done:{DAY}"]) == ["ABB"]      # a wrong page does not change on a retry


def test_a_finished_company_and_a_stored_page_are_not_fetched_again():
    sink, seen = Sink(), []
    sink.objects[f"raw/tijori/{DAY}/ABB.json.gz"] = tijori.pack("{}")
    client, _ = client_for(site, seen)
    with client:
        first = tijori.run(sink, COMPANIES[:2], client, DAY)
        assert first["pages_already_stored"] == 1 and first["pages_stored"] == 1
        assert tijori.unpack(sink.objects[f"raw/tijori/{DAY}/ABB.json.gz"]) == "{}"
        again = tijori.run(sink, COMPANIES[:2], client, DAY)
    assert again["companies_done_before"] == 2 and again["requests_made"] == 1   # only the sitemap


def test_a_server_error_is_retried_by_the_next_run_and_a_new_day_starts_again():
    sink, state = Sink(), {"fail": True}

    def answers(url):
        return (500, "") if state["fail"] and "/abb-india-limited/" in url else site(url)
    client, _ = client_for(answers, [])
    with client:
        first = tijori.run(sink, COMPANIES[:2], client, DAY)
        assert first["pages_failed"] == 1 and first["failed"]
        state["fail"] = False
        second = tijori.run(sink, COMPANIES[:2], client, DAY)
        assert second["pages_stored"] == 1 and second["companies_done_before"] == 1
        third = tijori.run(sink, COMPANIES[:2], client, "2026-10-28")
    assert third["pages_stored"] == 2


def test_the_time_budget_leaves_companies_and_says_so():
    sink = Sink()
    client, _ = client_for(site, [])
    ticks = iter([0, 100, 100, 100, 100, 100, 100])
    with client:
        out = tijori.run(sink, COMPANIES[:2], client, DAY, time_budget=10, clock=lambda: next(ticks), workers=1)
    assert out["more"] and not sink.objects


# --- pace and refusal --------------------------------------------------------------------------------------------

def test_one_shared_limiter_spaces_every_start_by_a_sixth_of_a_second():
    assert tijori.RATE == 6.0 and tijori.WORKERS == 8
    client, naps = client_for(site, [])
    with client:
        for _ in range(4):
            client.get("https://www.tijorifinance.com/company/abb-india-limited/financials/")
    assert [round(n, 3) for n in naps] == [0.167, 0.333, 0.5]    # the clock stands still: each waits for its own slot


def test_the_first_refusal_slows_the_run_and_the_page_is_asked_again():
    sink, state = Sink(), {"left": 1}

    def answers(url):
        if "/abb-india-limited/" in url and state["left"]:
            state["left"] -= 1
            return 429, ""
        return site(url)
    client, naps = client_for(answers, [])
    with client:
        out = tijori.run(sink, COMPANIES[:2], client, DAY, workers=1)
    assert out["slowed"] and out["slowed_after_requests"] == 2 and "429" in out["refusal"]
    assert out["pages_stored"] == 2 and out["pages_failed"] == 0
    assert any(n >= 3.0 for n in naps)     # one request every 3 s from then on


@pytest.mark.parametrize("status", [403, 429, 503])
def test_a_second_refusal_after_slowing_down_stops_the_run_and_keeps_what_is_done(status):
    sink, seen = Sink(), []

    def answers(url):
        if "/apar-industries-limited/" in url:
            return status, ""
        return site(url)
    client, _ = client_for(answers, seen)
    with client, pytest.raises(tijori.TijoriRefused):
        tijori.run(sink, COMPANIES[:3], client, DAY, workers=1)
    assert f"raw/tijori/{DAY}/ABB.json.gz" in sink.objects          # stored before the refusal
    assert json.loads(sink.kv[f"tijoridl:done:{DAY}"]) == ["ABB"]
    assert not any("the-anup" in u for u in seen)               # nothing asked after it


def test_a_challenge_page_counts_as_a_refusal_but_the_recaptcha_script_of_a_real_page_does_not():
    gate = "<html><title>Just a moment...</title><div class='g-recaptcha'></div></html>"
    client, _ = client_for(lambda url: (200, gate), [])
    with client:
        with pytest.raises(tijori.TijoriRefused):
            client.get("https://www.tijorifinance.com/company/abb-india-limited/financials/")
        assert client.slowed and "challenge" in client.refusal
    real = page_html(fixture("abb"))
    assert "recaptcha" in real
    client, _ = client_for(lambda url: (200, real), [])
    with client:
        assert client.get("https://www.tijorifinance.com/x/")[0] == 200 and not client.slowed


BIG = "<html>" + "x" * 60_000


def test_a_normal_page_without_tables_is_no_tables_not_a_refusal_and_a_short_gate_is_refused():
    normal = ('<html><script src="https://www.google.com/recaptcha/api.js"></script>'
              '<script id="company_details" type="application/json">{"symbol": "ABB"}</script>' + "x" * 60_000 + "</html>")
    assert not tijori.is_challenge(normal) and not tijori.is_challenge(BIG + "recaptcha")
    client, _ = client_for(lambda url: (200, normal), [])
    with client:
        out = tijori._fetch(client, "ABB", "ABB India Ltd.", "abb-india-limited")
        assert out["kind"] == "no_tables" and not client.slowed
    short = "<html><title>Just a moment...</title></html>"
    assert tijori.is_challenge(short) and not tijori.is_challenge("<div class='g-recaptcha'></div>")
    client, _ = client_for(lambda url: (200, short), [])
    with client, pytest.raises(tijori.TijoriRefused):
        client.get("https://www.tijorifinance.com/x/")


def test_no_request_goes_out_after_a_stop_even_from_a_thread_that_was_sleeping():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, text="ok")
    client = tijori.TijoriClient(transport=httpx.MockTransport(handler), clock=lambda: 0.0, sleep=lambda n: None)
    with client:
        client.get("https://x/1")

        def stopping_sleep(n):
            client._stopped = "stopped while waiting"     # the stop arrives during the sleep
        client._sleep = stopping_sleep
        with pytest.raises(tijori.TijoriRefused):
            client.get("https://x/2")
    assert seen == ["https://x/1"]


def test_an_ambiguous_name_takes_the_first_candidate_whose_page_verifies():
    sink, seen = Sink(), []

    def answers(url):
        if url.endswith("/sitemap.xml"):
            return 200, SITEMAP.replace("abb-india-limited", "x-abb-india-ltd").replace("</urlset>",
                "<url><loc>https://www.tijorifinance.com/company/abb-india-ltd/</loc></url></urlset>")
        if "/abb-india-ltd/" in url:
            return 200, page_html(fixture("abb"))
        if "/x-abb-india-ltd/" in url:
            return 200, page_html(fixture("apar"))   # another company's page
        return site(url)
    client, _ = client_for(answers, seen)
    with client:
        out = tijori.run(sink, [("1", "ABB", "ABB India Ltd.")], client, DAY, workers=1)
    assert out["pages_stored"] == 1 and f"raw/tijori/{DAY}/ABB.json.gz" in sink.objects


@pytest.mark.parametrize("gate", ["<html>Sorry, you have been blocked. Cloudflare Ray ID: 8a1</html>",
                                  "<html><h1>Error 1015</h1>You are being rate limited</html>"])
def test_other_gate_wordings_on_a_200_page_are_refusals(gate):
    assert tijori.is_challenge(gate)
    client, _ = client_for(lambda url: (200, gate), [])
    with client, pytest.raises(tijori.TijoriRefused):
        client.get("https://www.tijorifinance.com/x/")
    assert client.slowed


def test_a_stub_page_is_suspect_not_stored_not_finished_and_not_a_refusal():
    stub = "<html><body>please verify you are human: captcha</body></html>"
    sink = Sink()

    def answers(url):
        return (200, stub) if "/abb-india-limited/" in url else site(url)
    client, _ = client_for(answers, [])
    with client:
        out = tijori.run(sink, COMPANIES[:1], client, DAY)
    assert not sink.objects and out["pages_suspect"] == 1 and len(out["suspect"]) == 1 and not out["slowed"]
    assert json.loads(sink.kv[f"tijoridl:done:{DAY}"]) == []          # a later run asks again
    assert "suspect" in tijori.render(out)


def test_candidates_a_failed_one_and_a_suspect_one_win_over_final_answers():
    def run_with(first, second):
        pages = {"/a/": first, "/b/": second}
        client, _ = client_for(lambda url: next(v for k, v in pages.items() if k in url), [])
        with client:
            return tijori._fetch(client, "ABB", "ABB India Ltd.", ["a", "b"])["kind"]
    other = (200, page_html(fixture("apar")))
    assert run_with((500, ""), other) == "failed" and run_with(other, (500, "")) == "failed"
    assert run_with((200, "<html>stub</html>"), (302, "")) == "suspect"
    assert run_with((500, ""), (200, "<html>stub</html>")) == "failed"
    assert run_with(other, (302, "")) == "no_page"


def test_a_symbol_that_is_not_ours_rejects_the_page_even_when_the_name_fits():
    page = {"symbol": "OTHER", "name": "ABB India Ltd", "slug": ""}
    assert not tijori.verifies(page, "ABB", "ABB India Ltd.")
    assert tijori.verifies({"symbol": "", "name": "ABB India Ltd", "slug": ""}, "ABB", "ABB India Ltd.")


@pytest.mark.parametrize("ld", ['[{"about": {"tickerSymbol": "ABB", "name": "ABB India"}}]',
                                '{"@graph": [{"@type": "x"}, {"about": {"tickerSymbol": "ABB", "name": "ABB India"}}]}',
                                '{"about": "a string"}', '"just a string"', "[1, 2]", "null"])
def test_identity_survives_odd_ld_json(ld):
    page = tijori.identity(f'<script type="application/ld+json">{ld}</script>')
    assert page["symbol"] in ("", "ABB") and set(page) == {"symbol", "name", "slug"}
    if "ABB" in ld:
        assert page["symbol"] == "ABB"


def test_an_unexpected_error_on_one_company_is_a_failure_of_that_company_only(monkeypatch):
    real = tijori._fetch

    def broken(client, symbol, name, slug):
        if symbol == "ABB":
            raise ValueError("boom")
        return real(client, symbol, name, slug)
    monkeypatch.setattr(tijori, "_fetch", broken)
    sink = Sink()
    client, _ = client_for(site, [])
    with client:
        out = tijori.run(sink, COMPANIES[:2], client, DAY, workers=1)
    assert out["pages_failed"] == 1 and "ValueError" in out["failed"][0] and out["pages_stored"] == 1
    assert json.loads(sink.kv[f"tijoridl:done:{DAY}"]) == ["APARINDS"]


def test_the_stop_is_checked_again_just_before_the_request_goes_out():
    seen = []
    client = tijori.TijoriClient(transport=httpx.MockTransport(lambda r: seen.append(1) or httpx.Response(200, text="ok")),
                                 clock=lambda: 0.0, sleep=lambda n: None)
    real = client._slot

    def slot():
        out = real()
        client._stopped = "stopped after the slot"
        return out
    client._slot = slot
    with client, pytest.raises(tijori.TijoriRefused):
        client.get("https://x/1")
    assert seen == []


# --- matching by the page's own symbol (the sweep) ------------------------------------------------------------------

def page_as(symbol, name="Whatever Ltd.", base="abb"):
    fx = json.loads(json.dumps(fixture(base)))
    fx["company_details"]["symbol"], fx["company_details"]["company"] = symbol, name
    return page_html(fx)


def no_symbol_page(base="abb"):
    fx = json.loads(json.dumps(fixture(base)))
    fx["company_details"]["symbol"] = ""
    fx["company_details"]["company"] = "ABB India Ltd."
    return ('<script id="company_details" type="application/json">%s</script><script id="%s" type="application/json">%s</script>'
            % (json.dumps(fx["company_details"]), tijori.TABLES_ID, json.dumps(fx["fin_tables_data"])))


def sweep_site(pages, extra=()):
    slugs = list(pages) + list(extra)
    xml = "<urlset>" + "".join(f"<url><loc>https://www.tijorifinance.com/company/{s}/</loc></url>" for s in slugs) + "</urlset>"

    def answers(url):
        if url.endswith("/sitemap.xml"):
            return 200, xml
        for slug, body in pages.items():
            if f"/company/{slug}/financials/" in url:
                return 200, body
        return 302, ""
    return answers


ETERNAL = [("1", "ETERNAL", "Eternal Limited"), ("2", "ABB", "ABB India Ltd.")]


def test_a_renamed_company_is_found_by_the_symbol_on_its_page_and_another_companys_page_is_only_recorded():
    pages = {"zomato-ltd": page_as("ETERNAL"), "abb-india-limited": page_as("abb"), "not-ours-ltd": page_as("ELSEWHERE")}
    sink, seen = Sink(seed=False), []
    client, _ = client_for(sweep_site(pages), seen)
    with client:
        out = tijori.run(sink, ETERNAL, client, DAY, workers=1)
    assert sorted(sink.objects) == [f"raw/tijori/{DAY}/ABB.json.gz", f"raw/tijori/{DAY}/ETERNAL.json.gz"]
    assert out["slugs_swept"] == 3 and out["slugs_in_map"] == 3 and out["ours_by_symbol"] == 2 and out["ours_by_name"] == 0
    assert out["ours_unmatched"] == [] and out["duplicate_symbols"] == {} and out["requests_made"] == 4 and out["pages_stored"] == 2
    saved = json.loads(sink.kv[tijori.SLUGS_KEY])
    assert saved["slugs"] == {"zomato-ltd": "ETERNAL", "abb-india-limited": "ABB", "not-ours-ltd": "ELSEWHERE"}
    assert sorted(json.loads(sink.kv[f"tijoridl:done:{DAY}"])) == ["ABB", "ETERNAL"]
    text = tijori.render(out)
    assert "slugs swept this run         3" in text and "ours matched by symbol       2" in text


def test_the_second_run_uses_the_saved_map_and_sweeps_nothing():
    pages = {"zomato-ltd": page_as("ETERNAL"), "not-ours-ltd": page_as("ELSEWHERE")}
    sink, seen = Sink(seed=False), []
    client, _ = client_for(sweep_site(pages), seen)
    with client:
        tijori.run(sink, ETERNAL[:1], client, DAY, workers=1)
        seen.clear()
        out = tijori.run(sink, ETERNAL[:1], client, "2026-10-28", workers=1)    # a new day: the page is fetched again, by slug
        assert out["slugs_swept"] == 0 and out["pages_stored"] == 1 and out["ours_by_symbol"] == 1
        assert [u for u in seen if "/company/" in u] == ["https://www.tijorifinance.com/company/zomato-ltd/financials/"]
        seen.clear()
        again = tijori.run(sink, ETERNAL[:1], client, "2026-10-28", workers=1)
        assert again["requests_made"] == 1 and again["companies_done_before"] == 1       # only the sitemap
        seen.clear()
        rebuilt = tijori.run(sink, ETERNAL[:1], client, "2026-10-29", workers=1, rebuild_map=True)
    assert rebuilt["slugs_swept"] == 2 and sum("/company/" in u for u in seen) == 2


def test_a_run_stopped_by_a_refusal_keeps_its_swept_slugs_and_the_next_run_does_not_fetch_them_again():
    pages = {"a-ltd": page_as("AAA"), "b-ltd": page_as("BBB"), "c-ltd": page_as("ETERNAL"), "d-ltd": page_as("DDD")}
    sink, seen = Sink(seed=False), []
    state = {"refuse": True}

    def answers(url):
        if "/c-ltd/" in url and state["refuse"]:
            return 429, ""
        return sweep_site(pages)(url)
    client, _ = client_for(answers, seen)
    with client, pytest.raises(tijori.TijoriRefused):
        tijori.run(sink, ETERNAL[:1], client, DAY, workers=1)
    assert sorted(json.loads(sink.kv[tijori.SLUGS_KEY])["slugs"]) == ["a-ltd", "b-ltd"]
    assert "d-ltd" not in "".join(seen)
    state["refuse"] = False
    seen.clear()
    client, _ = client_for(answers, seen)
    with client:
        out = tijori.run(sink, ETERNAL[:1], client, DAY, workers=1)
    fetched = [u.split("/company/")[1].split("/")[0] for u in seen if "/company/" in u]
    assert fetched == ["c-ltd", "d-ltd"] and out["pages_stored"] == 1 and out["slugs_in_map"] == 4


def test_two_slugs_with_one_symbol_keep_the_first_and_list_both():
    pages = {"abb-india-limited": page_as("ABB"), "abb-india-ltd": page_as("ABB")}
    sink, seen = Sink(seed=False), []
    client, _ = client_for(sweep_site(pages), seen)
    with client:
        out = tijori.run(sink, ETERNAL[1:], client, DAY, workers=1)
    assert out["pages_stored"] == 1 and out["duplicate_symbols"] == {"ABB": ["abb-india-limited", "abb-india-ltd"]}
    assert tijori.unpack(sink.objects[f"raw/tijori/{DAY}/ABB.json.gz"])


def test_a_page_without_a_symbol_is_recorded_empty_and_matched_by_name_only():
    pages = {"abb-india-limited": no_symbol_page(), "zomato-ltd": page_as("ETERNAL")}
    sink, seen = Sink(seed=False), []
    client, _ = client_for(sweep_site(pages), seen)
    with client:
        out = tijori.run(sink, ETERNAL, client, DAY, workers=1)
    assert json.loads(sink.kv[tijori.SLUGS_KEY])["slugs"]["abb-india-limited"] == ""
    assert out["ours_by_symbol"] == 1 and out["ours_by_name"] == 1 and out["ours_unmatched"] == []
    assert sorted(sink.objects) == [f"raw/tijori/{DAY}/ABB.json.gz", f"raw/tijori/{DAY}/ETERNAL.json.gz"]
    assert sum("abb-india-limited" in u for u in seen) == 2        # once in the sweep, once by the name rule


def test_the_limit_caps_the_sweep_and_the_estimate_counts_it():
    pages = {f"co-{i}-ltd": page_as(f"S{i}") for i in range(10)}
    sink, seen = Sink(seed=False), []
    client, _ = client_for(sweep_site(pages), seen)
    with client:
        out = tijori.run(sink, ETERNAL, client, DAY, workers=1, sweep_limit=3)
    assert out["slugs_swept"] == 3 and out["slugs_left_to_sweep"] == 7 and sum("/company/" in u for u in seen) == 3
    assert out["ours_unmatched"] == ["ETERNAL", "ABB"]
    assert tijori.estimate(100, rate=10, sweep=50) == {"requests": 151, "seconds": 15}
