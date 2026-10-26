// The card's "say each thing once" rules (src/lib/cardText.ts). Run: npm test (node --test, types stripped).
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { changeTone, executionFact, figures, repeats, showsFigure, statesEps } from "../src/lib/cardText.ts";

test("a point that restates the headline is a repeat", () => {
  // the owner's Punjab & Sind Bank card: headline and first point were the same figure
  assert.ok(repeats("Interest earned Q1FY27: **₹3,213.37 Cr**.", "Punjab & Sind Bank Q1FY27: interest earned ₹3,213.37 Cr"));
  assert.ok(repeats("Rating revised to CARE A- (Negative) from CARE A (Stable) on ₹1,800 Cr facilities",
    "CARE cuts Demo Finance to A- (Negative) on ₹1,800 Cr facilities"));
});

test("a point that adds a counterparty, a place or a new figure is kept", () => {
  const headline = "Demo Infra arm wins ₹228 Cr wind EPC LOI, near three-quarters of Q1 sales";
  assert.ok(!repeats("Subsidiary Demo Wind EPC received an LOI from Demo Renewables LLP for a ₹228 Cr turnkey contract", headline));
  assert.ok(!repeats("Covers an 80 MW wind project at Satara, Maharashtra", headline));
  assert.ok(!repeats("Stage 3 assets at 4.9%", "CARE cuts Demo Finance to A- (Negative) on ₹1,800 Cr facilities"));
});

test("periods and years are not figures; rounding is allowed", () => {
  assert.deepEqual(figures("Q2FY27 revenue ₹456 Cr in FY 2026-27, up 19.6% in 2026"), [456, 19.6]);
  assert.ok(repeats("Revenue ₹455.6 Cr, up 19.6% YoY", "Demo Cement Q2 revenue up 19.6% YoY to ₹455.6 Cr"));
  assert.ok(!repeats("Exports ₹141 Cr, up 35%", "Revenue ₹318 Cr, up 19%"));
});

test("empty and figure-free text is never a repeat by figures alone", () => {
  assert.ok(!repeats("", "anything"));
  assert.ok(!repeats("No volume given", ""));
});

test("a figure is shown only as a whole number", () => {
  assert.ok(showsFigure("GNPA at 2.1% this quarter", "2.1%"));
  assert.ok(!showsFigure("margin 12.1%", "2.1%"));
  assert.ok(!showsFigure("₹2,104 Cr", "2.1"));
  assert.ok(showsFigure("interest earned ₹3,213.37 Cr", "₹3,213.37 Cr"));
  assert.ok(showsFigure("D/E 0.53x", "0.53x"));
  assert.ok(!showsFigure("anything", ""));
  assert.ok(showsFigure("a (b) c", "(b") && !showsFigure("a b) c", "(b"));   // regex characters are escaped, not run
});

test("one event per company and day in the calendar", async () => {
  const { dedupeEvents } = await import("../shared/events.ts");
  const e = (scrip_code: string, event_date: string, event_type: string) => ({ scrip_code, event_date, event_type });
  const got = dedupeEvents([
    e("1", "2026-10-24", "RIGHTS_OPEN"), e("1", "2026-10-24", "MILESTONE"), e("1", "2026-10-24", "OTHER"),
    e("1", "2026-10-24", "RIGHTS_OPEN"),                    // the same event from a second filing
    e("1", "2026-10-25", "MILESTONE"),                      // alone on its day: kept
    e("2", "2026-10-24", "OTHER"),                          // another company: kept
    e("1", "2026-10-24", "RECORD_DATE"),                    // a different named event the same day: kept
    e("3", "2026-10-26", "OTHER"), e("3", "2026-10-26", "MILESTONE"),   // UCO's strike, two generic types: one
  ]);
  assert.deepEqual(got.map((x) => `${x.scrip_code} ${x.event_date} ${x.event_type}`), [
    "1 2026-10-24 RIGHTS_OPEN", "1 2026-10-25 MILESTONE", "2 2026-10-24 OTHER", "1 2026-10-24 RECORD_DATE",
    "3 2026-10-26 OTHER"]);
});

