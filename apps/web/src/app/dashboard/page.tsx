/**
 * DashboardListPage — Browse and manage dashboards.
 * Day 15: Dashboard list view.
 *
 * Protocols: None
 * SOLID: SRP — list view only; OCP — card rendering delegated to DashboardCard
 */
"use client";

import { useState } from "react";
import Link from "next/link";
import { LayoutDashboard, Plus, Search, RefreshCw } from "lucide-react";
import { useDashboards, useDeleteDashboard } from "@/hooks/useDashboards";
import { useDashboardStore } from "@/store/dashboard";
import { DashboardCard } from "@/components/dashboard/DashboardCard";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";

export default function DashboardListPage() {
  const { tenantId } = useDashboardStore();
  const { data: dashboards, isLoading, isError, error, refetch } = useDashboards(tenantId);
  const deleteMutation = useDeleteDashboard(tenantId);

  const [search, setSearch] = useState("");

  const filtered = (dashboards ?? []).filter(
    (d) =>
      d.title.toLowerCase().includes(search.toLowerCase()) ||
      d.description.toLowerCase().includes(search.toLowerCase()) ||
      d.tags.some((t) => t.toLowerCase().includes(search.toLowerCase())),
  );

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-blue-600/10 border border-blue-700/30">
            <LayoutDashboard size={20} className="text-blue-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-100">Dashboards</h1>
            <p className="text-xs text-slate-500">
              {dashboards ? `${dashboards.length} dashboard${dashboards.length !== 1 ? "s" : ""}` : "Loading..."}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<RefreshCw size={13} />}
            onClick={() => refetch()}
            loading={isLoading}
          >
            Refresh
          </Button>
          <Link href="/builder">
            <Button size="sm" leftIcon={<Plus size={14} />}>
              New Dashboard
            </Button>
          </Link>
        </div>
      </div>

      {/* Search */}
      <div className="mb-6">
        <Input
          placeholder="Search dashboards..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          leftIcon={<Search size={14} />}
          className="max-w-sm"
        />
      </div>

      {/* Error state */}
      {isError && (
        <div className="flex items-center gap-3 p-4 rounded-lg bg-red-900/20 border border-red-800/40 mb-6">
          <Badge variant="danger">Error</Badge>
          <p className="text-sm text-red-300">
            {error instanceof Error ? error.message : "Failed to load dashboards"}
          </p>
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto text-red-400"
            onClick={() => refetch()}
          >
            Retry
          </Button>
        </div>
      )}

      {/* Loading skeleton */}
      {isLoading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="rounded-xl bg-[#161b27] border border-[#1e2332] h-52 animate-pulse"
            />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !isError && filtered.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <div className="p-6 rounded-2xl bg-[#161b27] border-2 border-dashed border-[#2a3347]">
            <LayoutDashboard size={40} className="text-slate-600" />
          </div>
          {search ? (
            <p className="text-slate-400 text-sm">
              No dashboards matching &ldquo;{search}&rdquo;
            </p>
          ) : (
            <>
              <p className="text-slate-400 text-sm font-medium">
                No dashboards yet
              </p>
              <p className="text-slate-600 text-xs text-center max-w-xs">
                Create one with NL generation or drag-and-drop in the builder.
              </p>
              <Link href="/builder">
                <Button leftIcon={<Plus size={14} />}>
                  Create with AI
                </Button>
              </Link>
            </>
          )}
        </div>
      )}

      {/* Dashboard grid */}
      {!isLoading && filtered.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((dashboard) => (
            <DashboardCard
              key={dashboard.dashboard_id}
              dashboard={dashboard}
              onDelete={(id) => {
                if (confirm(`Delete "${dashboard.title}"?`)) {
                  deleteMutation.mutate(id);
                }
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
