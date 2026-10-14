import { useEffect, useState } from "react";
import { Route, Switch } from "wouter";
import { CommandPalette } from "./components/CommandPalette";
import { CompanyDrawer } from "./components/CompanyDrawer";
import { Sidebar } from "./components/Sidebar";
import { CalendarView } from "./views/CalendarView";
import { CompaniesView } from "./views/CompaniesView";
import { Empty, FeedView } from "./views/FeedView";
import { SystemView } from "./views/SystemView";

export function App() {
  const [searchOpen, setSearchOpen] = useState(false);
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

  return (
    <div className="flex min-h-dvh flex-col lg:flex-row">
      <Sidebar onSearch={() => setSearchOpen(true)} />
      <main className="min-w-0 flex-1">
        <Switch>
          <Route path="/" component={FeedView} />
          <Route path="/companies" component={CompaniesView} />
          <Route path="/calendar" component={CalendarView} />
          <Route path="/system" component={SystemView} />
          <Route>
            <div className="p-6"><Empty title="Page not found" /></div>
          </Route>
        </Switch>
      </main>
      <CompanyDrawer />
      <CommandPalette open={searchOpen} onOpenChange={setSearchOpen} />
    </div>
  );
}
