import { useMemo, useState } from "react";
import type { CardBody, CardRow, Dossier } from "../../../shared/types";
import { cn } from "../../lib/cn";
import { cr, istDate, todayIST } from "../../lib/format";
import { EVENT_LABELS } from "../../lib/taxonomy";
import { RichText } from "../RichText";
import { composeStory, goodAndBad, latestQuarter, trackTiles, type GoodBadItem } from "./companyText";
import { Panel } from "./Panel";

export type Parsed = { row: CardRow; card: CardBody };

/** "15 Oct", the short date of a source line. */
export const dayMonth = (iso: string) => istDate(iso).replace("Sept", "Sep").split(" ").slice(0, 2).join(" ");
/** Where a point comes from: "Q2FY27 results · 15 Oct", "M&A · 16 Oct". */
export const sourceOf = ({ row, card }: Parsed) =>
  `${card.results?.period ? `${card.results.period} results` : EVENT_LABELS[row.event_category] ?? "Filing"} · ${dayMonth(row.filed_at)}`;

/** Two or three sentences from memory: the results streak, the latest deal and the promise record, until memory
 *  writes a narrative of its own. Falls back to the business summary. */
export function StorySoFar({ dossier, parsed, count }: { dossier: Dossier | null; parsed: Parsed[]; count: number }) {
  const story = useMemo(() => dossier && composeStory({
    metrics: dossier.financial_metrics, deals: dossier.deals ?? [], guidance: dossier.guidance, money: cr,
    latest: parsed.find((p) => p.card.results)?.card.results,
  }), [dossier, parsed]);
  const updated = dossier?.updated_at ?? parsed[0]?.row.filed_at;
  const text = story ?? dossier?.business_summary?.text;
  return (
    <Panel title="The story so far" sub={count ? `from ${count} filing${count > 1 ? "s" : ""}${updated ? `, updated ${dayMonth(updated)}` : ""}` : undefined}>
      {text ? (
        <p className="m-0 rounded-2xl bg-insight px-4 py-3.5 text-[15px] leading-relaxed text-ink">
          <RichText text={text} strongClass="font-bold text-accent" />
        </p>
      ) : <p className="text-sm text-ink-3">No story yet. It is written from the first material filing analysed.</p>}
    </Panel>
  );
}

const GB_SHOWN = 3;

/** The newest positive and negative points, three of each, on green and red panels with their source. */
export function GoodAndBad({ parsed }: { parsed: Parsed[] }) {
  const { good, bad } = useMemo(() => goodAndBad(parsed.slice(0, 12).map((p) => ({ source: sourceOf(p), card: p.card }))), [parsed]);
  const [all, setAll] = useState(false);
  const more = good.length > GB_SHOWN || bad.length > GB_SHOWN;
  return (
    <Panel title="The good & the bad" sub="from recent filings">
      <div className="grid gap-3 md:grid-cols-2">
        <GoodBadBox title="The good" items={all ? good : good.slice(0, GB_SHOWN)} good />
        <GoodBadBox title="The bad" items={all ? bad : bad.slice(0, GB_SHOWN)} />
      </div>
      {more && (
        <button type="button" onClick={() => setAll(!all)} className="mt-2.5 text-[12.5px] font-bold text-accent hover:underline">
          {all ? "Show fewer" : `Show all (${good.length} good, ${bad.length} bad)`}
        </button>
      )}
    </Panel>
  );
}

function GoodBadBox({ title, items, good = false }: { title: string; items: GoodBadItem[]; good?: boolean }) {
  return (
    <div className={cn("flex flex-col gap-2 rounded-2xl px-3.5 py-3", good ? "bg-pos-soft" : "bg-neg-soft")}>
      <h3 className={cn("text-[11px] font-extrabold uppercase tracking-[0.1em]", good ? "text-pos" : "text-neg")}>{title}</h3>
      {items.length ? items.map((item, i) => (
        <p key={i} className="m-0 text-[13.5px] leading-snug text-ink">{item.text}
          <small className="mt-0.5 block text-[11.5px] text-ink-3">{item.source}</small></p>
      )) : <p className="m-0 text-[13px] text-ink-3">Nothing flagged in recent filings.</p>}
    </div>
  );
}

/** Four tiles, the newest current item of each kind; the Promise tracker lists them all. */
export function WhatToTrack({ dossier, parsed, onTracker }: { dossier: Dossier | null; parsed: Parsed[]; onTracker: () => void }) {
  const tiles = useMemo(() => trackTiles({
    watchlist: dossier?.watchlist ?? [], guidance: dossier?.guidance ?? [], today: todayIST(), date: dayMonth,
    latestQuarter: latestQuarter(dossier?.financial_metrics ?? []),
    risks: parsed.slice(0, 6).flatMap((p) => (p.card.track_next?.risks ?? []).slice(0, 1).map((text) => ({ text, source: sourceOf(p) }))),
  }), [dossier, parsed]);
  return (
    <Panel title="What to track" hint={<button type="button" onClick={onTracker} className="text-[12.5px] font-bold text-accent hover:underline">Promise tracker →</button>}>
      <div className="grid gap-2.5 sm:grid-cols-2">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-xl bg-surface-2 px-3 py-2.5">
            <b className="mb-0.5 block text-[10.5px] font-extrabold uppercase tracking-[0.07em] text-ink-3">{t.label}</b>
            {t.text ? (
              <>
                <span className="block text-[13.5px] leading-snug text-ink">{t.text}</span>
                <small className="mt-0.5 block text-[11.5px] text-ink-3">{t.sub}</small>
              </>
            ) : <span className="block text-[13px] text-ink-3">Nothing open</span>}
          </div>
        ))}
      </div>
    </Panel>
  );
}
