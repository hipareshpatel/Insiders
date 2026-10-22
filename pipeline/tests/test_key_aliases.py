"""A second key for a provider (gateway.expand_key_aliases; owner, 2026-10-22)."""

from bse_intel.ai.gateway import AIGateway, expand_key_aliases

CONFIG = {
    "providers": {
        "gemini": {"base_url": "https://g.example/v1", "api_key_env": "GEMINI_API_KEY", "quota_tz": "America/Los_Angeles"},
        "gemini_2": {"same_as": "gemini", "api_key_env": "GEMINI_API_KEY_2"},
        "zai": {"base_url": "https://z.example/v1", "api_key_env": "ZAI_API_KEY"},
    },
    "routes": {"pass2": [
        {"provider": "gemini", "model": "flash", "weight": 3, "limits": {"rpm": 5, "rpd": 20}},
        {"provider": "zai", "model": "glm", "weight": 4},
    ]},
}


def test_a_second_key_repeats_every_entry_of_its_provider_with_its_own_limits():
    out = expand_key_aliases(CONFIG, {"GEMINI_API_KEY": "a", "GEMINI_API_KEY_2": "b"})
    assert [e["provider"] for e in out["routes"]["pass2"]] == ["gemini", "gemini_2", "zai"]
    assert out["providers"]["gemini_2"]["base_url"] == "https://g.example/v1"
    assert out["providers"]["gemini_2"]["quota_tz"] == "America/Los_Angeles"
    gw = AIGateway(CONFIG, env={"GEMINI_API_KEY": "a", "GEMINI_API_KEY_2": "b", "ZAI_API_KEY": "z"})
    keys = [t.key for t in gw.routes["pass2"]]
    assert keys == ["gemini:flash", "gemini_2:flash", "zai:glm"]
    assert gw.limiters["gemini:flash"] is not gw.limiters["gemini_2:flash"]
    assert [t.api_key for t in gw.routes["pass2"]][:2] == ["a", "b"]


def test_no_second_key_changes_nothing():
    out = expand_key_aliases(CONFIG, {"GEMINI_API_KEY": "a"})
    assert [e["provider"] for e in out["routes"]["pass2"]] == ["gemini", "zai"]
    assert "gemini_2" not in out["providers"]
