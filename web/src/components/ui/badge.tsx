import type { HTMLAttributes, SelectHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-md px-1.5 py-0.5 text-[11px] font-medium", className)}
      {...props}
    />
  );
}

/** Underlined tab strip, used for page-level sub-navigation. */
export function TabStrip({ items, value, onChange, className }: {
  items: { key: string; label: string; count?: number }[];
  value: string;
  onChange: (key: string) => void;
  className?: string;
}) {
  return (
    <div role="tablist" className={cn("-mx-1 flex gap-1 overflow-x-auto border-b border-line px-1", className)}>
      {items.map((item) => {
        const active = item.key === value;
        return (
          <button
            key={item.key}
            role="tab"
            type="button"
            aria-selected={active}
            onClick={() => onChange(item.key)}
            className={cn(
              "-mb-px shrink-0 whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition-colors",
              active ? "border-accent text-accent" : "border-transparent text-ink-2 hover:text-ink",
            )}
          >
            {item.label}
            {item.count != null ? <span className="num ml-1.5 text-xs text-ink-3">{item.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-9 rounded-lg border border-line bg-surface px-3 pr-8 text-[13px] text-ink hover:border-line-strong focus:border-accent focus:outline-none",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}
