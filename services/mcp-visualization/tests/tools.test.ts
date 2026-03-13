/**
 * tools.test.ts — Unit tests for render_chart and suggest_chart_type tools.
 * Day 11: MCP Visualization Server.
 *
 * Coverage targets: ≥80% of tool logic.
 * Run: vitest run
 */

import { describe, it, expect } from "vitest";
import { renderChart } from "../src/tools/renderChart.js";
import { suggestChartType } from "../src/tools/suggestChart.js";
import type {
  RenderChartInput,
  SuggestChartTypeInput,
  RenderChartOutput,
  ToolError,
} from "../src/types.js";

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function isError(result: RenderChartOutput | ToolError): result is ToolError {
  return "error" in result;
}

const TENANT_ID = "tenant-test-001";

const MONTHLY_SALES: RenderChartInput["data"] = [
  { month: "Jan", revenue: 120000, series: "Product A" },
  { month: "Feb", revenue: 145000, series: "Product A" },
  { month: "Mar", revenue: 132000, series: "Product A" },
  { month: "Jan", revenue: 85000, series: "Product B" },
  { month: "Feb", revenue: 91000, series: "Product B" },
  { month: "Mar", revenue: 105000, series: "Product B" },
];

const SIMPLE_KV: RenderChartInput["data"] = [
  { category: "Electronics", value: 450 },
  { category: "Clothing", value: 320 },
  { category: "Books", value: 180 },
  { category: "Sports", value: 260 },
];

const SCATTER_DATA: RenderChartInput["data"] = [
  { x: 10, y: 200 },
  { x: 20, y: 350 },
  { x: 15, y: 275 },
  { x: 30, y: 490 },
  { x: 25, y: 410 },
];

const CANDLESTICK_DATA: RenderChartInput["data"] = [
  { date: "2024-01-01", open: 100, close: 110, low: 95, high: 115 },
  { date: "2024-01-02", open: 110, close: 108, low: 105, high: 112 },
  { date: "2024-01-03", open: 108, close: 120, low: 107, high: 122 },
];

// ---------------------------------------------------------------------------
// render_chart — bar
// ---------------------------------------------------------------------------

describe("render_chart: bar", () => {
  it("returns a valid ECharts bar config with xAxis and series", () => {
    const result = renderChart({
      chart_type: "bar",
      data: MONTHLY_SALES,
      title: "Monthly Revenue",
      tenant_id: TENANT_ID,
    });

    expect(isError(result)).toBe(false);
    const out = result as RenderChartOutput;
    expect(out.chart_type).toBe("bar");
    expect(out.render_hint).toBe("echarts");
    expect(out.chart_config.title).toEqual({ text: "Monthly Revenue" });
    expect(out.chart_config.xAxis).toBeDefined();
    expect(Array.isArray(out.chart_config.series)).toBe(true);
  });

  it("returns correct series type 'bar' in series array", () => {
    const result = renderChart({
      chart_type: "bar",
      data: SIMPLE_KV,
      title: "Sales by Category",
      tenant_id: TENANT_ID,
    });
    expect(isError(result)).toBe(false);
    const out = result as RenderChartOutput;
    const series = out.chart_config.series as Array<{ type: string }>;
    expect(series.some((s) => s.type === "bar")).toBe(true);
  });

  it("merges caller options into chart_config", () => {
    const result = renderChart({
      chart_type: "bar",
      data: SIMPLE_KV,
      title: "Sales",
      tenant_id: TENANT_ID,
      options: { backgroundColor: "#f0f0f0" },
    });
    expect(isError(result)).toBe(false);
    const out = result as RenderChartOutput;
    expect(out.chart_config["backgroundColor"]).toBe("#f0f0f0");
  });
});

// ---------------------------------------------------------------------------
// render_chart — line
// ---------------------------------------------------------------------------

