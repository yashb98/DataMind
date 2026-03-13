/**
 * renderChart — ECharts 5 option generator for 25 chart types.
 * Day 11: MCP Visualization Server — render_chart tool.
 *
 * Protocols: MCP
 * SOLID: SRP (only chart config generation), OCP (new chart type = new case, no existing edits needed)
 * Benchmark: tests/benchmarks/bench_render_chart.ts
 */

import type {
  ChartType,
  DataRow,
  EChartsOption,
  RenderChartInput,
  RenderChartOutput,
  ToolError,
} from "../types.js";
import { SUPPORTED_CHART_TYPES } from "../types.js";

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/** Extract unique values of a key from data rows (coerced to string). */
function uniqueValues(data: DataRow[], key: string): string[] {
  const seen = new Set<string>();
  for (const row of data) {
    const val = row[key];
    if (val !== null && val !== undefined) seen.add(String(val));
  }
  return Array.from(seen);
}

/** Detect the x-axis key: first string/date column, or first column. */
function detectXKey(data: DataRow[]): string {
  if (data.length === 0) return "x";
  const firstRow = data[0];
  if (!firstRow) return "x";
  const keys = Object.keys(firstRow);
  for (const k of keys) {
    if (typeof firstRow[k] === "string") return k;
  }
  return keys[0] ?? "x";
}

/** Detect numeric (y-axis) keys from a data row. */
function detectNumericKeys(data: DataRow[]): string[] {
  if (data.length === 0) return ["y"];
  const firstRow = data[0];
  if (!firstRow) return ["y"];
  return Object.keys(firstRow).filter((k) => typeof firstRow[k] === "number");
}

/** Detect series key: a string column that is not the x-axis key. */
function detectSeriesKey(data: DataRow[], xKey: string): string | null {
  if (data.length === 0) return null;
  const firstRow = data[0];
  if (!firstRow) return null;
  for (const [k, v] of Object.entries(firstRow)) {
    if (k !== xKey && typeof v === "string") return k;
  }
  return null;
}

/** Group data by series key, returning { seriesName: DataRow[] }. */
function groupBySeries(
  data: DataRow[],
  seriesKey: string
): Map<string, DataRow[]> {
  const groups = new Map<string, DataRow[]>();
  for (const row of data) {
    const key = String(row[seriesKey] ?? "default");
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(row);
  }
  return groups;
}

/** Build a series entry for bar/line/area charts. */
function buildCartesianSeries(
  name: string,
  type: "bar" | "line",
  xValues: string[],
  data: DataRow[],
  yKey: string,
  smooth?: boolean,
  areaStyle?: boolean
): Record<string, unknown> {
  const xIndex = new Map<string, DataRow>();
  const xKey = detectXKey(data);
  for (const row of data) xIndex.set(String(row[xKey] ?? ""), row);
  const values = xValues.map((xv) => {
    const row = xIndex.get(xv);
    return row ? (row[yKey] ?? 0) : 0;
  });
  const series: Record<string, unknown> = { name, type, data: values };
  if (smooth !== undefined) series["smooth"] = smooth;
  if (areaStyle) series["areaStyle"] = {};
  return series;
}

// ---------------------------------------------------------------------------
// Chart builders (one per chart type)
// ---------------------------------------------------------------------------

function buildBar(data: DataRow[], title: string): EChartsOption {
  const xKey = detectXKey(data);
  const numericKeys = detectNumericKeys(data);
  const seriesKey = detectSeriesKey(data, xKey);
  const xValues = uniqueValues(data, xKey);

  if (seriesKey) {
    const groups = groupBySeries(data, seriesKey);
    const seriesNames = Array.from(groups.keys());
    const yKey = numericKeys[0] ?? "y";
    const series = seriesNames.map((name) =>
      buildCartesianSeries(name, "bar", xValues, groups.get(name)!, yKey)
    );
    return {
      title: { text: title },
      tooltip: { trigger: "axis" },
      legend: { data: seriesNames },
      xAxis: { type: "category", data: xValues },
      yAxis: { type: "value" },
      series,
    };
  }

  const yKey = numericKeys[0] ?? "y";
  const yValues = xValues.map((xv) => {
    const row = data.find((r) => String(r[xKey]) === xv);
    return row ? (row[yKey] ?? 0) : 0;
  });
  return {
    title: { text: title },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: xValues },
    yAxis: { type: "value" },
    series: [{ name: yKey, type: "bar", data: yValues }],
  };
}

