/**
 * DashboardGrid — react-grid-layout grid container for widgets.
 * Day 15: Dashboard grid system.
 *
 * Protocols: None
 * SOLID: SRP — layout management only; OCP — widget rendering delegated to ChartWidget
 * Benchmark: tests/benchmarks/bench_grid_render.ts
 */
"use client";

import { useCallback } from "react";
import GridLayout, { type Layout } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { ChartWidget } from "@/components/charts/ChartWidget";
import { useDashboardStore } from "@/store/dashboard";
import type { WidgetConfig } from "@/lib/types";

interface DashboardGridProps {
  widgets: WidgetConfig[];
  isEditing?: boolean;
  onLayoutChange?: (layout: Layout[]) => void;
  containerWidth?: number;
}

export function DashboardGrid({
  widgets,
  isEditing = false,
  onLayoutChange,
  containerWidth = 1200,
}: DashboardGridProps) {
  const { updateWidget, removeWidget } = useDashboardStore();

  const layout: Layout[] = widgets.map((w) => ({
    i: w.widget_id,
    x: w.x,
    y: w.y,
    w: w.w,
    h: w.h,
    minW: 2,
    minH: 2,
    isDraggable: isEditing,
    isResizable: isEditing,
  }));

  const handleLayoutChange = useCallback(
    (newLayout: Layout[]) => {
      newLayout.forEach((item) => {
        updateWidget(item.i, {
          x: item.x,
          y: item.y,
          w: item.w,
          h: item.h,
        });
      });
      onLayoutChange?.(newLayout);
    },
    [updateWidget, onLayoutChange],
  );

  const handleRemove = useCallback(
    (id: string) => {
      removeWidget(id);
    },
    [removeWidget],
  );

  if (widgets.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-slate-500 gap-3">
        <div className="w-16 h-16 rounded-xl bg-[#161b27] border-2 border-dashed border-[#2a3347] flex items-center justify-center">
          <span className="text-2xl opacity-40">+</span>
        </div>
        <p className="text-sm">
          {isEditing
            ? "Drag widgets from the palette or use NL generation"
            : "No widgets configured"}
        </p>
      </div>
    );
  }

  return (
    <GridLayout
      className="layout"
      layout={layout}
      cols={12}
      rowHeight={80}
      width={containerWidth}
      margin={[8, 8]}
      containerPadding={[0, 0]}
      draggableHandle=".drag-handle"
      isDraggable={isEditing}
      isResizable={isEditing}
      onLayoutChange={handleLayoutChange}
      useCSSTransforms
    >
      {widgets.map((widget) => (
        <div key={widget.widget_id}>
          <ChartWidget
            widget={widget}
            isEditing={isEditing}
            onRemove={isEditing ? handleRemove : undefined}
            className="h-full"
          />
        </div>
      ))}
    </GridLayout>
  );
}
