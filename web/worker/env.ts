export interface Env {
  DB: D1Database;
  VAULT: R2Bucket;
  AI: Ai;
  ASSETS: Fetcher;
  INGEST_TOKEN: string;
  OWNER_TOKEN?: string;
  SHADOW_TOKEN?: string;   // the PDF shadow job's token: read queries and meta/pdf-shadow/ only (shared/shadowToken.ts)
}

export type AppEnv = { Bindings: Env };