function buildLine(
  data: DataRow[],
  title: string,
  areaStyle = false
): EChartsOption {
  const xKey = detectXKey(data);
  const numericKeys = detectNumericKeys(data);
  const seriesKey = detectSeriesKey(data, xKey);
  const xValues = uniqueValues(data, xKey);

  if (seriesKey) {
    const groups = groupBySeries(data, seriesKey);
    const seriesNames = Array.from(groups.keys());
    const yKey = numericKeys[0] ?? "y";
    const series = seriesNames.map((name) =>
      buildCartesianSeries(
        name,
        "line",
        xValues,
        groups.get(name)!,
        yKey,
        true,
        areaStyle
      )
    );
    return {
      title: { text: title },
      tooltip: { trigger: "axis" },
      legend: { data: seriesNames },
      xAxis: { type: "category", data: xValues },
      yAxis: { type: "value" },
      series,
    };
  }

  const yKey = numericKeys[0] ?? "y";
  const yValues = xValues.map((xv) => {
    const row = data.find((r) => String(r[xKey]) === xv);
    return row ? (row[yKey] ?? 0) : 0;
  });
  const s: Record<string, unknown> = {
    name: yKey,
    type: "line",
    smooth: true,
    data: yValues,
  };
  if (areaStyle) s["areaStyle"] = {};
  return {
    title: { text: title },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: xValues },
    yAxis: { type: "value" },
    series: [s],
  };
}

function buildPie(
  data: DataRow[],
  title: string,
  radius: string | [string, string] = "50%"
): EChartsOption {
  const xKey = detectXKey(data);
  const numericKeys = detectNumericKeys(data);
  const yKey = numericKeys[0] ?? "y";
  const pieData = data.map((row) => ({
    value: row[yKey] ?? 0,
    name: String(row[xKey] ?? ""),
  }));
  return {
    title: { text: title },
    tooltip: { trigger: "item" },
    legend: { orient: "vertical", left: "left" },
    series: [
      {
        type: "pie",
        radius,
        data: pieData,
        emphasis: {
          itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: "rgba(0,0,0,0.5)" },
        },
      },
    ],
  };
}

function buildScatter(data: DataRow[], title: string): EChartsOption {
  const numericKeys = detectNumericKeys(data);
  const xKey = numericKeys[0] ?? "x";
  const yKey = numericKeys[1] ?? "y";
  const seriesKey = detectSeriesKey(data, xKey);

  if (seriesKey) {
    const groups = groupBySeries(data, seriesKey);
    const seriesNames = Array.from(groups.keys());
    const series = seriesNames.map((name) => ({
      name,
      type: "scatter",
      data: groups.get(name)!.map((r) => [r[xKey] ?? 0, r[yKey] ?? 0]),
    }));
    return {
      title: { text: title },
      tooltip: { trigger: "item" },
      legend: { data: seriesNames },
      xAxis: { type: "value", name: xKey },
      yAxis: { type: "value", name: yKey },
      series,
    };
  }

  const scatterData = data.map((r) => [r[xKey] ?? 0, r[yKey] ?? 0]);
  return {
    title: { text: title },
    tooltip: { trigger: "item" },
    xAxis: { type: "value", name: xKey },
    yAxis: { type: "value", name: yKey },
    series: [{ type: "scatter", data: scatterData }],
  };
}

function buildBubble(data: DataRow[], title: string): EChartsOption {
  const numericKeys = detectNumericKeys(data);
  const xKey = numericKeys[0] ?? "x";
  const yKey = numericKeys[1] ?? "y";
  const sizeKey = numericKeys[2] ?? yKey;
  const bubbleData = data.map((r) => [r[xKey] ?? 0, r[yKey] ?? 0, r[sizeKey] ?? 10]);
  return {
    title: { text: title },
    tooltip: { trigger: "item" },
    xAxis: { type: "value", name: xKey },
    yAxis: { type: "value", name: yKey },
    series: [
      {
        type: "scatter",
        data: bubbleData,
        symbolSize: (val: number[]) => Math.sqrt(Math.abs(val[2] ?? 10)) * 5,
      },
    ],
  };
}

