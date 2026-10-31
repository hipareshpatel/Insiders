// The Results report's rules: the summary and the group figures (shared/resultsStats.ts). Run: npm test.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { bandOf, computeGroups, isFinancial, median, membersOn, summarise, totalGrowth, type GroupCompany, type IndexMember, type StatRow, type SummaryRow } from "../shared/resultsStats.ts";
import { periodsBack } from "../shared/resultsKpi.ts";
import type { Turn } from "../shared/resultsTypes.ts";

const sr = (o: Partial<SummaryRow>): SummaryRow => ({ kind: "company", revenue: 100, revenue_yoy: 10, ebitda: 20, ebitda_yoy: 10, ebitda_turn: null, pat: 10, pat_yoy: 10,
  pat_turn: null, nfo: 0, prev_pat_yoy: 10, ...o });

test("median: the middle company, the mean of the middle two for an even count, none for no one", () => {
  assert.equal(median([3, 1, 2]), 2);
  assert.equal(median([4, 1, 2, 3]), 2.5);
  assert.equal(median([]), null);
  assert.equal(median([-5]), -5);
});

test("spread bands: exactly 20 is above, a fall is below 0, a turn beats the per cent, loss to profit and narrowed sit outside", () => {
  const b = (pat_yoy: number | null, pat_turn: Turn | null = null) => bandOf({ pat_yoy, pat_turn });
  assert.equal(b(20), "above_20");
  assert.equal(b(19.99), "from_10_to_20");
  assert.equal(b(10), "from_10_to_20");
  assert.equal(b(9.99), "from_0_to_10");
  assert.equal(b(0), "from_0_to_10");
  assert.equal(b(-0.01), "below_0");
  assert.equal(b(null, "PROFIT_TO_LOSS"), "below_0");
  assert.equal(b(null, "LOSS_WIDENED"), "below_0");
  assert.equal(b(-30, "LOSS_WIDENED"), "below_0");
  assert.equal(b(null, "LOSS_TO_PROFIT"), "loss_to_profit");
  assert.equal(b(null, "LOSS_NARROWED"), "loss_narrowed");
  assert.equal(b(null), null);
});

test("summary: up counts and their bases; EBITDA statistics are for ordinary companies only", () => {
  const rows = [
    sr({ revenue_yoy: 5, ebitda_yoy: 5, pat_yoy: 5 }),
    sr({ revenue_yoy: -5, ebitda_yoy: -5, pat_yoy: -5 }),
    sr({ pat_yoy: null, pat_turn: "LOSS_TO_PROFIT", ebitda_yoy: null, ebitda_turn: "LOSS_TO_PROFIT" }),
    sr({ kind: "bank", revenue_yoy: 30, ebitda: null, ebitda_yoy: null, pat_yoy: 40 }),
    sr({ kind: "insurer", revenue: null, revenue_yoy: null, ebitda: null, ebitda_yoy: null, pat_yoy: 15 }),
    sr({ pat_yoy: null, pat_turn: "PROFIT_TO_LOSS", ebitda_yoy: null, ebitda_turn: "PROFIT_TO_LOSS" }),
  ];
  const s = summarise(rows);
  assert.equal(s.n, 6);
  assert.deepEqual([s.revenue_up, s.revenue_of], [4, 5]);            // the insurer has no revenue and is not in the base
  assert.deepEqual([s.ebitda_up, s.ebitda_of], [2, 4]);              // 4 ordinary companies; the loss-to-profit one is up; bank and insurer out
  assert.deepEqual([s.pat_up, s.pat_of], [4, 6]);                    // 5, loss to profit, bank 40, insurer 15; the base is every company
  assert.equal(s.loss_to_profit, 1);
  assert.equal(s.loss_prev_n, 1);                                      // the base of loss to profit: a loss a year ago (profit to loss is not)
});

test("summary: a company with no year-ago quarter is reported but not in the base of X of Y", () => {
  const rows = [sr({}), sr({ revenue_yoy: -5, ebitda_yoy: -5, pat_yoy: -5 }), sr({ revenue_yoy: null, ebitda_yoy: null, pat_yoy: null }),
    sr({ pat_yoy: null, pat_turn: "LOSS_NARROWED", ebitda_yoy: null, ebitda_turn: "LOSS_NARROWED" })];
  const s = summarise(rows);
  assert.deepEqual([s.pat_up, s.pat_of, s.pat_n], [1, 3, 4]);          // the loss that narrowed has a turn and is comparable (not up)
  assert.deepEqual([s.revenue_up, s.revenue_of, s.revenue_n], [2, 3, 4]);
  assert.deepEqual([s.ebitda_up, s.ebitda_of, s.ebitda_n], [1, 3, 4]);
});

