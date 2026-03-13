/**
 * Config — Environment-driven configuration for mcp-visualization.
 * Day 11: MCP Visualization Server configuration.
 *
 * Protocols: MCP
 * SOLID: SRP (single config module)
 */

export const config = {
  port: parseInt(process.env["PORT"] ?? "8070", 10),
  serviceName: "mcp-visualization",
  logLevel: process.env["LOG_LEVEL"] ?? "info",
  otelEndpoint:
    process.env["OTEL_EXPORTER_OTLP_ENDPOINT"] ?? "http://otel-collector:4317",
  mcpPath: "/mcp",
} as const;

export type Config = typeof config;