function buildHeatmap(data: DataRow[], title: string): EChartsOption {
  const keys = data.length > 0 ? Object.keys(data[0]!) : ["x", "y", "value"];
  const xKey = keys[0] ?? "x";
  const yKey = keys[1] ?? "y";
  const valueKey = keys[2] ?? "value";
  const xValues = uniqueValues(data, xKey);
  const yValues = uniqueValues(data, yKey);
  const heatData = data.map((r) => [
    xValues.indexOf(String(r[xKey] ?? "")),
    yValues.indexOf(String(r[yKey] ?? "")),
    r[valueKey] ?? 0,
  ]);
  const numericVals = data.map((r) => Number(r[valueKey] ?? 0));
  const minVal = Math.min(...numericVals);
  const maxVal = Math.max(...numericVals);
  return {
    title: { text: title },
    tooltip: { position: "top" },
    grid: { height: "50%", top: "10%" },
    xAxis: { type: "category", data: xValues, splitArea: { show: true } },
    yAxis: { type: "category", data: yValues, splitArea: { show: true } },
    visualMap: {
      min: minVal,
      max: maxVal,
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: "15%",
    },
    series: [
      {
        type: "heatmap",
        data: heatData,
        label: { show: true },
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: "rgba(0,0,0,0.5)" } },
      },
    ],
  };
}

function buildTreemap(data: DataRow[], title: string): EChartsOption {
  const xKey = detectXKey(data);
  const numericKeys = detectNumericKeys(data);
  const valueKey = numericKeys[0] ?? "value";
  const treemapData = data.map((r) => ({
    name: String(r[xKey] ?? ""),
    value: Number(r[valueKey] ?? 0),
  }));
  return {
    title: { text: title },
    tooltip: { trigger: "item" },
    series: [
      {
        type: "treemap",
        data: treemapData,
        label: { show: true, formatter: "{b}: {c}" },
      },
    ],
  };
}

function buildFunnel(data: DataRow[], title: string): EChartsOption {
  const xKey = detectXKey(data);
  const numericKeys = detectNumericKeys(data);
  const valueKey = numericKeys[0] ?? "value";
  const funnelData = data.map((r) => ({
    value: Number(r[valueKey] ?? 0),
    name: String(r[xKey] ?? ""),
  }));
  return {
    title: { text: title },
    tooltip: { trigger: "item", formatter: "{a} <br/>{b}: {c}" },
    series: [
      {
        name: title,
        type: "funnel",
        left: "10%",
        width: "80%",
        label: { formatter: "{b}({c})" },
        data: funnelData,
      },
    ],
  };
}

function buildGauge(data: DataRow[], title: string): EChartsOption {
  const numericKeys = detectNumericKeys(data);
  const valueKey = numericKeys[0] ?? "value";
  const value = data.length > 0 ? Number(data[0]![valueKey] ?? 0) : 0;
  return {
    title: { text: title },
    tooltip: { formatter: "{a} <br/>{b}: {c}%" },
    series: [
      {
        name: title,
        type: "gauge",
        detail: { formatter: "{value}%" },
        data: [{ value, name: title }],
      },
    ],
  };
}

function buildRadar(data: DataRow[], title: string): EChartsOption {
  if (data.length === 0) {
    return { title: { text: title }, series: [] };
  }
  const keys = Object.keys(data[0]!);
  const numericKeys = detectNumericKeys(data);
  const labelKey = keys.find((k) => !numericKeys.includes(k)) ?? keys[0] ?? "name";
  const indicators = numericKeys.map((k) => ({
    name: k,
    max: Math.max(...data.map((r) => Number(r[k] ?? 0))) * 1.2,
  }));
  const seriesData = data.map((r) => ({
    name: String(r[labelKey] ?? ""),
    value: numericKeys.map((k) => Number(r[k] ?? 0)),
  }));
  return {
    title: { text: title },
    tooltip: {},
    legend: { data: seriesData.map((s) => s.name) },
    radar: { indicator: indicators },
    series: [{ type: "radar", data: seriesData }],
  };
}

