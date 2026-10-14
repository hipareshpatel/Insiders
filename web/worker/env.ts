export interface Env {
  DB: D1Database;
  VAULT: R2Bucket;
  AI: Ai;
  ASSETS: Fetcher;
  INGEST_TOKEN: string;
}

export type AppEnv = { Bindings: Env };
