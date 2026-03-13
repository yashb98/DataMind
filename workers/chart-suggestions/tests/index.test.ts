/**
 * index.test.ts — Unit tests for chart-suggestions worker.
 * Day 11: Vitest tests covering rule-based engine + edge cases.
 *
 * Run: npm test
 */

import { describe, it, expect } from "vitest";
import { suggestByRules } from "../src/rules";
import type { SuggestRequest } from "../src/types";

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function req(overrides: Partial<SuggestRequest> & Pick<SuggestRequest, "columns" | "intent">): SuggestRequest {
  return {
    row_count: 100,
    tenant_id: "test-tenant",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Trend intent
// ---------------------------------------------------------------------------

describe("suggestByRules — trend", () => {
  it("suggests line for trend intent with date column", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "date", type: "date", cardinality: 365 },
          { name: "revenue", type: "number", cardinality: 300 },
        ],
        row_count: 365,
        intent: "trend",
      }),
    );
    expect(result.primary_suggestion).toBe("line");
    expect(result.mode).toBe("rules");
    expect(result.latency_ms).toBeLessThan(5);
  });

  it("suggests mixed_bar_line when multiple numeric cols and date present", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "month", type: "date", cardinality: 12 },
          { name: "revenue", type: "number", cardinality: 12 },
          { name: "cost", type: "number", cardinality: 12 },
        ],
        intent: "trend",
      }),
    );
    expect(result.primary_suggestion).toBe("mixed_bar_line");
  });

  it("falls back to bar for trend when no date column exists", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "product", type: "string", cardinality: 10 },
          { name: "sales", type: "number", cardinality: 100 },
        ],
        intent: "trend",
      }),
    );
    expect(result.primary_suggestion).toBe("bar");
  });

  it("includes x_axis and y_axis config hints for trend", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "created_at", type: "date", cardinality: 100 },
          { name: "orders", type: "number", cardinality: 50 },
        ],
        intent: "trend",
      }),
    );
    expect(result.config_hints.x_axis).toBe("created_at");
    expect(result.config_hints.y_axis).toBe("orders");
  });
});

// ---------------------------------------------------------------------------
// Compare intent
// ---------------------------------------------------------------------------

describe("suggestByRules — compare", () => {
  it("suggests bar for single numeric compare", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "region", type: "string", cardinality: 5 },
          { name: "sales", type: "number", cardinality: 100 },
        ],
        intent: "compare",
      }),
    );
    expect(result.primary_suggestion).toBe("bar");
  });

  it("suggests stacked_bar for multi-metric compare", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "region", type: "string", cardinality: 5 },
          { name: "sales", type: "number", cardinality: 100 },
          { name: "profit", type: "number", cardinality: 80 },
        ],
        intent: "compare",
      }),
    );
    expect(result.primary_suggestion).toBe("stacked_bar");
  });
});

// ---------------------------------------------------------------------------
// Distribution intent
// ---------------------------------------------------------------------------

describe("suggestByRules — distribution", () => {
  it("suggests histogram for large datasets", () => {
    const result = suggestByRules(
      req({
        columns: [{ name: "age", type: "number", cardinality: 80 }],
        row_count: 5000,
        intent: "distribution",
      }),
    );
    expect(result.primary_suggestion).toBe("histogram");
  });

  it("suggests boxplot for small datasets", () => {
    const result = suggestByRules(
      req({
        columns: [{ name: "score", type: "number", cardinality: 50 }],
        row_count: 200,
        intent: "distribution",
      }),
    );
    expect(result.primary_suggestion).toBe("boxplot");
  });

  it("suggests pie when no numeric columns present", () => {
    const result = suggestByRules(
      req({
        columns: [{ name: "status", type: "string", cardinality: 4 }],
        row_count: 50,
        intent: "distribution",
      }),
    );
    expect(result.primary_suggestion).toBe("pie");
  });
});

// ---------------------------------------------------------------------------
// Composition intent
// ---------------------------------------------------------------------------

