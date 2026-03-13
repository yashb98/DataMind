/**
 * index.ts — Cloudflare Workers edge service for DataMind chart suggestions.
 * Day 11: Sub-20ms chart type suggestions at 300+ global PoPs.
 *
 * Protocols: None (edge HTTP with CORS)
 * SOLID: SRP — routing only; OCP — AI/rules strategy swappable; DIP — depends on Env interface
 * Benchmark: tests/benchmarks/bench_worker.ts (SLO: p99 < 20ms)
 *
 * Two modes:
 *   1. AI mode  — Workers AI (@cf/meta/llama-3.1-8b-instruct) within latency budget
 *   2. Rules    — Deterministic fallback, guaranteed < 1ms, always available
 */

import type { Env, SuggestRequest, SuggestResponse } from "./types";
import { suggestByRules } from "./rules";

// ---------------------------------------------------------------------------
// CORS helper
// ---------------------------------------------------------------------------

const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Tenant-ID",
};

function withCors(
  body: unknown,
  init: ResponseInit & { headers?: Record<string, string> } = {},
): Response {
  return Response.json(body, {
    ...init,
    headers: { ...CORS_HEADERS, ...(init.headers ?? {}) },
  });
}

// ---------------------------------------------------------------------------
// Main fetch handler
// ---------------------------------------------------------------------------

export default {
  async fetch(
    request: Request,
    env: Env,
    _ctx: ExecutionContext,
  ): Promise<Response> {
    const url = new URL(request.url);
    const start = Date.now();

    // Pre-flight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    // GET /health
    if (url.pathname === "/health" && request.method === "GET") {
      return withCors({
        status: "alive",
        service: env.SERVICE_NAME ?? "chart-suggestions-worker",
        region: (request.cf as { colo?: string } | undefined)?.colo ?? "unknown",
      });
    }

    // GET /
    if (url.pathname === "/" && request.method === "GET") {
      return withCors({
        service: "DataMind Chart Suggestions",
        version: "0.1.0",
        endpoint: "POST /suggest",
        slo: "p99 < 20ms",
        modes: ["ai", "rules"],
      });
    }

    // POST /suggest
    if (url.pathname === "/suggest" && request.method === "POST") {
      return handleSuggest(request, env, start);
    }

    return new Response("Not Found", { status: 404, headers: CORS_HEADERS });
  },
} satisfies ExportedHandler<Env>;

// ---------------------------------------------------------------------------
// /suggest handler
// ---------------------------------------------------------------------------

async function handleSuggest(
  request: Request,
  env: Env,
  start: number,
): Promise<Response> {
  // Parse body
  let body: SuggestRequest;
  try {
    body = (await request.json()) as SuggestRequest;
  } catch {
    return withCors(
      { error: "Invalid JSON body" },
      { status: 400 },
    );
  }

  // Validate required fields
  if (!body.columns || !Array.isArray(body.columns) || body.columns.length === 0) {
    return withCors(
      { error: "Missing required field: columns (non-empty array)" },
      { status: 400 },
    );
  }
  if (typeof body.intent !== "string" || body.intent.trim() === "") {
    return withCors(
      { error: "Missing required field: intent (string)" },
      { status: 400 },
    );
  }
  if (typeof body.row_count !== "number" || body.row_count < 0) {
    return withCors(
      { error: "Missing or invalid field: row_count (non-negative number)" },
      { status: 400 },
    );
  }

  const maxLatencyMs = parseInt(env.MAX_LATENCY_MS ?? "15", 10);

  // Attempt Workers AI within latency budget
  let result: SuggestResponse | null = null;

  // env.AI may be undefined in local/test environments — always guard
  if (typeof env.AI !== "undefined" && env.AI !== null) {
    try {
      result = await tryWorkersAI(body, env, start, maxLatencyMs);
    } catch {
      // Silent fallback — rules engine below
    }
  }

  // Rule-based fallback
  if (!result) {
    result = suggestByRules(body);
  }

  // Stamp final wall-clock latency
  result.latency_ms = Date.now() - start;

  return withCors(result, {
    headers: {
      "Cache-Control": "no-store",
      "X-Latency-Ms": result.latency_ms.toString(),
      "X-Mode": result.mode,
    },
  });
}

