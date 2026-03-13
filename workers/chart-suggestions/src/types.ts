/**
 * types.ts — Request/response type definitions for chart-suggestions worker.
 * Day 11: Cloudflare Workers AI edge service for sub-20ms chart type suggestions.
 *
 * Protocols: None (edge HTTP)
 * SOLID: ISP — small focused interfaces, no bloat
 */

export interface ColumnInfo {
  name: string;
  type: string; // "string" | "number" | "date" | "boolean" | "geo"
  cardinality: number; // distinct value count
}

export interface SuggestRequest {
  columns: ColumnInfo[];
  row_count: number;
  intent: string; // "trend" | "compare" | "distribution" | "composition" | "correlation" | "ranking" | "flow" | "geographic"
  tenant_id: string;
}

export interface SuggestResponse {
  primary_suggestion: string;
  alternatives: string[];
  reasoning: string;
  latency_ms: number;
  mode: "ai" | "rules";
  config_hints: {
    x_axis?: string;
    y_axis?: string;
    color_by?: string;
    aggregation?: string;
  };
}

export interface Env {
  AI: Ai;
  SERVICE_NAME: string;
  MAX_LATENCY_MS: string;
}
