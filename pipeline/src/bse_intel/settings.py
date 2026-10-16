"""Runtime settings, read from environment variables.

Everything secret (API keys, tokens) comes from the environment so the same
code runs on a self-hosted runner, a GitHub-hosted runner, or a laptop.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent
_PIPELINE_DIR = _PKG_DIR.parents[1]
_REPO_DIR = _PIPELINE_DIR.parent


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    return int(value) if value is not None else default


@dataclass(frozen=True)
class Settings:
    config_dir: Path = field(default_factory=lambda: Path(_env("BSE_INTEL_CONFIG_DIR", str(_PIPELINE_DIR / "config"))))
    db_dir: Path = field(default_factory=lambda: Path(_env("BSE_INTEL_DB_DIR", str(_REPO_DIR / "db"))))

    # Where results go. "platform" = the deployed Worker's internal API,
    # "local" = a SQLite file + a directory of dossiers (dry runs, development).
    sink: str = field(default_factory=lambda: _env("BSE_INTEL_SINK", "local"))
    local_dir: Path = field(default_factory=lambda: Path(_env("BSE_INTEL_LOCAL_DIR", str(_REPO_DIR / "data" / "local"))))
    # Extracted PDF text per filing (gzip JSON), so re-analysis never downloads or OCRs again.
    text_cache_dir: Path | None = field(default_factory=lambda: (None if _env("TEXT_CACHE", "1") in ("0", "off")
                                                                 else Path(_env("TEXT_CACHE_DIR", str(_REPO_DIR / "data" / "text_cache")))))
    # Daily price series per company for point-in-time footers during the history fill (laptop).
    price_dir: Path | None = field(default_factory=lambda: (None if _env("PRICE_DIR", "") in ("0", "off")
                                                            else Path(_env("PRICE_DIR", str(_REPO_DIR / "data" / "prices")))))
    # Companies analysed: market cap at least this (₹ Cr), or unknown, or on the watchlist. 0 = all.
    universe_min_mcap_cr: float = field(default_factory=lambda: float(_env("UNIVERSE_MIN_MCAP_CR", "100")))
    platform_url: str | None = field(default_factory=lambda: _env("PLATFORM_API_URL"))
    ingest_token: str | None = field(default_factory=lambda: _env("INGEST_TOKEN"))

    backfill_start: str = field(default_factory=lambda: _env("BACKFILL_START", "2025-01-01"))
    max_attempts: int = field(default_factory=lambda: _env_int("MAX_ATTEMPTS", 3))
    # Stop discovering backfill days once this many D1 rows were written today
    # (free tier allows 100k/day; live processing is never throttled by this).
    d1_daily_write_budget: int = field(default_factory=lambda: _env_int("D1_DAILY_WRITE_BUDGET", 80_000))
    # A card that fails the number, claim or math checks gets a second opinion from another provider.
    second_opinion: bool = field(default_factory=lambda: _env("SECOND_OPINION", "1") not in ("0", "false", "no"))
    # Decision D20: one card per company per results quarter; later documents of that quarter are linked to it.
    one_card_per_results_quarter: bool = field(default_factory=lambda: _env("ONE_CARD_PER_RESULTS_QUARTER", "1") not in ("0", "false", "no"))
    max_ocr_pages: int = field(default_factory=lambda: _env_int("MAX_OCR_PAGES", 6))
    pass2_char_budget: int = field(default_factory=lambda: _env_int("PASS2_CHAR_BUDGET", 40_000))
    workers: int = field(default_factory=lambda: _env_int("PIPELINE_WORKERS", 3))

    def load_toml(self, name: str) -> dict:
        return _load_toml(self.config_dir / name)

    def sql(self, kind: str, name: str) -> str:
        return (self.db_dir / kind / f"{name}.sql").read_text()


@cache
def _load_toml(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


@cache
def get_settings() -> Settings:
    return Settings()
