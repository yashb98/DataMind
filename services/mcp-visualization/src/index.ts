/**
 * index — MCP Visualization Server entry point.
 * Day 11: ECharts 5 chart generation + chart type suggestion via MCP JSON-RPC 2.0.
 *
 * Protocols: MCP (streamable-HTTP transport, tools/list + tools/call)
 * SOLID: SRP (HTTP wiring only), DIP (tool implementations injected)
 * Benchmark: tests/benchmarks/bench_render_chart.ts
 */

import express, { type Request, type Response, type NextFunction } from "express";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { z } from "zod";
import { config } from "./config.js";
import { renderChart } from "./tools/renderChart.js";
import { suggestChartType } from "./tools/suggestChart.js";
import type { MetricsStore, ToolError } from "./types.js";
import { SUPPORTED_CHART_TYPES } from "./types.js";

// ---------------------------------------------------------------------------
// In-memory metrics store
// ---------------------------------------------------------------------------

const metrics: MetricsStore = {
  mcp_viz_tool_calls_total: {
    render_chart: 0,
    suggest_chart_type: 0,
  },
  mcp_viz_errors_total: {
    render_chart: 0,
    suggest_chart_type: 0,
  },
};

function incrementCall(tool: string): void {
  metrics.mcp_viz_tool_calls_total[tool] =
    (metrics.mcp_viz_tool_calls_total[tool] ?? 0) + 1;
}

function incrementError(tool: string): void {
  metrics.mcp_viz_errors_total[tool] =
    (metrics.mcp_viz_errors_total[tool] ?? 0) + 1;
}

// ---------------------------------------------------------------------------
// MCP Server setup
// ---------------------------------------------------------------------------

function createMcpServer(): McpServer {
  const server = new McpServer({
    name: config.serviceName,
    version: "0.1.0",
  });

  // --- Tool: render_chart ---------------------------------------------------
  server.tool(
    "render_chart",
    "Generate an ECharts 5 chart configuration object from input data. Returns a valid ECharts option object ready for client-side rendering.",
    {
      chart_type: z
        .enum(SUPPORTED_CHART_TYPES as [string, ...string[]])
        .describe(
          `Chart type to render. Supported: ${SUPPORTED_CHART_TYPES.join(", ")}`
        ),
      data: z
        .array(z.record(z.union([z.string(), z.number(), z.null()])))
        .describe(
          "Array of data row objects. Keys become axis/series labels. Values must be string, number, or null."
        ),
      title: z.string().describe("Chart title displayed in the ECharts option."),
      tenant_id: z
        .string()
        .describe("Tenant identifier for multi-tenancy context."),
      options: z
        .record(z.unknown())
        .optional()
        .describe(
          "Optional ECharts option overrides merged into the generated config at top level."
        ),
    },
    async (args) => {
      incrementCall("render_chart");
      const result = renderChart({
        chart_type: args.chart_type,
        data: args.data,
        title: args.title,
        tenant_id: args.tenant_id,
        options: args.options,
      });

      const isError = "error" in result;
      if (isError) {
        incrementError("render_chart");
        const err = result as ToolError;
        return {
          isError: true,
          content: [
            {
              type: "text" as const,
              text: JSON.stringify(err),
            },
          ],
        };
      }

      return {
        content: [
          {
            type: "text" as const,
            text: JSON.stringify(result),
          },
        ],
      };
    }
  );

  // --- Tool: suggest_chart_type ---------------------------------------------
  server.tool(
    "suggest_chart_type",
    "Suggest the best ECharts chart type for given data characteristics and analysis intent. Uses a deterministic rule engine — no LLM call required.",
    {
      columns: z
        .array(
          z.object({
            name: z.string().describe("Column name."),
            type: z
              .enum(["string", "number", "date", "boolean", "unknown"])
              .describe("Data type of the column."),
            cardinality: z
              .number()
              .int()
              .nonnegative()
              .describe("Number of distinct values in the column."),
          })
        )
        .describe("Array of column descriptors from the dataset."),
      row_count: z
        .number()
        .int()
        .positive()
        .describe("Total number of rows in the dataset."),
      intent: z
        .string()
        .describe(
          'Analysis intent. Examples: "compare", "trend", "distribution", "correlation", "composition", "relationship", "ranking", "flow", "geographic", "part_to_whole".'
        ),
      tenant_id: z
        .string()
        .describe("Tenant identifier for multi-tenancy context."),
    },
    async (args) => {
      incrementCall("suggest_chart_type");
      const result = suggestChartType({
        columns: args.columns,
        row_count: args.row_count,
        intent: args.intent,
        tenant_id: args.tenant_id,
      });
      return {
        content: [
          {
            type: "text" as const,
            text: JSON.stringify(result),
          },
        ],
      };
    }
  );

  return server;
}

