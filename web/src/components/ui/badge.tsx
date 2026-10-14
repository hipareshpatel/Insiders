import type { HTMLAttributes } from "react";
import { cn } from "../../lib/cn";

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
        className,
      )}
      {...props}
    />
  );
}

export function Pill({ active, className, ...props }: HTMLAttributes<HTMLButtonElement> & { active?: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={cn(
        "inline-flex h-7 items-center whitespace-nowrap rounded-full border px-3 text-xs font-medium transition-colors",
        active ? "border-forest bg-forest text-forest-ink" : "border-line bg-surface text-ink-2 hover:text-ink",
        className,
      )}
      {...props}
    />
  );
}
