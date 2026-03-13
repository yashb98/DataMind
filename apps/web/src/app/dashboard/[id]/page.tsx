/**
 * DashboardViewerPage — Live dashboard viewer with real-time WebSocket updates.
 * Day 15: Dashboard viewer.
 *
 * Protocols: None (WebSocket for real-time)
 * SOLID: SRP — viewing only; OCP — widget rendering delegated
 * Benchmark: tests/benchmarks/bench_dashboard_load.ts
 */
"use client";

import { useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Edit2,
  Download,
  RefreshCw,
  Wifi,
  WifiOff,
  Loader2,
} from "lucide-react";
import { useDashboard } from "@/hooks/useDashboards";
import { useExportDashboard } from "@/hooks/useDashboards";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useDashboardStore } from "@/store/dashboard";
import { DashboardGrid } from "@/components/dashboard/DashboardGrid";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { formatRelative } from "@/lib/utils";
import type { WSMessage } from "@/lib/types";

export default function DashboardViewerPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const { tenantId, setActiveDashboard, setWidgets, editingWidgets, activeDashboard } =
    useDashboardStore();

  const {
    data: dashboard,
    isLoading,
    isError,
    error,
    refetch,
  } = useDashboard(id, tenantId);

  const exportMutation = useExportDashboard();

  // Load dashboard into store when fetched
  useEffect(() => {
    if (dashboard) {
      setActiveDashboard(dashboard);
      setWidgets(dashboard.widgets);
    }
    return () => {
      setActiveDashboard(null);
    };
  }, [dashboard, setActiveDashboard, setWidgets]);

  // Track live widget updates from WebSocket
  const { updateWidget } = useDashboardStore();
  const containerRef = useRef<HTMLDivElement>(null);

  const handleWsMessage = useCallback(
    (msg: WSMessage) => {
      if (msg.type === "event" && msg.widget_id && msg.data) {
        updateWidget(msg.widget_id, { live_data: msg.data });
      }
    },
    [updateWidget],
  );

  const { connectionStatus } = useWebSocket(id, tenantId, {
    onMessage: handleWsMessage,
    enabled: Boolean(id) && Boolean(tenantId),
  });

  const handleExport = () => {
    exportMutation.mutate({ id, tenantId, format: "pdf" });
  };

  const title = dashboard?.title ?? activeDashboard?.title ?? "Dashboard";

  // Show loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 gap-3 text-slate-400">
        <Loader2 size={20} className="animate-spin" />
        <span className="text-sm">Loading dashboard...</span>
      </div>
    );
  }

  // Show error state
  if (isError) {
    return (
      <div className="p-6 max-w-xl mx-auto mt-8">
        <div className="rounded-lg bg-red-900/20 border border-red-800/40 p-6 flex flex-col gap-4">
          <Badge variant="danger">Error loading dashboard</Badge>
          <p className="text-sm text-red-300">
            {error instanceof Error ? error.message : "Unknown error"}
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => router.back()}>
              Go back
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => refetch()}
              leftIcon={<RefreshCw size={12} />}
            >
              Retry
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-[#1e2332] shrink-0 bg-[#0f1117]">
        <Button
          variant="ghost"
          size="sm"
          leftIcon={<ArrowLeft size={14} />}
          onClick={() => router.push("/dashboard")}
        >
          Back
        </Button>

        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-semibold text-slate-200 truncate">
            {title}
          </h2>
          {dashboard && (
            <p className="text-[11px] text-slate-500">
              Updated {formatRelative(dashboard.updated_at)}
              {dashboard.widgets.length > 0 && (
                <> · {dashboard.widgets.length} widgets</>
              )}
            </p>
          )}
        </div>

        {/* Connection status */}
        <div className="flex items-center gap-1.5">
          {connectionStatus === "connected" ? (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <Wifi size={12} className="text-emerald-400" />
              <span className="text-[11px] text-emerald-400 hidden sm:inline">Live</span>
            </>
          ) : connectionStatus === "connecting" ? (
            <>
              <Loader2 size={12} className="text-slate-400 animate-spin" />
              <span className="text-[11px] text-slate-500 hidden sm:inline">Connecting</span>
            </>
          ) : (
            <>
              <WifiOff size={12} className="text-slate-600" />
              <span className="text-[11px] text-slate-600 hidden sm:inline">Offline</span>
            </>
          )}
        </div>

        {/* Tags */}
        {dashboard?.tags.slice(0, 2).map((tag) => (
          <Badge key={tag} variant="muted" className="hidden lg:inline-flex">
            {tag}
          </Badge>
        ))}

        <Button
          variant="secondary"
          size="sm"
          leftIcon={<RefreshCw size={12} />}
          onClick={() => refetch()}
          loading={isLoading}
        >
          Refresh
        </Button>

        <Button
          variant="secondary"
          size="sm"
          leftIcon={<Download size={12} />}
          onClick={handleExport}
          loading={exportMutation.isPending}
        >
          Export PDF
        </Button>

        <Link href={`/builder?id=${id}`}>
          <Button size="sm" variant="secondary" leftIcon={<Edit2 size={12} />}>
            Edit
          </Button>
        </Link>
      </div>

      {/* Grid */}
      <div ref={containerRef} className="flex-1 overflow-y-auto p-4">
        <DashboardGrid
          widgets={editingWidgets.length > 0 ? editingWidgets : (dashboard?.widgets ?? [])}
          isEditing={false}
          containerWidth={containerRef.current?.clientWidth ?? 1200}
        />
      </div>
    </div>
  );
}