describe("suggestByRules — composition", () => {
  it("suggests pie for composition with few categories", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "category", type: "string", cardinality: 5 },
          { name: "value", type: "number", cardinality: 100 },
        ],
        intent: "composition",
      }),
    );
    expect(result.primary_suggestion).toBe("pie");
  });

  it("suggests donut for medium cardinality (9-20)", () => {
    const result = suggestByRules(
      req({
        columns: [{ name: "sub_category", type: "string", cardinality: 15 }],
        intent: "composition",
      }),
    );
    expect(result.primary_suggestion).toBe("donut");
  });

  it("suggests treemap for composition with many categories (>20)", () => {
    const result = suggestByRules(
      req({
        columns: [{ name: "product", type: "string", cardinality: 25 }],
        row_count: 500,
        intent: "composition",
      }),
    );
    expect(result.primary_suggestion).toBe("treemap");
  });

  it("also handles part_to_whole as composition alias", () => {
    const result = suggestByRules(
      req({
        columns: [{ name: "segment", type: "string", cardinality: 4 }],
        intent: "part_to_whole",
      }),
    );
    expect(result.primary_suggestion).toBe("pie");
  });
});

// ---------------------------------------------------------------------------
// Correlation / relationship intent
// ---------------------------------------------------------------------------

describe("suggestByRules — correlation", () => {
  it("suggests scatter for correlation with 2 numeric columns (large dataset)", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "x", type: "number", cardinality: 1000 },
          { name: "y", type: "number", cardinality: 1000 },
        ],
        row_count: 1000,
        intent: "correlation",
      }),
    );
    expect(result.primary_suggestion).toBe("scatter");
  });

  it("suggests bubble for correlation with small dataset", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "x", type: "number", cardinality: 20 },
          { name: "y", type: "number", cardinality: 20 },
        ],
        row_count: 100,
        intent: "correlation",
      }),
    );
    expect(result.primary_suggestion).toBe("bubble");
  });

  it("suggests heatmap when fewer than 2 numeric columns", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "category_a", type: "string", cardinality: 5 },
          { name: "category_b", type: "string", cardinality: 8 },
        ],
        intent: "correlation",
      }),
    );
    expect(result.primary_suggestion).toBe("heatmap");
  });

  it("also handles relationship as correlation alias", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "a", type: "number", cardinality: 100 },
          { name: "b", type: "number", cardinality: 100 },
        ],
        row_count: 600,
        intent: "relationship",
      }),
    );
    expect(result.primary_suggestion).toBe("scatter");
  });
});

// ---------------------------------------------------------------------------
// Ranking intent
// ---------------------------------------------------------------------------

describe("suggestByRules — ranking", () => {
  it("suggests bar for small ranking (<=20 items)", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "product", type: "string", cardinality: 10 },
          { name: "revenue", type: "number", cardinality: 10 },
        ],
        row_count: 10,
        intent: "ranking",
      }),
    );
    expect(result.primary_suggestion).toBe("bar");
  });

  it("suggests treemap for large ranking (>20 items)", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "product", type: "string", cardinality: 50 },
          { name: "revenue", type: "number", cardinality: 50 },
        ],
        row_count: 50,
        intent: "ranking",
      }),
    );
    expect(result.primary_suggestion).toBe("treemap");
  });

  it("includes aggregation: sum in config hints", () => {
    const result = suggestByRules(
      req({
        columns: [{ name: "product", type: "string", cardinality: 10 }],
        row_count: 10,
        intent: "ranking",
      }),
    );
    expect(result.config_hints.aggregation).toBe("sum");
  });
});

// ---------------------------------------------------------------------------
// Flow intent
// ---------------------------------------------------------------------------

describe("suggestByRules — flow", () => {
  it("suggests sankey for flow intent", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "source", type: "string", cardinality: 5 },
          { name: "target", type: "string", cardinality: 8 },
          { name: "value", type: "number", cardinality: 40 },
        ],
        row_count: 40,
        intent: "flow",
      }),
    );
    expect(result.primary_suggestion).toBe("sankey");
  });
});

// ---------------------------------------------------------------------------
// Geographic intent
// ---------------------------------------------------------------------------

