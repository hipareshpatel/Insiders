import { Activity, Building2, CalendarDays, Menu, Monitor, Moon, Search, Sun, X, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation } from "wouter";
import { cn } from "../lib/cn";

const NAV = [
  { href: "/", label: "Live intelligence feed", icon: Zap },
  { href: "/companies", label: "Company memory", icon: Building2 },
  { href: "/calendar", label: "Catalyst calendar", icon: CalendarDays },
  { href: "/system", label: "System & AI monitor", icon: Activity },
];

type Theme = "system" | "light" | "dark";

function readTheme(): Theme {
  try {
    const value = localStorage.getItem("theme");
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(readTheme);
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* private mode: keep the in-memory choice */
    }
  }, [theme]);
  return [theme, setTheme] as const;
}

export function Sidebar({ onSearch }: { onSearch: () => void }) {
  const [location] = useLocation();
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useTheme();
  const nextTheme: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };
  const ThemeIcon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;
  useEffect(() => setOpen(false), [location]);

  const nav = (
    <nav className="flex flex-col gap-0.5">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? location === "/" : location.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium transition-colors",
              active ? "bg-forest text-forest-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink",
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        );
      })}
    </nav>
  );

  const brand = (
    <div className="flex items-center gap-2">
      <span className="grid h-7 w-7 place-items-center rounded-md bg-forest font-display text-sm font-extrabold text-forest-ink">B</span>
      <span className="font-display text-[15px] font-bold leading-tight text-ink">
        BSE Intelligence
        <span className="block text-[11px] font-medium text-ink-3">Filings · memory · catalysts</span>
      </span>
    </div>
  );

  const footer = (
    <div className="mt-auto space-y-2">
      <button type="button" onClick={onSearch}
        className="flex w-full items-center gap-2 rounded-md border border-line bg-surface px-2.5 py-2 text-sm text-ink-2 hover:text-ink">
        <Search className="h-4 w-4" /> Search
        <kbd className="num ml-auto rounded border border-line px-1.5 text-[10px] text-ink-3">Ctrl K</kbd>
      </button>
      <button type="button" onClick={() => setTheme(nextTheme[theme])}
        className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-sm text-ink-2 hover:bg-surface-2 hover:text-ink">
        <ThemeIcon className="h-4 w-4" /> Theme: {theme}
      </button>
      <p className="px-2.5 text-[11px] leading-snug text-ink-3">
        AI summaries of public BSE filings. Not investment advice. Verify against the original filing.
      </p>
    </div>
  );

  return (
    <>
      <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 flex-col gap-6 border-r border-line bg-surface px-3 py-4 lg:flex">
        {brand}
        {nav}
        {footer}
      </aside>
      <div className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-surface px-4 py-2.5 lg:hidden">
        {brand}
        <div className="flex gap-1">
          <button type="button" onClick={onSearch} className="rounded-md p-2 text-ink-2 hover:bg-surface-2" aria-label="Search">
            <Search className="h-5 w-5" />
          </button>
          <button type="button" onClick={() => setOpen((v) => !v)} className="rounded-md p-2 text-ink-2 hover:bg-surface-2" aria-label="Menu" aria-expanded={open}>
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>
      {open && (
        <div className="fixed inset-x-0 top-[53px] z-30 flex flex-col gap-4 border-b border-line bg-surface px-3 py-3 shadow-lg lg:hidden">
          {nav}
          {footer}
        </div>
      )}
    </>
  );
}
