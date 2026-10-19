import { Menu, Monitor, Moon, Search, Sun, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation } from "wouter";
import { cn } from "../lib/cn";

const NAV = [
  { href: "/", label: "Top signals" },
  { href: "/feed", label: "Live feed" },
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
    <Link href="/" className="flex items-center gap-2">
      <svg viewBox="0 0 24 24" className="h-6 w-6 text-accent" aria-hidden>
        <rect x="2" y="2" width="20" height="20" rx="6" fill="currentColor" />
        <path d="M7 15.5l3.2-3.4 2.6 2.4L17 9.5" stroke="white" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="text-[17px] font-semibold tracking-tight text-ink">
        Insiders<span className="ml-1 text-[11px] font-medium text-ink-3">NSE</span>
      </span>
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
    <header className="sticky top-0 z-30 border-b border-line bg-surface/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1200px] items-center gap-6 px-4 sm:px-6">
        <Logo />
        <nav className="hidden items-center gap-1 md:flex">
          {NAV.map((item) => (
            <Link key={item.href} href={item.href}
              className={cn("rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                isActive(item.href) ? "bg-accent-soft text-accent" : "text-ink-2 hover:text-ink")}>
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <button type="button" onClick={onSearch}
            className="hidden h-9 w-60 items-center gap-2 rounded-lg border border-line bg-surface px-3 text-[13px] text-ink-3 hover:border-line-strong sm:flex">
            <Search className="h-4 w-4 shrink-0" /><span className="truncate">Search companies</span>
            <kbd className="num ml-auto rounded border border-line px-1.5 text-[10px]">⌘K</kbd>
          </button>
          <button type="button" onClick={onSearch} aria-label="Search" className="grid h-9 w-9 place-items-center rounded-lg text-ink-2 hover:bg-surface-2 sm:hidden">
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
              className={cn("block rounded-lg px-3 py-2 text-sm font-medium", isActive(item.href) ? "bg-accent-soft text-accent" : "text-ink-2")}>
              {item.label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}
