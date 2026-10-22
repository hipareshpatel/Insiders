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


def _local_ocr() -> bool:
    from .ocr import available
    return available()


def _env_share(name: str, default: float) -> float:
    try:
        return min(1.0, max(0.0, float(_env(name, str(default)))))
    except ValueError:
        return default


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
    # Where filings are discovered: "nse" (owner, 2026-10-18: online-only, NSE only) or "bse" (kept as a backup,
    # off the daily path). NSE needs the universe file built by `sync-universe` to map its rows onto our companies.
    discovery_source: str = field(default_factory=lambda: (_env("DISCOVERY_SOURCE", "nse") or "nse").lower())
    # Companies analysed: market cap at least this (₹ Cr; owner, 2026-10-19: ₹500 Cr, was 100), or unknown, or on the
    # watchlist. 0 = all.
    universe_min_mcap_cr: float = field(default_factory=lambda: float(_env("UNIVERSE_MIN_MCAP_CR", "500")))
    # A company in the universe leaves only below this (owner, 22 Oct 2026: "go ahead with both universe changes"), so
    # one near the floor does not drop out and back day to day. Unset: 80% of the floor (₹400 Cr at ₹500 Cr); 0 = none.
    universe_exit_mcap_cr: float = field(default_factory=lambda: float(
        _env("UNIVERSE_EXIT_MCAP_CR", "") or 0.8 * float(_env("UNIVERSE_MIN_MCAP_CR", "500"))))
    platform_url: str | None = field(default_factory=lambda: _env("PLATFORM_API_URL"))
    ingest_token: str | None = field(default_factory=lambda: _env("INGEST_TOKEN"))

    backfill_start: str = field(default_factory=lambda: _env("BACKFILL_START", "2026-04-19"))
    max_attempts: int = field(default_factory=lambda: _env_int("MAX_ATTEMPTS", 3))
    # Stop discovering backfill days once this many D1 rows were written today
    # (free tier allows 100k/day; live processing is never throttled by this).
    d1_daily_write_budget: int = field(default_factory=lambda: _env_int("D1_DAILY_WRITE_BUDGET", 80_000))
    # A card that fails the number, claim or math checks gets a second opinion from another provider.
    second_opinion: bool = field(default_factory=lambda: _env("SECOND_OPINION", "1") not in ("0", "false", "no"))
    # Human hold list (gate.load_holds): cards named there are published as "held after review".
    card_holds_file: str = "card_holds.txt"
    # Decision D20: one card per company per results quarter; later documents of that quarter are linked to it.
    one_card_per_results_quarter: bool = field(default_factory=lambda: _env("ONE_CARD_PER_RESULTS_QUARTER", "1") not in ("0", "false", "no"))
    # An annual report's own XBRL from NSE, as a table in front of its text (annual_xbrl.py). Off where NSE is
    # not reachable or another run on the same address is already calling it (NSE limits by IP).
    nse_annual_xbrl: bool = field(default_factory=lambda: _env("NSE_ANNUAL_XBRL", "1") not in ("0", "false", "no"))
    # Where scripts/laptop.ps1 logs each command; annual_catchup.py waits while another run is writing there.
    log_dir: Path = field(default_factory=lambda: Path(_env("LOG_DIR", str(_REPO_DIR / "data" / "logs"))))
    # Pages OCR'd per document. 20 with RapidOCR, which runs on the CPU with no quota (about 5 s a page);
    # 6 when only the vision route can read them, since every page there is a free-tier request.
    # The exact JSON answers of BSE and NSE, saved before parsing (raw.py, docs/DATA_QUALITY.md).
    save_raw: bool = field(default_factory=lambda: _env("SAVE_RAW", "1") not in ("0", "false", "no"))
    # Each card's raw model reply, in the object store under evidence/ (R2 online, no D1 row; pipeline._save_evidence).
    save_evidence: bool = field(default_factory=lambda: _env("SAVE_EVIDENCE", "1") not in ("0", "false", "no"))
    max_ocr_pages: int = field(default_factory=lambda: _env_int("MAX_OCR_PAGES", 20 if _local_ocr() else 6))
    pass2_char_budget: int = field(default_factory=lambda: _env_int("PASS2_CHAR_BUDGET", 40_000))
    workers: int = field(default_factory=lambda: _env_int("PIPELINE_WORKERS", 3))
    # Pass 2 packed: this many filings in one request on the `pass2_packed` route (Gemini; ai/packer.py). 0 = off.
    pass2_pack: int = field(default_factory=lambda: _env_int("PASS2_PACK", 0))
    # Seconds a filing waits for others to fill its pack. 20 s gave 1.25 filings a call on round 5's companies
    # (2026-10-19): filings reach pass 2 one by one, and Gemini's free tier counts calls, not filings.
    pass2_pack_wait_s: int = field(default_factory=lambda: _env_int("PASS2_PACK_WAIT", 20))
    # The same for backfill filings, which no reader is waiting for: longer, so packs fill (owner, 22 Oct: "go ahead"; a
    # 60 s wait gave 2 filings a pack on 22 Oct 05:33 IST). Unset = the live wait.
    pass2_pack_wait_bulk_s: int = field(default_factory=lambda: _env_int("PASS2_PACK_WAIT_BULK",
                                                                         _env_int("PASS2_PACK_WAIT", 20)))
    # Long filings (pass2_long) packed with other long ones, at most this many a request when packing is on. 1 = off.
    pass2_pack_long: int = field(default_factory=lambda: _env_int("PASS2_PACK_LONG", 3))
    # The shadow meaning critic (critic.py): live published cards judged point by point on spare free quota after they
    # are committed; verdicts stored, never acted on. CRITIC=0 off; at most CRITIC_MAX cards and CRITIC_MAX_S seconds a run.
    critic: bool = field(default_factory=lambda: _env("CRITIC", "1") not in ("0", "false", "no"))
    critic_max: int = field(default_factory=lambda: _env_int("CRITIC_MAX", 8))
    critic_max_s: int = field(default_factory=lambda: _env_int("CRITIC_MAX_S", 180))
    # The short pass-2 prompt (prompts/pass2_short.md, deep audit B1) on this share of live filings, chosen by news id
    # so a re-run gets the same one; card_json.grounding.prompt_variant says which wrote a card, for the daily audit.
    prompt_short_share: float = field(default_factory=lambda: _env_share("PROMPT_SHORT_SHARE", 0.3))

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
