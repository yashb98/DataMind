/**
 * suggestChart — Rule-based chart type recommendation engine.
 * Day 11: MCP Visualization Server — suggest_chart_type tool.
 *
 * No LLM call needed — pure deterministic rule engine covering
 * all standard BI analysis intents.
 *
 * Protocols: MCP
 * SOLID: SRP (only suggestion logic), OCP (add rules, never edit existing)
 * Benchmark: tests/benchmarks/bench_suggest_chart.ts
 */

import type {
  ChartType,
  ColumnDescriptor,
  SuggestChartTypeInput,
  SuggestChartTypeOutput,
} from "../types.js";

// ---------------------------------------------------------------------------
// Column type analysis helpers
// ---------------------------------------------------------------------------

/** Count columns matching a given type. */
function countCols(
  columns: ColumnDescriptor[],
  type: ColumnDescriptor["type"]
): number {
  return columns.filter((c) => c.type === type).length;
}

/** Check if any column has a time/date-related name. */
function hasTimeColumn(columns: ColumnDescriptor[]): boolean {
  const timeKeywords = ["date", "time", "year", "month", "week", "day", "hour", "period", "quarter", "timestamp"];
  return columns.some((c) =>
    timeKeywords.some((kw) => c.name.toLowerCase().includes(kw)) || c.type === "date"
  );
}

/** Count numeric columns. */
function numericCount(columns: ColumnDescriptor[]): number {
  return countCols(columns, "number");
}

/** Count categorical (string) columns. */
function categoricalCount(columns: ColumnDescriptor[]): number {
  return countCols(columns, "string");
}

/** Get the max cardinality of categorical columns. */
function maxCategoricalCardinality(columns: ColumnDescriptor[]): number {
  const catCols = columns.filter((c) => c.type === "string");
  if (catCols.length === 0) return 0;
  return Math.max(...catCols.map((c) => c.cardinality));
}

/** Check if data has lat/lng columns suggesting geographic data. */
function hasGeoColumns(columns: ColumnDescriptor[]): boolean {
  const geoKeywords = ["lat", "lng", "lon", "longitude", "latitude", "geo", "region", "country", "city", "state"];
  return columns.some((c) =>
    geoKeywords.some((kw) => c.name.toLowerCase().includes(kw))
  );
}

/** Normalise intent string for matching. */
function normaliseIntent(intent: string): string {
  return intent.toLowerCase().trim().replace(/[\s-_]+/g, "_");
}

// ---------------------------------------------------------------------------
// Rule engine
// ---------------------------------------------------------------------------

interface SuggestionRule {
  intent: string;
  condition: (columns: ColumnDescriptor[], rowCount: number) => boolean;
  primary: ChartType;
  alternatives: ChartType[];
  reasoning: string;
  configHints: Record<string, unknown>;
}

