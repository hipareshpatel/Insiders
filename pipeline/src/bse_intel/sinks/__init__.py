from ..settings import Settings
from .base import Sink


def make_sink(settings: Settings) -> Sink:
    if settings.sink == "platform":
        from .platform import PlatformSink

        return PlatformSink(settings.platform_url or "", settings.ingest_token or "")
    if settings.sink == "local":
        from .local import LocalSink

        return LocalSink(settings)
    raise ValueError(f"unknown sink: {settings.sink!r} (expected 'local' or 'platform')")


__all__ = ["Sink", "make_sink"]