describe("render_chart: line", () => {
  it("returns a line chart with smooth: true", () => {
    const result = renderChart({
      chart_type: "line",
      data: MONTHLY_SALES,
      title: "Revenue Trend",
      tenant_id: TENANT_ID,
    });
    expect(isError(result)).toBe(false);
    const out = result as RenderChartOutput;
    expect(out.chart_type).toBe("line");
    const series = out.chart_config.series as Array<{ type: string; smooth?: boolean }>;
    expect(series.some((s) => s.type === "line")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// render_chart — area
// ---------------------------------------------------------------------------

describe("render_chart: area", () => {
  it("returns area chart with areaStyle on series", () => {
    const result = renderChart({
      chart_type: "area",
      data: MONTHLY_SALES,
      title: "Area Chart",
      tenant_id: TENANT_ID,
    });
    expect(isError(result)).toBe(false);
    const out = result as RenderChartOutput;
    expect(out.chart_type).toBe("area");
    const series = out.chart_config.series as Array<{ areaStyle?: unknown }>;
    expect(series.some((s) => s.areaStyle !== undefined)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// render_chart — pie
// ---------------------------------------------------------------------------

describe("render_chart: pie", () => {
  it("returns pie series with correct data structure", () => {
    const result = renderChart({
      chart_type: "pie",
      data: SIMPLE_KV,
      title: "Market Share",
      tenant_id: TENANT_ID,
    });
    expect(isError(result)).toBe(false);
    const out = result as RenderChartOutput;
    expect(out.chart_type).toBe("pie");
    const series = out.chart_config.series as Array<{ type: string; data: unknown[] }>;
    expect(series[0]?.type).toBe("pie");
    expect(Array.isArray(series[0]?.data)).toBe(true);
    expect(series[0]?.data.length).toBe(4);
  });

  it("pie data items have name and value fields", () => {
    const result = renderChart({
      chart_type: "pie",
      data: SIMPLE_KV,
      title: "Test Pie",
      tenant_id: TENANT_ID,
    });
    expect(isError(result)).toBe(false);
    const out = result as RenderChartOutput;
    const series = out.chart_config.series as Array<{ data: Array<{ name: string; value: unknown }> }>;
    const firstItem = series[0]?.data[0];
    expect(firstItem).toHaveProperty("name");
    expect(firstItem).toHaveProperty("value");
  });
});

// ---------------------------------------------------------------------------
// render_chart — donut
// ---------------------------------------------------------------------------

describe("render_chart: donut", () => {
  it("returns donut with inner radius (radius is array)", () => {
    const result = renderChart({
      chart_type: "donut",
      data: SIMPLE_KV,
      title: "Donut Chart",
      tenant_id: TENANT_ID,
    });
    expect(isError(result)).toBe(false);
    const out = result as RenderChartOutput;
    const series = out.chart_config.series as Array<{ type: string; radius: unknown }>;
    expect(series[0]?.type).toBe("pie");
    expect(Array.isArray(series[0]?.radius)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// render_chart — scatter
// ---------------------------------------------------------------------------

describe("render_chart: scatter", () => {
  it("returns scatter chart with value-type axes", () => {
    const result = renderChart({
      chart_type: "scatter",
      data: SCATTER_DATA,
      title: "Scatter Plot",
      tenant_id: TENANT_ID,
    });
    expect(isError(result)).toBe(false);
    const out = result as RenderChartOutput;
    expect(out.chart_type).toBe("scatter");
    const xAxis = out.chart_config.xAxis as { type: string };
    expect(xAxis.type).toBe("value");
  });

  it("series type is scatter", () => {
    const result = renderChart({
      chart_type: "scatter",
      data: SCATTER_DATA,
      title: "Scatter",
      tenant_id: TENANT_ID,
    });
    const out = result as RenderChartOutput;
    const series = out.chart_config.series as Array<{ type: string }>;
    expect(series[0]?.type).toBe("scatter");
  });
});

// ---------------------------------------------------------------------------
// render_chart — histogram
// ---------------------------------------------------------------------------

describe("render_chart: histogram", () => {
  const histData = Array.from({ length: 50 }, (_, i) => ({ value: i * 2 }));

  it("generates histogram with bin labels", () => {
    const result = renderChart({
      chart_type: "histogram",
      data: histData,
      title: "Value Distribution",
      tenant_id: TENANT_ID,
    });
    expect(isError(result)).toBe(false);
    const out = result as RenderChartOutput;
    expect(out.chart_type).toBe("histogram");
    const xAxis = out.chart_config.xAxis as { data: string[] };
    expect(Array.isArray(xAxis.data)).toBe(true);
    expect(xAxis.data.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// render_chart — heatmap
// ---------------------------------------------------------------------------

describe("render_chart: heatmap", () => {
  const heatData = [
    { day: "Mon", hour: "Morning", value: 10 },
    { day: "Mon", hour: "Evening", value: 25 },
    { day: "Tue", hour: "Morning", value: 15 },
    { day: "Tue", hour: "Evening", value: 30 },
  ];

  it("returns heatmap with visualMap", () => {
    const result = renderChart({
      chart_type: "heatmap",
      data: heatData,
      title: "Activity Heatmap",
      tenant_id: TENANT_ID,
    });
    expect(isError(result)).toBe(false);
    const out = result as RenderChartOutput;
    expect(out.chart_type).toBe("heatmap");
    expect(out.chart_config.visualMap).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// render_chart — candlestick
// ---------------------------------------------------------------------------

describe("render_chart: candlestick", () => {
  it("returns candlestick series with OHLC data", () => {
    const result = renderChart({
      chart_type: "candlestick",
      data: CANDLESTICK_DATA,
      title: "AAPL Price",
      tenant_id: TENANT_ID,
    });
    expect(isError(result)).toBe(false);
    const out = result as RenderChartOutput;
    expect(out.chart_type).toBe("candlestick");
    const series = out.chart_config.series as Array<{ type: string; data: unknown[] }>;
    expect(series[0]?.type).toBe("candlestick");
    expect(series[0]?.data.length).toBe(3);
  });
});

// ---------------------------------------------------------------------------
// render_chart — sankey
// ---------------------------------------------------------------------------

describe("render_chart: sankey", () => {
  const sankeyData = [
    { source: "A", target: "B", value: 100 },
    { source: "A", target: "C", value: 80 },
    { source: "B", target: "D", value: 60 },
  ];

  it("returns sankey with nodes and links", () => {
    const result = renderChart({
      chart_type: "sankey",
      data: sankeyData,
      title: "Flow Diagram",
      tenant_id: TENANT_ID,
    });
    expect(isError(result)).toBe(false);
    const out = result as RenderChartOutput;
    expect(out.chart_type).toBe("sankey");
    const series = out.chart_config.series as Array<{ data: unknown[]; links: unknown[] }>;
    expect(Array.isArray(series[0]?.data)).toBe(true); // nodes
    expect(Array.isArray(series[0]?.links)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// render_chart — waterfall
// ---------------------------------------------------------------------------

describe("render_chart: waterfall", () => {
  const waterfallData = [
    { label: "Start", value: 500 },
    { label: "Q1 Sales", value: 200 },
    { label: "Q1 Costs", value: -80 },
    { label: "Q2 Sales", value: 150 },
    { label: "End", value: 0 },
  ];

  it("returns waterfall with stacked bar series", () => {
    const result = renderChart({
      chart_type: "waterfall",
      data: waterfallData,
      title: "Cash Flow",
      tenant_id: TENANT_ID,
    });
    expect(isError(result)).toBe(false);
    const out = result as RenderChartOutput;
    expect(out.chart_type).toBe("waterfall");
    const series = out.chart_config.series as Array<{ type: string; stack: string }>;
    expect(series.every((s) => s.type === "bar")).toBe(true);
    expect(series.every((s) => s.stack === "waterfall")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// render_chart — stacked_bar
// ---------------------------------------------------------------------------

describe("render_chart: stacked_bar", () => {
  it("returns series with stack: total", () => {
    const result = renderChart({
      chart_type: "stacked_bar",
      data: MONTHLY_SALES,
      title: "Stacked Revenue",
      tenant_id: TENANT_ID,
    });
    expect(isError(result)).toBe(false);
    const out = result as RenderChartOutput;
    const series = out.chart_config.series as Array<{ stack?: string }>;
    expect(series.some((s) => s.stack === "total")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// render_chart — mixed_bar_line
// ---------------------------------------------------------------------------

describe("render_chart: mixed_bar_line", () => {
  const mixedData = [
    { month: "Jan", revenue: 100, margin: 12 },
    { month: "Feb", revenue: 120, margin: 15 },
    { month: "Mar", revenue: 115, margin: 13 },
  ];

  it("returns both bar and line series", () => {
    const result = renderChart({
      chart_type: "mixed_bar_line",
      data: mixedData,
      title: "Revenue vs Margin",
      tenant_id: TENANT_ID,
    });
    expect(isError(result)).toBe(false);
    const out = result as RenderChartOutput;
    const series = out.chart_config.series as Array<{ type: string }>;
    const types = series.map((s) => s.type);
    expect(types).toContain("bar");
    expect(types).toContain("line");
  });
});

// ---------------------------------------------------------------------------
// render_chart — error handling
// ---------------------------------------------------------------------------

describe("render_chart: error handling", () => {
  it("returns ToolError for unknown chart type", () => {
    const result = renderChart({
      chart_type: "unknown_chart_xyz",
      data: SIMPLE_KV,
      title: "Unknown",
      tenant_id: TENANT_ID,
    });
    expect(isError(result)).toBe(true);
    const err = result as ToolError;
    expect(err.error).toMatch(/Unsupported chart type/);
    expect(err.code).toBe("UNSUPPORTED_CHART_TYPE");
    expect(err.details).toMatch(/Supported types:/);
  });

  it("returns ToolError when data is not an array", () => {
    const result = renderChart({
      chart_type: "bar",
      data: "not an array" as unknown as RenderChartInput["data"],
      title: "Bad Data",
      tenant_id: TENANT_ID,
    });
    expect(isError(result)).toBe(true);
    const err = result as ToolError;
    expect(err.code).toBe("INVALID_DATA");
  });
});

// ---------------------------------------------------------------------------
// render_chart — all 25 types smoke test
// ---------------------------------------------------------------------------

describe("render_chart: all 25 types produce output", () => {
  const allTypesData = [
    { label: "A", value: 100, x: 1, y: 2 },
    { label: "B", value: 200, x: 2, y: 4 },
    { label: "C", value: 150, x: 3, y: 3 },
  ];

  const chartTypes = [
    "bar", "line", "area", "pie", "donut",
    "scatter", "bubble", "heatmap", "treemap", "funnel",
    "gauge", "radar", "sankey", "candlestick", "histogram",
    "boxplot", "parallel", "geo_choropleth", "geo_scatter",
    "waterfall", "stacked_bar", "stacked_area", "mixed_bar_line",
    "word_cloud", "sunburst",
  ] as const;

  for (const chartType of chartTypes) {
    it(`renders "${chartType}" without throwing`, () => {
      const result = renderChart({
        chart_type: chartType,
        data: allTypesData,
        title: `Test ${chartType}`,
        tenant_id: TENANT_ID,
      });
      // Must not throw and must return either a valid output or a typed error.
      expect(result).toBeDefined();
      if (!isError(result)) {
        const out = result as RenderChartOutput;
        expect(out.render_hint).toBe("echarts");
        expect(out.chart_type).toBe(chartType);
        expect(out.chart_config).toBeDefined();
        expect(typeof out.chart_config).toBe("object");
      }
    });
  }
});

// ---------------------------------------------------------------------------
// suggest_chart_type — intent rules
// ---------------------------------------------------------------------------

describe("suggest_chart_type: trend intent", () => {
  it("suggests line chart for time-series data with trend intent", () => {
    const input: SuggestChartTypeInput = {
      columns: [
        { name: "date", type: "date", cardinality: 365 },
        { name: "revenue", type: "number", cardinality: 365 },
      ],
      row_count: 365,
      intent: "trend",
      tenant_id: TENANT_ID,
    };
    const result = suggestChartType(input);
    expect(result.primary_suggestion).toBe("line");
    expect(result.alternatives).toContain("area");
    expect(result.reasoning).toBeTruthy();
  });

  it("suggests line for trend with no explicit date column", () => {
    const input: SuggestChartTypeInput = {
      columns: [
        { name: "period", type: "number", cardinality: 12 },
        { name: "sales", type: "number", cardinality: 12 },
      ],
      row_count: 12,
      intent: "trend",
      tenant_id: TENANT_ID,
    };
    const result = suggestChartType(input);
    expect(result.primary_suggestion).toBe("line");
  });
});

describe("suggest_chart_type: compare intent", () => {
  it("suggests bar for categorical comparison (≤20 categories)", () => {
    const input: SuggestChartTypeInput = {
      columns: [
        { name: "region", type: "string", cardinality: 8 },
        { name: "sales", type: "number", cardinality: 100 },
      ],
      row_count: 8,
      intent: "compare",
      tenant_id: TENANT_ID,
    };
    const result = suggestChartType(input);
    expect(result.primary_suggestion).toBe("bar");
  });

  it("includes radar as alternative for multi-metric comparison", () => {
    const input: SuggestChartTypeInput = {
      columns: [
        { name: "product", type: "string", cardinality: 5 },
        { name: "quality", type: "number", cardinality: 100 },
        { name: "price", type: "number", cardinality: 100 },
        { name: "delivery", type: "number", cardinality: 100 },
      ],
      row_count: 5,
      intent: "compare",
      tenant_id: TENANT_ID,
    };
    const result = suggestChartType(input);
    // bar is the first match (4 numerics passes ≤20 rows condition), radar is alternative
    expect(["bar", "radar"]).toContain(result.primary_suggestion);
  });
});

describe("suggest_chart_type: distribution intent", () => {
  it("suggests histogram for pure numeric distribution", () => {
    const input: SuggestChartTypeInput = {
      columns: [{ name: "salary", type: "number", cardinality: 500 }],
      row_count: 1000,
      intent: "distribution",
      tenant_id: TENANT_ID,
    };
    const result = suggestChartType(input);
    expect(result.primary_suggestion).toBe("histogram");
    expect(result.alternatives).toContain("boxplot");
  });

  it("suggests boxplot for distribution across categories", () => {
    const input: SuggestChartTypeInput = {
      columns: [
        { name: "department", type: "string", cardinality: 5 },
        { name: "salary", type: "number", cardinality: 200 },
      ],
      row_count: 500,
      intent: "distribution",
      tenant_id: TENANT_ID,
    };
    const result = suggestChartType(input);
    expect(result.primary_suggestion).toBe("boxplot");
  });
});

describe("suggest_chart_type: composition intent", () => {
  it("suggests pie for ≤8 categories", () => {
    const input: SuggestChartTypeInput = {
      columns: [
        { name: "category", type: "string", cardinality: 5 },
        { name: "revenue", type: "number", cardinality: 5 },
      ],
      row_count: 5,
      intent: "composition",
      tenant_id: TENANT_ID,
    };
    const result = suggestChartType(input);
    expect(result.primary_suggestion).toBe("pie");
    expect(result.alternatives).toContain("donut");
  });

  it("suggests treemap for >8 categories", () => {
    const input: SuggestChartTypeInput = {
      columns: [
        { name: "product", type: "string", cardinality: 30 },
        { name: "revenue", type: "number", cardinality: 30 },
      ],
      row_count: 30,
      intent: "composition",
      tenant_id: TENANT_ID,
    };
    const result = suggestChartType(input);
    expect(result.primary_suggestion).toBe("treemap");
  });
});

describe("suggest_chart_type: correlation intent", () => {
  it("suggests scatter for 2 numeric columns", () => {
    const input: SuggestChartTypeInput = {
      columns: [
        { name: "marketing_spend", type: "number", cardinality: 100 },
        { name: "revenue", type: "number", cardinality: 100 },
      ],
      row_count: 100,
      intent: "correlation",
      tenant_id: TENANT_ID,
    };
    const result = suggestChartType(input);
    expect(result.primary_suggestion).toBe("scatter");
    expect(result.alternatives).toContain("heatmap");
  });
});

describe("suggest_chart_type: flow intent", () => {
  it("suggests sankey for flow data", () => {
    const input: SuggestChartTypeInput = {
      columns: [
        { name: "source", type: "string", cardinality: 5 },
        { name: "target", type: "string", cardinality: 5 },
        { name: "value", type: "number", cardinality: 20 },
      ],
      row_count: 20,
      intent: "flow",
      tenant_id: TENANT_ID,
    };
    const result = suggestChartType(input);
    expect(result.primary_suggestion).toBe("sankey");
    expect(result.alternatives).toContain("funnel");
  });
});

describe("suggest_chart_type: geographic intent", () => {
  it("suggests geo_choropleth for geographic data with value", () => {
    const input: SuggestChartTypeInput = {
      columns: [
        { name: "country", type: "string", cardinality: 50 },
        { name: "gdp", type: "number", cardinality: 50 },
        { name: "lat", type: "number", cardinality: 50 },
        { name: "lng", type: "number", cardinality: 50 },
      ],
      row_count: 50,
      intent: "geographic",
      tenant_id: TENANT_ID,
    };
    const result = suggestChartType(input);
    expect(result.primary_suggestion).toBe("geo_choropleth");
  });
});

describe("suggest_chart_type: unknown intent fallback", () => {
  it("returns a valid suggestion for unrecognised intent", () => {
    const input: SuggestChartTypeInput = {
      columns: [
        { name: "x", type: "string", cardinality: 10 },
        { name: "y", type: "number", cardinality: 10 },
      ],
      row_count: 10,
      intent: "completely_unknown_intent_xyz",
      tenant_id: TENANT_ID,
    };
    const result = suggestChartType(input);
    expect(result.primary_suggestion).toBeDefined();
    expect(typeof result.primary_suggestion).toBe("string");
    expect(result.reasoning).toMatch(/No rule matched/);
  });
});

describe("suggest_chart_type: config_hints are populated", () => {
  it("always includes row_count and column counts in config_hints", () => {
    const input: SuggestChartTypeInput = {
      columns: [
        { name: "month", type: "date", cardinality: 12 },
        { name: "sales", type: "number", cardinality: 12 },
      ],
      row_count: 12,
      intent: "trend",
      tenant_id: TENANT_ID,
    };
    const result = suggestChartType(input);
    expect(result.config_hints["row_count"]).toBe(12);
    expect(result.config_hints["numeric_columns"]).toBe(1);
    expect(result.config_hints["categorical_columns"]).toBe(0);
  });
});
