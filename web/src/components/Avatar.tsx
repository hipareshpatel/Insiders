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
  // Large badges (cards, company pages) take two initials on a rounded square, as in the redesign; small ones a letter
  const words = name.replace(/^(the|demo)\s+/i, "").replace(/\b(ltd|limited|ltd\.)\b/gi, "").trim().split(/\s+/).filter(Boolean);
  const large = size >= 28;
  const letters = (large && words.length > 1 ? words[0][0] + words[1][0] : (words[0]?.[0] ?? key[0] ?? "?")).toUpperCase();
  return (
    <span
      aria-hidden
      className={cn("inline-grid shrink-0 place-items-center font-extrabold text-white", large ? "rounded-[30%]" : "rounded-full", className)}
      style={{ width: size, height: size, fontSize: Math.round(size * (large ? 0.34 : 0.5)), background: hue(key) }}
    >
      {letters}
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
