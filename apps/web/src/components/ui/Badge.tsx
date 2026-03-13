/**
 * Badge — Status / label badge component.
 * Day 15: UI component library.
 *
 * Protocols: None
 * SOLID: OCP — variant-driven, never modified
 */
"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type BadgeVariant =
  | "default"
  | "primary"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "muted";

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
  dot?: boolean;
}

const variantClasses: Record<BadgeVariant, string> = {
  default: "bg-[#1e2332] text-slate-300 border border-[#2a3347]",
  primary: "bg-blue-900/50 text-blue-300 border border-blue-800/50",
  success: "bg-emerald-900/50 text-emerald-300 border border-emerald-800/50",
  warning: "bg-amber-900/50 text-amber-300 border border-amber-800/50",
  danger: "bg-red-900/50 text-red-300 border border-red-800/50",
  info: "bg-sky-900/50 text-sky-300 border border-sky-800/50",
  muted: "bg-transparent text-slate-500 border border-[#2a3347]",
};

const dotClasses: Record<BadgeVariant, string> = {
  default: "bg-slate-400",
  primary: "bg-blue-400",
  success: "bg-emerald-400",
  warning: "bg-amber-400",
  danger: "bg-red-400",
  info: "bg-sky-400",
  muted: "bg-slate-600",
};

export function Badge({
  children,
  variant = "default",
  className,
  dot = false,
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium",
        variantClasses[variant],
        className,
      )}
    >
      {dot && (
        <span
          className={cn("w-1.5 h-1.5 rounded-full shrink-0", dotClasses[variant])}
        />
      )}
      {children}
    </span>
  );
}
