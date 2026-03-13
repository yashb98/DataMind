/**
 * MetricCard — Single KPI metric display card.
 * Day 15: Dashboard chart components.
 *
 * Protocols: None
 * SOLID: SRP — metric display only
 */
"use client";

import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { cn, formatNumber } from "@/lib/utils";

interface MetricCardProps {
  title: string;
  value: number | string;
  unit?: string;
  change?: number;
  changePeriod?: string;
  subtitle?: string;
  className?: string;
}

export function MetricCard({
  title,
  value,
  unit,
  change,
  changePeriod = "vs last period",
  subtitle,
  className,
}: MetricCardProps) {
  const displayValue =
    typeof value === "number" ? formatNumber(value) : value;

  const trend =
    change === undefined ? null : change > 0 ? "up" : change < 0 ? "down" : "flat";

  return (
    <div
      className={cn(
        "flex flex-col justify-between h-full p-4",
        className,
      )}
    >
      <p className="text-xs font-medium text-slate-400 uppercase tracking-wide truncate">
        {title}
      </p>

      <div className="mt-2">
        <div className="flex items-end gap-1.5">
          <span className="text-3xl font-bold text-slate-100 leading-none">
            {displayValue}
          </span>
          {unit && (
            <span className="text-sm text-slate-400 mb-0.5">{unit}</span>
          )}
        </div>

        {subtitle && (
          <p className="mt-1 text-xs text-slate-500 truncate">{subtitle}</p>
        )}
      </div>

      {trend !== null && change !== undefined && (
        <div className="mt-3 flex items-center gap-1">
          {trend === "up" && (
            <TrendingUp size={13} className="text-emerald-400 shrink-0" />
          )}
          {trend === "down" && (
            <TrendingDown size={13} className="text-red-400 shrink-0" />
          )}
          {trend === "flat" && (
            <Minus size={13} className="text-slate-400 shrink-0" />
          )}
          <span
            className={cn(
              "text-xs font-medium",
              trend === "up" && "text-emerald-400",
              trend === "down" && "text-red-400",
              trend === "flat" && "text-slate-400",
            )}
          >
            {change > 0 ? "+" : ""}
            {change.toFixed(1)}%
          </span>
          <span className="text-xs text-slate-500 truncate">
            {changePeriod}
          </span>
        </div>
      )}
    </div>
  );
}