function buildSankey(data: DataRow[], title: string): EChartsOption {
  const keys = data.length > 0 ? Object.keys(data[0]!) : ["source", "target", "value"];
  const sourceKey = keys[0] ?? "source";
  const targetKey = keys[1] ?? "target";
  const valueKey = keys[2] ?? "value";
  const nodeSet = new Set<string>();
  const links = data.map((r) => {
    const src = String(r[sourceKey] ?? "");
    const tgt = String(r[targetKey] ?? "");
    nodeSet.add(src);
    nodeSet.add(tgt);
    return { source: src, target: tgt, value: Number(r[valueKey] ?? 0) };
  });
  const nodes = Array.from(nodeSet).map((name) => ({ name }));
  return {
    title: { text: title },
    tooltip: { trigger: "item", triggerOn: "mousemove" },
    series: [{ type: "sankey", data: nodes, links, emphasis: { focus: "adjacency" } }],
  };
}

function buildCandlestick(data: DataRow[], title: string): EChartsOption {
  const keys = data.length > 0 ? Object.keys(data[0]!) : ["date", "open", "close", "low", "high"];
  const dateKey = keys[0] ?? "date";
  const openKey = keys[1] ?? "open";
  const closeKey = keys[2] ?? "close";
  const lowKey = keys[3] ?? "low";
  const highKey = keys[4] ?? "high";
  const dates = data.map((r) => String(r[dateKey] ?? ""));
  const ohlc = data.map((r) => [
    Number(r[openKey] ?? 0),
    Number(r[closeKey] ?? 0),
    Number(r[lowKey] ?? 0),
    Number(r[highKey] ?? 0),
  ]);
  return {
    title: { text: title },
    tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
    xAxis: { type: "category", data: dates, scale: true },
    yAxis: { type: "value", scale: true },
    dataZoom: [
      { type: "inside", start: 50, end: 100 },
      { start: 50, end: 100 },
    ],
    series: [{ type: "candlestick", data: ohlc }],
  };
}

function buildHistogram(data: DataRow[], title: string): EChartsOption {
  const numericKeys = detectNumericKeys(data);
  const valueKey = numericKeys[0] ?? "value";
  const values = data.map((r) => Number(r[valueKey] ?? 0)).sort((a, b) => a - b);
  const binCount = Math.max(5, Math.min(50, Math.ceil(Math.sqrt(values.length))));
  const minVal = values[0] ?? 0;
  const maxVal = values[values.length - 1] ?? 1;
  const binWidth = (maxVal - minVal) / binCount || 1;
  const bins: number[] = new Array(binCount).fill(0);
  for (const v of values) {
    const idx = Math.min(Math.floor((v - minVal) / binWidth), binCount - 1);
    bins[idx]!++;
  }
  const xLabels = bins.map((_, i) =>
    `${(minVal + i * binWidth).toFixed(1)}-${(minVal + (i + 1) * binWidth).toFixed(1)}`
  );
  return {
    title: { text: title },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: xLabels },
    yAxis: { type: "value", name: "Count" },
    series: [{ name: "Frequency", type: "bar", data: bins, barWidth: "99.3%" }],
  };
}

function buildBoxplot(data: DataRow[], title: string): EChartsOption {
  const numericKeys = detectNumericKeys(data);
  const xKey = detectXKey(data);
  const yKey = numericKeys[0] ?? "value";
  const groups = groupBySeries(data, xKey);
  const categories = Array.from(groups.keys());
  const boxData = categories.map((cat) => {
    const vals = (groups.get(cat) ?? [])
      .map((r) => Number(r[yKey] ?? 0))
      .sort((a, b) => a - b);
    if (vals.length === 0) return [0, 0, 0, 0, 0];
    const q1 = vals[Math.floor(vals.length * 0.25)] ?? 0;
    const q2 = vals[Math.floor(vals.length * 0.5)] ?? 0;
    const q3 = vals[Math.floor(vals.length * 0.75)] ?? 0;
    return [vals[0] ?? 0, q1, q2, q3, vals[vals.length - 1] ?? 0];
  });
  return {
    title: { text: title },
    tooltip: { trigger: "item", axisPointer: { type: "shadow" } },
    xAxis: { type: "category", data: categories },
    yAxis: { type: "value" },
    series: [{ type: "boxplot", data: boxData }],
  };
}

