import { useEffect, useRef, useState } from "react";
import { Route, Switch, useLocation } from "wouter";
import { CommandPalette } from "./components/CommandPalette";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { MemoryDrawer } from "./components/MemoryDrawer";
import { TopNav } from "./components/TopNav";
import { CalendarView } from "./views/CalendarView";
import { CompaniesView } from "./views/CompaniesView";
import { CompanyPage } from "./views/CompanyPage";
import { Empty, FeedView } from "./views/FeedView";
import { IssuesView } from "./views/IssuesView";
import { ResultsView } from "./views/ResultsView";
import { SystemView } from "./views/SystemView";
import { TodayView } from "./views/TodayView";
import { TopSignalsView } from "./views/TopSignalsView";

export function App() {
  const [searchOpen, setSearchOpen] = useState(false);
  const [location] = useLocation();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  // A new page starts at the top; query-string changes (filters, tabs) keep the scroll position,
  // and Back/Forward leave it to the browser, which restores where the reader was.
  const popped = useRef(false);
  useEffect(() => {
    const onPop = () => { popped.current = true; };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  useEffect(() => {
    if (!popped.current) window.scrollTo(0, 0);
    popped.current = false;
  }, [location]);

  return (
    <div className="flex min-h-dvh flex-col">
      <TopNav onSearch={() => setSearchOpen(true)} />
      <main className="min-w-0 flex-1">
        <ErrorBoundary key={location}>
        <Switch>
          <Route path="/" component={TodayView} />
          <Route path="/signals" component={TopSignalsView} />
          <Route path="/feed" component={FeedView} />
          <Route path="/results" component={ResultsView} />
          <Route path="/companies" component={CompaniesView} />
          <Route path="/company/:scrip" component={CompanyPage} />
          <Route path="/calendar" component={CalendarView} />
          <Route path="/system" component={SystemView} />
          <Route path="/issues" component={IssuesView} />
          <Route>
            <div className="mx-auto max-w-[1240px] px-4 py-10 sm:px-6"><Empty title="Page not found" /></div>
          </Route>
        </Switch>
        </ErrorBoundary>
      </main>
      <footer className="border-t border-line">
        <p className="mx-auto max-w-[1240px] px-4 py-5 text-xs leading-relaxed text-ink-2 sm:px-6">
          Built from NSE corporate filings and AI analysis. Information only, not investment advice; always read the original filing before acting.
        </p>
      </footer>
      <CommandPalette open={searchOpen} onOpenChange={setSearchOpen} />
      <MemoryDrawer />
    </div>
  );
}