test("summary: medians use companies with a per cent; turns are left out and lenders stay out of EBITDA", () => {
  const rows = [
    sr({ pat_yoy: 10, ebitda_yoy: 1, revenue_yoy: 1 }), sr({ pat_yoy: 30, ebitda_yoy: 3, revenue_yoy: 3 }),
    sr({ pat_yoy: null, pat_turn: "LOSS_TO_PROFIT", ebitda_yoy: null, ebitda_turn: "LOSS_TO_PROFIT" }),
    sr({ kind: "nbfc", pat_yoy: 50, ebitda_yoy: 99, revenue_yoy: 5 }),
  ];
  const s = summarise(rows);
  assert.equal(s.median_pat_yoy, 30);        // 10, 30, 50
  assert.equal(s.median_ebitda_yoy, 2);      // 1 and 3 only: the turn has no per cent, the NBFC is not ordinary
  assert.equal(s.median_revenue_yoy, 4);     // all four have revenue: 1, 3, 5 and the turn's own 10
  assert.equal(summarise([]).median_pat_yoy, null);
});

test("summary: spread counts, with_pct and momentum counts", () => {
  const rows = [sr({ pat_yoy: 25, prev_pat_yoy: 20 }), sr({ pat_yoy: 20, prev_pat_yoy: 25 }), sr({ pat_yoy: 5, prev_pat_yoy: 5 }), sr({ pat_yoy: -3, prev_pat_yoy: null }),
    sr({ pat_yoy: null, pat_turn: "LOSS_TO_PROFIT", prev_pat_yoy: null }), sr({ pat_yoy: null, pat_turn: "LOSS_NARROWED" }), sr({ pat_yoy: null, pat_turn: "LOSS_WIDENED" }),
    sr({ pat_yoy: 12, prev_pat_yoy: 9 })];
  const s = summarise(rows);
  assert.deepEqual(s.spread, { below_0: 2, from_0_to_10: 1, from_10_to_20: 1, above_20: 2, loss_to_profit: 1, loss_narrowed: 1, with_pct: 6 });
  assert.deepEqual(s.momentum, { speeding_up: 2, slowing: 1, steady: 1, not_comparable: 4 });   // +5, -5, 0, then 12 against 9 is +3
});

test("summary: profit not from operations counts ordinary companies flagged only", () => {
  const s = summarise([sr({ nfo: 1 }), sr({ nfo: 1 }), sr({ nfo: 0 }), sr({ kind: "bank", nfo: 1 })]);
  assert.equal(s.nfo, 2);
});

test("total growth: only companies with both amounts, loss-makers included, null when the base is not positive", () => {
  assert.equal(totalGrowth([{ cur: 120, prev: 100 }, { cur: 10, prev: -20 }]), (130 / 80 - 1) * 100);   // a loss-maker's amounts count
  assert.ok(Math.abs(totalGrowth([{ cur: 120, prev: 100 }, { cur: 500, prev: null }, { cur: null, prev: 7 }])! - 20) < 1e-9);   // a missing base leaves the company out
  assert.equal(totalGrowth([{ cur: 5, prev: -10 }]), null);       // base total below zero
  assert.equal(totalGrowth([{ cur: 5, prev: 0 }]), null);
  assert.equal(totalGrowth([]), null);
});

test("index members are those on the day: valid_from <= day and valid_to empty or after it", () => {
  const m: IndexMember[] = [
    { index_id: "NIFTY50", isin: "A", valid_from: "1900-01-01", valid_to: null },
    { index_id: "NIFTY50", isin: "B", valid_from: "1900-01-01", valid_to: "2026-09-30" },   // left on the day itself: not a member that day
    { index_id: "NIFTY50", isin: "C", valid_from: "2026-09-30", valid_to: null },            // joined on the day: a member
    { index_id: "NIFTY50", isin: "D", valid_from: "2026-10-01", valid_to: null },
    { index_id: "NIFTY100", isin: "E", valid_from: "1900-01-01", valid_to: null },
  ];
  assert.deepEqual([...membersOn(m, "NIFTY50", "2026-09-30")].sort(), ["A", "C"]);
  assert.deepEqual([...membersOn(m, "NIFTY50", "2026-06-30")].sort(), ["A", "B"]);
});

