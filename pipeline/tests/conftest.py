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
def _sums_off_for_partial_files(request, monkeypatch):
    """The hand-made XBRL files of test_xbrl and test_seed are partial and do not add up (3 tests fail with the sums
    check on); every other module runs with it on, as production does (F140)."""
    from bse_intel.settings import get_settings
    monkeypatch.setenv("XBRL_SUMS", "0" if request.module.__name__.endswith(("test_xbrl", "test_seed")) else "1")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _clear_of_ist_midnight(monkeypatch):
    """Tests date filings "minutes ago" or "minutes ahead"; just after midnight IST the first lands on yesterday, and
    in the last hour before it the second lands on tomorrow. In those windows, run the clock two hours behind so every
    test sees one calendar day."""
    real = timeutil.datetime
    if 1 <= real.now(timeutil.IST).hour < 23:
        return

    class Shifted(real):
        @classmethod
        def now(cls, tz=None):
            return real.now(tz) - timeutil.timedelta(hours=2)

    monkeypatch.setattr(timeutil, "datetime", Shifted)


@pytest.fixture(autouse=True)
def _no_local_ocr_on_figure_pages(monkeypatch):
    """analyze() reads a page of figures with local OCR when it is installed. The tests' PDFs are the same
    on a laptop that has it and a runner that does not; a test that wants it turns it on."""
    monkeypatch.setattr("bse_intel.pipeline.local_ocr_available", lambda: False)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return replace(Settings(), sink="local", local_dir=tmp_path / "local", workers=2, text_cache_dir=tmp_path / "text_cache", price_dir=tmp_path / "prices",
                   universe_min_mcap_cr=0, one_card_per_results_quarter=False,  # fixtures reuse one quarter's results text
                   discovery_source="bse",  # the BSE fakes; NSE discovery has its own tests
                   critic=False,  # the shadow critic has its own tests (test_critic.py); scripts here are the writers'
                   backfill_cards_from=None,  # memory-only backfill has its own tests (test_memory_only.py)
                   prompt_short_share=0.0)  # the short prompt has its own tests (test_prompt_short.py)


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


@pytest.fixture(autouse=True)
def _file_counter_reset():
    """F213: the run's file counter is process-wide; every test starts from zero, and a batch pause never really sleeps."""
    from bse_intel.file_batch import files
    files.reset()
    files.sleep = lambda s: None
    yield
    files.reset()
