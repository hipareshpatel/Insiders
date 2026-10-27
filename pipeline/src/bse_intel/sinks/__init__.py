import os

from ..settings import Settings
from .base import Sink


def _env_number(name: str, default, cast):
    try:
        value = cast(os.environ.get(name) or default)
    except ValueError:
        return default
    return value if value > 0 else default


def make_sink(settings: Settings) -> Sink:
    if settings.sink == "platform":
        from .platform import PlatformSink

        # F216: PLATFORM_TIMEOUT_S and PLATFORM_ATTEMPTS bound a dead request in a long read-only run; unset = 60 s, 4 tries
        return PlatformSink(settings.platform_url or "", settings.ingest_token or "",
                            timeout=_env_number("PLATFORM_TIMEOUT_S", 60.0, float),
                            attempts=_env_number("PLATFORM_ATTEMPTS", 4, int))
    if settings.sink == "local":
        from .local import LocalSink

        return LocalSink(settings)
    raise ValueError(f"unknown sink: {settings.sink!r} (expected 'local' or 'platform')")


__all__ = ["Sink", "make_sink"]
