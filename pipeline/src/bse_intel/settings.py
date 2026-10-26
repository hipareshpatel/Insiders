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


# D1's write allowance by plan (repository variable D1_PLAN): Workers Paid since 22 Oct 2026 (D40, bought for a month)
# includes 50M rows written a month, about 1.6M a day; "free" is the free tier's hard 100,000 a day. If the plan is
# not renewed, D1_PLAN=free keeps every job under the free cap instead of D1 refusing writes mid-run.
D1_PLANS = {"paid": (1_500_000, 1_600_000), "free": (80_000, 100_000)}   # (backfill budget, day's cap)


def d1_plan() -> tuple[int, int]:
    return D1_PLANS.get((_env("D1_PLAN", "paid") or "paid").strip().lower(), D1_PLANS["paid"])


def quote_exact_numbers() -> bool:
    """QUOTE_EXACT_NUMBERS (default off; F156): a figure of a card's claim matches the quote's figure token for token
    (grouping commas and the claim's own rounding allowed), never as the front digits of a longer one ("95" of 951.96).
    Read at the call, so a script can run the same check on and off."""
    return (_env("QUOTE_EXACT_NUMBERS", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def card_ebitda_profit_v2() -> bool:
    """CARD_EBITDA_PROFIT_V2 (default off; TODO 11, 14, 15, F151): a results card shows the company's printed EBITDA first
    and ours as "Operating EBITDA (calculated)", and one profit line only. Read at the call, so a script can run the same
    card code with the switch off and on."""
    return (_env("CARD_EBITDA_PROFIT_V2", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def memory_standalone_only() -> bool:
    """MEMORY_STANDALONE_ONLY (default off; TODO 49, F162): a quarter for which NSE lists no consolidated results file is kept
    from its standalone file (basis STANDALONE, listed in the dossier's ``standalone_only``), even when the company's other
    quarters are consolidated (Jyothy Labs after it sold its only subsidiary, ABB India before its first one). Off, such a
    quarter is dropped, as before. Read at the call."""
    return (_env("MEMORY_STANDALONE_ONLY", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def memory_restated() -> bool:
    """MEMORY_RESTATED (default off; F167, TODO 53): the memory view a card reads names a restated comparative as such
    ("restated in Q2FY27's filing, first filed X") instead of the bare "restated <date>" note. Read at the call."""
    return (_env("MEMORY_RESTATED", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def memory_screener() -> bool:
    """MEMORY_SCREENER (default off; TODO 48, F161): a memory figure labelled by="screener" (the one-time screener.in fill)
    is read like any other. Off, every reader skips it, so no card changes. Read at the call."""
    return (_env("MEMORY_SCREENER", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def card_two_parts() -> bool:
    """CARD_TWO_PARTS (default off; TODO 21, F152): a card carries a `parts` block that sorts every line into part 1,
    "From the filing (checked)", or part 2, "Our reading (AI)", by a code rule, and a part 2 line whose figure or claim
    fails the existing checks is hidden alone instead of the card being held. Read at the call."""
    return (_env("CARD_TWO_PARTS", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def card_same_definition() -> bool:
    """CARD_SAME_DEFINITION (default off; F155): a line's year-ago and previous-quarter figures are shown only when they
    are on the definition of the figure beside them. Piramal Finance's Q2FY27 release headlines profit before tax 580
    (after the associates' share) while memory's previous quarter, 344.12, is the file's, before it: the card said
    +68.5% where the release's own 443 gives +31%. Where the figure shown matches no file-tagged source and
    another source for the quarter states a different one, the changes are left off. Read at the call."""
    return (_env("CARD_SAME_DEFINITION", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def card_grounded_figures() -> bool:
    """CARD_GROUNDED_FIGURES (default off; 26 Oct 2026 live audit): three places where our own code damaged a right figure
    are refused. (1) An event-XBRL order amount that rounds to 0 Cr (the file gave it in crore, not rupees) is not put on
    the deal: DSSL's Rs 137.15 Cr order showed 0. (2) The Reg 30 template's own "withdrawal/cancellation or suspension"
    row is not a withdrawal: Omaxe's RERA approval showed CANCELLED. (3) A KPI whose figure is in MW or GW is not shown
    as crore or given a change beside a figure of another unit: Emmvee's order book showed 10,404 cr, +104,990.9% QoQ.
    Read at the call."""
    return (_env("CARD_GROUNDED_FIGURES", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def card_consolidated_only() -> bool:
    """CARD_CONSOLIDATED_ONLY (default off; TODO 44, F154; owner, 25 Oct 2026: consolidated first, standalone kept from the
    AI): the figure blocks the model sees name their basis and carry no standalone figures for a consolidated filer, the
    pass-2 prompt says to state consolidated figures only, and a standalone figure the model writes on a consolidated card
    is taken out. Turned on together with CARD_EBITDA_PROFIT_V2 for the release check. Read at the call."""
    return (_env("CARD_CONSOLIDATED_ONLY", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def eps_share_adjust() -> bool:
    """EPS_SHARE_ADJUST (default off; F153, TODO 43): an EPS change on a card is worked out on today's share count (the older
    period's EPS divided by the split, bonus or consolidation factor between the two periods), or left out where the share
    count changed and no record says why. Off: cards compare EPS as the file states it. Read at the call."""
    return (_env("EPS_SHARE_ADJUST", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    return int(value) if value is not None else default


def _cards_from() -> str | None:
    value = (_env("BACKFILL_CARDS_FROM", "off") or "").strip()
    return None if value.lower() in ("off", "none", "0", "") else value


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
    # Backfill filings before this day go into memory only, with no card (F117): a slimmer AI reading of the memory
    # delta, the deal and what to track. Off by default (owner, 24 Oct 2026: "let current flow remains"): every backfill
    # filing gets its card as before; a date in the repository variable BACKFILL_CARDS_FROM switches it on.
    backfill_cards_from: str | None = field(default_factory=lambda: _cards_from())
    # Stop discovering backfill days once this many D1 rows were written today
    # (Workers Paid since 22 Oct 2026: 50M a month included, about 1.6M a day; live processing is never throttled).
    d1_daily_write_budget: int = field(default_factory=lambda: _env_int("D1_DAILY_WRITE_BUDGET", d1_plan()[0]))
    # A card that fails the number, claim or math checks gets a second opinion from another provider.
    second_opinion: bool = field(default_factory=lambda: _env("SECOND_OPINION", "1") not in ("0", "false", "no"))
    # Human hold list (gate.load_holds): cards named there are published as "held after review".
    card_holds_file: str = "card_holds.txt"
    # Decision D20: one card per company per results quarter; later documents of that quarter are linked to it.
    # results cards get cost shares, margins in bps, tax rate, cash conversion and balance-sheet moves computed in code
    # (facts.py, owner 24 Oct 2026). On since the on/off over 25 stored cards (105 right, 5 wrong, all 5 fixed) and the
    # owner's go; RESULTS_FACTS=0 turns it off
    results_facts: bool = field(default_factory=lambda: _env("RESULTS_FACTS", "1") not in ("0", "false", "no"))
    # results cards keep the model's quoted facts, memory points with their ids, notable changes and core catalyst
    # beside code's figures (results_card.build, owner 24 Oct 2026: sample card approved, then switched on for the
    # sampling re-run); RESULTS_RICH=0 turns it off
    results_rich: bool = field(default_factory=lambda: _env("RESULTS_RICH", "1") not in ("0", "false", "no"))
    one_card_per_results_quarter: bool = field(default_factory=lambda: _env("ONE_CARD_PER_RESULTS_QUARTER", "1") not in ("0", "false", "no"))
    # A results file whose lines fail SEBI's own sums has those lines left off the card (xbrl.untrusted_lines, item 23,
    # F140); XBRL_SUMS=0 turns it off
    xbrl_sums: bool = field(default_factory=lambda: _env("XBRL_SUMS", "1") not in ("0", "false", "no"))
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
    # Seconds of AI time one filing's card writing (pass 2: every model tried, repairs, retries) may take before the
    # filing waits for the next run with no attempt spent (owner, 25 Oct 2026; TODO 35). Run 40192588628: single filings
    # spent 480-1,062 s walking slow spare models, each holding a worker. 0 = no cap. The packed call is not under it.
    pass2_cap_s: int = field(default_factory=lambda: _env_int("PASS2_CAP_S", 360))
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
    # Off since 24 Oct 2026 (owner, D41): 9% precision and 12% recall against the blind reviewers on a 600-character
    # excerpt, for up to CRITIC_MAX_S of every run and spare quota; CRITIC=1 runs it, until it is rebuilt to read the
    # whole filing.
    critic: bool = field(default_factory=lambda: _env("CRITIC", "0") not in ("0", "false", "no"))
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