function buildParallel(data: DataRow[], title: string): EChartsOption {
  if (data.length === 0) return { title: { text: title }, series: [] };
  const numericKeys = detectNumericKeys(data);
  const parallelAxis = numericKeys.map((k, i) => ({
    dim: i,
    name: k,
  }));
  const parallelData = data.map((r) => numericKeys.map((k) => Number(r[k] ?? 0)));
  return {
    title: { text: title },
    parallelAxis,
    series: [{ type: "parallel", data: parallelData }],
  };
}

function buildGeoChloropleth(data: DataRow[], title: string): EChartsOption {
  const keys = data.length > 0 ? Object.keys(data[0]!) : ["region", "value"];
  const regionKey = keys[0] ?? "region";
  const numericKeys = detectNumericKeys(data);
  const valueKey = numericKeys[0] ?? "value";
  const mapData = data.map((r) => ({
    name: String(r[regionKey] ?? ""),
    value: Number(r[valueKey] ?? 0),
  }));
  const values = mapData.map((d) => d.value);
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  return {
    title: { text: title },
    tooltip: { trigger: "item" },
    visualMap: { left: "right", min: minVal, max: maxVal, inRange: { color: ["#eee", "#00449e"] } },
    series: [{ type: "map", map: "world", data: mapData }],
  };
}

function buildGeoScatter(data: DataRow[], title: string): EChartsOption {
  const keys = data.length > 0 ? Object.keys(data[0]!) : ["lng", "lat", "value", "name"];
  const lngKey = keys[0] ?? "lng";
  const latKey = keys[1] ?? "lat";
  const numericKeys = detectNumericKeys(data);
  const valueKey = numericKeys.find((k) => k !== lngKey && k !== latKey) ?? numericKeys[0] ?? "value";
  const nameKey = keys.find((k) => typeof data[0]?.[k] === "string") ?? keys[3] ?? "name";
  const scatterData = data.map((r) => ({
    name: String(r[nameKey] ?? ""),
    value: [Number(r[lngKey] ?? 0), Number(r[latKey] ?? 0), Number(r[valueKey] ?? 0)],
  }));
  return {
    title: { text: title },
    tooltip: { trigger: "item" },
    geo: { map: "world", roam: true, itemStyle: { areaColor: "#e7e8ea", borderColor: "#555" } },
    series: [{ type: "scatter", coordinateSystem: "geo", data: scatterData, symbolSize: 5 }],
  };
}

function buildWaterfall(data: DataRow[], title: string): EChartsOption {
  const xKey = detectXKey(data);
  const numericKeys = detectNumericKeys(data);
  const valueKey = numericKeys[0] ?? "value";
  const categories = uniqueValues(data, xKey);
  const rawValues = categories.map((cat) => {
    const row = data.find((r) => String(r[xKey]) === cat);
    return Number(row?.[valueKey] ?? 0);
  });
  let running = 0;
  const placeholder: number[] = [];
  const bar: number[] = [];
  for (const v of rawValues) {
    placeholder.push(v >= 0 ? running : running + v);
    bar.push(Math.abs(v));
    running += v;
  }
  return {
    title: { text: title },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: { type: "category", data: categories },
    yAxis: { type: "value" },
    series: [
      { type: "bar", stack: "waterfall", itemStyle: { opacity: 0 }, data: placeholder },
      { name: title, type: "bar", stack: "waterfall", data: bar },
    ],
  };
}

