"""BSE client for api.bseindia.com, ported from the reference repository Pareshking/NSE-BSE-Insider-Tracker
(`collectors/bse/client.py` at d2a929e, and `ixbrl_facts` from `collectors/bse/parsers.py`). Owner, 25 Oct 2026: port
the request mechanics, headers and response parsing as written. Off the primary NSE path: nothing in the pipeline calls
it; it is for a backup runner and for checks by hand.

Kept exactly: the endpoints and their parameters, the headers (User-Agent, Accept, Accept-Language, Origin, Referer,
Connection, Sec-Fetch-Site), the session, the 4-6 s pace, 3 retries on network errors and 5xx, the stop on 401/403/429,
404 as Missing for a filing's file, the raw copy before any parsing, and the JSON (`Table`, `Table1` ROWCNT) and inline
XBRL parsing.

Left out, on purpose: the reference's fallback that, once BSE refuses a plain request, calls the API from inside a
bseindia.com page in headless Chrome started with automation detection switched off. That is a way round BSE's refusal,
which this project does not do (CLAUDE.md: "Don't work around BSE's firewall"). Here a refusal is a refusal: it raises
Blocked with the HTTP status, logged.

Measured 25 Oct 2026 (this session, a US machine): with these headers BSE's API answered 200 for announcements (60 KB)
and bulk deals (28 KB); with only a User-Agent and Referer it answered 403 "Access Denied". From the reference's notes
(12 Oct 2026): endpoints and caps as listed below.

* insider (SEBI PIT): Corp_Regulation_DownloadCSV_ng/w?scripCode=&Regulation=&fromDT=YYYYMMDD&ToDate=YYYYMMDD
  &Isdefault=2, the CSV behind the download button of BSE's insider page; filters on the date reported to BSE.
* bulk / block deals: BulkDealData_ng/w?DealType=1|2&sc_code=&FDate=DD/MM/YYYY&TDate=DD/MM/YYYY (deal date).
* SAST: Corporatesast/w?scripcode=&ddlregul=ALL&fromdate=YYYYMMDD&todate=YYYYMMDD (first acquisition date; some windows
  answer [] although a wider window holds rows for those days, so callers tile and split).
* announcements: AnnSubCategoryGetData/w?pageno=N&strCat=-1&strPrevDate=YYYYMMDD&strScrip=&strSearch=P
  &strToDate=YYYYMMDD&strType=C&subcategory=-1: 50 rows a page, newest first, Table1 ROWCNT the day's count. The
  attachment is at www.bseindia.com/xml-data/corpfiling/AttachLive/<ATTACHMENTNAME>.
* corporate actions: DefaultData/w?ddlcategorys=E&ddlindustrys=&segment=0&strSearch=S&Fdate=YYYYMMDD&TDate=YYYYMMDD
  &Purposecode=&scripcode= (ex-date).
* board meetings: boardmeeting_fno/w?securityName=&txtDate=DD/MM/YYYY&txtTodate=DD/MM/YYYY&ddlPurpose=&ddlindustry=
  &ddlsegment=C: `Table` each meeting once, `Table1` the earlier dates of moved meetings.
* shareholding pattern: Corp_Shareholding_ng/w?scripcode=&flag=&indtype= (`flag`: 1 today, 2 a week, 3 15 days,
  4 a month, 5 3 months, 6 a year); each row links its filing as inline XBRL (`ixbrl_facts`).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import random
import re
import time
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, TypeVar

import requests

from ..file_cap import files

log = logging.getLogger(__name__)

API = 'https://api.bseindia.com/BseIndiaAPI/api/'
HOME = 'https://www.bseindia.com/'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/153.0.0.0 Safari/537.36')
HEADERS = {'User-Agent': UA, 'Accept': 'application/json, text/plain, */*', 'Accept-Language': 'en-US,en;q=0.5',
           'Origin': 'https://www.bseindia.com', 'Referer': HOME, 'Connection': 'keep-alive',
           'Sec-Fetch-Site': 'same-site'}
PACE_SECONDS = (4.0, 6.0)
RETRIES = 3
STOP_STATUSES = (401, 403, 429)
INSIDER_CSV_HEAD = 'Security Code,Security Name,Name of Person'


class Blocked(RuntimeError):
    """BSE refused us (401/403/429) or sent something that is not data. Stop."""


class Failed(RuntimeError):
    """Still failing after the retries (network error or 5xx)."""


class Missing(Failed):
    """A filing's file answered 404: that file only, not a refusal."""


class RawStore(Protocol):
    """Where every answer is kept byte for byte before it is read (the reference's insiders_clean.raw_store.RawStore)."""

    def put(self, source: str, dataset: str, body: bytes, **meta: Any) -> Any: ...


def ymd(d: date) -> str:
    return d.strftime('%Y%m%d')


def dmy(d: date) -> str:
    return d.strftime('%d/%m/%Y')