test("an execution term reads as a term, a date as a date", () => {
  assert.deepEqual(executionFact("05 years"), ["Term", "5 years"]);
  assert.deepEqual(executionFact("within 36 months"), ["Term", "36 months"]);
  assert.deepEqual(executionFact("for a period of five years"), ["Complete by", "for a period of five years"]); // words kept as written
  assert.deepEqual(executionFact("30 June 2027"), ["Complete by", "30 June 2027"]);
  assert.deepEqual(executionFact("2.5 Years"), ["Term", "2.5 years"]);
});

test("price chart: range, filings on their trading day, move", async () => {
  const { placeFilings, rangeMove, sliceRange } = await import("../src/lib/chart.ts");
  const series = { d: ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"], c: [100, 101, 99, 103, 110] };
  assert.deepEqual(sliceRange(series, "1M"), series);                     // shorter than the range: all of it
  const long = { d: Array.from({ length: 300 }, (_, i) => `d${String(i).padStart(3, "0")}`), c: Array.from({ length: 300 }, (_, i) => i + 1) };
  assert.equal(sliceRange(long, "1Y").d.length, 250);
  assert.equal(sliceRange(long, "1M").c[0], 280);
  const placed = placeFilings(series, [
    { filed_at: "2026-10-13T18:20:00+05:30", id: "a" },   // trading day itself
    { filed_at: "2026-10-11T10:00:00+05:30", id: "b" },   // before the range: left out
    { filed_at: "2026-10-14T09:00:00+05:30", id: "c" },
    { filed_at: "2026-10-14T19:00:00+05:30", id: "d" },   // same day: shares the point
    { filed_at: "2026-10-17T10:00:00+05:30", id: "e" },   // after the last close: left out
  ]);
  assert.deepEqual(placed.map((p) => [p.index, p.items.map((x) => x.id)]), [[1, ["a"]], [2, ["c", "d"]]]);
  assert.equal(Math.round(rangeMove(series)!), 10);
  assert.equal(rangeMove({ d: ["x"], c: [0] }), null);
  assert.deepEqual(placeFilings({ d: [], c: [] }, [{ filed_at: "2026-10-13" }]), []);
});

test("a fact is on the verified face only with a quote from the filing and no unfound figure", async () => {
  const { verifiedFact } = await import("../src/lib/cardText.ts");
  assert.equal(verifiedFact({ text: "Order worth ₹29.13 Cr from Northern Railway", quote: "LOA worth Rs. 29.13 crore" }), true);
  assert.equal(verifiedFact({ text: "Order worth ₹29.13 Cr", quote: null }), false);           // no quote: the AI's reading
  assert.equal(verifiedFact("Isuzu exits as a promoter"), false);                                // a bare string: no quote
  assert.equal(verifiedFact({ text: "An ₹800 Cr NCD issue", quote: "NCDs" }, ["800"]), false);  // a figure the checks did not find
  assert.equal(verifiedFact({ text: "Revenue ₹1,800 Cr", quote: "Revenue 1,800" }, ["800"]), true); // "800" is not 1,800
});

test("a point with two figures of the headline or a block is a repeat, however it is worded", () => {
  const heritage = "Heritage Foods Q2 revenue up 19% YoY to ₹1,320 Cr; EBITDA margin recovers 98 bps QoQ to 5.6%";
  assert.ok(repeats("Sales rose to ₹1,320 Cr in the September quarter, a 19% gain on last year", heritage));
  assert.ok(!repeats("Exports ₹141 Cr, 19% of sales", heritage));                       // one figure shared: it adds one
  assert.ok(!repeats("Stage 3 approval covers 2 new kilns at Satara", "Demo Cement gets Stage 3 nod for 2 units"));   // counts are not figures
  // the table's values join the headline: UCO's point restated operating profit and provisions
  assert.ok(repeats("Operating profit ₹1,511 Cr and provisions ₹402 Cr", "UCO Bank Q2FY27 net profit ₹807.67 Cr 1511.2 402.1 807.67"));
});

test("a figure keeps no sign or unit when it is looked for", () => {
  assert.ok(showsFigure("EPS 0.63 vs 0.49", "₹0.63 per share"));
  assert.ok(showsFigure("net NPA down 26 bps", "-26 bps"));
  assert.ok(showsFigure("NNPA fell 26 bp", "−26 bp"));
  assert.ok(showsFigure("order book 3.1x sales", "3.1 x"));
  assert.ok(showsFigure("up 12% YoY", "+12%"));
  assert.ok(!showsFigure("up 12.5%", "+12%"));
});

test("tiles and the Scale line leave out what the headline says", async () => {
  const { restatesHeadline, tilesBesides } = await import("../src/lib/cardText.ts");
  const headline = "HDFC Life Q2 VNB ₹2,037 Cr, up 12%";
  const tiles = [{ label: "VNB", value: "₹2,037 Cr" }, { label: "VNB margin", value: "24.7%" }, { label: "APE", value: "₹8,107 Cr" }];
  assert.deepEqual(tilesBesides(tiles, headline).map((t) => t.label), ["VNB margin", "APE"]);
  assert.ok(restatesHeadline("Deal is 35% of net worth (₹2,400 Cr)", "Jubilant buys a stake for 35% of its net worth"));
  assert.ok(!restatesHeadline("18% of FY26 revenue (₹1,239 Cr)", "Demo Infra arm wins ₹228 Cr wind EPC LOI"));
  assert.ok(!restatesHeadline("2 orders in Q1", "Demo wins 2 orders"));              // a count is not the amount
});

test("more from the filing is the verified rest, never a face point or an unquoted fact", async () => {
  const { splitFacts } = await import("../src/lib/cardText.ts");
  const q = (text: string) => ({ text, quote: text });
  const facts = [q("A ₹10 Cr"), "B unquoted", q("C ₹20 Cr"), q("D ₹30 Cr"), { text: "E ₹40 Cr", quote: null }, q("F ₹50 Cr")];
  const got = splitFacts(facts, [], 2);
  assert.deepEqual(got.face.map((f) => (typeof f === "string" ? f : f.text)), ["A ₹10 Cr", "C ₹20 Cr"]);
  assert.deepEqual(got.more.map((f) => (typeof f === "string" ? f : f.text)), ["D ₹30 Cr", "F ₹50 Cr"]);
  assert.deepEqual(got.unverified.map((f) => (typeof f === "string" ? f : f.text)), ["B unquoted", "E ₹40 Cr"]);
  assert.deepEqual(splitFacts([q("G ₹800 Cr")], ["800"], 3).unverified.length, 1);   // an unfound figure: the AI's reading
});

test("deal and rating labels say only what the filing says", async () => {
  const { ratedAmount, realValue, saysExGst } = await import("../src/lib/cardText.ts");
  assert.equal(realValue("Investors (to be determined via private placement)"), null);   // Jubilant's placeholder
  assert.equal(realValue("N/A"), null);
  assert.equal(realValue(""), null);
  assert.equal(realValue("Not disclosed"), null);
  assert.equal(realValue("National Highways Authority of India"), "National Highways Authority of India");
  assert.ok(saysExGst("LOA worth Rs. 228 crore (excluding GST)"));
  assert.ok(saysExGst("contract value of ₹29.13 Cr plus applicable GST"));
  assert.ok(saysExGst("₹29.13 Cr + GST"));
  assert.ok(!saysExGst("worth ₹228 Cr inclusive of GST"));
  assert.ok(!saysExGst("worth ₹228 Cr"));
  assert.equal(ratedAmount("CARE cuts Demo Finance to A- (Negative) on ₹1,800 Cr facilities"), "₹1,800 Cr facilities");
  assert.equal(ratedAmount("Jubilant Pharmova gets ICRA AA+ (Stable) for ₹1,400 Cr NCDs"), "₹1,400 Cr NCDs");
  assert.equal(ratedAmount("ICRA reaffirms AA+", "Rated ₹500 crore bank loan facilities"), "₹500 Cr bank facilities");
  assert.equal(ratedAmount("Revenue ₹1,320 Cr; rating AA"), null);                       // an amount that is not the rated one
});

test("results table: turns, lower-is-better lines and filler rows", async () => {
  const { allZero, lowerIsBetter, turnOf } = await import("../src/lib/results.ts");
  assert.equal(turnOf({ value: 12, prev_year: -4 }), "LOSS_TO_PROFIT");
  assert.equal(turnOf({ value: -2, prev_quarter: 5, prev_year: -9 }, "qoq"), "PROFIT_TO_LOSS");
  assert.equal(turnOf({ value: -2, prev_year: -9 }, "yoy"), "LOSS_NARROWED");
  assert.equal(turnOf({ value: 3, qoq_turn: "LOSS_TO_PROFIT" }, "qoq"), "LOSS_TO_PROFIT");
  assert.equal(turnOf({ value: 3, prev_year: 2 }), undefined);
  for (const [key, label] of [["nnpa_pct", "Net NPA"], ["gnpa_pct", "Gross NPA"], ["provisions", "Provisions"], ["combined_ratio", "Combined ratio"],
    ["claims_ratio", "Claims ratio"], ["incurred_claims", "Claims"], ["kpi:cost_to_income", "Cost to income"]]) assert.ok(lowerIsBetter(key, label), key);
  for (const [key, label] of [["pat", "Net profit"], ["roa_pct", "Return on assets"], ["nii", "Net interest income"]]) assert.ok(!lowerIsBetter(key, label), key);
  assert.ok(allZero({ value: 0, prev_year: 0, prev_quarter: 0 }));
  assert.ok(!allZero({ value: 0, prev_year: 4 }));
});

test("a catalyst's line drops the exchange's preamble", async () => {
  const { catalystText } = await import("../src/lib/taxonomy.ts");
  assert.equal(catalystText("BOARD_MEETING", "Newgen Software Technologies Ltdhas informed BSE that the meeting of the Board of Directors of the Company is scheduled on 23/10/2026 ,inter alia, to consider and approve the financial results for the quarter ended September 30, 2026."),
    "Board meeting: to consider and approve the financial results for the quarter ended September 30, 2026");
  assert.equal(catalystText("BOARD_MEETING", "Capri Global Capital Ltdhas informed BSE that the meeting of the Board of Directors"), "Board meeting");
  assert.equal(catalystText("RECORD_DATE", "Record date for interim dividend of ₹25 per equity share"), "Record date for interim dividend of ₹25 per equity share");
});

test("the exchange's preamble goes even with no space before 'has'", async () => {
  const { catalystText } = await import("../src/lib/taxonomy.ts");
  assert.equal(catalystText("RECORD_DATE", "L&T Technology Services Ltdhas informed BSE that the record date is October 27, 2026"),
    "The record date is October 27, 2026");
});

test("the three analysis boxes keep housekeeping out", async () => {
  const { boxSignal, missingOnTopic, procedural } = await import("../src/lib/cardText.ts");
  assert.ok(!boxSignal("LOW_CASH_TAX") && !boxSignal("REG30_THRESHOLD") && boxSignal("SCALE") && boxSignal("GUIDANCE_BREACH"));
  // Indosolar's results card: the swap ratio belongs to the merger filing
  assert.ok(!missingOnTopic("RESULTS", "Share exchange / swap ratio for the amalgamation with Waaree Energies Limited not disclosed"));
  assert.ok(missingOnTopic("M_AND_A", "No share exchange ratio or consideration terms for the merger are stated"));
  assert.ok(missingOnTopic("RESULTS", "Segment revenue split for the quarter"));
  assert.ok(procedural("Shareholders' approval for appointment of M/s N Ritesh and Associates as cost auditor for FY2026-27"));
  assert.ok(!procedural("Shareholders' approval for appointment of a cost auditor", "GOVERNANCE"));
  assert.ok(!procedural("EBIT margin holds at or above Q2 level (>=14.8%)"));
  assert.ok(!procedural("Deployment of ₹5,940 Cr cash across subsidiaries for capex"));
});

test("an EGM's borrowing resolution is business, a dividend's AGM approval is procedure", async () => {
  const { procedural } = await import("../src/lib/cardText.ts");
  assert.ok(!procedural("EGM considered enabling resolutions for borrowing up to USD 1,250 million", "DEBT_RATINGS"));
  assert.ok(procedural("Final Dividend approval by shareholders in Annual General Meeting", "CORPORATE_ACTION"));
});

test("a key number's colour follows what the change means, not its first character (deep audit F-13)", () => {
  assert.equal(changeTone("GNPA", "-17 bps"), "pos");
  assert.equal(changeTone("Net NPA", "+0.2 pp"), "neg");
  assert.equal(changeTone("Revenue", "+12.4% YoY"), "pos");
  assert.equal(changeTone("PAT", "−8% YoY"), "neg");
  assert.equal(changeTone("PAT", "down 8% YoY"), "neg");
  assert.equal(changeTone("Finance cost", "+₹12 Cr"), "neg");
  assert.equal(changeTone("Order book", "vs ₹1,200 Cr in Q1"), null);
  assert.equal(changeTone("EBITDA margin", "flat"), null);
});

test("governance flags: exits, orders, defaults; never an appointment", async () => {
  const { governanceFlags } = await import("../src/lib/cardText.ts");
  assert.deepEqual(governanceFlags("Statutory auditor Deloitte resigns citing lack of information"), ["Auditor exit"]);
  assert.deepEqual(governanceFlags("CFO Rajesh Kumar resigned with effect from 30 Oct"), ["CFO exit"]);
  assert.deepEqual(governanceFlags("SEBI passes order debarring promoters for two years"), ["Regulator action"]);
  assert.deepEqual(governanceFlags("Company defaulted on interest on NCDs due 15 Oct"), ["Default"]);
  assert.deepEqual(governanceFlags("Board appoints M/s ABC & Co as statutory auditors for five years"), []);
  assert.deepEqual(governanceFlags("No fraud was reported by the auditors"), []);
});

test("a stored card line that states EPS is told apart from a dividend per share (owner rule 26 Oct 2026)", () => {
  for (const t of ["EPS ₹5.20", "Basic EPS of 3.1", "Earnings per share rose 12%", "profit per share ₹4", "Diluted earnings a share ₹2"]) assert.ok(statesEps(t), t);
  for (const t of ["Dividend of ₹5 per share", "Interim dividend 250% (₹2.5 a share)", "Net profit ₹46 Cr", "steps taken"]) assert.ok(!statesEps(t), t);
});

test("more ways to write EPS are caught and per-share figures that are not EPS stay (owner rule 26 Oct 2026)", () => {
  for (const t of ["E.P.S. ₹5", "earnings of ₹5 a share", "earnings/share ₹5", "PAT per share ₹3", "diluted earnings per ordinary share ₹4", "Earnings per equity share 3",
    "profit after tax per share ₹3", "PAT/share 3", "profit/share 3", "earnings ₹5 per share", "earning ₹5/share", "earnings of ₹ 5 / share",
    "earnings per ₹10 share 4", "Earnings per equity share of ₹10 each 4.5", "earnings per share ₹५.२"]) assert.ok(statesEps(t), t);
  for (const t of ["Dividend ₹5 per share", "DPS ₹5", "Book value per share ₹40", "NAV per share ₹12", "Issue price ₹10 per share", "Net profit ₹5 Cr",
    "Interim dividend 250% (₹2.5 a share)", "Final dividend of ₹५ per share"]) assert.ok(!statesEps(t), t);
});
