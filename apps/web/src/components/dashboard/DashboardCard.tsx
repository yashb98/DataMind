/**
 * DashboardCard — Card in the dashboard list page.
 * Day 15: Dashboard listing UI.
 *
 * Protocols: None
 * SOLID: SRP — card rendering only
 */
"use client";

import Link from "next/link";
import { LayoutDashboard, MoreHorizontal, Clock, Tag, Trash2, Edit2 } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { formatRelative } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { DashboardConfig } from "@/lib/types";

interface DashboardCardProps {
  dashboard: DashboardConfig;
  onDelete?: (id: string) => void;
}

export function DashboardCard({ dashboard, onDelete }: DashboardCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div
      className={cn(
        "group relative flex flex-col rounded-xl bg-[#161b27] border border-[#1e2332]",
        "hover:border-blue-700/50 hover:shadow-lg hover:shadow-blue-900/10 transition-all duration-200",
      )}
    >
      {/* Thumbnail / preview */}
      <Link href={`/dashboard/${dashboard.dashboard_id}`} className="block">
        <div className="h-32 rounded-t-xl bg-gradient-to-br from-[#1a2035] to-[#0f1117] flex items-center justify-center border-b border-[#1e2332] overflow-hidden">
          {dashboard.thumbnail_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={dashboard.thumbnail_url}
              alt={`${dashboard.title} preview`}
              className="w-full h-full object-cover opacity-70"
            />
          ) : (
            <div className="flex flex-col items-center gap-2 opacity-30">
              <LayoutDashboard size={32} className="text-blue-400" />
              <div className="flex gap-1">
                {Array.from({ length: Math.min(dashboard.widgets.length, 4) }).map((_, i) => (
                  <div
                    key={i}
                    className="h-2 bg-blue-600 rounded-sm"
                    style={{ width: `${16 + Math.random() * 24}px` }}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </Link>

      {/* Content */}
      <div className="p-4 flex flex-col gap-2 flex-1">
        <div className="flex items-start justify-between gap-2">
          <Link href={`/dashboard/${dashboard.dashboard_id}`} className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-slate-200 truncate group-hover:text-blue-300 transition-colors">
              {dashboard.title}
            </h3>
            {dashboard.description && (
              <p className="mt-0.5 text-xs text-slate-500 line-clamp-2">
                {dashboard.description}
              </p>
            )}
          </Link>

          <div className="relative shrink-0">
            <button
              onClick={() => setMenuOpen((o) => !o)}
              className="p-1 rounded text-slate-600 hover:text-slate-300 hover:bg-[#1e2332] transition-colors"
              aria-label="Dashboard options"
            >
              <MoreHorizontal size={14} />
            </button>

            {menuOpen && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setMenuOpen(false)}
                />
                <div className="absolute right-0 top-6 z-50 w-40 rounded-md bg-[#1e2332] border border-[#2a3347] shadow-xl py-1">
                  <Link
                    href={`/builder?id=${dashboard.dashboard_id}`}
                    className="flex items-center gap-2 px-3 py-1.5 text-xs text-slate-300 hover:bg-[#252d42] transition-colors"
                    onClick={() => setMenuOpen(false)}
                  >
                    <Edit2 size={11} />
                    Edit in Builder
                  </Link>
                  {onDelete && (
                    <button
                      className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-red-400 hover:bg-[#252d42] transition-colors"
                      onClick={() => {
                        onDelete(dashboard.dashboard_id);
                        setMenuOpen(false);
                      }}
                    >
                      <Trash2 size={11} />
                      Delete
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Meta */}
        <div className="flex items-center gap-2 mt-auto pt-1">
          <Badge variant="muted" className="text-[10px]">
            {dashboard.widgets.length} widget{dashboard.widgets.length !== 1 ? "s" : ""}
          </Badge>

          <div className="flex items-center gap-1 text-[10px] text-slate-600 ml-auto">
            <Clock size={10} />
            {formatRelative(dashboard.updated_at)}
          </div>
        </div>

        {/* Tags */}
        {dashboard.tags.length > 0 && (
          <div className="flex items-center gap-1 flex-wrap">
            <Tag size={10} className="text-slate-600 shrink-0" />
            {dashboard.tags.slice(0, 3).map((tag) => (
              <Badge key={tag} variant="muted" className="text-[10px]">
                {tag}
              </Badge>
            ))}
            {dashboard.tags.length > 3 && (
              <span className="text-[10px] text-slate-600">
                +{dashboard.tags.length - 3}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
