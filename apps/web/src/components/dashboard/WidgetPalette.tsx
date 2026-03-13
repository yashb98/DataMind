/**
 * WidgetPalette — Drag-source palette of widget types for the builder.
 * Day 15: Dashboard builder.
 *
 * Protocols: None
 * SOLID: SRP — palette/drag-source only; OCP — add widget types by extending paletteItems
 */
"use client";

import { useDrag } from "react-dnd";
import {
  LineChart,
  BarChart2,
  PieChart,
  Gauge,
  Hash,
  AlignLeft,
  Map,
  Table2,
  Activity,
  TrendingUp,
  ScatterChart,
  Layers,
} from "lucide-react";
import { cn, generateWidgetId } from "@/lib/utils";
import type { WidgetConfig, WidgetType, ChartType } from "@/lib/types";

export const PALETTE_DRAG_TYPE = "PALETTE_WIDGET";

interface PaletteItemConfig {
  label: string;
  icon: React.ElementType;
  widget_type: WidgetType;
  chart_type?: ChartType;
  default_w: number;
  default_h: number;
  description: string;
}

const paletteItems: PaletteItemConfig[] = [
  {
    label: "Line Chart",
    icon: LineChart,
    widget_type: "chart",
    chart_type: "line",
    default_w: 6,
    default_h: 4,
    description: "Trends over time",
  },
  {
    label: "Bar Chart",
    icon: BarChart2,
    widget_type: "chart",
    chart_type: "bar",
    default_w: 6,
    default_h: 4,
    description: "Compare categories",
  },
  {
    label: "Area Chart",
    icon: Activity,
    widget_type: "chart",
    chart_type: "area",
    default_w: 6,
    default_h: 4,
    description: "Volume over time",
  },
  {
    label: "Pie Chart",
    icon: PieChart,
    widget_type: "chart",
    chart_type: "pie",
    default_w: 4,
    default_h: 4,
    description: "Part-to-whole",
  },
  {
    label: "Scatter",
    icon: ScatterChart,
    widget_type: "chart",
    chart_type: "scatter",
    default_w: 5,
    default_h: 4,
    description: "Correlation",
  },
  {
    label: "Gauge",
    icon: Gauge,
    widget_type: "chart",
    chart_type: "gauge",
    default_w: 3,
    default_h: 3,
    description: "Single value gauge",
  },
  {
    label: "Heatmap",
    icon: Layers,
    widget_type: "chart",
    chart_type: "heatmap",
    default_w: 6,
    default_h: 4,
    description: "Matrix density",
  },
  {
    label: "Treemap",
    icon: TrendingUp,
    widget_type: "chart",
    chart_type: "treemap",
    default_w: 5,
    default_h: 4,
    description: "Hierarchical data",
  },
  {
    label: "Metric",
    icon: Hash,
    widget_type: "metric",
    default_w: 3,
    default_h: 2,
    description: "KPI number",
  },
  {
    label: "Table",
    icon: Table2,
    widget_type: "table",
    default_w: 6,
    default_h: 4,
    description: "Tabular data",
  },
  {
    label: "Text",
    icon: AlignLeft,
    widget_type: "text",
    default_w: 4,
    default_h: 2,
    description: "Free text / notes",
  },
  {
    label: "Map",
    icon: Map,
    widget_type: "map",
    chart_type: "geo",
    default_w: 6,
    default_h: 5,
    description: "Geographic data",
  },
];

interface PaletteItemProps {
  item: PaletteItemConfig;
}

function PaletteItem({ item }: PaletteItemProps) {
  const Icon = item.icon;

  const [{ isDragging }, dragRef] = useDrag<
    WidgetConfig,
    void,
    { isDragging: boolean }
  >({
    type: PALETTE_DRAG_TYPE,
    item: (): WidgetConfig => ({
      widget_id: generateWidgetId(),
      widget_type: item.widget_type,
      chart_type: item.chart_type,
      title: item.label,
      x: 0,
      y: Infinity,
      w: item.default_w,
      h: item.default_h,
      data_source: {},
      chart_config: {},
      refresh_interval_s: 0,
    }),
    collect: (monitor) => ({
      isDragging: monitor.isDragging(),
    }),
  });

  return (
    <div
      ref={dragRef as unknown as React.RefObject<HTMLDivElement>}
      className={cn(
        "flex flex-col items-center gap-1.5 p-3 rounded-lg cursor-grab active:cursor-grabbing",
        "bg-[#1a2035] border border-[#2a3347] hover:border-blue-600/50 hover:bg-[#1e2845]",
        "transition-all duration-150 select-none",
        isDragging && "opacity-50 scale-95",
      )}
      title={item.description}
    >
      <Icon size={18} className="text-blue-400 shrink-0" />
      <span className="text-[10px] text-slate-400 text-center leading-tight">
        {item.label}
      </span>
    </div>
  );
}

export function WidgetPalette() {
  return (
    <aside className="w-52 shrink-0 flex flex-col gap-3 p-3 border-r border-[#1e2332] overflow-y-auto">
      <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider px-1">
        Widgets
      </p>
      <div className="grid grid-cols-2 gap-2">
        {paletteItems.map((item) => (
          <PaletteItem key={`${item.widget_type}-${item.chart_type ?? "none"}`} item={item} />
        ))}
      </div>
      <p className="text-[10px] text-slate-600 px-1 leading-relaxed mt-2">
        Drag widgets onto the canvas, or use the NL generator to auto-build.
      </p>
    </aside>
  );
}
