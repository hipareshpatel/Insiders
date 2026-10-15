// Minimal OpenAI chat-completions facade over the Workers AI binding, so the
// pipeline's gateway can use Cloudflare's free allocation as a spare provider
// without holding a Cloudflare API token (it authenticates with INGEST_TOKEN).
import type { Context } from "hono";
import type { AppEnv } from "./env";

interface ChatRequest {
  model: string;
  messages: { role: string; content: unknown }[];
  max_tokens?: number;
  temperature?: number;
}

interface AiResult {
  // Older models reply { response: "..." }; a JSON reply may arrive already parsed as an object.
  // Newer ones (gpt-oss, Qwen 3) reply in OpenAI shape: { choices: [{ message: { content } }] }.
  response?: unknown;
  choices?: { message?: { content?: unknown } }[];
  usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
}

type AiRunner = { run(model: string, inputs: Record<string, unknown>): Promise<AiResult | string> };

export async function aiChatCompletions(c: Context<AppEnv>) {
  const req = await c.req.json<ChatRequest>().catch(() => null);
  if (!req || !Array.isArray(req.messages)) {
    return c.json({ error: { message: "body must be a chat request with messages", type: "invalid_request_error" } }, 400);
  }
  if (!req.model?.startsWith("@cf/")) {
    return c.json({ error: { message: `model not found: ${req.model}`, type: "invalid_request_error" } }, 404);
  }
  const messages = req.messages.map((m) => ({
    role: m.role,
    content: typeof m.content === "string" ? m.content : JSON.stringify(m.content),
  }));
  try {
    const raw = await (c.env.AI as unknown as AiRunner).run(req.model, {
      messages,
      max_tokens: req.max_tokens ?? 1024,
      temperature: req.temperature ?? 0.1,
    });
    const result: AiResult = typeof raw === "string" ? { response: raw } : raw;
    const reply = result.choices?.[0]?.message?.content ?? result.response ?? "";
    const content = typeof reply === "string" ? reply : JSON.stringify(reply);
    return c.json({
      id: `cf-${crypto.randomUUID()}`,
      object: "chat.completion",
      created: Math.floor(Date.now() / 1000),
      model: req.model,
      choices: [{ index: 0, message: { role: "assistant", content }, finish_reason: "stop" }],
      usage: result.usage
        ? {
            prompt_tokens: result.usage.prompt_tokens ?? 0,
            completion_tokens: result.usage.completion_tokens ?? 0,
            total_tokens: result.usage.total_tokens ?? 0,
          }
        : undefined,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    // Free-plan exhaustion surfaces as an error mentioning the daily Neuron
    // allocation; report it as a daily-quota 429 so the gateway retires this
    // model for the day.
    if (/neuron|allocation|quota/i.test(message)) {
      return c.json({ error: { message: `daily quota reached: ${message}`, type: "rate_limit" } }, 429);
    }
    if (/rate.?limit|too many requests|capacity/i.test(message)) {
      return c.json({ error: { message, type: "rate_limit" } }, 429);
    }
    if (/deprecat|retired|no longer (?:available|supported)/i.test(message)) {
      return c.json({ error: { message, type: "invalid_request_error" } }, 410);
    }
    if (/not found|no such model|unknown model/i.test(message)) {
      return c.json({ error: { message, type: "invalid_request_error" } }, 404);
    }
    return c.json({ error: { message, type: "server_error" } }, 502);
  }
}