// ---------------------------------------------------------------------------
// Workers AI integration
// ---------------------------------------------------------------------------

/**
 * Attempt to get a chart suggestion from Workers AI.
 * Returns null if:
 *   - Already past 60% of the latency budget
 *   - AI response times out
 *   - AI output cannot be parsed into a valid chart type
 */
async function tryWorkersAI(
  body: SuggestRequest,
  env: Env,
  start: number,
  maxLatencyMs: number,
): Promise<SuggestResponse | null> {
  const elapsed = Date.now() - start;

  // Bail early if we've already consumed too much of the budget
  if (elapsed > maxLatencyMs * 0.6) {
    return null;
  }

  const prompt = buildPrompt(body);
  const remaining = maxLatencyMs - elapsed;

  // Race AI call against a timeout that respects the latency budget
  const aiPromise = env.AI.run(
    "@cf/meta/llama-3.1-8b-instruct" as Parameters<typeof env.AI.run>[0],
    {
      prompt,
      max_tokens: 100,
      stream: false,
    },
  );

  const timeoutPromise = new Promise<null>((resolve) =>
    setTimeout(() => resolve(null), remaining),
  );

  const winner = await Promise.race([aiPromise, timeoutPromise]);
  if (!winner) return null;

  const raw = winner as Record<string, unknown>;
  const text =
    typeof raw["response"] === "string"
      ? raw["response"]
      : String(winner);

  return parseAIResponse(text);
}

/**
 * Build a compact, token-efficient prompt for the AI model.
 * Limited to 5 columns to stay within the latency budget.
 */
function buildPrompt(body: SuggestRequest): string {
  const colSummary = body.columns
    .slice(0, 5)
    .map((c) => `${c.name} (${c.type}, ${c.cardinality} unique)`)
    .join(", ");

  return (
    `Suggest the best chart type for this data. Reply with ONLY a JSON object.\n` +
    `Data: ${body.row_count} rows, columns: ${colSummary}\n` +
    `User intent: ${body.intent}\n` +
    `Reply format: {"chart":"<type>","alt":["<alt1>","<alt2>"],"reason":"<one sentence>"}\n` +
    `Valid types: bar, line, area, pie, donut, scatter, bubble, histogram, heatmap, treemap, funnel, gauge, radar, sankey, boxplot`
  );
}

// Valid chart types accepted from AI output
const VALID_CHART_TYPES = new Set([
  "bar",
  "line",
  "area",
  "pie",
  "donut",
  "scatter",
  "bubble",
  "heatmap",
  "treemap",
  "funnel",
  "gauge",
  "radar",
  "sankey",
  "histogram",
  "boxplot",
  "mixed_bar_line",
  "stacked_bar",
  "stacked_area",
  "horizontal_bar",
  "geo_choropleth",
  "geo_scatter",
  "parallel",
  "sunburst",
]);

/**
 * Parse the raw AI text response into a SuggestResponse.
 * Returns null if the response is invalid or the chart type is unrecognised.
 */
function parseAIResponse(text: string): SuggestResponse | null {
  try {
    // Extract the first JSON object from the response text
    const match = text.match(/\{[^}]+\}/);
    if (!match) return null;

    const parsed = JSON.parse(match[0]) as {
      chart?: string;
      alt?: unknown;
      reason?: string;
    };

    const chart = typeof parsed.chart === "string"
      ? parsed.chart.toLowerCase().trim()
      : "";
    if (!chart || !VALID_CHART_TYPES.has(chart)) return null;

    const alternatives = Array.isArray(parsed.alt)
      ? (parsed.alt as unknown[])
          .filter((a): a is string => typeof a === "string")
          .map((a) => a.toLowerCase().trim())
          .filter((a) => VALID_CHART_TYPES.has(a) && a !== chart)
          .slice(0, 3)
      : [];

    return {
      primary_suggestion: chart,
      alternatives,
      reasoning:
        typeof parsed.reason === "string" && parsed.reason.trim() !== ""
          ? parsed.reason.trim()
          : "AI-suggested based on data characteristics.",
      latency_ms: 0, // overwritten by caller
      mode: "ai",
      config_hints: {},
    };
  } catch {
    return null;
  }
}
