from __future__ import annotations

import pytest
from conftest import api_error, completion, gateway_config, openai

from bse_intel.ai.gateway import AllProvidersFailed
from bse_intel.models import Pass1Result

GOOD = {"is_material": True, "event_type": "RESULTS", "confidence": 0.9, "reason": "quarterly results"}


def route(*targets):
    return {"r": [dict(t) for t in targets]}


def test_fails_over_on_429_and_cools_down(make_gateway):
    config = gateway_config(route({"provider": "a", "model": "m-a"}, {"provider": "b", "model": "m-b"}))
    gw, fake = make_gateway(config, {"m-a": [api_error(openai.RateLimitError, 429, "slow down", {"retry-after": "120"})],
                                      "m-b": [GOOD]})
    result = gw.complete_json("r", "sys JSON", "user", Pass1Result)
    assert result.provider == "b" and result.value.is_material
    assert gw.usage["a:m-a"].rate_limited == 1
    assert gw.limiters["a:m-a"].cooling_down()


def test_daily_quota_429_retires_model_for_the_day(make_gateway):
    config = gateway_config(route({"provider": "a", "model": "m-a"}, {"provider": "b", "model": "m-b"}))
    err = api_error(openai.RateLimitError, 429, "Rate limit reached: tokens per day (TPD) limit 500000")
    gw, _ = make_gateway(config, {"m-a": [err], "m-b": [GOOD]})
    gw.complete_json("r", "s", "u", Pass1Result)
    assert gw.limiters["a:m-a"].quota.exhausted() == "provider reported daily quota reached"


def test_per_minute_quota_429_only_cools_down(make_gateway):
    config = gateway_config(route({"provider": "a", "model": "m-a"}, {"provider": "b", "model": "m-b"}))
    err = api_error(openai.RateLimitError, 429, "You exceeded your current quota. Quota exceeded for metric: "
                    "generate_content_free_tier_requests, quotaId: GenerateRequestsPerMinutePerProjectPerModel-FreeTier")
    gw, _ = make_gateway(config, {"m-a": [err], "m-b": [GOOD]})
    gw.complete_json("r", "s", "u", Pass1Result)
    assert not gw.limiters["a:m-a"].quota.exhausted()
    assert gw.limiters["a:m-a"].cooling_down()


def test_a_reply_passed_through_as_parsed_json_is_still_read(make_gateway):
    config = gateway_config(route({"provider": "a", "model": "m-a"}))
    reply = completion("")
    reply.choices[0].message.content = dict(GOOD)  # Workers AI hands JSON back as an object
    gw, _ = make_gateway(config, {"m-a": [reply]})
    result = gw.complete_json("r", "s", "u", Pass1Result)
    assert result.value.is_material


def test_a_model_allowing_one_request_at_a_time_sends_the_next_elsewhere(make_gateway, monkeypatch):
    import threading

    from bse_intel.ai import gateway as gateway_module

    monkeypatch.setattr(gateway_module, "MAX_SLOT_WAIT", 0.05)
    config = gateway_config(route({"provider": "a", "model": "m-a", "limits": {"rpm": 60, "concurrency": 1}},
                                  {"provider": "b", "model": "m-b"}))
    inside, release = threading.Event(), threading.Event()

    def slow(kwargs):
        inside.set()
        release.wait(5)
        return GOOD

    gw, fake = make_gateway(config, {"m-a": [slow], "m-b": [GOOD]})
    first = {}
    worker = threading.Thread(target=lambda: first.update(r=gw.complete_json("r", "s", "u", Pass1Result)))
    worker.start()
    assert inside.wait(5)
    second = gw.complete_json("r", "s", "u", Pass1Result)  # m-a is busy: goes to m-b, not a second m-a call
    release.set()
    worker.join(5)
    assert first["r"].provider == "a" and second.provider == "b"
    assert [c["model"] for c in fake.calls] == ["m-a", "m-b"]


def test_95_percent_ceiling_moves_traffic_before_the_hard_limit(make_gateway):
    config = gateway_config(route(
        {"provider": "a", "model": "m-a", "limits": {"rpd": 100}},
        {"provider": "b", "model": "m-b"},
    ))
    # 95 of 100 daily requests already used (persisted from earlier runs)
    gw, fake = make_gateway(config, {"m-a": [GOOD], "m-b": [GOOD]},
                            usage_today=[{"provider": "a", "model": "m-a", "requests": 95}])
    result = gw.complete_json("r", "s", "u", Pass1Result)
    assert result.provider == "b"
    assert [c["model"] for c in fake.calls] == ["m-b"]


