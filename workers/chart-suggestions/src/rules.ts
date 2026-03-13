/**
 * rules.ts — Deterministic rule-based chart suggestion engine.
 * Day 11: Pure rules fallback guaranteeing < 1ms latency at the edge.
 *
 * Protocols: None (pure logic, no I/O)
 * SOLID: SRP — only determines chart type; OCP — new intents = new case branch
 * Benchmark: tests/benchmarks/bench_rules.ts (target < 1ms p99)
 */

import type { SuggestRequest, SuggestResponse } from "./types";

/**
 * Suggest a chart type using deterministic rules derived from column types,
 * cardinality, row count, and user intent.
 *
 * @param req - Validated suggest request
 * @returns SuggestResponse with mode === "rules"
 */
export function suggestByRules(req: SuggestRequest): SuggestResponse {
  const { columns, row_count, intent } = req;
  const start = Date.now();

  const timeCol = columns.find(
    (c) =>
      c.type === "date" ||
      /date|time|month|year|week|day/.test(c.name.toLowerCase()),
  );
  const numCols = columns.filter((c) => c.type === "number");
  const catCols = columns.filter((c) => c.type === "string");
  const geoCol = columns.find(
    (c) =>
      c.type === "geo" ||
      /lat|lng|longitude|latitude|country|region|city|zip/.test(
        c.name.toLowerCase(),
      ),
  );

  let primary: string;
  let alternatives: string[];
  let reasoning: string;
  let config_hints: SuggestResponse["config_hints"] = {};

  switch (intent) {
    case "trend":
      primary = timeCol
        ? numCols.length > 1
          ? "mixed_bar_line"
          : "line"
        : "bar";
      alternatives = ["area", "stacked_area", "bar"];
      reasoning = timeCol
        ? `Time column '${timeCol.name}' detected — line chart best shows trends over time.`
        : "No time column found — bar chart used as fallback.";
      config_hints = { x_axis: timeCol?.name, y_axis: numCols[0]?.name };
      break;

    case "compare":
      primary =
        catCols.length > 0
          ? numCols.length > 1
            ? "stacked_bar"
            : "bar"
          : "bar";
      alternatives = ["horizontal_bar", "radar", "scatter"];
      reasoning = `Comparing ${catCols[0]?.name ?? "categories"} across ${numCols[0]?.name ?? "metrics"}.`;
      config_hints = { x_axis: catCols[0]?.name, y_axis: numCols[0]?.name };
      break;

    case "distribution":
      primary =
        numCols.length > 0 ? (row_count > 1000 ? "histogram" : "boxplot") : "pie";
      alternatives = ["histogram", "boxplot", "scatter"];
      reasoning =
        row_count > 1000
          ? `Large dataset (${row_count} rows) — histogram shows distribution efficiently.`
          : "Boxplot for smaller datasets to show quartiles and outliers.";
      config_hints = { x_axis: numCols[0]?.name };
      break;

    case "composition":
    case "part_to_whole": {
      const catCardinality = catCols[0]?.cardinality ?? 0;
      primary =
        catCardinality <= 8
          ? "pie"
          : catCardinality <= 20
            ? "donut"
            : "treemap";
      alternatives = ["donut", "treemap", "sunburst", "stacked_bar"];
      reasoning = `${catCardinality} categories — ${primary} chosen for clarity.`;
      config_hints = { color_by: catCols[0]?.name };
      break;
    }

    case "correlation":
    case "relationship":
      primary =
        numCols.length >= 2
          ? row_count > 500
            ? "scatter"
            : "bubble"
          : "heatmap";
      alternatives = ["scatter", "heatmap", "parallel"];
      reasoning =
        numCols.length >= 2
          ? `Two numeric columns (${numCols[0]?.name}, ${numCols[1]?.name}) — scatter shows correlation.`
          : "Heatmap for categorical correlation matrix.";
      config_hints = {
        x_axis: numCols[0]?.name,
        y_axis: numCols[1]?.name,
      };
      break;

    case "ranking":
      primary = row_count <= 20 ? "bar" : "treemap";
      alternatives = ["bar", "funnel", "treemap"];
      reasoning = `Ranked data with ${row_count} items — ${primary} is most readable.`;
      config_hints = {
        x_axis: numCols[0]?.name,
        y_axis: catCols[0]?.name,
        aggregation: "sum",
      };
      break;

    case "flow":
      primary = "sankey";
      alternatives = ["funnel", "bar"];
      reasoning =
        "Flow/funnel intent — Sankey diagram shows value flow between stages.";
      break;

    case "geographic":
      primary = geoCol ? "geo_choropleth" : "geo_scatter";
      alternatives = ["geo_scatter", "geo_choropleth", "bubble"];
      reasoning = geoCol
        ? `Geographic column '${geoCol.name}' detected — choropleth map for regional density.`
        : "Geo scatter for point-based geographic data.";
      config_hints = { color_by: numCols[0]?.name };
      break;

    default:
      // Generic fallback based on column types
      if (timeCol && numCols.length > 0) {
        primary = "line";
        alternatives = ["bar", "area"];
        reasoning = "Default: time + numeric = line chart.";
      } else if (catCols.length > 0 && numCols.length > 0) {
        primary = "bar";
        alternatives = ["horizontal_bar", "treemap"];
        reasoning = "Default: category + numeric = bar chart.";
      } else {
        primary = "table";
        alternatives = ["bar", "scatter"];
        reasoning =
          "Complex or unknown data structure — table view recommended.";
      }
  }

  return {
    primary_suggestion: primary,
    alternatives: alternatives
      .filter((a) => a !== primary)
      .slice(0, 3),
    reasoning,
    latency_ms: Date.now() - start,
    mode: "rules",
    config_hints,
  };
}