// ---- groups ----
const stat = (scrip_code: string, period: string, o: Partial<StatRow> = {}): StatRow => ({ scrip_code, period, kind: "company", revenue: 100, revenue_prev: 80,
  revenue_yoy: 25, ebitda: 20, ebitda_prev: 16, ebitda_yoy: 25, ebitda_turn: null, pat: 10, pat_prev: 8, pat_yoy: 25, pat_turn: null, ...o });
const co = (scrip_code: string, isin: string, industry: string | null, market_cap_cr = 1000): GroupCompany => ({ scrip_code, isin, industry, market_cap_cr });
const NOW = "Q2FY27";
const mem = (index_id: string, isin: string, valid_from = "1900-01-01", valid_to: string | null = null): IndexMember => ({ index_id, isin, valid_from, valid_to });

test("groups by sector: medians, totals with a missing base, financials share, cuts", () => {
  const companies = [co("1", "I1", "Tech > Software > IT"), co("2", "I2", "Tech > Software > IT"), co("3", "I3", "Tech > Hardware > X"), co("4", "I4", "Fin > Banks > Private"), co("5", "I5", null)];
  const rows = [
    stat("1", NOW, { pat: 12, pat_prev: 10, pat_yoy: 20 }),
    stat("2", NOW, { pat: 30, pat_prev: null, pat_yoy: null, pat_turn: "LOSS_TO_PROFIT" }),   // no base: left out of the total, and of the median
    stat("3", NOW, { pat: 8, pat_prev: 10, pat_yoy: -20 }),
    stat("4", NOW, { kind: "bank", pat: 60, pat_prev: 50, pat_yoy: 20, ebitda: null, ebitda_prev: null, ebitda_yoy: null }),
    stat("5", NOW),
  ];
  const all = computeGroups({ quarter: NOW, by: "sector", cut: "all", rows, companies, members: [], withinIndex: null, withinMcap: null });
  assert.deepEqual(all.map((g) => g.id), ["Fin", "Tech"]);    // by median profit growth: 20 then (20, -20) -> 0; the unclassified one has no group
  const tech = all[1];
  assert.equal(tech.reported, 3);
  assert.equal(tech.of, null);
  assert.equal(tech.pat_median, 0);
  assert.equal(tech.pat_total_all, (20 / 20 - 1) * 100);      // companies 1 and 3: 12 + 8 against 10 + 10
  assert.equal(tech.financials_share_pct, 0);
  const fin = all[0];
  assert.equal(fin.financials_share_pct, 100);
  assert.ok(Math.abs(fin.pat_total_financials! - 20) < 1e-9);
  assert.equal(fin.pat_total_ex_financials, null);
  assert.equal(fin.ebitda_total_ex_financials, null);
  assert.deepEqual(tech.spread_pct, [50, 0, 0, 50]);          // -20 below 0; 20 above; the turn is outside
  const ex = computeGroups({ quarter: NOW, by: "sector", cut: "ex_financials", rows, companies, members: [], withinIndex: null, withinMcap: null });
  assert.deepEqual(ex.map((g) => g.id), ["Tech"]);             // the bank's group has no one left in this cut
  const fo = computeGroups({ quarter: NOW, by: "sector", cut: "financials", rows, companies, members: [], withinIndex: null, withinMcap: null });
  assert.deepEqual(fo.map((g) => g.id), ["Fin"]);
  assert.equal(fo[0].reported, 1);
});

test("groups by industry use classification steps 1 and 2; within_mcap narrows the companies first", () => {
  const companies = [co("1", "I1", "Tech > Software > IT", 100), co("2", "I2", "Tech > Software > Services", 9000), co("3", "I3", "Tech", 9000)];
  const rows = [stat("1", NOW), stat("2", NOW, { pat_yoy: 40 }), stat("3", NOW)];
  const g = computeGroups({ quarter: NOW, by: "industry", cut: "all", rows, companies, members: [], withinIndex: null, withinMcap: null });
  assert.deepEqual(g.map((x) => [x.id, x.label, x.reported]), [["Tech > Software", "Software", 2]]);   // the one-step company has no industry
  const big = computeGroups({ quarter: NOW, by: "industry", cut: "all", rows, companies, members: [], withinIndex: null, withinMcap: 5000 });
  assert.equal(big[0].reported, 1);
  assert.equal(big[0].pat_median, 40);
});

