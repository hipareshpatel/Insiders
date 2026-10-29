// What the PDF shadow job's own token may do on the internal API (TODO 123 (10)): read cards through the read-only queries
// and read and write its own rows under meta/pdf-shadow/. No write statement, no other object, no delete, no AI, so a leaked
// shadow token cannot change a card. INGEST_TOKEN keeps every route.
export const SHADOW_PREFIX = "meta/pdf-shadow/";

export function shadowAllowed(method: string, path: string): boolean {
  const route = path.replace(/^\/api\/internal/, "");
  if (method === "POST") return /^\/query\/[\w-]+$/.test(route);
  const object = /^\/objects\/(.+)$/.exec(route);
  if (!object) return false;
  const key = object[1];
  if (!key.startsWith(SHADOW_PREFIX) || key.includes("..")) return false;
  return method === "GET" || method === "HEAD" || method === "PUT";
}
