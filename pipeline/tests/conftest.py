from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import httpx
import openai
import pytest

from bse_intel import timeutil
from bse_intel.settings import Settings


@pytest.fixture(autouse=True)
def _clear_of_ist_midnight(monkeypatch):
    """Tests date filings "minutes ago"; just after midnight IST that lands on yesterday.
    In that window, run the clock two hours behind so every test sees one calendar day."""
    real = timeutil.datetime
    if real.now(timeutil.IST).hour >= 1:
        return

    class Shifted(real):
        @classmethod
        def now(cls, tz=None):
            return real.now(tz) - timeutil.timedelta(hours=2)

    monkeypatch.setattr(timeutil, "datetime", Shifted)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return replace(Settings(), sink="local", local_dir=tmp_path / "local", workers=2, text_cache_dir=tmp_path / "text_cache", price_dir=tmp_path / "prices",
                   universe_min_mcap_cr=0, one_card_per_results_quarter=False)  # fixtures reuse one quarter's results text


def completion(text: str, prompt_tokens: int = 100, completion_tokens: int = 50):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


def api_error(cls, status: int, message: str = "error", headers: dict | None = None):
    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    response = httpx.Response(status, request=request, headers=headers or {})
    return cls(message, response=response, body=None)


class FakeProvider:
    """Stands in for an OpenAI-compatible client. ``script`` maps model -> list of
    responses (str = content, Exception = raised, callable = called with kwargs)."""

    def __init__(self, script: dict[str, list]):
        self.script = script
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        queue = self.script.get(kwargs["model"])
        if not queue:
            raise AssertionError(f"unexpected call to {kwargs['model']}")
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        if callable(item):
            item = item(kwargs)
        if isinstance(item, SimpleNamespace):  # a whole completion, as given
            return item
        return completion(item if isinstance(item, str) else json.dumps(item))


def gateway_config(routes: dict, providers: dict | None = None, **gateway) -> dict:
    providers = providers or {
        name: {"base_url": f"https://{name}.invalid/v1", "api_key_env": f"{name.upper()}_KEY"}
        for name in ("a", "b", "c", "spare")
    }
    return {"gateway": gateway, "providers": providers, "routes": routes}


ENV = {"A_KEY": "ka", "B_KEY": "kb", "C_KEY": "kc", "SPARE_KEY": "ks"}


@pytest.fixture
def make_gateway():
    from bse_intel.ai.gateway import AIGateway

    def build(config: dict, script: dict, env: dict | None = None, **kwargs):
        fake = FakeProvider(script)
        gw = AIGateway(config, client_factory=lambda base, key, timeout: fake, env=ENV if env is None else env, **kwargs)
        return gw, fake

    return build


__all__ = ["FakeProvider", "api_error", "completion", "gateway_config", "openai"]