// ---------------------------------------------------------------------------
// Express app + routes
// ---------------------------------------------------------------------------

async function createApp(): Promise<express.Application> {
  const app = express();
  app.use(express.json({ limit: "10mb" }));

  // Request logging middleware.
  app.use((req: Request, _res: Response, next: NextFunction) => {
    if (config.logLevel === "debug") {
      console.log(
        JSON.stringify({
          ts: new Date().toISOString(),
          method: req.method,
          path: req.path,
          service: config.serviceName,
        })
      );
    }
    next();
  });

  // ---- Health endpoints ----------------------------------------------------

  app.get("/health/liveness", (_req: Request, res: Response) => {
    res.json({ status: "alive", service: config.serviceName });
  });

  app.get("/health/readiness", (_req: Request, res: Response) => {
    res.json({ status: "healthy", service: config.serviceName });
  });

  // ---- Tool discovery endpoint --------------------------------------------

  app.get("/tools", (_req: Request, res: Response) => {
    res.json({
      tools: ["render_chart", "suggest_chart_type"],
      mcp_endpoint: config.mcpPath,
      transport: "streamable-http",
      supported_chart_types: SUPPORTED_CHART_TYPES,
      version: "0.1.0",
    });
  });

  // ---- Metrics endpoint ---------------------------------------------------

  app.get("/metrics", (_req: Request, res: Response) => {
    res.json(metrics);
  });

  // ---- MCP streamable-HTTP endpoint ----------------------------------------
  // Each request gets a fresh transport instance (stateless per MCP spec for
  // streamable-HTTP without session resumption).

  const mcpServer = createMcpServer();

  app.post(config.mcpPath, async (req: Request, res: Response) => {
    try {
      const transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: undefined, // stateless mode
      });
      await mcpServer.connect(transport);
      await transport.handleRequest(req, res, req.body);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error(
        JSON.stringify({
          ts: new Date().toISOString(),
          level: "error",
          service: config.serviceName,
          error: message,
          path: req.path,
        })
      );
      if (!res.headersSent) {
        res.status(500).json({
          jsonrpc: "2.0",
          id: null,
          error: { code: -32603, message: "Internal error", data: message },
        });
      }
    }
  });

  // GET /mcp — return service info for MCP client discovery.
  app.get(config.mcpPath, (_req: Request, res: Response) => {
    res.json({
      service: config.serviceName,
      protocol: "MCP JSON-RPC 2.0",
      transport: "streamable-http",
      endpoint: config.mcpPath,
      tools: ["render_chart", "suggest_chart_type"],
    });
  });

  // ---- 404 handler --------------------------------------------------------

  app.use((_req: Request, res: Response) => {
    res.status(404).json({ error: "Not found" });
  });

  // ---- Global error handler ------------------------------------------------

  app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
    console.error(
      JSON.stringify({
        ts: new Date().toISOString(),
        level: "error",
        service: config.serviceName,
        error: err.message,
        stack: err.stack,
      })
    );
    res.status(500).json({ error: "Internal server error" });
  });

  return app;
}

// ---------------------------------------------------------------------------
// Server bootstrap
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const app = await createApp();

  const server = app.listen(config.port, () => {
    console.log(
      JSON.stringify({
        ts: new Date().toISOString(),
        level: "info",
        service: config.serviceName,
        message: `MCP Visualization Server started`,
        port: config.port,
        mcp_endpoint: `http://localhost:${config.port}${config.mcpPath}`,
        health: `http://localhost:${config.port}/health/liveness`,
        tools: ["render_chart", "suggest_chart_type"],
        chart_types_supported: SUPPORTED_CHART_TYPES.length,
      })
    );
  });

  // Graceful shutdown.
  const shutdown = (signal: string): void => {
    console.log(
      JSON.stringify({
        ts: new Date().toISOString(),
        level: "info",
        service: config.serviceName,
        message: `Received ${signal}, shutting down gracefully`,
      })
    );
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(1), 10_000);
  };

  process.on("SIGTERM", () => shutdown("SIGTERM"));
  process.on("SIGINT", () => shutdown("SIGINT"));
}

main().catch((err: unknown) => {
  console.error(
    JSON.stringify({
      ts: new Date().toISOString(),
      level: "fatal",
      service: config.serviceName,
      error: err instanceof Error ? err.message : String(err),
    })
  );
  process.exit(1);
});