test("groups by index: reported against members matched to companies, speeding-up share, membership read on each quarter's last day", () => {
  const periods = periodsBack(NOW);
  const companies = [co("1", "I1", null), co("2", "I2", null), co("3", "I3", null)];
  // I2 joins NIFTY50 on 2026-07-01: a member on 2026-09-30 (Q2FY27) but not on 2026-06-30 (Q1FY27) or before
  const members = [mem("NIFTY50", "I1"), mem("NIFTY50", "I2", "2026-07-01"), mem("NIFTY50", "MISSING"), mem("NIFTY500", "I1"), mem("NIFTY500", "I2"), mem("NIFTY500", "I3")];
  const rows: StatRow[] = [];
  for (const p of periods) {
    rows.push(stat("1", p, { pat_yoy: 10 }), stat("2", p, { pat_yoy: 50 }), stat("3", p, { pat_yoy: 100 }));
  }
  rows.find((r) => r.scrip_code === "1" && r.period === NOW)!.pat_yoy = 15;   // 15 against 10 last quarter: speeding up
  rows.find((r) => r.scrip_code === "2" && r.period === NOW)!.pat_yoy = 40;   // 40 against 50: slowing
  const g = computeGroups({ quarter: NOW, by: "index", cut: "all", rows, companies, members, withinIndex: null, withinMcap: null });
  assert.deepEqual(g.map((x) => x.id), ["NIFTY500", "NIFTY50"]);   // NIFTY500 median 40 (15, 40, 100), NIFTY50 median 27.5; indices without members are not groups
  const n50 = g[1];
  assert.equal(n50.of, 2);            // the MISSING isin matches no company
  assert.equal(n50.reported, 2);
  assert.equal(n50.speeding_up_pct, 50);
  assert.equal(n50.pat_median, 27.5);
  assert.deepEqual(n50.trend_pat_median.slice(0, 6), [10, 10, 10, 10, 10, 10].slice(0, 6));   // I2 was not a member before: only I1 (10)
  assert.equal(n50.trend_pat_median[6], 10);                        // Q1FY27, day 2026-06-30: I2 not yet a member
  assert.equal(n50.trend_pat_median[7], 27.5);                      // Q2FY27: I1 15 and I2 40
  assert.equal(n50.trend_pat_median.length, 8);
  const inside = computeGroups({ quarter: NOW, by: "sector", cut: "all", rows, companies: companies.map((c) => ({ ...c, industry: "S > T > U" })), members, withinIndex: "NIFTY50", withinMcap: null });
  assert.equal(inside[0].reported, 2);                              // within_index narrows to members on the day
  assert.deepEqual(inside[0].trend_pat_median.slice(5), [10, 10, 27.5]);
});

test("groups: trend points are null where the group had no per cent, and a median that is null sorts last", () => {
  const companies = [co("1", "I1", "A > B > C"), co("2", "I2", "D > E > F")];
  const rows = [stat("1", NOW, { pat_yoy: null, pat_turn: "LOSS_TO_PROFIT" }), stat("2", NOW, { pat_yoy: -5 })];
  const g = computeGroups({ quarter: NOW, by: "sector", cut: "all", rows, companies, members: [], withinIndex: null, withinMcap: null });
  assert.deepEqual(g.map((x) => x.id), ["D", "A"]);
  assert.equal(g[1].pat_median, null);
  assert.ok(g[1].trend_pat_median.every((v) => v === null));
  assert.deepEqual(g[1].spread_pct, [0, 0, 0, 0]);
  assert.equal(g[1].speeding_up_pct, null);
});

