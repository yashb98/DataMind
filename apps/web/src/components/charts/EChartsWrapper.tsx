/**
 * EChartsWrapper — Client-only lazy-loaded ECharts wrapper.
 * Day 15: Chart rendering.
 *
 * Protocols: None
 * SOLID: SRP — wraps ECharts, handles SSR safety + resize
 * Benchmark: tests/benchmarks/bench_chart_render.ts
 */
"use client";

import React, {
  lazy,
  Suspense,
  useRef,
  useEffect,
  useCallback,
  memo,
} from "react";
import { cn } from "@/lib/utils";

// Lazy load the heavy echarts-for-react module so it is never included in SSR bundle
const ReactECharts = lazy(() => import("echarts-for-react"));

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type EChartsOption = Record<string, any>;

interface EChartsWrapperProps {
  option: EChartsOption;
  style?: React.CSSProperties;
  className?: string;
  loading?: boolean;
  theme?: string;
  /** Called when chart is ready */
  onChartReady?: (chart: unknown) => void;
}

function ChartSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex items-center justify-center bg-[#161b27] rounded-md",
        "animate-pulse",
        className,
      )}
    >
      <div className="flex flex-col items-center gap-2 opacity-30">
        <div className="w-8 h-8 rounded bg-slate-600" />
        <div className="w-20 h-2 rounded bg-slate-600" />
      </div>
    </div>
  );
}

export const EChartsWrapper = memo(function EChartsWrapper({
  option,
  style,
  className,
  loading = false,
  theme = "dark",
  onChartReady,
}: EChartsWrapperProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<{ getEchartsInstance?: () => unknown } | null>(null);

  // Auto-resize via ResizeObserver
  const handleResize = useCallback(() => {
    if (chartRef.current?.getEchartsInstance) {
      const instance = chartRef.current.getEchartsInstance();
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (instance as any)?.resize?.();
    }
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(handleResize);
    ro.observe(el);
    return () => ro.disconnect();
  }, [handleResize]);

  const mergedStyle: React.CSSProperties = {
    width: "100%",
    height: "100%",
    minHeight: 120,
    ...style,
  };

  return (
    <div ref={containerRef} className={cn("w-full h-full", className)}>
      <Suspense fallback={<ChartSkeleton className={cn("w-full", className)} style={mergedStyle} />}>
        <ReactECharts
          ref={chartRef as React.RefObject<{ getEchartsInstance?: () => unknown }>}
          option={option}
          style={mergedStyle}
          theme={theme}
          showLoading={loading}
          loadingOption={{
            text: "",
            color: "#3b82f6",
            textColor: "#94a3b8",
            maskColor: "rgba(15,17,23,0.6)",
          }}
          notMerge
          lazyUpdate
          onChartReady={onChartReady}
        />
      </Suspense>
    </div>
  );
});
