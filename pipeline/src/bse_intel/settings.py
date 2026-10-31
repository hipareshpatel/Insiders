"""Runtime settings, read from environment variables.

Everything secret (API keys, tokens) comes from the environment so the same
code runs on a self-hosted runner, a GitHub-hosted runner, or a laptop.
"""

from __future__ import annotations

import os
import tomllib
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent
_PIPELINE_DIR = _PKG_DIR.parents[1]
_REPO_DIR = _PIPELINE_DIR.parent


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


_TRUE = ("1", "true", "yes", "on")


@cache
def _switch_file(path: str) -> dict:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh).get("on", {})
    except FileNotFoundError:
        return {}


def _repo_vars() -> dict:
    """The repository variables a workflow passes as REPO_VARS (``toJSON(vars)``); {} outside a workflow."""
    import json

    try:
        found = json.loads(_env("REPO_VARS", "{}") or "{}")
    except ValueError:
        return {}
    return found if isinstance(found, dict) else {}


def _switch(name: str, default: bool = False) -> bool:
    """A card or memory switch, the same in every job (owner, 27 Oct 2026: "one list for every job"): an environment
    variable a workflow step sets, else the repository variable of that name (REPO_VARS), else config/switches.toml,
    else the switch's code default (off for all but MEMORY_STANDALONE_ONLY). Read at the call, so a script can run the same code with the switch off and on."""
    value = _env(name)
    if value is None:
        value = str(_repo_vars().get(name, "") or "") or None
    if value is None:
        value = _switch_file(switch_file()).get(name, default)
        return value is True or str(value).strip().lower() in _TRUE   # a written "0" or false is off
    return value.strip().lower() in _TRUE


def switch_file() -> str:
    """config/switches.toml, or BSE_INTEL_SWITCHES ("off": no file, every switch at its code default; the unit tests)."""
    path = _env("BSE_INTEL_SWITCHES")
    if path:
        return path
    return str(Path(_env("BSE_INTEL_CONFIG_DIR", str(_PIPELINE_DIR / "config"))) / "switches.toml")


def switches_on() -> list[str]:
    """The switches config/switches.toml turns on."""
    return sorted(k for k, v in _switch_file(switch_file()).items() if v is True or str(v).strip().lower() in _TRUE)


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
    """QUOTE_EXACT_NUMBERS (on in config/switches.toml; F156): a figure of a card's claim matches the quote's figure token for token
    (grouping commas and the claim's own rounding allowed), never as the front digits of a longer one ("95" of 951.96).
    Read at the call, so a script can run the same check on and off."""
    return _switch("QUOTE_EXACT_NUMBERS")


def card_ebitda_profit_v2() -> bool:
    """CARD_EBITDA_PROFIT_V2 (default off; TODO 11, 14, 15, F151): a results card shows the company's printed EBITDA first
    and ours as "Operating EBITDA (calculated)", and one profit line only. Read at the call, so a script can run the same
    card code with the switch off and on."""
    return _switch("CARD_EBITDA_PROFIT_V2")


def memory_standalone_only() -> bool:
    """MEMORY_STANDALONE_ONLY (default ON since the owner's Yes, 27 Oct 2026, TODO 99; 0 turns it off; TODO 49, F162): a quarter for which NSE lists no consolidated results file is kept
    from its standalone file (basis STANDALONE, listed in the dossier's ``standalone_only``), even when the company's other
    quarters are consolidated (Jyothy Labs after it sold its only subsidiary, ABB India before its first one). Off, such a
    quarter is dropped, as before. Read at the call."""
    return _switch("MEMORY_STANDALONE_ONLY", default=True)


def bse_fill_pre_nse() -> bool:
    """BSE_FILL_PRE_NSE (default off; TODO 108, F214): the BSE gap fill (F201) also fills, for a company NSE does list, the
    quarters strictly older than its first NSE results row. Off, a company NSE lists any row for is left alone. Read at
    the call."""
    return _switch("BSE_FILL_PRE_NSE")


def slip_check_numfirst() -> bool:
    """SLIP_CHECK_NUMFIRST (default off; owner 29 Oct 2026, step 1): the unit-slip check (slip_check.PdfCheck) asks the
    numbers-first reader first; where it has no answer the text-layer reader decides, as before. Read at the call."""
    return _switch("SLIP_CHECK_NUMFIRST")


