import { Component, type ReactNode } from "react";

/** One broken view (a bad link, an unexpected card shape) shows a message instead of a blank page. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.error(error);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="mx-auto max-w-[1200px] px-4 py-10 sm:px-6">
        <div className="rounded-xl border border-dashed border-line-strong bg-surface px-6 py-12 text-center">
          <p className="text-[15px] font-medium text-ink">Something went wrong on this page</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-ink-2">The link may be malformed. Clear the filters or go back to the feed.</p>
          <div className="mt-4 flex justify-center gap-2">
            <button type="button" onClick={() => { window.location.href = window.location.pathname; }}
              className="h-9 rounded-lg border border-line px-3 text-[13px] font-medium text-ink hover:border-accent-line hover:text-accent">
              Clear filters and reload
            </button>
            <a href="/feed" className="inline-flex h-9 items-center rounded-lg px-3 text-[13px] font-medium text-accent hover:bg-accent-soft">Live feed</a>
          </div>
        </div>
      </div>
    );
  }
}
