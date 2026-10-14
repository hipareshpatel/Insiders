import { Fragment } from "react";

/** Renders the model's **bold** markers as <strong>; everything else stays plain text (no HTML). */
export function RichText({ text, strongClass = "font-semibold text-ink" }: { text: string; strongClass?: string }) {
  const parts = text.split(/\*\*(.+?)\*\*/g);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? <strong key={i} className={strongClass}>{part}</strong> : <Fragment key={i}>{part.replace(/\*\*/g, "")}</Fragment>,
      )}
    </>
  );
}

/** Plain text with the bold markers removed (headlines, exports, titles). */
export function plain(text: string): string {
  return text.replace(/\*\*/g, "");
}