def numfirst_stop_early() -> bool:
    """NUMFIRST_STOP_EARLY (on since 30 Oct 2026, owner; switches.toml): the numbers-first reader stops OCR-reading the scanned pages whose text
    layer named no usable table once every basis the filing needs has a statement (revenue or total income, PBT and PAT named) on
    a trusted page, its lines solved by the table's arithmetic. Out of sample (62 PDFs, 500 figures): 178 of 547 such page reads
    skipped, about 28% of the reader's time, and the same 243 right / 11 wrong / 246 none (0 changed). Read at the call."""
    return _switch("NUMFIRST_STOP_EARLY")


def slip_check_reader_options() -> bool:
    """SLIP_CHECK_READER_OPTIONS (default off; lead, 30 Oct 2026): the unit-slip check's text-layer reader (the fallback after
    numbers-first) runs with the F215 options on (``pdf_reader_options``: PDF_DATES_2DIGIT, PDF_PAGE_RANK, PDF_ROW_FIXES), as the
    bench scored it: hard key 156 right / 0 wrong on, 65 / 10 off; out of sample, numbers-first then this fallback 267 right /
    12 wrong of 500 on, 262 / 12 off. Read at the call."""
    return _switch("SLIP_CHECK_READER_OPTIONS")


def slip_check_numfirst_seconds() -> float:
    """SLIP_CHECK_NUMFIRST_SECONDS (default 60): the wall-clock cap on the numbers-first read of one filing in the unit-slip check.
    A scan can cost 16 pages of OCR and 220 cell re-reads under the one OCR lock, so past the cap the reader gives no answer
    and the text-layer reader decides. Read at the call."""
    try:
        return max(0.0, float(_env("SLIP_CHECK_NUMFIRST_SECONDS", "60")))
    except ValueError:
        return 60.0


def card_yoy_restated() -> bool:
    """CARD_YOY_RESTATED (on in config/switches.toml; TODO 104, F202): a results card's YoY is worked against the restated year-ago figure
    where memory holds one (read from a later filing's PDF text layer, restated_pdf.py) and says "vs restated". The history
    keeps the original. Read at the call."""
    return _switch("CARD_YOY_RESTATED")


def memory_restated() -> bool:
    """MEMORY_RESTATED (default off; F167, TODO 53): the memory view a card reads names a restated comparative as such
    ("restated in Q2FY27's filing, first filed X") instead of the bare "restated <date>" note. Read at the call."""
    return _switch("MEMORY_RESTATED")


def memory_screener() -> bool:
    """MEMORY_SCREENER (default off; TODO 48, F161): a memory figure labelled by="screener" (the one-time screener.in fill)
    is read like any other. Off, every reader skips it, so no card changes. Read at the call."""
    return _switch("MEMORY_SCREENER")


def card_two_parts() -> bool:
    """CARD_TWO_PARTS (default off; TODO 21, F152): a card carries a `parts` block that sorts every line into part 1,
    "From the filing (checked)", or part 2, "Our reading (AI)", by a code rule, and a part 2 line whose figure or claim
    fails the existing checks is hidden alone instead of the card being held. Read at the call."""
    return _switch("CARD_TWO_PARTS")


def card_same_definition() -> bool:
    """CARD_SAME_DEFINITION (on in config/switches.toml; F155): a line's year-ago and previous-quarter figures are shown only when they
    are on the definition of the figure beside them. Piramal Finance's Q2FY27 release headlines profit before tax 580
    (after the associates' share) while memory's previous quarter, 344.12, is the file's, before it: the card said
    +68.5% where the release's own 443 gives +31%. Where the figure shown matches no file-tagged source and
    another source for the quarter states a different one, the changes are left off. Read at the call."""
    return _switch("CARD_SAME_DEFINITION")


def memory_year_check() -> bool:
    """MEMORY_YEAR_CHECK (default off; F177, TODO 64-65): a read-time hold, nothing stored is changed. (A) A flow line's year
    or year-to-date figure (FY, 9M, H1) whose own quarters are in memory and do not add up to it beyond rounding is not used:
    not on a card, not as the input of a derived quarter (Q4 = FY - 9M), not as the base of a change. (B) A period's owners'
    profit under 5% of its profit, where the year before it was 80% or more, is held with its minorities' figure (the labels
    are swapped: Glenmark FY26, Nitco FY25). Each held figure carries a reason. Read at the call."""
    return _switch("MEMORY_YEAR_CHECK")