def test_provider_level_monthly_ceiling(make_gateway):
    providers = {
        "a": {"base_url": "https://a.invalid", "api_key_env": "A_KEY", "limits": {"tpmo": 1_000_000}},
        "b": {"base_url": "https://b.invalid", "api_key_env": "B_KEY"},
    }
    config = gateway_config(route({"provider": "a", "model": "m-a"}, {"provider": "b", "model": "m-b"}), providers)
    gw, _ = make_gateway(config, {"m-a": [GOOD], "m-b": [GOOD]},
                         usage_month=[{"provider": "a", "model": "m-a", "input_tokens": 940_000, "output_tokens": 20_000}])
    assert gw.complete_json("r", "s", "u", Pass1Result).provider == "b"


def test_provider_level_daily_requests_are_shared_by_its_models(make_gateway):
    """OpenRouter's free models share one allowance per day: requests to either model count against it."""
    providers = {
        "a": {"base_url": "https://a.invalid", "api_key_env": "A_KEY", "limits": {"rpd": 20}},
        "b": {"base_url": "https://b.invalid", "api_key_env": "B_KEY"},
    }
    config = gateway_config(route({"provider": "a", "model": "m-a1"}, {"provider": "a", "model": "m-a2"},
                                  {"provider": "b", "model": "m-b"}), providers)
    used = [{"provider": "a", "model": "m-a1", "requests": 12}, {"provider": "a", "model": "m-a2", "requests": 7}]
    gw, fake = make_gateway(config, {"m-a1": [GOOD], "m-a2": [GOOD], "m-b": [GOOD]}, usage_today=used)
    assert gw.complete_json("r", "s", "u", Pass1Result).provider == "b"  # 19 of 20 x 95% spent
    assert [c["model"] for c in fake.calls] == ["m-b"]


def test_openrouter_free_models_are_spares_under_one_daily_allowance(settings):
    config = settings.load_toml("providers.toml")
    assert config["providers"]["openrouter"]["limits"]["rpd"] == 1_000  # after the one-time credit purchase (D19)
    entries = [e for route in config["routes"].values() for e in route if e["provider"] == "openrouter"]
    assert entries and all(e["model"].endswith(":free") for e in entries)  # never a paid model by accident
    for name, route in config["routes"].items():  # a regular, weighted share in the backfill only, for the VL model alone:
        for e in (e for e in route if e["provider"] == "openrouter"):  # Ultra (53% wrong in the audit) is a spare everywhere
            regular = name == "pass2_bulk" and "3.5-super-vl" in e["model"]
            assert (not e.get("spare") and e.get("weight", 1) >= 1) if regular else e.get("spare"), (name, e)
    assert config["gateway"]["strategies"]["pass2_bulk"] == "weighted"
    for route in config["routes"].values():  # the free allowance is 20/min across the models of one route
        assert sum(e["limits"]["rpm"] for e in route if e["provider"] == "openrouter") <= 20


def test_quota_exhausted_everywhere_is_reported_not_raised_as_crash(make_gateway):
    config = gateway_config(route({"provider": "a", "model": "m-a", "limits": {"rpd": 10}}))
    gw, _ = make_gateway(config, {"m-a": [GOOD]}, usage_today=[{"provider": "a", "model": "m-a", "requests": 10}])
    with pytest.raises(AllProvidersFailed) as info:
        gw.complete_json("r", "s", "u", Pass1Result)
    assert info.value.quota_exhausted and not info.value.transient and not info.value.attempted


def test_rate_limited_everywhere_is_transient(make_gateway):
    config = gateway_config(route({"provider": "a", "model": "m-a"}))
    gw, _ = make_gateway(config, {"m-a": [api_error(openai.RateLimitError, 429, "busy")]})
    with pytest.raises(AllProvidersFailed):
        gw.complete_json("r", "s", "u", Pass1Result)
    # second request: the model is cooling down for 60s, which exceeds the pacing wait
    gw.limiters["a:m-a"]._blocked_until += 1000
    with pytest.raises(AllProvidersFailed) as info:
        gw.complete_json("r", "s", "u", Pass1Result)
    assert info.value.transient and not info.value.quota_exhausted


def test_spare_is_used_only_after_primary_pool(make_gateway):
    config = gateway_config(route(
        {"provider": "spare", "model": "m-spare", "spare": True},
        {"provider": "a", "model": "m-a"},
    ))
    gw, fake = make_gateway(config, {"m-a": [api_error(openai.InternalServerError, 503)], "m-spare": [GOOD]})
    assert gw.complete_json("r", "s", "u", Pass1Result).provider == "spare"
    assert [c["model"] for c in fake.calls] == ["m-a", "m-spare"]