class BSEClient:
    def __init__(self, session: requests.Session | None = None, sleep: Callable[[float], None] = time.sleep,
                 rng: random.Random | None = None, pace: tuple[float, float] = PACE_SECONDS,
                 raw: RawStore | None = None):
        self.raw = raw  # a RawStore, or None (dry run)
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)
        self.sleep, self.rng, self.pace = sleep, rng or random.Random(), pace
        self.via = 'requests'
        self.calls = 0

    def _wait(self) -> None:
        if self.calls:
            self.sleep(self.rng.uniform(*self.pace))
        self.calls += 1

    def _fetch(self, url: str, params: dict) -> tuple[int, str, bytes]:
        r = self.session.get(url, params=params, timeout=45)
        return r.status_code, r.headers.get('Content-Type', ''), r.content

    def get(self, path: str, params: dict, dataset: str, covers: dict | None = None) -> bytes:
        return self.fetch_url(API + path, params, dataset, covers)

    def fetch_url(self, url: str, params: dict, dataset: str, covers: dict | None = None,
                  file: bool = False) -> bytes:
        """`file`: one filing's file (a 404 is Missing, not a refusal), kept
        gzip-compressed in the raw store (no timestamp, so the same file is one
        blob), with the SHA-256 of the bytes as sent. A file counts once toward the run's file cap (file_cap.py, F213; past it
        FileCapReached): list and JSON calls do not."""
        if file:
            files.take(url)
        last = None
        for _ in range(RETRIES + 1):
            self._wait()
            try:
                status, ctype, body = self._fetch(url, params)
            except requests.RequestException as e:
                last = f'{type(e).__name__}: {e}'
                log.warning('BSE %s: %s; retrying', dataset, last)
                continue
            if status in STOP_STATUSES:
                log.error('BSE %s: HTTP %s from %s; stopping (a refusal is not worked round)', dataset, status, url)
                raise Blocked(f'HTTP {status} from {url} ({self.via})')
            if status == 0 or status >= 500:
                last = f'HTTP {status} from {url} ({self.via})'
                log.warning('BSE %s: %s; retrying', dataset, last)
                continue
            if status == 404 and file:
                raise Missing(f'HTTP 404 from {url}')
            if status != 200:
                log.error('BSE %s: HTTP %s from %s', dataset, status, url)
                raise Blocked(f'HTTP {status} from {url} ({self.via})')
            if self.raw is not None:
                stored, kw = body, {}
                if file:
                    stored = gzip.compress(body, 9, mtime=0)
                    kw = {'params': dict(params or {}, stored_as='gzip', sha256_as_sent=hashlib.sha256(body).hexdigest()),
                          'content_type': 'application/gzip'}
                try:  # exact bytes first, before any parsing
                    self.raw.put('bse', dataset, stored, url=url, status=status,
                                 **({'params': params, 'content_type': ctype or None} | kw),
                                 covers=dict(covers or {}, via=self.via))
                except Exception as e:  # noqa: BLE001 -- never continue without the raw copy
                    raise Failed(f'raw store write failed: {type(e).__name__}: {e}') from e
            return body
        log.error('BSE %s: %s (after %d retries)', dataset, last, RETRIES)
        raise Failed(f'{last} (after {RETRIES} retries)')

    # --- endpoints -----------------------------------------------------------------

    def insider_csv(self, a: date, b: date) -> bytes:
        body = self.get('Corp_Regulation_DownloadCSV_ng/w',
                        {'scripCode': '', 'Regulation': '', 'fromDT': ymd(a), 'ToDate': ymd(b), 'Isdefault': '2'},
                        'insider_csv', {'from': a.isoformat(), 'to': b.isoformat()})
        head = body.decode('utf-8-sig', errors='replace').lstrip()[:200]
        if not head.startswith(INSIDER_CSV_HEAD):
            raise Blocked(f'not the insider CSV ({body[:60]!r})')
        return body

    def _payload(self, path: str, params: dict, dataset: str, covers: dict | None) -> Any:
        body = self.get(path, params, dataset, covers)
        try:
            return json.loads(body.decode('utf-8', errors='replace'))
        except ValueError:
            raise Blocked(f'not JSON from {path} ({body[:60]!r})') from None

    def _json(self, path: str, params: dict, dataset: str, covers: dict | None) -> list[dict]:
        payload = self._payload(path, params, dataset, covers)
        rows = payload.get('Table') if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise Blocked(f'JSON without a row list from {path}')
        return rows

    def deals(self, kind: str, a: date, b: date) -> list[dict]:
        deal_type = {'bulk': '1', 'block': '2'}[kind]
        return self._json('BulkDealData_ng/w', {'DealType': deal_type, 'sc_code': '', 'FDate': dmy(a), 'TDate': dmy(b)},
                          f'{kind}_deals_history', {'from': a.isoformat(), 'to': b.isoformat()})

    def sast(self, a: date, b: date) -> list[dict]:
        return self._json('Corporatesast/w', {'scripcode': '', 'ddlregul': 'ALL', 'fromdate': ymd(a), 'todate': ymd(b)},
                          'sast', {'from': a.isoformat(), 'to': b.isoformat()})

    def actions(self, a: date, b: date) -> list[dict]:
        return self._json('DefaultData/w', {'ddlcategorys': 'E', 'ddlindustrys': '', 'segment': '0', 'strSearch': 'S',
                                            'Fdate': ymd(a), 'TDate': ymd(b), 'Purposecode': '', 'scripcode': ''},
                          'corporate_actions', {'from': a.isoformat(), 'to': b.isoformat()})

    def announcements(self, day: date, page: int) -> tuple[list[dict], int | None]:
        """One page (50 rows, newest first) of the filings BSE disseminated on `day`, and BSE's count for the
        day (Table1 ROWCNT). Reference, 13 Oct 2026: 12 Oct = 1,136 rows in 23 pages, no row on two pages."""
        body = self.get('AnnSubCategoryGetData/w', {'pageno': page, 'strCat': '-1', 'strPrevDate': ymd(day),
                                                    'strScrip': '', 'strSearch': 'P', 'strToDate': ymd(day),
                                                    'strType': 'C', 'subcategory': '-1'},
                        'announcements', {'day': day.isoformat(), 'page': page})
        try:
            payload = json.loads(body.decode('utf-8', errors='replace'))
        except ValueError:
            raise Blocked(f'not JSON from AnnSubCategoryGetData ({body[:60]!r})') from None
        rows = payload.get('Table') if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise Blocked('JSON without a row list from AnnSubCategoryGetData')
        total = (payload.get('Table1') or [{}])[0].get('ROWCNT')
        return rows, int(total) if isinstance(total, (int, float)) else None

    def board_meetings(self, a: date, b: date) -> dict:
        """{'Table': meetings in [a, b] by meeting date, 'Table1': moved-from dates}."""
        payload = self._payload('boardmeeting_fno/w', {'securityName': '', 'txtDate': dmy(a), 'txtTodate': dmy(b),
                                                       'ddlPurpose': '', 'ddlindustry': '', 'ddlsegment': 'C'},
                                'board_meetings', {'from': a.isoformat(), 'to': b.isoformat()})
        if not isinstance(payload, dict) or not isinstance(payload.get('Table'), list):
            raise Blocked('board meetings: JSON without a Table list')
        return {'Table': payload['Table'], 'Table1': payload.get('Table1') or []}

    def shareholding_filings(self, flag: int) -> list[dict]:
        return self._json('Corp_Shareholding_ng/w', {'scripcode': '', 'flag': str(flag), 'indtype': ''},
                          'shareholding_filings', {'flag': flag})

    def shareholding_xbrl(self, url: str, covers: dict | None = None) -> bytes:
        """One filing's inline XBRL, as sent (raw copy gzip-compressed)."""
        if url.startswith('/'):
            url = HOME.rstrip('/') + url
        return self.fetch_url(url, {}, 'shareholding_xbrl', covers, file=True)

    def close(self) -> None:
        self.session.close()