def card_watch_verdict() -> bool:
    """CARD_WATCH_VERDICT (on in config/switches.toml; F205, TODO 106): code decides a watch's or guidance's MET / MISSED / NOT DUE from the
    target's direction (at or below, at or above, a range), the target's period against the filing's (a later period is not
    due, no missed signal) and the figure on the target's own kind and unit (``watch_code.py``); a card sentence that says
    met when code says missed, or the reverse, is cut with a change-log note. MAHABANK's GNPA 1.25% "missed" a 1.45% ceiling;
    SAKAR's FY27 target "missed" on a Q2 card; APL Apollo's 9.63 lakh t "meets" a 10 lakh t watch; Unimech's breach on a
    target memory shows met. Read at the call."""
    return _switch("CARD_WATCH_VERDICT")


def memory_call_v2() -> bool:
    """MEMORY_CALL_V2 (default off; TODO 83, F180): every earnings-call transcript and investor deck gets a second, memory-only
    AI reading (call_memory.py) whose typed points, each with its page and exact quote, are checked by code and kept in the
    dossier's `call_memory`; and a figure a call or deck gives for a metric and period an exchange file already holds, more
    than 5% away from the file's, is not added as a source of that metric (Sobha's own "operational cash flow" +755 Cr
    beside the statutory -342 Cr; Vishal Mega Mart's operating EBITDA margin 7.7% beside the file's 12.1%). Off until the
    measured pass in docs/design/call-memory.md. Read at the call."""
    return _switch("MEMORY_CALL_V2")


def results_press_release() -> bool:
    """RESULTS_PRESS_RELEASE (default off; TODO 135, owner Yes 30 Oct 2026): a results press release or investor release filed
    beside a quarter's statement is not simply dropped as a D20 duplicate. Its text is added to the quarter's one results card
    when that card is read again (words only: management lines, one-offs, segment notes, order wins, guidance; the table stays
    the exchange file's), and call memory reads the release like a deck. Still no second card. Read at the call."""
    return _switch("RESULTS_PRESS_RELEASE")


def call_memory_geometry() -> bool:
    """CALL_MEMORY_GEOMETRY (default off; TODO 144): a call-memory point on a deck slide is kept only when the word boxes of
    its page tie its figure to the label its quote names (slide_geometry.py): same row, same column, or a list in order. A
    figure that stands by another label, or by none that can be read, is dropped with the reason "label". Needs the page's
    boxes (the PDF), so it judges only where the reader hands them to call_memory.check_points. Read at the call."""
    return _switch("CALL_MEMORY_GEOMETRY")


def card_ground_all_fields() -> bool:
    """CARD_GROUND_ALL_FIELDS (on in config/switches.toml; TODO 105, F204): the figures in the timeline entry, the core catalyst and the
    track-next lists (milestones, pending approvals, catalysts, risks, KPI targets) go through the same grounding as the
    points, and a sentence with a figure the filing and memory do not state is dropped (blind audit of 27 Oct 2026: a
    timeline's "NCDs of up to Rs 175 Cr" for 125, a risk's "dilution of 1%" for 4.9%, a target of 13.1 in no source).
    Read at the call."""
    return _switch("CARD_GROUND_ALL_FIELDS")


def card_text_support() -> bool:
    """CARD_TEXT_SUPPORT (default off, not in config/switches.toml; TODO 142, prompt audit of 30 Oct 2026): the free text the
    grounding never read (track-next risks, catalysts, milestones and approvals, the core catalyst, a change's "why", SECTOR
    and memory-less MEMORY insights) must have its names and content words in the filing, memory or scale block, and a
    whole number of 31 or less beside a noun or a day-month date must be printed there; an item with two or more words
    missing, or one such number or date, is dropped. A "net profit", "to shareholders", "discontinued" or "total
    comprehensive income" claim on a figure needs that label in its quote or on the figure's own line. The pass-2 prompt
    adds the sources-only rule. Read at the call."""
    return _switch("CARD_TEXT_SUPPORT")


