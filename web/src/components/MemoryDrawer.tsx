import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, X } from "lucide-react";
import { Fragment, useEffect, type ReactNode } from "react";
import { Link, useLocation } from "wouter";
import type { CardBody, CardRow } from "../../shared/types";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { istDateTime, listing, rupees, titleCase } from "../lib/format";
import { SECTORS } from "../lib/taxonomy";
import { useQueryState } from "../lib/url";
import { Panel } from "../views/CompanyPage";
import { Empty, Loading } from "../views/FeedView";
import { Avatar } from "./Avatar";
import { parseCard } from "./FilingCard";
import { TabStrip } from "./ui/badge";

/**
 * The PDF check over any page, from `?memory=<scrip>&verify=<news_id>`: the official filing beside the card with every
 * figure marked as found in it or not, so the feed keeps its scroll position. The company's memory itself lives on the
 * company page (owner, 2026-10-21: one company view, no half-window); an older `?memory=` link without `verify` goes there.
 */
export function MemoryDrawer() {
  const [params, setParams] = useQueryState();
  const [, go] = useLocation();
  const memory = params.get("memory");
  const verify = params.get("verify");
  const scrip = verify ? memory : null;
  useEffect(() => {
    if (memory && !verify) go(`/company/${encodeURIComponent(memory)}`, { replace: true });
  }, [memory, verify, go]);
  const tab = "verify";
  const close = () => setParams({ memory: null, verify: null, mtab: null });
  return (
    <Dialog.Root open={!!scrip} onOpenChange={(open) => !open && close()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/30 data-[state=open]:animate-in" />
        <Dialog.Content
          className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[1240px] flex-col border-l border-line bg-bg shadow-2xl focus:outline-none"
          aria-describedby={undefined}>
          {scrip && <DrawerBody scrip={scrip} verify={verify} tab={tab} onTab={(t) => setParams({ mtab: t })} onClose={close} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function DrawerBody({ scrip, verify, tab, onTab, onClose }: {
  scrip: string; verify: string | null; tab: string; onTab: (t: string) => void; onClose: () => void;
}) {
  const query = useQuery({ queryKey: ["company", scrip], queryFn: () => api.company(scrip) });
  const company = query.data?.company ?? null;
  const dossier = query.data?.dossier ?? null;
  const cards = query.data?.cards ?? [];
  const name = company?.company_name ?? dossier?.company_name ?? scrip;
  const symbol = company?.symbol ?? dossier?.symbol ?? null;
  const tabs = [{ key: "verify", label: "Verify against the PDF" }];
  return (
    <>
      <header className="flex items-start gap-3 border-b border-line px-5 py-4">
        <Avatar name={name} symbol={symbol} size={32} />
        <div className="min-w-0 flex-1">
          <Dialog.Title className="font-display text-[22px] leading-tight text-ink">{symbol ?? name}</Dialog.Title>
          <p className="truncate text-[13px] text-ink-2">
            {name} · {listing(symbol, scrip)}
            {company?.sector ? ` · ${SECTORS[company.sector] ?? titleCase(company.sector)}` : ""}
            {company?.median_turnover_cr != null ? ` · 💧 ₹${company.median_turnover_cr.toFixed(2)} Cr/day` : ""}
          </p>
        </div>
        <Link href={`/company/${encodeURIComponent(symbol ?? scrip)}`} className="mt-1 inline-flex items-center gap-1 text-[12.5px] text-accent hover:underline">
          Full page <ExternalLink className="h-3.5 w-3.5" />
        </Link>
        <Dialog.Close className="grid h-8 w-8 place-items-center rounded-lg text-ink-2 hover:bg-surface-2" aria-label="Close">
          <X className="h-4 w-4" />
        </Dialog.Close>
      </header>
      <TabStrip className="px-5" items={tabs} value={tab} onChange={onTab} />
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4" onKeyDown={(e) => e.key === "Escape" && onClose()}>
        {query.isPending ? <Loading /> : query.isError ? <Empty title="Couldn't load this company" body={String(query.error)} /> : (
          <>
            {tab === "verify" && verify && <Verifier row={cards.find((c) => c.news_id === verify) ?? null} newsId={verify} />}
          </>
        )}
      </div>
    </>
  );
}

const NUMBER = /(?:₹\s?)?[-−]?\d[\d,]*(?:\.\d+)?\s?(?:%|bps|x|Cr|crore|lakh|MW|TPD|MTPA)?/g;

/** Card text with each figure marked: green when it was found in the filing, amber when not.
 * Spans wrapped in ** are bold, as on the card. */
function Marked({ text, ungrounded }: { text: string; ungrounded: Set<string> }) {
  const spans = text.split("**");
  if (spans.length > 1) {
    return <>{spans.map((s, i) => (i % 2 ? <strong key={i}><MarkedPlain text={s} ungrounded={ungrounded} /></strong>
      : <MarkedPlain key={i} text={s} ungrounded={ungrounded} />))}</>;
  }
  return <MarkedPlain text={text} ungrounded={ungrounded} />;
}

function MarkedPlain({ text, ungrounded }: { text: string; ungrounded: Set<string> }) {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(NUMBER)) {
    const raw = m[0].trim();
    if (!/\d/.test(raw) || /^\d{1,2}$/.test(raw)) continue; // bare small integers are not checked
    const at = m.index ?? 0;
    parts.push(text.slice(last, at));
    const bad = [...ungrounded].some((u) => u.includes(raw.replace(/[₹\s]/g, "")) || raw.includes(u));
    parts.push(
      <mark key={at} className={cn("rounded px-0.5", bad ? "bg-warn-soft text-warn" : "bg-pos-soft text-pos")}
        title={bad ? "Not found in the filing" : "Found in the filing"}>{m[0]}</mark>,
    );
    last = at + m[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts.map((p, i) => <Fragment key={i}>{p}</Fragment>)}</>;
}

/** Split screen: the official NSE PDF beside the card's figures and the math working. */
function Verifier({ row, newsId }: { row: CardRow | null; newsId: string }) {
  const card: CardBody | null = row ? parseCard(row) : null;
  if (!row || !card) return <Empty title="This card is not in the company's last 60 filings" body={newsId} />;
  const ungrounded = new Set(card.grounding?.ungrounded ?? []);
  const lines = [card.headline, ...(card.what_happened ?? []).map((f) => (typeof f === "string" ? f : f.text)), ...(card.why_it_matters ?? []).map((w) => w.text)];
  return (
    <div className="grid h-full gap-4 lg:grid-cols-2">
      <section className="flex min-h-[60vh] flex-col overflow-hidden rounded-xl border border-line bg-surface">
        <header className="flex items-center justify-between gap-2 border-b border-line px-3 py-2 text-[12.5px] text-ink-2">
          <span>Official filing · {istDateTime(row.filed_at)}</span>
          {row.pdf_url && (
            <a href={row.pdf_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent hover:underline">
              Open on NSE <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </header>
        {row.pdf_url ? (
          <iframe src={row.pdf_url} title="Official NSE filing" className="min-h-[60vh] w-full flex-1 bg-white" />
        ) : (
          <Empty title="No PDF attached to this filing" />
        )}
        <p className="border-t border-line px-3 py-1.5 text-[11px] text-ink-3">
          If NSE does not allow the PDF to show here, use "Open on NSE".
        </p>
      </section>
      <section className="space-y-4">
        <Panel title="The card's figures"
          hint={`${card.grounding?.checked ?? 0} figures checked · ${ungrounded.size} not found`}>
          <ul className="space-y-2 text-[14px] leading-relaxed text-ink">
            {lines.filter(Boolean).map((l, i) => (
              <li key={i} className={i === 0 ? "font-semibold" : ""}><Marked text={l} ungrounded={ungrounded} /></li>
            ))}
          </ul>
          {ungrounded.size > 0 && (
            <p className="mt-3 text-[12.5px] text-warn">Not found in the filing: {[...ungrounded].join(", ")}</p>
          )}
          {(card.grounding?.unsupported_claims ?? []).length > 0 && (
            <p className="mt-1 text-[12.5px] text-warn">Claims without support: {card.grounding!.unsupported_claims!.join("; ")}</p>
          )}
          {card.xbrl && (
            <p className="mt-2 text-[12.5px] text-ink-3">
              Results figures in memory come from the filing's XBRL file ({card.xbrl.basis?.toLowerCase() ?? "basis not stated"}, {card.xbrl.period}).
            </p>
          )}
        </Panel>
        {(card.quantified_impact ?? []).length > 0 && (
          <Panel title="Math working" hint="recomputed by code from the stated inputs">
            <div className="space-y-3">
              {(card.quantified_impact ?? []).map((q, i) => (
                <div key={i} className="rounded-lg border border-line p-3 text-[13px]">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-semibold text-ink">{q.label}</span>
                    <span className={cn("text-xs font-semibold", q.check === "VERIFIED" ? "text-pos" : q.check === "MISMATCH" ? "text-neg" : "text-ink-3")}>
                      {q.check === "VERIFIED" ? "✓ Recomputed" : q.check === "MISMATCH" ? `✗ Code got ${q.computed ?? "?"}` : "Not checked"}
                    </span>
                  </div>
                  <code className="num mt-1 block break-words text-[12px] text-ink-2">{q.formula}</code>
                  <table className="num mt-2 w-full text-[12px]">
                    <tbody>
                      {q.inputs.map((input) => (
                        <tr key={input.name} className="border-t border-line">
                          <td className="py-1 pr-2 text-ink-2">{input.name}</td>
                          <td className="py-1 pr-2 text-ink">{input.value ?? "–"} {input.unit}</td>
                          <td className={cn("py-1 text-right", input.source === "ASSUMPTION" ? "text-warn" : "text-ink-3")}>{titleCase(input.source)}</td>
                        </tr>
                      ))}
                      <tr className="border-t border-line font-semibold">
                        <td className="py-1 pr-2 text-ink">Result</td>
                        <td className="py-1 pr-2 text-ink" colSpan={2}>{q.unit === "INR_CR" && q.result != null ? `₹${q.result} Cr` : `${q.result ?? "–"} ${q.unit}`}</td>
                      </tr>
                    </tbody>
                  </table>
                  {q.check_note && <p className="mt-1 text-[12px] text-ink-3">{q.check_note}</p>}
                </div>
              ))}
            </div>
          </Panel>
        )}
        {card.priced_at_filing?.last_price !== undefined && (
          <p className="num text-[12.5px] text-ink-3">
            Price at filing ({card.priced_at_filing.price_date}): {rupees(card.priced_at_filing.last_price)}
          </p>
        )}
      </section>
    </div>
  );
}
