/**
 * types — Shared TypeScript interfaces for DataMind dashboard.
 * Day 15: Dashboard UI foundation.
 *
 * Protocols: None
 * SOLID: ISP — focused interfaces, no fat contracts
 */

export type WidgetType = "chart" | "metric" | "table" | "text" | "map";

export type ChartType =
  | "line"
  | "bar"
  | "pie"
  | "scatter"
  | "area"
  | "heatmap"
  | "funnel"
  | "gauge"
  | "radar"
  | "treemap"
  | "sankey"
  | "candlestick"
  | "geo";

export interface WidgetConfig {
  widget_id: string;
  widget_type: WidgetType;
  title: string;
  /** react-grid-layout x position (0-based, in cols) */
  x: number;
  /** react-grid-layout y position (0-based, in rows) */
  y: number;
  /** width in grid columns */
  w: number;
  /** height in grid rows */
  h: number;
  chart_type?: ChartType;
  data_source: Record<string, unknown>;
  chart_config: Record<string, unknown>;
  /** refresh interval in seconds; 0 = no auto refresh */
  refresh_interval_s: number;
  /** cached live data for real-time updates */
  live_data?: Record<string, unknown>;
}

export interface DashboardConfig {
  dashboard_id: string;
  tenant_id: string;
  title: string;
  description: string;
  widgets: WidgetConfig[];
  theme: "dark" | "light";
  cols: number;
  row_height: number;
  created_at: string;
  updated_at: string;
  tags: string[];
  thumbnail_url?: string;
}

export interface CreateDashboardRequest {
  tenant_id: string;
  title: string;
  description?: string;
  widgets?: WidgetConfig[];
  theme?: "dark" | "light";
  tags?: string[];
}

export interface UpdateDashboardRequest {
  tenant_id: string;
  title?: string;
  description?: string;
  widgets?: WidgetConfig[];
  theme?: "dark" | "light";
  tags?: string[];
}

export interface NLToDashboardRequest {
  tenant_id: string;
  prompt: string;
  /** Existing dashboard id to modify (optional) */
  dashboard_id?: string;
}

export interface NLToDashboardResponse {
  dashboard_id: string;
  title: string;
  description: string;
  widgets: WidgetConfig[];
  latency_ms: number;
  model_used: string;
}

export interface ApiError {
  detail: string;
  status: number;
}

/** Payload arriving over WebSocket for real-time updates */
export type WSMessageType = "event" | "heartbeat" | "error";

export interface WSMessage {
  type: WSMessageType;
  widget_id?: string;
  data?: Record<string, unknown>;
  timestamp?: string;
  error?: string;
}