function buildStackedBar(data: DataRow[], title: string): EChartsOption {
  const xKey = detectXKey(data);
  const numericKeys = detectNumericKeys(data);
  const seriesKey = detectSeriesKey(data, xKey);
  const xValues = uniqueValues(data, xKey);

  if (seriesKey) {
    const groups = groupBySeries(data, seriesKey);
    const seriesNames = Array.from(groups.keys());
    const yKey = numericKeys[0] ?? "y";
    const series = seriesNames.map((name) => ({
      name,
      type: "bar",
      stack: "total",
      data: xValues.map((xv) => {
        const row = groups.get(name)?.find((r) => String(r[xKey]) === xv);
        return row ? (row[yKey] ?? 0) : 0;
      }),
    }));
    return {
      title: { text: title },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      legend: { data: seriesNames },
      xAxis: { type: "category", data: xValues },
      yAxis: { type: "value" },
      series,
    };
  }

  return buildBar(data, title);
}

function buildStackedArea(data: DataRow[], title: string): EChartsOption {
  const xKey = detectXKey(data);
  const numericKeys = detectNumericKeys(data);
  const seriesKey = detectSeriesKey(data, xKey);
  const xValues = uniqueValues(data, xKey);

  if (seriesKey) {
    const groups = groupBySeries(data, seriesKey);
    const seriesNames = Array.from(groups.keys());
    const yKey = numericKeys[0] ?? "y";
    const series = seriesNames.map((name) => ({
      name,
      type: "line",
      stack: "total",
      smooth: true,
      areaStyle: {},
      data: xValues.map((xv) => {
        const row = groups.get(name)?.find((r) => String(r[xKey]) === xv);
        return row ? (row[yKey] ?? 0) : 0;
      }),
    }));
    return {
      title: { text: title },
      tooltip: { trigger: "axis" },
      legend: { data: seriesNames },
      xAxis: { type: "category", data: xValues },
      yAxis: { type: "value" },
      series,
    };
  }

  return buildLine(data, title, true);
}

function buildMixedBarLine(data: DataRow[], title: string): EChartsOption {
  const xKey = detectXKey(data);
  const numericKeys = detectNumericKeys(data);
  const xValues = uniqueValues(data, xKey);
  const yKey1 = numericKeys[0] ?? "y1";
  const yKey2 = numericKeys[1] ?? yKey1;
  const bar1Values = xValues.map((xv) => {
    const row = data.find((r) => String(r[xKey]) === xv);
    return row ? (row[yKey1] ?? 0) : 0;
  });
  const line2Values = xValues.map((xv) => {
    const row = data.find((r) => String(r[xKey]) === xv);
    return row ? (row[yKey2] ?? 0) : 0;
  });
  return {
    title: { text: title },
    tooltip: { trigger: "axis" },
    legend: { data: [yKey1, yKey2] },
    xAxis: { type: "category", data: xValues },
    yAxis: [
      { type: "value", name: yKey1 },
      { type: "value", name: yKey2, position: "right" },
    ],
    series: [
      { name: yKey1, type: "bar", data: bar1Values },
      { name: yKey2, type: "line", smooth: true, yAxisIndex: 1, data: line2Values },
    ],
  };
}

function buildWordCloud(data: DataRow[], title: string): EChartsOption {
  const xKey = detectXKey(data);
  const numericKeys = detectNumericKeys(data);
  const valueKey = numericKeys[0] ?? "value";
  const wordData = data.map((r) => ({
    name: String(r[xKey] ?? ""),
    value: Number(r[valueKey] ?? 0),
  }));
  return {
    title: { text: title },
    tooltip: {},
    series: [
      {
        type: "wordCloud",
        sizeRange: [12, 60],
        rotationRange: [-90, 90],
        shape: "circle",
        data: wordData,
      },
    ],
  };
}