def test_weighted_rotation_spreads_load(make_gateway):
    config = gateway_config(route(
        {"provider": "a", "model": "m-a", "weight": 3},
        {"provider": "b", "model": "m-b", "weight": 1},
    ), strategies={"r": "weighted"})
    gw, fake = make_gateway(config, {"m-a": [GOOD], "m-b": [GOOD]})
    picks = [gw.complete_json("r", "s", "u", Pass1Result).provider for _ in range(8)]
    assert picks.count("a") == 6 and picks.count("b") == 2
    assert "bbb" not in "".join(picks) and "aaaa" not in "".join(picks)


def test_invalid_json_is_repaired_by_the_same_model(make_gateway):
    config = gateway_config(route({"provider": "a", "model": "m-a"}))
    gw, fake = make_gateway(config, {"m-a": ['{"is_material": "maybe"}', GOOD]})
    result = gw.complete_json("r", "s", "u", Pass1Result)
    assert result.value.event_type == "RESULTS"
    assert len(fake.calls) == 2 and "did not match" in fake.calls[1]["messages"][-1]["content"]


def test_reasoning_block_is_stripped(make_gateway):
    config = gateway_config(route({"provider": "a", "model": "r1", "strip_reasoning": True}))
    text = '<think>Let me consider {"is_material": false}...</think>\n```json\n{"is_material": true, "event_type": "capex"}\n```'
    gw, _ = make_gateway(config, {"r1": [text]})
    value = gw.complete_json("r", "s", "u", Pass1Result).value
    assert value.is_material and value.event_type == "CAPEX"


def test_json_mode_rejection_falls_back_to_plain_mode(make_gateway):
    config = gateway_config(route({"provider": "a", "model": "m-a", "json_mode": True}))
    err = api_error(openai.BadRequestError, 400, "response_format json_object is not supported")
    gw, fake = make_gateway(config, {"m-a": [err, GOOD]})
    gw.complete_json("r", "s", "u", Pass1Result)
    assert "response_format" in fake.calls[0] and "response_format" not in fake.calls[1]


def test_bad_key_disables_target_and_missing_key_skips(make_gateway):
    config = gateway_config(route(
        {"provider": "a", "model": "m-a"}, {"provider": "b", "model": "m-b"}, {"provider": "c", "model": "m-c"},
    ))
    gw, fake = make_gateway(config, {"m-a": [api_error(openai.AuthenticationError, 401)], "m-c": [GOOD]},
                            env={"A_KEY": "bad", "C_KEY": "kc"})
    assert gw.complete_json("r", "s", "u", Pass1Result).provider == "c"
    assert "a:m-a" in gw.disabled
    assert [c["model"] for c in fake.calls] == ["m-a", "m-c"]  # b had no key and was never called


def test_prompt_larger_than_context_window_skips_model(make_gateway):
    config = gateway_config(route(
        {"provider": "a", "model": "small", "context_tokens": 100},
        {"provider": "b", "model": "long"},
    ))
    gw, fake = make_gateway(config, {"long": [GOOD]})
    assert gw.complete_json("r", "s", "x" * 3000, Pass1Result).model == "long"


def test_base_url_env_interpolation(make_gateway):
    providers = {"cf": {"base_url": "${PLATFORM_API_URL}/api/internal/ai/v1", "api_key_env": "INGEST_TOKEN"}}
    config = gateway_config(route({"provider": "cf", "model": "@cf/x"}), providers)
    gw, _ = make_gateway(config, {"@cf/x": [GOOD]}, env={"PLATFORM_API_URL": "https://site.example/", "INGEST_TOKEN": "t"})
    target = gw.routes["r"][0]
    assert target.base_url == "https://site.example/api/internal/ai/v1" and target.api_key == "t"
    gw2, _ = make_gateway(config, {}, env={"INGEST_TOKEN": "t"})
    assert gw2.routes["r"][0].api_key is None  # base URL variable missing -> not configured


def test_usage_rows_report_limits(make_gateway):
    config = gateway_config(route({"provider": "a", "model": "m-a", "limits": {"rpd": 14400, "tpd": 500000}}))
    gw, _ = make_gateway(config, {"m-a": [GOOD]})
    gw.complete_json("r", "s", "u", Pass1Result)
    (row,) = gw.usage_rows("2026-10-14", "now")
    assert row["requests"] == 1 and row["input_tokens"] == 100 and row["limit_rpd"] == 14400


def test_outage_is_transient_so_the_filing_keeps_its_attempts(make_gateway):
    config = gateway_config(route({"provider": "a", "model": "m-a"}, {"provider": "b", "model": "m-b"}))
    timeout = openai.APITimeoutError(request=__import__("httpx").Request("POST", "https://a.invalid"))
    gw, _ = make_gateway(config, {"m-a": [timeout], "m-b": [api_error(openai.InternalServerError, 502)]})
    with pytest.raises(AllProvidersFailed) as info:
        gw.complete_json("r", "s", "u", Pass1Result)
    assert info.value.transient and not info.value.attempted


