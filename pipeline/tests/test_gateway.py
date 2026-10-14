from __future__ import annotations

import pytest
from conftest import api_error, gateway_config, openai

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