def card_grounded_figures() -> bool:
    """CARD_GROUNDED_FIGURES (on in config/switches.toml; 26 Oct 2026 live audit): three places where our own code damaged a right figure
    are refused. (1) An event-XBRL order amount that rounds to 0 Cr (the file gave it in crore, not rupees) is not put on
    the deal: DSSL's Rs 137.15 Cr order showed 0. (2) The Reg 30 template's own "withdrawal/cancellation or suspension"
    row is not a withdrawal: Omaxe's RERA approval showed CANCELLED. (3) A KPI whose figure is in MW or GW is not shown
    as crore or given a change beside a figure of another unit: Emmvee's order book showed 10,404 cr, +104,990.9% QoQ.
    Read at the call."""
    return _switch("CARD_GROUNDED_FIGURES")


def card_guidance_dated() -> bool:
    """CARD_GUIDANCE_DATED (default off; F172; owner, 26 Oct 2026): a guidance verdict (delivered, on track, delayed,
    missed) is made only from a memory target that has its own date (not before the day it was said), is due for the
    period this filing reports, and is for a metric this filing prints a figure for. Castrol India's "medium term"
    EBITDA margin band and one stored as due FY26 in August 2026 were "missed" on a Q2FY27 card; Union Bank's FCNR target
    was "missed" by a filing that never mentions FCNR. Otherwise no verdict: a dated "management said X on <date>" line
    stands instead (a KPI watch item follows the same rule). Read at the call."""
    return _switch("CARD_GUIDANCE_DATED")


def card_one_basis() -> bool:
    """CARD_ONE_BASIS (on in config/switches.toml; live audit of 26 Oct 2026, class "two bases of one figure"): a card states one basis for a
    figure. A profit, or its change, whose quarter or comparison base holds a discontinued operation is labelled with it (an
    EPS change across one is taken out); a line whose quote carries the company's adjusted basis ("non-GAAP") is labelled
    with it; a results table on another basis (standalone against consolidated) than the card states is removed; a
    presentation's own EBITDA is labelled beside the table's. Read at the call."""
    return _switch("CARD_ONE_BASIS")


def card_results_one_line() -> bool:
    """CARD_RESULTS_ONE_LINE (on in config/switches.toml; TODO 107, F206; live audit of 26 Oct 2026, class "two bases in the results block"):
    each row of the results block takes its current and comparative figures from one statement line (revenue from
    operations with revenue from operations, total income with total income; an EBITDA our code works out from the
    tagged file with one worked out the same way). A comparative from another line is worked out again from the same line
    when the tagged data has it, else its change is left out. A headline or key-number revenue or EBITDA on another
    basis than the block's row is labelled "company-reported", and two EBITDA figures on one card are each named.
    Read at the call."""
    return _switch("CARD_RESULTS_ONE_LINE")


def card_consolidated_only() -> bool:
    """CARD_CONSOLIDATED_ONLY (default off; TODO 44, F154; owner, 25 Oct 2026: consolidated first, standalone kept from the
    AI): the figure blocks the model sees name their basis and carry no standalone figures for a consolidated filer, the
    pass-2 prompt says to state consolidated figures only, and a standalone figure the model writes on a consolidated card
    is taken out. Turned on together with CARD_EBITDA_PROFIT_V2 for the release check. Read at the call."""
    return _switch("CARD_CONSOLIDATED_ONLY")


def card_fact_sheet() -> bool:
    """CARD_FACT_SHEET (default off, not in config/switches.toml; owner, 30 Oct 2026, TODO 131 and 134: the A/B of results cards whose
    results figures come from memory): for a corporate filer's results filing whose quarter memory holds from the exchange file
    (dossier["statements"], screener's rules), the results table's rows are that sheet's, pass 2 is given the sheet as its only results
    figures, and a revenue / EBITDA / PBT / profit amount or change the model writes that disagrees with it is taken out of the text
    (fact_sheet.py). With no sheet, nothing changes. Read at the call."""
    return _switch("CARD_FACT_SHEET")


def results_needs_statement() -> bool:
    """RESULTS_NEEDS_STATEMENT (default off; 31 Oct 2026, TMB nse-106836238): a filing typed RESULTS whose text holds no results
    statement, no covering letter submitting results and no "financial results for the quarter/half/year" is read as OTHER
    (pipeline.lacks_results), so a note about the results (a provision, a clarification) does not take the quarter's results path.
    On only after the on/off check over stored cards (release_check.py results_statement) and a blind sample. Read at the call."""
    return _switch("RESULTS_NEEDS_STATEMENT")


