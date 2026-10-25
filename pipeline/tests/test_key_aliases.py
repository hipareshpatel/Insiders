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


def test_every_second_key_in_the_config_follows_its_provider():
    """Owner, 25 Oct 2026: Groq, Z.AI, Gemini and NVIDIA each have two keys (Mistral one); every route entry of the base
    provider is repeated for the second key once its secret is set, and nothing changes while it is not."""
    import tomllib
    from pathlib import Path

    config = tomllib.loads((Path(__file__).parents[1] / "config" / "providers.toml").read_text(encoding="utf-8"))
    pairs = {"groq": "GROQ_API_KEY_2", "zai": "ZAI_API_KEY_2",
             "gemini": "GEMINI_API_KEY_2", "nvidia": "NVIDIA_API_KEY_2"}
    for base, env_name in pairs.items():
        alias = f"{base}_2"
        assert config["providers"][alias] == {"same_as": base, "api_key_env": env_name}
        out = expand_key_aliases(config, {env_name: "k"})
        for route, entries in out["routes"].items():
            assert sum(e["provider"] == alias for e in entries) == sum(e["provider"] == base for e in entries), route
        assert alias not in expand_key_aliases(config, {})["providers"]
    assert "mistral_2" not in config["providers"]   # Mistral has one key (owner, 25 Oct 2026)