test("a REIT or an InvIT counts in profit and revenue statistics but is no ordinary company for EBITDA and no financial for the cuts", () => {
  const rows = [sr({}), sr({ kind: "reit", pat_yoy: 30, ebitda_yoy: 30 }), sr({ kind: "invit", pat_yoy: 20, ebitda_yoy: 20 })];
  const s = summarise(rows);
  assert.equal(s.n, 3);
  assert.equal(s.pat_of, 3);        // every company counts in profit
  assert.equal(s.ebitda_of, 1);     // the EBITDA statistics are for ordinary companies only
  assert.equal(s.nfo, 0);
  assert.deepEqual(["company", "bank", "nbfc", "insurer", "reit", "invit"].map((k) => isFinancial(k as never)), [false, true, true, true, false, false]);
});

test("group coverage counts every member that reported, whatever the cut (R7)", () => {
  const companies = [co("1", "I1", null), co("2", "I2", null), co("3", "I3", null), co("4", "I4", null)];
  const members = ["I1", "I2", "I3", "I4"].map((i) => mem("NIFTY50", i));
  const rows = [stat("1", NOW), stat("2", NOW), stat("3", NOW, { kind: "bank" }), stat("4", NOW, { kind: "nbfc" })];
  for (const cut of ["all", "ex_financials", "financials"] as const) {
    const g = computeGroups({ quarter: NOW, by: "index", cut, rows, companies, members, withinIndex: null, withinMcap: null }).find((x) => x.id === "NIFTY50")!;
    assert.deepEqual([g.reported, g.of], [4, 4], cut);   // 4 of 4 reported, not 2 of 4 under ex-financials
  }
});

test("group momentum and the trend use only quarters on the company's basis this quarter (R8)", () => {
  const companies = [co("1", "I1", "A > B > C")];
  const rows = [stat("1", NOW, { basis: "CONSOLIDATED", pat_yoy: 30 }), stat("1", "Q1FY27", { basis: "STANDALONE", pat_yoy: 5 }), stat("1", "Q4FY26", { basis: "CONSOLIDATED", pat_yoy: 8 })];
  const g = computeGroups({ quarter: NOW, by: "sector", cut: "all", rows, companies, members: [], withinIndex: null, withinMcap: null })[0];
  assert.equal(g.speeding_up_pct, null);              // last quarter was on another basis: no pace
  assert.equal(g.trend_pat_median[6], null);          // and no trend point either
  assert.equal(g.trend_pat_median[5], 8);             // the same basis as this quarter's: kept
  const same = computeGroups({ quarter: NOW, by: "sector", cut: "all", rows: [stat("1", NOW, { basis: "CONSOLIDATED", pat_yoy: 30 }), stat("1", "Q1FY27", { basis: "CONSOLIDATED", pat_yoy: 5 })], companies, members: [], withinIndex: null, withinMcap: null })[0];
  assert.equal(same.speeding_up_pct, 100);
});

test("a bank's financing profit stays out of the EBITDA tile and median (R10)", () => {
  const s = summarise([sr({ ebitda_yoy: 10 }), sr({ kind: "bank", ebitda_yoy: 50, ebitda: 400 })]);
  assert.deepEqual([s.ebitda_n, s.ebitda_of, s.median_ebitda_yoy], [1, 1, 10]);
});

test("like for like: revenue, EBITDA and profit medians over the same ordinary companies only (#303 item A)", () => {
  const rows = [
    sr({ revenue_yoy: 20, ebitda_yoy: 22, pat_yoy: 18 }), sr({ revenue_yoy: 22, ebitda_yoy: 24, pat_yoy: 20 }),
    sr({ revenue_yoy: 24, ebitda_yoy: 23, pat_yoy: 21 }), sr({ revenue_yoy: 21, ebitda_yoy: 25, pat_yoy: 19 }),
    sr({ revenue_yoy: 23, ebitda_yoy: 21, pat_yoy: 22 }),
    sr({ kind: "bank", revenue_yoy: 5, ebitda: null, ebitda_yoy: null, pat_yoy: 60 }),   // a bank: not in the like-for-like set
    sr({ revenue_yoy: 2, ebitda_yoy: 1, pat_yoy: null, pat_turn: "LOSS_TO_PROFIT" }),     // no profit per cent: left out
  ];
  const s = summarise(rows);
  assert.deepEqual(s.like_for_like, { n: 5, revenue: 22, ebitda: 23, pat: 20 });
  assert.ok((s.median_pat_yoy ?? 0) > 20);   // the tile median, over a different set, would have read "profit faster"
  assert.equal(summarise(rows.slice(0, 3)).like_for_like, null);   // too few companies to say
});
