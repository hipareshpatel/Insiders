"""Telegram channel alerts for high-impact cards.

Telegram allows roughly 20 messages per minute into one channel, and results
season can produce hundreds of HIGH cards a day, so sends are paced (3 s
apart) and a run caps how many it sends; the rest stay visible on the site.
"""

from __future__ import annotations

import html
import logging
import time
from urllib.parse import quote

import httpx

log = logging.getLogger(__name__)

MIN_INTERVAL_S = 3.1
DISCLAIMER = "Summary of a public BSE filing. Not investment advice."
BADGE = {"HIGH": "🔴 HIGH IMPACT", "MODERATE": "🟠 MODERATE", "LOW": "⚪ LOW"}
SIGNAL_ICON = {"POSITIVE": "✅", "WARNING": "⚠️", "INFO": "ℹ️"}
SIGNAL_LABEL = {
    "PROMISE_DELIVERED": "Promise delivered", "GUIDANCE_BREACH": "Guidance breach", "WATCH_RESOLVED": "Follow-up",
    "DILUTION": "Dilution", "WORKING_CAPITAL_STRAIN": "Working capital strain", "METRIC_SHIFT": "Metric shift",
}


def format_message(row: dict, card: dict) -> str:
    esc = html.escape
    lines = [
        f"<b>{BADGE.get(row['impact_level'], row['impact_level'])} · {esc(card.get('category_tag', ''))}</b>",
        f"<b>{esc(row['company_name'])}</b> ({esc(row['scrip_code'])}{' · ' + esc(row['symbol']) if row.get('symbol') else ''})",
        "",
        f"<b>{esc(card['headline'])}</b>",
    ]
    if card.get("what_happened"):
        lines += ["", "<b>What happened</b>"] + [f"• {esc(b)}" for b in card["what_happened"][:4]]
    insights = [i["text"] if isinstance(i, dict) else i for i in card.get("why_it_matters", [])]
    if insights:
        lines += ["", "<b>Why it matters</b>"] + [f"• {esc(t)}" for t in insights[:3]]
    for signal in card.get("signals", [])[:3]:
        kind = signal.get("type", "")
        label = SIGNAL_LABEL.get(kind, kind.replace("_", " ").capitalize() or "Signal")
        lines.append(f"{SIGNAL_ICON.get(signal['severity'], '•')} <b>{label}:</b> {esc(signal['text'])}")
    for missing in card.get("missing_disclosures", [])[:2]:
        lines.append(f"⚠️ Missing disclosure: {esc(missing)}")
    track = card.get("track_next") or {}
    tracked = [f"⏱️ {esc(m['what'])}" + (f" ({esc(m['when'])})" if m.get("when") else "") for m in track.get("milestones", [])[:2]]
    tracked += [f"📊 Verify: {esc(k['kpi'])}" + (f" in {esc(k['check_in'])}" if k.get("check_in") else "") for k in track.get("kpis_to_verify", [])[:1]]
    tracked += [f"⚖️ Pending: {esc(a)}" for a in track.get("pending_approvals", [])[:1]]
    if tracked:
        lines += ["", "<b>Track next</b>"] + tracked
    lines += ["", f"<i>{esc(row['filed_at'][:16].replace('T', ' '))} IST · {DISCLAIMER}</i>"]
    text = "\n".join(lines)
    return text[:4000]


def buttons(row: dict, card: dict, site_url: str) -> dict:
    card_url = f"{site_url.rstrip('/')}/?card={quote(row['news_id'])}"
    share = quote(f"{row['company_name']}: {card['headline']}\n{card_url}")
    first_row = [{"text": "🌐 View on site", "url": card_url}]
    if row.get("pdf_url"):
        first_row.append({"text": "📄 PDF", "url": row["pdf_url"]})
    return {"inline_keyboard": [first_row, [{"text": "📲 Share to WhatsApp", "url": f"https://wa.me/?text={share}"}]]}


class TelegramNotifier:
    def __init__(self, token: str | None, chat_id: str | None, site_url: str, max_per_run: int = 40,
                 transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self.enabled = bool(token and chat_id)
        self._chat_id = chat_id
        self._site_url = site_url
        self._max = max_per_run
        self._sent = 0
        self._last = 0.0
        self._sleep = sleep
        self._http = httpx.Client(base_url=f"https://api.telegram.org/bot{token}", timeout=20, transport=transport) if self.enabled else None

    def send(self, row: dict, card: dict) -> bool:
        if not self.enabled or self._sent >= self._max:
            return False
        wait = MIN_INTERVAL_S - (time.monotonic() - self._last)
        if wait > 0:
            self._sleep(wait)
        payload = {
            "chat_id": self._chat_id,
            "text": format_message(row, card),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": buttons(row, card, self._site_url),
        }
        for _ in range(2):
            self._last = time.monotonic()
            try:
                resp = self._http.post("/sendMessage", json=payload)
            except httpx.HTTPError as exc:
                log.warning("Telegram send failed: %s", exc)
                return False
            if resp.status_code == 429:
                retry = resp.json().get("parameters", {}).get("retry_after", 30)
                self._sleep(min(float(retry), 60))
                continue
            if resp.is_success:
                self._sent += 1
                return True
            log.warning("Telegram rejected message (%s): %s", resp.status_code, resp.text[:200])
            return False
        return False
