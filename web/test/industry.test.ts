// The line under a company's name, from its stored NSE classification (shared/industry.ts). Run: npm test.
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { industryLine, industryParts } from "../shared/industry.ts";

test("three steps: the second and the narrowest (real stored paths)", () => {
  assert.equal(industryLine("Healthcare > Pharmaceuticals & Biotechnology > Pharmaceuticals"), "Pharmaceuticals & Biotechnology › Pharmaceuticals");
  assert.equal(industryLine("Financial Services > Banks > Private Sector Bank"), "Banks › Private Sector Bank");
  assert.equal(industryLine("Consumer Discretionary > Realty > Residential, Commercial Projects"), "Realty › Residential, Commercial Projects");
  assert.equal(industryLine("Services > Transport Services > Logistics Solution Provider"), "Transport Services › Logistics Solution Provider");
});

test("four steps: the second and the fourth, not the third", () => {
  assert.equal(industryLine("Energy > Oil, Gas & Consumable Fuels > Petroleum Products > Refineries & Marketing"), "Oil, Gas & Consumable Fuels › Refineries & Marketing");
  assert.equal(industryLine("Consumer Discretionary > Media, Entertainment & Publication > Entertainment > TV Broadcasting & Software Production"),
    "Media, Entertainment & Publication › TV Broadcasting & Software Production");   // Zee: not 'IT services'
  assert.equal(industryLine("Fast Moving Consumer Goods > Agricultural Food & other Products > Tea & Coffee"), "Agricultural Food & other Products › Tea & Coffee");
});

test("one or two steps show what there is, none is null", () => {
  assert.equal(industryLine("Diversified"), "Diversified");
  assert.equal(industryLine("Financial Services > Finance"), "Financial Services › Finance");
  for (const none of [null, undefined, "", "   ", " > ", ">"]) assert.equal(industryLine(none), null, String(none));
});

test("spacing around the arrows does not matter", () => {
  assert.deepEqual(industryParts("A>B >  C"), ["A", "B", "C"]);
  assert.equal(industryLine("Healthcare>Healthcare Services>Hospital"), "Healthcare Services › Hospital");
});
