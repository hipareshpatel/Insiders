import { cloudflare } from "@cloudflare/vite-plugin";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // Workers AI has no local emulator. Remote bindings need a Cloudflare
    // login, so they are opt-in for local dev: CF_REMOTE_BINDINGS=1 npm run dev
    // Local D1/R2 live in ../data/wrangler, next to the pipeline's text cache: the laptop backfill
    // writes there through the local Worker, the local site shows it, and sync-to-cloud reads it.
    cloudflare({ remoteBindings: process.env.CF_REMOTE_BINDINGS === "1", persistState: { path: "../data/wrangler" } }),
  ],
  server: { fs: { allow: [".."] } }, // the Worker imports shared SQL from ../db
});