def memory_file_only() -> bool:
    """MEMORY_FILE_ONLY (owner, 30 Oct 2026: "memory must be filled using exchange data and screener rules not using cards
    data"): a statement line (dossier.STATEMENT_FIGURES) enters memory only from the exchange's own file; a model's reading of
    a PDF, deck or call is kept on its card and never becomes the company's figure. Read at the call."""
    return _switch("MEMORY_FILE_ONLY")


def card_footer_plausible() -> bool:
    """CARD_FOOTER_PLAUSIBLE (on in config/switches.toml; F182, TODO 77): a footer KPI that cannot be right is not shown, and the card stores
    why (`grounding.footer_hidden`, listed on the owner's Issues page): one more than 3x the highest of the company's own
    last four periods of the same metric and kind, or a NIM outside what its type of lender can earn (home-loan lender
    1-15%, bank 1-8.5%). No low side and no margin range (independent review: a collapse is news; Power Grid's ~85% is real).
    GIC Housing Finance showed a NIM of 19.63% against its FY26 3.41% (26 Oct 2026). Read at the call."""
    return _switch("CARD_FOOTER_PLAUSIBLE")


def card_eps_follows_profit() -> bool:
    """CARD_EPS_FOLLOWS_PROFIT (on in config/switches.toml; F183, TODO 78): on a results table an EPS change that does not follow the profit
    change by more than 5 points plus share-count noise and rounding, with no split, bonus, buyback or rights issue on record,
    is not shown, nor the comparative it rests on. An EPS change below the profit change (real dilution) is shown; nothing is
    ever replaced by a figure read from the filing's words. Wipro's card (26 Oct 2026) showed EPS 3.23 against 2.74 and 2.50, +18%,
    beside profit +1%. Read at the call."""
    return _switch("CARD_EPS_FOLLOWS_PROFIT")


def eps_base_check() -> bool:
    """EPS_BASE_CHECK (on in config/switches.toml; F208, TODO 78): on a results file, an EPS YoY / QoQ that the profit does not carry (same
    test as CARD_EPS_FOLLOWS_PROFIT) with no share-count event on record is not stored as a comparable change, and a comparative
    from an earlier file with no basis recorded is not taken for a file whose basis is known. The filing's own stated EPS
    change is not read in its place (a review dropped that: "EPS declined by 5%" was read as +5%). Wipro (26 Oct 2026): EPS 3.23
    against standalone 2.74 and 2.50 stored as consolidated, +18% beside profit +1.5%. Read at the call."""
    return _switch("EPS_BASE_CHECK")


def card_eps_whole() -> bool:
    """CARD_EPS_WHOLE (default off; F188, TODO 89): on a results table the EPS line is the whole company's (continuing and
    discontinued operations together), with the continuing-operations EPS shown beside it only when the two differ; an older
    period without a whole-company figure in memory falls back to the EPS it has, and a change is left out rather than set
    across the two bases. ABB India's Q4FY26 card showed 16.14 (continuing, from a profit of ₹341.91 Cr) beside a company
    profit of ₹1,783.65 Cr, where screener says 84.17. Off: the line is the `eps` memory holds, as before. Read at the call."""
    return _switch("CARD_EPS_WHOLE")


def eps_share_adjust() -> bool:
    """EPS_SHARE_ADJUST (on in config/switches.toml; F153, TODO 43): an EPS change on a card is worked out on today's share count (the older
    period's EPS divided by the split, bonus or consolidation factor between the two periods), or left out where the share
    count changed and no record says why. Off: cards compare EPS as the file states it. Read at the call."""
    return _switch("EPS_SHARE_ADJUST")


def xbrl_filer_checks() -> bool:
    """XBRL_FILER_CHECKS (default off; TODO 109, F219): where the filer's own NSE XBRL contradicts itself, two signals in the
    file must agree before a figure is trusted. (A) owners' + minority profit against the whole profit, decided by the EPS
    share count of the file's other periods; (B) a profit the EPS and the other periods' share count contradict is held,
    not kept, even where the year-against-quarters check cannot run; (C) a lender's revenue that equals its total income
    beside an "other revenue from operations" is held. Off: the reader copies the file as before. Read at the call."""
    return _switch("XBRL_FILER_CHECKS")


