import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

/** A company-page panel: the title with a short note beside it (`sub`), a control or note on the right (`hint`). */
export function Panel({ title, children, hint, sub, className }: { title: string; children: ReactNode; hint?: ReactNode; sub?: ReactNode; className?: string }) {
  return (
    <section className={cn("card-soft rise-in min-w-0", className)}>
      <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 px-5 pt-4">
        <h2 className="text-[16px] font-extrabold leading-tight tracking-tight text-ink">
          {title}{sub ? <small className="ml-1.5 text-[12.5px] font-semibold text-ink-3">{sub}</small> : null}
        </h2>
        {hint ? <span className="text-xs text-ink-3">{hint}</span> : null}
      </header>
      <div className="px-5 pb-5 pt-3">{children}</div>
    </section>
  );
}
