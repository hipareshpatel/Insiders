import { Fragment } from "react";

import type { Fact } from "../../shared/types";

/** Renders the model's **bold** markers as <strong>; everything else stays plain text (no HTML).
 *  A fact arrives as {text, quote}: the quote is the filing's own words, shown on hover. */
export function RichText({ text, strongClass = "font-semibold text-ink" }: { text: string | Fact; strongClass?: string }) {
  const value = typeof text === "string" ? text : text.text;
  const quote = typeof text === "string" ? null : text.quote;
  const parts = value.split(/\*\*(.+?)\*\*/g);
  const body = (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? <strong key={i} className={strongClass}>{part}</strong> : <Fragment key={i}>{part.replace(/\*\*/g, "")}</Fragment>,
      )}
    </>
  );
  return quote ? <span title={quote}>{body}</span> : body;
}

/** Plain text with the bold markers removed (headlines, exports, titles). */
export function plain(text: string | Fact): string {
  return (typeof text === "string" ? text : text.text).replace(/\*\*/g, "");
}