def file_cap() -> int:
    """FILE_CAP (default 0 = no cap; F213): the most NSE/BSE files one run downloads, the rest waiting for the next run. The
    owner set a cap of 100 on 27 Oct 2026 and lifted it the same day ("Ignore rule of 100, continue with existing rule");
    set FILE_CAP to bring it back. Read at the call."""
    try:
        return max(0, int((_env("FILE_CAP", "0") or "0").strip()))
    except ValueError:
        return 0


def file_cap_used() -> int:
    """FILE_CAP_USED (default 0): files an earlier process of the same dispatch (the same job) already downloaded, written to
    GITHUB_ENV by file_cap.py; one dispatch is one budget, so the next process holds the cap less this. Read at the call."""
    try:
        return max(0, int((_env("FILE_CAP_USED", "0") or "0").strip()))
    except ValueError:
        return 0


def file_cap_shards() -> int:
    """FILE_CAP_SHARDS (default 1): how many shards of one run share the cap; each shard process holds FILE_CAP // shards."""
    try:
        return max(1, int((_env("FILE_CAP_SHARDS", "1") or "1").strip()))
    except ValueError:
        return 1


def eps_share_count_check() -> bool:
    """EPS_SHARE_COUNT_CHECK (on in config/switches.toml; F211, TODO 79): memory's EPS lines keep EPS as filed and EPS on today's shares, and
    adjust only when NSE's corporate-action record and the share-count change (profit over EPS) agree; a recorded action the
    share count does not follow, or a share-count jump with no record, is marked "possible split or bonus, not confirmed" and
    nothing is adjusted. Memory only: EPS is never shown on cards or stock pages. Read at the call."""
    return _switch("EPS_SHARE_COUNT_CHECK")


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
    # The row-name map (line_map.py, TODO 93, F209). The map itself is data and its refactored readers (the cross-checks'
    # row names, screener_fill's rows) behave as before, switch or not. LINE_MAP=1 is reserved for changes that would alter
    # a figure (the PDF reader taking its labels from the map, TODO 93 item 4); none is built, so it does nothing yet
    line_map: bool = field(default_factory=lambda: _env("LINE_MAP", "0") in ("1", "true", "yes"))
    # The PDF page and row matcher fixes of the hard-set root cause (F215), each off by default. PDF_DATES_2DIGIT: dates with
    # a two-digit year ("31-Mar-24", "31Mar-23") count in the results-page header (the live card path never sets it);
    # PDF_PAGE_RANK: split-line date headers and 3-metric pages pass the page gate, results pages rank above segment pages,
    # scanned PDFs are searched to PDF_SCAN_PAGE_LIMIT_ON pages; PDF_ROW_FIXES: a row with one extra non-date figure and
    # a total profit row followed by owners' / minority sub-lines are read (basis, unit and text-layer proofs unchanged)
    pdf_dates_2digit: bool = field(default_factory=lambda: _env("PDF_DATES_2DIGIT", "0") in ("1", "true", "yes"))
    pdf_page_rank: bool = field(default_factory=lambda: _env("PDF_PAGE_RANK", "0") in ("1", "true", "yes"))
    pdf_row_fixes: bool = field(default_factory=lambda: _env("PDF_ROW_FIXES", "0") in ("1", "true", "yes"))
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


# The numbers-first reader was measured with PDF_DATES_2DIGIT, PDF_PAGE_RANK and PDF_ROW_FIXES on; the live pipeline runs with
# them off for the old reader. ``pdf_reader_options()`` turns the three on inside its block for this thread only (a ContextVar:
# the pipeline's other worker threads, and the old reader there, keep the settings), 29 Oct 2026.
_PDF_READER_OPTIONS: ContextVar[bool] = ContextVar("pdf_reader_options", default=False)


def pdf_option(name: str) -> bool:
    """``pdf_dates_2digit``, ``pdf_page_rank`` or ``pdf_row_fixes``: on inside ``pdf_reader_options()``, else the setting."""
    return _PDF_READER_OPTIONS.get() or bool(getattr(get_settings(), name))


@contextmanager
def pdf_reader_options():
    token = _PDF_READER_OPTIONS.set(True)
    try:
        yield
    finally:
        _PDF_READER_OPTIONS.reset(token)
