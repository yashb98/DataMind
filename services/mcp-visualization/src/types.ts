/**
 * Types — Request/response types for mcp-visualization tools.
 * Day 11: MCP Visualization Server type definitions.
 *
 * Protocols: MCP
 * SOLID: ISP (narrow interfaces per tool)
 */

/** Supported ECharts 5 chart types. */
export type ChartType =
  | "bar"
  | "line"
  | "area"
  | "pie"
  | "donut"
  | "scatter"
  | "bubble"
  | "heatmap"
  | "treemap"
  | "funnel"
  | "gauge"
  | "radar"
  | "sankey"
  | "candlestick"
  | "histogram"
  | "boxplot"
  | "parallel"
  | "geo_choropleth"
  | "geo_scatter"
  | "waterfall"
  | "stacked_bar"
  | "stacked_area"
  | "mixed_bar_line"
  | "word_cloud"
  | "sunburst";

/** All supported chart types as a const array for runtime validation. */
export const SUPPORTED_CHART_TYPES: ChartType[] = [
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
  "candlestick",
  "histogram",
  "boxplot",
  "parallel",
  "geo_choropleth",
  "geo_scatter",
  "waterfall",
  "stacked_bar",
  "stacked_area",
  "mixed_bar_line",
  "word_cloud",
  "sunburst",
];

/** A single data row — flexible key/value. Values can be string, number, or null. */
export type DataRow = Record<string, string | number | null>;

/** Input to render_chart tool. */
export interface RenderChartInput {
  chart_type: string;
  data: DataRow[];
  title: string;
  tenant_id: string;
  options?: Record<string, unknown>;
}

/** Output from render_chart tool. */
export interface RenderChartOutput {
  chart_config: EChartsOption;
  chart_type: ChartType;
  render_hint: "echarts";
}

/** Column descriptor for suggest_chart_type. */
export interface ColumnDescriptor {
  name: string;
  type: "string" | "number" | "date" | "boolean" | "unknown";
  cardinality: number;
}

/** Supported analysis intents. */
export type AnalysisIntent =
  | "compare"
  | "trend"
  | "distribution"
  | "correlation"
  | "composition"
  | "relationship"
  | "ranking"
  | "flow"
  | "geographic"
  | "part_to_whole";

/** Input to suggest_chart_type tool. */
export interface SuggestChartTypeInput {
  columns: ColumnDescriptor[];
  row_count: number;
  intent: string;
  tenant_id: string;
}

/** Output from suggest_chart_type tool. */
export interface SuggestChartTypeOutput {
  primary_suggestion: ChartType;
  alternatives: ChartType[];
  reasoning: string;
  config_hints: Record<string, unknown>;
}

/**
 * Minimal ECharts option type covering all use-cases in this service.
 * Uses unknown for nested structures to avoid over-specifying the ECharts API.
 */
export interface EChartsOption {
  title?: { text: string; subtext?: string };
  tooltip?: { trigger?: string; formatter?: string; [key: string]: unknown };
  legend?: { data?: string[]; [key: string]: unknown };
  xAxis?: unknown;
  yAxis?: unknown;
  series?: unknown[];
  radar?: unknown;
  geo?: unknown;
  visualMap?: unknown;
  dataZoom?: unknown[];
  grid?: unknown;
  [key: string]: unknown;
}

/** In-memory prometheus-style metrics. */
export interface MetricsStore {
  mcp_viz_tool_calls_total: Record<string, number>;
  mcp_viz_errors_total: Record<string, number>;
}

/** MCP JSON-RPC 2.0 request envelope. */
export interface McpRpcRequest {
  jsonrpc: "2.0";
  id: string | number;
  method: string;
  params?: unknown;
}

/** MCP JSON-RPC 2.0 response envelope. */
export interface McpRpcResponse {
  jsonrpc: "2.0";
  id: string | number | null;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

/** Tool error result. */
export interface ToolError {
  error: string;
  code: string;
  details?: string;
}