const RULES: SuggestionRule[] = [
  // ---- TREND ---------------------------------------------------------------
  {
    intent: "trend",
    condition: (cols) => hasTimeColumn(cols) && numericCount(cols) >= 1,
    primary: "line",
    alternatives: ["area", "bar"],
    reasoning: "Time-series data with a date column is best represented as a line chart to show trends over time.",
    configHints: { smooth: true, xAxis_type: "time" },
  },
  {
    intent: "trend",
    condition: (cols) => numericCount(cols) >= 1,
    primary: "line",
    alternatives: ["area", "bar"],
    reasoning: "Trend analysis without explicit time column defaults to a line chart ordered by row index.",
    configHints: { smooth: true },
  },

  // ---- COMPARE -------------------------------------------------------------
  {
    intent: "compare",
    condition: (cols, rows) => categoricalCount(cols) >= 1 && numericCount(cols) >= 1 && rows <= 20,
    primary: "bar",
    alternatives: ["stacked_bar", "radar"],
    reasoning: "Comparing values across categories with ≤20 categories is ideal for a bar chart.",
    configHints: { orient: "vertical" },
  },
  {
    intent: "compare",
    condition: (cols, rows) => categoricalCount(cols) >= 1 && numericCount(cols) >= 1 && rows > 20,
    primary: "bar",
    alternatives: ["treemap", "funnel"],
    reasoning: "Many categories — a horizontal bar chart with scrollable axis is recommended.",
    configHints: { orient: "horizontal", dataZoom: true },
  },
  {
    intent: "compare",
    condition: (cols) => numericCount(cols) >= 3,
    primary: "radar",
    alternatives: ["bar", "parallel"],
    reasoning: "Multi-metric comparison across entities suits a radar chart.",
    configHints: {},
  },

  // ---- DISTRIBUTION --------------------------------------------------------
  {
    intent: "distribution",
    condition: (cols) => numericCount(cols) >= 1 && categoricalCount(cols) === 0,
    primary: "histogram",
    alternatives: ["boxplot", "scatter"],
    reasoning: "Continuous numeric distribution is best shown as a histogram.",
    configHints: { binCount: "auto" },
  },
  {
    intent: "distribution",
    condition: (cols) => numericCount(cols) >= 1 && categoricalCount(cols) >= 1,
    primary: "boxplot",
    alternatives: ["histogram", "scatter"],
    reasoning: "Distribution across categories suits a box plot for quartile visibility.",
    configHints: {},
  },

  // ---- COMPOSITION / PART-TO-WHOLE -----------------------------------------
  {
    intent: "composition",
    condition: (cols) => categoricalCount(cols) >= 1 && maxCategoricalCardinality(cols) <= 8,
    primary: "pie",
    alternatives: ["donut", "treemap", "funnel"],
    reasoning: "Part-to-whole with ≤8 categories is ideal for a pie chart.",
    configHints: { radius: "50%", label_show: true },
  },
  {
    intent: "composition",
    condition: (cols) => categoricalCount(cols) >= 1 && maxCategoricalCardinality(cols) > 8,
    primary: "treemap",
    alternatives: ["stacked_bar", "sunburst"],
    reasoning: "Many categories (>8) suit a treemap for hierarchical part-to-whole view.",
    configHints: {},
  },
  {
    intent: "part_to_whole",
    condition: (cols) => maxCategoricalCardinality(cols) <= 8,
    primary: "pie",
    alternatives: ["donut", "sunburst"],
    reasoning: "Part-to-whole with few categories maps directly to a pie chart.",
    configHints: { radius: "50%" },
  },
  {
    intent: "part_to_whole",
    condition: () => true,
    primary: "treemap",
    alternatives: ["sunburst", "stacked_bar"],
    reasoning: "Hierarchical part-to-whole with many segments uses a treemap.",
    configHints: {},
  },

  // ---- CORRELATION ---------------------------------------------------------
  {
    intent: "correlation",
    condition: (cols) => numericCount(cols) >= 2,
    primary: "scatter",
    alternatives: ["bubble", "heatmap"],
    reasoning: "Correlation between two numeric variables is most clearly shown as a scatter plot.",
    configHints: { trendline: false },
  },
  {
    intent: "correlation",
    condition: (cols) => numericCount(cols) >= 3,
    primary: "bubble",
    alternatives: ["scatter", "parallel"],
    reasoning: "Three-variable correlation uses bubble chart with size encoding the third dimension.",
    configHints: {},
  },

  // ---- RELATIONSHIP --------------------------------------------------------
  {
    intent: "relationship",
    condition: (cols) => numericCount(cols) >= 2,
    primary: "scatter",
    alternatives: ["bubble", "parallel"],
    reasoning: "Relationships between numeric dimensions suit a scatter plot.",
    configHints: {},
  },
  {
    intent: "relationship",
    condition: (cols) => categoricalCount(cols) >= 2,
    primary: "sankey",
    alternatives: ["heatmap"],
    reasoning: "Flow relationships between categorical dimensions suit a Sankey diagram.",
    configHints: {},
  },

  // ---- RANKING -------------------------------------------------------------
  {
    intent: "ranking",
    condition: (cols, rows) => categoricalCount(cols) >= 1 && rows <= 15,
    primary: "bar",
    alternatives: ["funnel"],
    reasoning: "Ranking up to 15 items is clearest as a sorted bar chart.",
    configHints: { sort: "descending", orient: "horizontal" },
  },
  {
    intent: "ranking",
    condition: () => true,
    primary: "treemap",
    alternatives: ["bar", "funnel"],
    reasoning: "Rankings with many items use a treemap to show relative size.",
    configHints: {},
  },

  // ---- FLOW ----------------------------------------------------------------
  {
    intent: "flow",
    condition: () => true,
    primary: "sankey",
    alternatives: ["funnel", "waterfall"],
    reasoning: "Flow data (source → target) is best visualised as a Sankey diagram.",
    configHints: {},
  },

  // ---- GEOGRAPHIC ----------------------------------------------------------
  {
    intent: "geographic",
    condition: (cols) => hasGeoColumns(cols) && numericCount(cols) >= 1,
    primary: "geo_choropleth",
    alternatives: ["geo_scatter"],
    reasoning: "Geographic data with a value metric suits a choropleth map.",
    configHints: { map: "world" },
  },
  {
    intent: "geographic",
    condition: () => true,
    primary: "geo_scatter",
    alternatives: ["geo_choropleth"],
    reasoning: "Geographic point data uses a geo scatter map.",
    configHints: {},
  },
];