def test_groq_json_validation_failure_is_not_mistaken_for_unsupported_json_mode(make_gateway):
    config = gateway_config(route({"provider": "a", "model": "m-a", "json_mode": True}))
    err = api_error(openai.BadRequestError, 400, "json_validate_failed: Failed to generate JSON")
    gw, fake = make_gateway(config, {"m-a": [err, GOOD]})
    with pytest.raises(AllProvidersFailed):
        gw.complete_json("r", "s", "u", Pass1Result)
    assert len(fake.calls) == 1 and gw.routes["r"][0].json_mode


def test_answer_after_closing_think_tag_without_an_opening_one(make_gateway):
    config = gateway_config(route({"provider": "a", "model": "r1", "strip_reasoning": True}))
    text = 'The filing says {"is_material": false} at first, but on reflection...</think>{"is_material": true, "event_type": "RESULTS"}'
    gw, _ = make_gateway(config, {"r1": [text]})
    assert gw.complete_json("r", "s", "u", Pass1Result).value.is_material


def test_no_request_starts_after_the_deadline(make_gateway):
    import time

    config = gateway_config(route({"provider": "a", "model": "m-a"}))
    gw, fake = make_gateway(config, {"m-a": [GOOD]})
    gw.deadline = time.monotonic() - 1
    with pytest.raises(AllProvidersFailed) as info:
        gw.complete_json("r", "s", "u", Pass1Result)
    assert info.value.transient and fake.calls == []
    gw.deadline = time.monotonic() + 100
    gw.complete_json("r", "s", "u", Pass1Result)
    assert fake.calls[0]["timeout"] <= 100


def test_non_json_body_fails_over(make_gateway):
    config = gateway_config(route({"provider": "a", "model": "m-a"}, {"provider": "b", "model": "m-b"}))
    gw, fake = make_gateway(config, {"m-a": [lambda kw: None], "m-b": [GOOD]})
    fake.chat.completions.create = lambda **kw: "<html>gateway error</html>" if kw["model"] == "m-a" else \
        __import__("conftest").completion(__import__("json").dumps(GOOD))
    assert gw.complete_json("r", "s", "u", Pass1Result).provider == "b"


def test_rejected_key_disables_every_model_of_that_provider(make_gateway):
    config = gateway_config(route(
        {"provider": "a", "model": "m-a"}, {"provider": "a", "model": "m-a2"}, {"provider": "b", "model": "m-b"},
    ))
    gw, fake = make_gateway(config, {"m-a": [api_error(openai.PermissionDeniedError, 403)], "m-b": [GOOD, GOOD]})
    assert gw.complete_json("r", "s", "u", Pass1Result).provider == "b"
    assert gw.complete_json("r", "s", "u", Pass1Result).provider == "b"
    assert "m-a2" not in [c["model"] for c in fake.calls]
    assert {h["target"]: h["status"] for h in gw.health()}["a:m-a2"] == "disabled"


def test_retired_model_410_is_disabled(make_gateway):
    config = gateway_config(route({"provider": "a", "model": "old"}, {"provider": "b", "model": "m-b"}))
    gw, fake = make_gateway(config, {"old": [api_error(openai.APIStatusError, 410, "gone")], "m-b": [GOOD, GOOD]})
    gw.complete_json("r", "s", "u", Pass1Result)
    gw.complete_json("r", "s", "u", Pass1Result)
    assert gw.disabled["a:old"] == "model retired" and [c["model"] for c in fake.calls] == ["old", "m-b", "m-b"]


def test_403_for_a_models_tier_disables_only_that_model(make_gateway):
    config = gateway_config(route(
        {"provider": "a", "model": "big"}, {"provider": "a", "model": "small"},
    ))
    err = api_error(openai.PermissionDeniedError, 403, "This model is not available in your subscription tier")
    gw, fake = make_gateway(config, {"big": [err], "small": [GOOD]})
    assert gw.complete_json("r", "s", "u", Pass1Result).model == "small"
    assert gw.disabled["a:big"] == "model not in subscription tier" and "a" not in gw.disabled_providers


def test_nemotron_super_runs_with_thinking_off_on_every_pass2_route():
    """Owner decision D21 (2026-10-16): thinking on took 150-760 s a card and timed out 1 call in 3; off took 23-68 s.
    With thinking off the model answers "{}" in JSON mode, so JSON mode is off on those entries."""
    import tomllib
    from pathlib import Path

    config = tomllib.loads((Path(__file__).parent.parent / "config" / "providers.toml").read_text(encoding="utf-8"))
    entries = [t for route in ("pass2", "pass2_bulk", "pass2_long") for t in config["routes"][route]
               if t["model"] == "nvidia/nemotron-3-super-120b-a12b"]
    assert len(entries) == 3
    for entry in entries:
        assert entry["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}} and entry["json_mode"] is False