T = TypeVar('T')


def safely(call: Callable[[], T], what: str) -> T | None:
    """Run one BSE call for a batch runner: a refusal or a failure is logged with its reason and gives None, so the
    batch goes on (a Blocked should still stop further calls in the same run: the caller checks for None)."""
    try:
        return call()
    except (Blocked, Failed) as exc:
        log.error('BSE %s: %s: %s', what, type(exc).__name__, exc)
        return None


# --- inline XBRL (reference collectors/bse/parsers.py) -------------------------------------------------------------

_IX_FACT = re.compile(r'<ix:(nonFraction|nonNumeric)\b([^>]*?)(?:/>|>(.*?)</ix:\1>)', re.S)
_IX_ATTR = re.compile(r"""([\w:]+)\s*=\s*(?:'([^']*)'|"([^"]*)")""")
_IX_CONTEXT = re.compile(r"""<xbrli:context\b[^>]*?\bid\s*=\s*['"]([^'"]+)['"]""")


def ixbrl_facts(text: str) -> str:
    """BSE's inline-XBRL shareholding pattern -> one plain fact a line, as in
    the XBRL NSE serves (`<in-bse-shp:Tag contextRef="ctx">value</...>`), plus
    each context id. Numbers are the stored value: the figure shown times
    10^scale (BSE shows 94.04 with scale -2 where NSE's XML holds 0.9404),
    negative with sign='-', commas dropped."""
    out = [f'<xbrli:context id="{c}"/>' for c in _IX_CONTEXT.findall(text)]
    for kind, attrs, body in _IX_FACT.findall(text):
        a = {k: v1 or v2 for k, v1, v2 in _IX_ATTR.findall(attrs)}
        name, ctx = a.get('name', ''), a.get('contextRef', '')
        if not name.startswith('in-bse-shp:') or not ctx:
            continue
        v = re.sub(r'<[^>]+>', '', body or '').strip()
        if kind == 'nonFraction' and v:
            try:
                d = Decimal(v.replace(',', '')).scaleb(int(a.get('scale') or 0))
            except (InvalidOperation, ValueError):
                continue
            d = -d if a.get('sign') == '-' else d
            v = str(int(d)) if d == d.to_integral() else format(d.normalize(), 'f')
        out.append(f'<{name} contextRef="{ctx}">{v}</{name}>')
    return '\n'.join(out)
