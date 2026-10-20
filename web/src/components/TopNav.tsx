import { Menu, Monitor, Moon, Search, Sun, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation } from "wouter";
import { cn } from "../lib/cn";

const NAV = [
  { href: "/", label: "Today" },
  { href: "/signals", label: "Signals" },
  { href: "/feed", label: "All filings" },
  { href: "/results", label: "Results" },
  { href: "/companies", label: "Companies" },
  { href: "/calendar", label: "Calendar" },
  { href: "/system", label: "System" },
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

function useTheme() {
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

export function Logo() {
  return (
    <Link href="/" className="flex shrink-0 items-center gap-[9px] text-[18px] font-extrabold tracking-[-0.02em] text-ink">
      {/* the approved mockup's tile: indigo gradient, white "In" (docs/design/home-premium.html) */}
      <i className="grid h-[30px] w-[30px] place-items-center rounded-[9px] bg-linear-135 from-accent to-accent-2 text-[13px] font-extrabold not-italic text-white shadow-[0_4px_12px_color-mix(in_srgb,var(--accent)_35%,transparent)]">In</i>
      Insiders
    </Link>
  );
}

export function TopNav({ onSearch }: { onSearch: () => void }) {
  const [location] = useLocation();
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useTheme();
  const next: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };
  const ThemeIcon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;
  useEffect(() => setOpen(false), [location]);
  const isActive = (href: string) => (href === "/" ? location === "/" : location.startsWith(href) || (href === "/companies" && location.startsWith("/company/")));

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/[.88] backdrop-blur-[14px] backdrop-saturate-[1.4]">
      <div className="mx-auto flex h-[62px] max-w-[1240px] items-center gap-5 px-4">
        <Logo />
        <nav className="hidden items-center gap-1 md:flex">
          {NAV.map((item) => (
            <Link key={item.href} href={item.href}
              className={cn("whitespace-nowrap rounded-[10px] px-2 py-2 text-sm font-semibold transition-colors lg:px-3",
                isActive(item.href) ? "bg-surface-2 text-ink" : "text-ink-2 hover:text-ink")}>
              {item.label}
            </Link>
          ))}
        </nav>
        <button type="button" onClick={onSearch}
          className="ml-auto hidden h-10 min-w-0 flex-[0_1_340px] items-center gap-2.5 rounded-xl bg-surface-2 px-3.5 text-[13.5px] text-ink-3 hover:text-ink-2 lg:flex">
          <Search className="h-4 w-4 shrink-0" /><span className="truncate">Search company, symbol or event</span>
          <kbd className="num ml-auto rounded-md border border-line-strong px-1.5 text-[11px] font-semibold">Ctrl K</kbd>
        </button>
        <div className="ml-auto flex items-center gap-2 lg:ml-0">
          <button type="button" onClick={onSearch} aria-label="Search" className="grid h-10 w-10 place-items-center rounded-xl bg-surface-2 text-ink-2 lg:hidden">
            <Search className="h-[18px] w-[18px]" />
          </button>
          <button type="button" onClick={() => setTheme(next[theme])} aria-label={`Theme: ${theme}`} title={`Theme: ${theme}`}
            className="grid h-9 w-9 place-items-center rounded-lg border border-line text-ink-2 hover:text-ink">
            <ThemeIcon className="h-4 w-4" />
          </button>
          <button type="button" onClick={() => setOpen((v) => !v)} aria-label="Menu" aria-expanded={open}
            className="grid h-9 w-9 place-items-center rounded-lg text-ink-2 hover:bg-surface-2 md:hidden">
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>
      {open && (
        <nav className="border-t border-line px-4 py-2 md:hidden">
          {NAV.map((item) => (
            <Link key={item.href} href={item.href}
              className={cn("block rounded-[10px] px-3 py-2 text-sm font-semibold", isActive(item.href) ? "bg-surface-2 text-ink" : "text-ink-2")}>
              {item.label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}
