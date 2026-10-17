// Shared SQL, imported verbatim from ../db so the Worker and the Python
// pipeline's LocalSink execute exactly the same statements.
import cardsReaction from "../../db/statements/cards_reaction.sql?raw";
import cardsUpsert from "../../db/statements/cards_upsert.sql?raw";
import catalystsUpsert from "../../db/statements/catalysts_upsert.sql?raw";
import companiesSeen from "../../db/statements/companies_seen.sql?raw";
import companiesUpsert from "../../db/statements/companies_upsert.sql?raw";
import filingsDiscover from "../../db/statements/filings_discover.sql?raw";
import filingsImport from "../../db/statements/filings_import.sql?raw";
import filingsUpdate from "../../db/statements/filings_update.sql?raw";
import kvSet from "../../db/statements/kv_set.sql?raw";
import runsUpsert from "../../db/statements/runs_upsert.sql?raw";
import usageAdd from "../../db/statements/usage_add.sql?raw";
import companiesForMarket from "../../db/queries/companies_for_market.sql?raw";
import companiesForMarketAll from "../../db/queries/companies_for_market_all.sql?raw";
import companiesOutsideUniverse from "../../db/queries/companies_outside_universe.sql?raw";
import companyGet from "../../db/queries/company_get.sql?raw";
import backfillCompanies from "../../db/queries/backfill_companies.sql?raw";
import filingsPending from "../../db/queries/filings_pending.sql?raw";
import filingsKnownDay from "../../db/queries/filings_known_day.sql?raw";
import filingsPendingCompany from "../../db/queries/filings_pending_company.sql?raw";
import filingsRecentCompany from "../../db/queries/filings_recent_company.sql?raw";
import cardHeld from "../../db/queries/card_held.sql?raw";
import filingsRemaining from "../../db/queries/filings_remaining.sql?raw";
import exportCards from "../../db/queries/export_cards.sql?raw";
import exportCompanies from "../../db/queries/export_companies.sql?raw";
import exportCatalysts from "../../db/queries/export_catalysts.sql?raw";
import exportFilings from "../../db/queries/export_filings.sql?raw";
import exportKv from "../../db/queries/export_kv.sql?raw";
import snapshotFeed from "../../db/queries/snapshot_feed.sql?raw";
import snapshotSignals from "../../db/queries/snapshot_signals.sql?raw";
import snapshotCount from "../../db/queries/snapshot_count.sql?raw";
import feedbackExamples from "../../db/queries/feedback_examples.sql?raw";
import cardsAwaitingReaction from "../../db/queries/cards_awaiting_reaction.sql?raw";
import reactionSummary from "../../db/queries/reaction_summary.sql?raw";
import kvGet from "../../db/queries/kv_get.sql?raw";
import peerCards from "../../db/queries/peer_cards.sql?raw";
import usageForDay from "../../db/queries/usage_for_day.sql?raw";
import usageForMonth from "../../db/queries/usage_for_month.sql?raw";

/** Write statements; each takes one bound parameter: a JSON array of rows. */
export const STATEMENTS: Record<string, string> = {
  filings_discover: filingsDiscover,
  filings_import: filingsImport,
  filings_update: filingsUpdate,
  cards_upsert: cardsUpsert,
  cards_reaction: cardsReaction,
  companies_upsert: companiesUpsert,
  companies_seen: companiesSeen,
  catalysts_upsert: catalystsUpsert,
  runs_upsert: runsUpsert,
  usage_add: usageAdd,
  kv_set: kvSet,
};

/** Read queries with positional parameters. */
export const QUERIES: Record<string, string> = {
  filings_pending: filingsPending,
  filings_pending_company: filingsPendingCompany,
  filings_recent_company: filingsRecentCompany,
  card_held: cardHeld,
  filings_remaining: filingsRemaining,
  filings_known_day: filingsKnownDay,
  backfill_companies: backfillCompanies,
  usage_for_day: usageForDay,
  usage_for_month: usageForMonth,
  kv_get: kvGet,
  cards_awaiting_reaction: cardsAwaitingReaction,
  reaction_summary: reactionSummary,
  company_get: companyGet,
  peer_cards: peerCards,
  companies_for_market: companiesForMarket,
  companies_outside_universe: companiesOutsideUniverse,
  companies_for_market_all: companiesForMarketAll,
  export_cards: exportCards,
  export_companies: exportCompanies,
  export_catalysts: exportCatalysts,
  export_filings: exportFilings,
  export_kv: exportKv,
  snapshot_feed: snapshotFeed,
  snapshot_signals: snapshotSignals,
  snapshot_count: snapshotCount,
  feedback_examples: feedbackExamples,
};