/** Default fallback when no rule matches. */
function defaultSuggestion(
  columns: ColumnDescriptor[],
  rowCount: number
): { primary: ChartType; alternatives: ChartType[]; reasoning: string; configHints: Record<string, unknown> } {
  const nums = numericCount(columns);
  const cats = categoricalCount(columns);

  if (nums >= 2) {
    return {
      primary: "scatter",
      alternatives: ["line", "bar"],
      reasoning: `Defaulting to scatter for ${nums} numeric columns.`,
      configHints: {},
    };
  }
  if (cats >= 1 && nums >= 1) {
    return {
      primary: rowCount > 20 ? "bar" : "bar",
      alternatives: ["line", "pie"],
      reasoning: "Defaulting to bar chart for categorical + numeric data.",
      configHints: {},
    };
  }
  return {
    primary: "bar",
    alternatives: ["line", "scatter"],
    reasoning: "No specific pattern detected — defaulting to bar chart.",
    configHints: {},
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Suggest the best ECharts chart type based on data characteristics and intent.
 *
 * Uses a deterministic rule engine — no LLM required.
 *
 * @param input - SuggestChartTypeInput with columns, row_count, intent, tenant_id
 * @returns SuggestChartTypeOutput with primary suggestion and alternatives
 */
export function suggestChartType(
  input: SuggestChartTypeInput
): SuggestChartTypeOutput {
  const normIntent = normaliseIntent(input.intent);

  // Find first matching rule for this intent.
  const matchingRules = RULES.filter(
    (r) =>
      normaliseIntent(r.intent) === normIntent &&
      r.condition(input.columns, input.row_count)
  );

  if (matchingRules.length > 0) {
    const best = matchingRules[0]!;
    return {
      primary_suggestion: best.primary,
      alternatives: best.alternatives,
      reasoning: best.reasoning,
      config_hints: {
        ...best.configHints,
        row_count: input.row_count,
        numeric_columns: numericCount(input.columns),
        categorical_columns: categoricalCount(input.columns),
        has_time_column: hasTimeColumn(input.columns),
      },
    };
  }

  // No intent-specific rule matched — apply defaults.
  const fallback = defaultSuggestion(input.columns, input.row_count);
  return {
    primary_suggestion: fallback.primary,
    alternatives: fallback.alternatives,
    reasoning: `No rule matched for intent "${input.intent}". ${fallback.reasoning}`,
    config_hints: {
      ...fallback.configHints,
      row_count: input.row_count,
      numeric_columns: numericCount(input.columns),
      categorical_columns: categoricalCount(input.columns),
    },
  };
}
