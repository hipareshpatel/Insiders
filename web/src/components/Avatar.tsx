import { cn } from "../lib/cn";
import { listing } from "../lib/format";

const PALETTE = ["#2563eb", "#7c3aed", "#db2777", "#ea580c", "#059669", "#0891b2", "#4f46e5", "#ca8a04", "#dc2626", "#0d9488"];

function hue(text: string): string {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

/** Letter avatar for a company (no logos: they are third-party trademarks). */
export function Avatar({ name, symbol, size = 20, className }: { name: string; symbol?: string | null; size?: number; className?: string }) {
  const key = symbol || name;
  const letter = (key.replace(/^(the|demo)\s+/i, "").trim()[0] ?? "?").toUpperCase();
  return (
    <span
      aria-hidden
      className={cn("inline-grid shrink-0 place-items-center rounded-full font-semibold text-white", className)}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.5), background: hue(key) }}
    >
      {letter}
    </span>
  );
}

/** Company chip: avatar + ticker, like a clickable tag. */
export function TickerChip({ name, symbol, scrip, onClick }: { name: string; symbol?: string | null; scrip: string; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); onClick?.(); }}
      className="inline-flex items-center gap-1.5 rounded-md border border-line bg-surface px-1.5 py-0.5 text-xs font-semibold text-ink hover:border-accent-line hover:text-accent"
      title={`${name} · ${listing(symbol, scrip)}`}
    >
      <Avatar name={name} symbol={symbol} size={16} />
      {symbol ?? scrip}
    </button>
  );
}