function buildSunburst(data: DataRow[], title: string): EChartsOption {
  const keys = data.length > 0 ? Object.keys(data[0]!) : ["name", "parent", "value"];
  const nameKey = keys[0] ?? "name";
  const numericKeys = detectNumericKeys(data);
  const valueKey = numericKeys[0] ?? "value";
  const parentKey = keys.find((k) => k !== nameKey && typeof data[0]?.[k] === "string") ?? keys[1] ?? "parent";

  const nodeMap = new Map<string, { name: string; value: number; children: unknown[] }>();
  for (const row of data) {
    const name = String(row[nameKey] ?? "");
    nodeMap.set(name, { name, value: Number(row[valueKey] ?? 0), children: [] });
  }
  const roots: unknown[] = [];
  for (const row of data) {
    const name = String(row[nameKey] ?? "");
    const parent = String(row[parentKey] ?? "");
    if (parent === "" || parent === name || !nodeMap.has(parent)) {
      roots.push(nodeMap.get(name));
    } else {
      nodeMap.get(parent)?.children.push(nodeMap.get(name));
    }
  }
  return {
    title: { text: title },
    tooltip: {},
    series: [{ type: "sunburst", data: roots, radius: [0, "90%"], label: { rotate: "radial" } }],
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Generate an ECharts 5 option object for the given chart type and data.
 *
 * @param input - RenderChartInput with chart_type, data, title, tenant_id, options
 * @returns RenderChartOutput or ToolError
 */
export function renderChart(
  input: RenderChartInput
): RenderChartOutput | ToolError {
  const chartType = input.chart_type as ChartType;

  if (!SUPPORTED_CHART_TYPES.includes(chartType)) {
    return {
      error: `Unsupported chart type: "${input.chart_type}"`,
      code: "UNSUPPORTED_CHART_TYPE",
      details: `Supported types: ${SUPPORTED_CHART_TYPES.join(", ")}`,
    };
  }

  if (!Array.isArray(input.data)) {
    return {
      error: "data must be an array of objects",
      code: "INVALID_DATA",
    };
  }

  let chartConfig: EChartsOption;

  switch (chartType) {
    case "bar":
      chartConfig = buildBar(input.data, input.title);
      break;
    case "line":
      chartConfig = buildLine(input.data, input.title);
      break;
    case "area":
      chartConfig = buildLine(input.data, input.title, true);
      break;
    case "pie":
      chartConfig = buildPie(input.data, input.title);
      break;
    case "donut":
      chartConfig = buildPie(input.data, input.title, ["40%", "70%"]);
      break;
    case "scatter":
      chartConfig = buildScatter(input.data, input.title);
      break;
    case "bubble":
      chartConfig = buildBubble(input.data, input.title);
      break;
    case "heatmap":
      chartConfig = buildHeatmap(input.data, input.title);
      break;
    case "treemap":
      chartConfig = buildTreemap(input.data, input.title);
      break;
    case "funnel":
      chartConfig = buildFunnel(input.data, input.title);
      break;
    case "gauge":
      chartConfig = buildGauge(input.data, input.title);
      break;
    case "radar":
      chartConfig = buildRadar(input.data, input.title);
      break;
    case "sankey":
      chartConfig = buildSankey(input.data, input.title);
      break;
    case "candlestick":
      chartConfig = buildCandlestick(input.data, input.title);
      break;
    case "histogram":
      chartConfig = buildHistogram(input.data, input.title);
      break;
    case "boxplot":
      chartConfig = buildBoxplot(input.data, input.title);
      break;
    case "parallel":
      chartConfig = buildParallel(input.data, input.title);
      break;
    case "geo_choropleth":
      chartConfig = buildGeoChloropleth(input.data, input.title);
      break;
    case "geo_scatter":
      chartConfig = buildGeoScatter(input.data, input.title);
      break;
    case "waterfall":
      chartConfig = buildWaterfall(input.data, input.title);
      break;
    case "stacked_bar":
      chartConfig = buildStackedBar(input.data, input.title);
      break;
    case "stacked_area":
      chartConfig = buildStackedArea(input.data, input.title);
      break;
    case "mixed_bar_line":
      chartConfig = buildMixedBarLine(input.data, input.title);
      break;
    case "word_cloud":
      chartConfig = buildWordCloud(input.data, input.title);
      break;
    case "sunburst":
      chartConfig = buildSunburst(input.data, input.title);
      break;
  }

  // Merge caller-provided overrides at top level (OCP: extensible without modifying base logic).
  if (input.options && typeof input.options === "object") {
    Object.assign(chartConfig, input.options);
  }

  return {
    chart_config: chartConfig,
    chart_type: chartType,
    render_hint: "echarts",
  };
}
