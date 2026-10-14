import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { Building2, FileText, Loader2, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { istDate } from "../lib/format";
import { IMPACT_STYLE } from "../lib/taxonomy";
import { useQueryState } from "../lib/url";
import { Badge } from "./ui/badge";

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [text, setText] = useState("");
  const [debounced, setDebounced] = useState("");
  const [active, setActive] = useState(0);
  const [, setParams] = useQueryState();

  useEffect(() => {
    const id = setTimeout(() => setDebounced(text.trim()), 180);
    return () => clearTimeout(id);
  }, [text]);
  useEffect(() => {
    if (!open) setText("");
  }, [open]);

  const query = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => api.search(debounced),
    enabled: debounced.length >= 2,
    staleTime: 60_000,
  });

  const items = [
    ...(query.data?.companies ?? []).map((c) => ({
      key: `c${c.scrip_code}`,
      kind: "company" as const,
      title: c.company_name,
      meta: `${c.symbol ?? ""} ${c.scrip_code}`.trim(),
      extra: c.card_count ? `${c.card_count} cards` : "",
      run: () => setParams({ company: c.scrip_code, tab: "dossier" }),
    })),
    ...(query.data?.cards ?? []).map((c) => ({
      key: `n${c.news_id}`,
      kind: "card" as const,
      title: c.headline,
      meta: `${c.company_name} · ${istDate(c.filed_at)}`,
      extra: c.impact_level,
      run: () => setParams({ card: c.news_id, noise: null }, { path: "/" }),
    })),
  ];
  useEffect(() => setActive(0), [debounced]);

  const choose = (i: number) => {
    const item = items[i];
    if (!item) return;
    onOpenChange(false);
    item.run();
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/30" />
        <Dialog.Content
          className="fixed left-1/2 top-[12vh] z-50 w-[calc(100vw-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-xl border border-line bg-surface shadow-2xl"
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
            if (e.key === "Enter") { e.preventDefault(); choose(active); }
          }}
        >
          <Dialog.Title className="sr-only">Search companies and cards</Dialog.Title>
          <Dialog.Description className="sr-only">Type a company name, symbol, scrip code or headline words.</Dialog.Description>
          <div className="flex items-center gap-2 border-b border-line px-4">
            <Search className="h-4 w-4 text-ink-3" />
            <input
              autoFocus
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Company, symbol, scrip code or headline…"
              className="h-12 flex-1 bg-transparent text-sm text-ink placeholder:text-ink-3 focus:outline-none focus-visible:outline-none"
            />
            {query.isFetching && <Loader2 className="h-4 w-4 animate-spin text-ink-3" />}
          </div>
          <ul className="max-h-[50vh] overflow-y-auto p-1.5" role="listbox">
            {debounced.length < 2 ? (
              <li className="px-3 py-6 text-center text-sm text-ink-3">Type at least two characters.</li>
            ) : items.length === 0 && !query.isFetching ? (
              <li className="px-3 py-6 text-center text-sm text-ink-3">No matches.</li>
            ) : (
              items.map((item, i) => (
                <li key={item.key} role="option" aria-selected={i === active}>
                  <button
                    type="button"
                    onMouseEnter={() => setActive(i)}
                    onClick={() => choose(i)}
                    className={cn("flex w-full items-center gap-3 rounded-md px-3 py-2 text-left", i === active && "bg-surface-2")}
                  >
                    {item.kind === "company" ? <Building2 className="h-4 w-4 shrink-0 text-forest" /> : <FileText className="h-4 w-4 shrink-0 text-ink-3" />}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-ink">{item.title}</span>
                      <span className="num block truncate text-[11px] text-ink-3">{item.meta}</span>
                    </span>
                    {item.kind === "card" && item.extra ? (
                      <Badge className={IMPACT_STYLE[item.extra as keyof typeof IMPACT_STYLE]}>{item.extra}</Badge>
                    ) : item.extra ? <span className="text-[11px] text-ink-3">{item.extra}</span> : null}
                  </button>
                </li>
              ))
            )}
          </ul>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