describe("suggestByRules — geographic", () => {
  it("suggests geo_choropleth for geographic with geo column", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "country", type: "geo", cardinality: 50 },
          { name: "revenue", type: "number", cardinality: 200 },
        ],
        row_count: 50,
        intent: "geographic",
      }),
    );
    expect(result.primary_suggestion).toBe("geo_choropleth");
  });

  it("detects geo column by name pattern (lat/lng)", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "latitude", type: "number", cardinality: 100 },
          { name: "longitude", type: "number", cardinality: 100 },
        ],
        intent: "geographic",
      }),
    );
    // latitude matches the /lat/ pattern → geoCol found → choropleth
    expect(result.primary_suggestion).toBe("geo_choropleth");
  });

  it("suggests geo_scatter when no geo column found", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "x_coord", type: "number", cardinality: 50 },
          { name: "y_coord", type: "number", cardinality: 50 },
        ],
        intent: "geographic",
      }),
    );
    expect(result.primary_suggestion).toBe("geo_scatter");
  });
});

// ---------------------------------------------------------------------------
// Unknown / default intent
// ---------------------------------------------------------------------------

describe("suggestByRules — default fallback", () => {
  it("falls back to bar for unknown intent with category + numeric", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "product", type: "string", cardinality: 10 },
          { name: "sales", type: "number", cardinality: 100 },
        ],
        intent: "unknown_xyz",
      }),
    );
    expect(result.primary_suggestion).toBe("bar");
  });

  it("falls back to line for unknown intent with date + numeric", () => {
    const result = suggestByRules(
      req({
        columns: [
          { name: "event_time", type: "date", cardinality: 50 },
          { name: "count", type: "number", cardinality: 50 },
        ],
        intent: "unknown_xyz",
      }),
    );
    expect(result.primary_suggestion).toBe("line");
  });

  it("falls back to table for unknown intent with only string columns", () => {
    const result = suggestByRules(
      req({
        columns: [{ name: "name", type: "string", cardinality: 100 }],
        intent: "unknown_xyz",
      }),
    );
    expect(result.primary_suggestion).toBe("table");
  });
});

// ---------------------------------------------------------------------------
// Shared invariants
// ---------------------------------------------------------------------------

describe("suggestByRules — invariants", () => {
  it("returns alternatives array with <= 3 items", () => {
    const result = suggestByRules(
      req({
        columns: [{ name: "x", type: "number", cardinality: 100 }],
        intent: "distribution",
      }),
    );
    expect(result.alternatives.length).toBeLessThanOrEqual(3);
  });

  it("alternatives never contain the primary suggestion", () => {
    const intents = [
      "trend",
      "compare",
      "distribution",
      "composition",
      "correlation",
      "ranking",
      "flow",
      "geographic",
      "unknown",
    ];
    for (const intent of intents) {
      const result = suggestByRules(
        req({
          columns: [
            { name: "a", type: "string", cardinality: 5 },
            { name: "b", type: "number", cardinality: 100 },
          ],
          intent,
        }),
      );
      expect(result.alternatives).not.toContain(result.primary_suggestion);
    }
  });

  it("always returns mode === 'rules'", () => {
    const result = suggestByRules(
      req({
        columns: [{ name: "x", type: "number", cardinality: 50 }],
        intent: "distribution",
      }),
    );
    expect(result.mode).toBe("rules");
  });

  it("latency_ms is a non-negative number", () => {
    const result = suggestByRules(
      req({
        columns: [{ name: "x", type: "number", cardinality: 50 }],
        intent: "trend",
      }),
    );
    expect(result.latency_ms).toBeGreaterThanOrEqual(0);
  });

  it("latency_ms is < 5ms (deterministic rules must be fast)", () => {
    const result = suggestByRules(
      req({
        columns: Array.from({ length: 10 }, (_, i) => ({
          name: `col_${i}`,
          type: i % 2 === 0 ? "number" : "string",
          cardinality: 100,
        })),
        intent: "compare",
      }),
    );
    expect(result.latency_ms).toBeLessThan(5);
  });

  it("config_hints is always an object", () => {
    const result = suggestByRules(
      req({
        columns: [{ name: "x", type: "string", cardinality: 5 }],
        intent: "flow",
      }),
    );
    expect(typeof result.config_hints).toBe("object");
    expect(result.config_hints).not.toBeNull();
  });

  it("reasoning is a non-empty string", () => {
    const result = suggestByRules(
      req({
        columns: [{ name: "x", type: "string", cardinality: 5 }],
        intent: "compare",
      }),
    );
    expect(typeof result.reasoning).toBe("string");
    expect(result.reasoning.length).toBeGreaterThan(0);
  });
});
