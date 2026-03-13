/**
 * ChartWidget — Widget card wrapping a chart or metric.
 * Day 15: Dashboard chart components.
 *
 * Protocols: None
 * SOLID: OCP — new widget_type handled by extending switch, no core change
 */
"use client";

import { useState, useCallback } from "react";
import {
  MoreHorizontal,
  GripVertical,
  RefreshCw,
  Trash2,
  Edit2,
  Maximize2,
} from "lucide-react";
import { EChartsWrapper } from "./EChartsWrapper";
import { MetricCard } from "./MetricCard";
import { cn } from "@/lib/utils";
import type { WidgetConfig } from "@/lib/types";

interface ChartWidgetProps {
  widget: WidgetConfig;
  isEditing?: boolean;
  onRemove?: (id: string) => void;
  className?: string;
}

function buildEChartsOption(widget: WidgetConfig): Record<string, unknown> {
  const { chart_type, chart_config, data_source } = widget;

  // Merge data_source into chart_config as a convenience
  const base: Record<string, unknown> = {
    backgroundColor: "transparent",
    textStyle: { color: "#94a3b8" },
    tooltip: { trigger: "axis", backgroundColor: "#1e2332", borderColor: "#2a3347", textStyle: { color: "#e2e8f0" } },
    grid: { top: 32, right: 20, bottom: 36, left: 52, containLabel: true },
    ...chart_config,
  };

  // Inject sample / placeholder data when data_source contains series data
  if (data_source.series) {
    base.series = data_source.series;
  }
  if (data_source.xAxis) base.xAxis = data_source.xAxis;
  if (data_source.yAxis) base.yAxis = data_source.yAxis;
  if (data_source.legend) base.legend = data_source.legend;

  // Sensible defaults per chart type
  if (!base.xAxis && (chart_type === "line" || chart_type === "bar" || chart_type === "area")) {
    base.xAxis = { type: "category", data: [] };
  }
  if (!base.yAxis && (chart_type === "line" || chart_type === "bar" || chart_type === "area")) {
    base.yAxis = { type: "value" };
  }

  return base;
}

export function ChartWidget({
  widget,
  isEditing = false,
  onRemove,
  className,
}: ChartWidgetProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleRefresh = useCallback(() => {
    setLoading(true);
    setTimeout(() => setLoading(false), 800);
  }, []);

  const renderContent = () => {
    switch (widget.widget_type) {
      case "metric": {
        const ds = widget.data_source as {
          value?: number | string;
          unit?: string;
          change?: number;
          change_period?: string;
          subtitle?: string;
        };
        return (
          <MetricCard
            title={widget.title}
            value={ds.value ?? 0}
            unit={ds.unit}
            change={ds.change}
            changePeriod={ds.change_period}
            subtitle={ds.subtitle}
          />
        );
      }

      case "text": {
        const ds = widget.data_source as { content?: string };
        return (
          <div className="p-4 h-full overflow-auto text-slate-300 text-sm leading-relaxed whitespace-pre-wrap">
            {ds.content ?? "No content"}
          </div>
        );
      }

      case "chart":
      case "map":
      default: {
        const option = buildEChartsOption(widget);
        return (
          <div className="flex-1 min-h-0 px-2 pb-2">
            <EChartsWrapper option={option} loading={loading} />
          </div>
        );
      }
    }
  };

  return (
    <div
      className={cn(
        "flex flex-col h-full rounded-lg bg-[#161b27] border border-[#1e2332]",
        "overflow-hidden group",
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-1.5 px-3 py-2 border-b border-[#1e2332] shrink-0">
        {isEditing && (
          <GripVertical
            size={14}
            className="drag-handle text-slate-600 cursor-grab active:cursor-grabbing shrink-0"
          />
        )}

        <span className="flex-1 text-xs font-semibold text-slate-300 truncate">
          {widget.title}
        </span>

        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={handleRefresh}
            className="p-1 rounded text-slate-500 hover:text-slate-300 hover:bg-[#1e2332] transition-colors"
            aria-label="Refresh widget"
          >
            <RefreshCw
              size={12}
              className={cn(loading && "animate-spin")}
            />
          </button>

          <button
            className="p-1 rounded text-slate-500 hover:text-slate-300 hover:bg-[#1e2332] transition-colors"
            aria-label="Expand widget"
          >
            <Maximize2 size={12} />
          </button>

          <div className="relative">
            <button
              onClick={() => setMenuOpen((o) => !o)}
              className="p-1 rounded text-slate-500 hover:text-slate-300 hover:bg-[#1e2332] transition-colors"
              aria-label="Widget menu"
            >
              <MoreHorizontal size={12} />
            </button>

            {menuOpen && (
              <div className="absolute right-0 top-6 z-50 w-36 rounded-md bg-[#1e2332] border border-[#2a3347] shadow-xl py-1">
                <button
                  className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-slate-300 hover:bg-[#252d42] transition-colors"
                  onClick={() => setMenuOpen(false)}
                >
                  <Edit2 size={11} />
                  Edit widget
                </button>
                {onRemove && (
                  <button
                    className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-red-400 hover:bg-[#252d42] transition-colors"
                    onClick={() => {
                      onRemove(widget.widget_id);
                      setMenuOpen(false);
                    }}
                  >
                    <Trash2 size={11} />
                    Remove
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 flex flex-col">
        {widget.widget_type === "metric" ? (
          renderContent()
        ) : (
          <>
            {widget.widget_type !== "text" && (
              <div className="flex-1 min-h-0">{renderContent()}</div>
            )}
            {widget.widget_type === "text" && renderContent()}
          </>
        )}
      </div>
    </div>
  );
}
