/**
 * DashboardBuilderPage — NL → Dashboard AI builder with drag-and-drop editor.
 * Day 15: Dashboard builder.
 *
 * Protocols: MCP (orchestration-engine → mcp-visualization)
 * SOLID: SRP — builder UI only; OCP — new panel types extend without change; DIP — logic in hooks
 * Benchmark: tests/benchmarks/bench_nl_to_dashboard.ts
 */
"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  Save,
  X,
  Wand2,
  AlertCircle,
  ChevronRight,
  ChevronLeft,
  Loader2,
} from "lucide-react";
import { useDrop } from "react-dnd";
import { useDashboardStore } from "@/store/dashboard";
import { useCreateDashboard, useUpdateDashboard, useDashboard } from "@/hooks/useDashboards";
import { useNLDashboard } from "@/hooks/useNLDashboard";
import { DashboardGrid } from "@/components/dashboard/DashboardGrid";
import { WidgetPalette, PALETTE_DRAG_TYPE } from "@/components/dashboard/WidgetPalette";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { generateWidgetId } from "@/lib/utils";
import type { WidgetConfig } from "@/lib/types";

export default function DashboardBuilderPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const editingId = searchParams.get("id");

  const {
    editingWidgets,
    addWidget,
    setWidgets,
    draftTitle,
    setDraftTitle,
    draftDescription,
    setDraftDescription,
    tenantId,
    nlPrompt,
    setNLPrompt,
  } = useDashboardStore();

  // Load existing dashboard if editing
  const { data: existingDashboard } = useDashboard(
    editingId ?? "",
    tenantId,
  );

  useEffect(() => {
    if (existingDashboard && editingId) {
      setWidgets(existingDashboard.widgets);
      setDraftTitle(existingDashboard.title);
      setDraftDescription(existingDashboard.description);
    }
  }, [existingDashboard, editingId, setWidgets, setDraftTitle, setDraftDescription]);

  const createMutation = useCreateDashboard();
  const updateMutation = useUpdateDashboard();
  const { generate, isGenerating, error: nlError, clearError } = useNLDashboard();

  const containerRef = useRef<HTMLDivElement>(null);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  // Drop zone for palette items
  const [{ isOver }, dropRef] = useDrop<WidgetConfig, void, { isOver: boolean }>({
    accept: PALETTE_DRAG_TYPE,
    drop: (item: WidgetConfig) => {
      addWidget({ ...item, widget_id: generateWidgetId() });
    },
    collect: (monitor) => ({ isOver: monitor.isOver() }),
  });

  const handleSave = async () => {
    if (!draftTitle.trim()) return;
    setIsSaving(true);
    try {
      if (editingId) {
        await updateMutation.mutateAsync({
          id: editingId,
          body: {
            tenant_id: tenantId,
            title: draftTitle,
            description: draftDescription,
            widgets: editingWidgets,
          },
        });
        router.push(`/dashboard/${editingId}`);
      } else {
        const created = await createMutation.mutateAsync({
          tenant_id: tenantId,
          title: draftTitle,
          description: draftDescription,
          widgets: editingWidgets,
        });
        router.push(`/dashboard/${created.dashboard_id}`);
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleGenerate = async () => {
    if (!nlPrompt.trim()) return;
    clearError();
    await generate(nlPrompt);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-[#1e2332] bg-[#0f1117] shrink-0">
        <Button
          variant="ghost"
          size="sm"
          leftIcon={<X size={14} />}
          onClick={() => router.push("/dashboard")}
        >
          Cancel
        </Button>

        <div className="w-px h-5 bg-[#2a3347]" />

        <Input
          value={draftTitle}
          onChange={(e) => setDraftTitle(e.target.value)}
          placeholder="Dashboard title..."
          className="w-56 h-7 text-sm font-medium bg-transparent border-transparent focus:bg-[#1e2332] focus:border-[#2a3347]"
        />

        {editingId && (
          <Badge variant="info" className="text-[10px]">
            Editing
          </Badge>
        )}

        <div className="flex-1" />

        <span className="text-xs text-slate-500">
          {editingWidgets.length} widget{editingWidgets.length !== 1 ? "s" : ""}
        </span>

        <Button
          size="sm"
          leftIcon={<Save size={13} />}
          onClick={handleSave}
          loading={isSaving}
          disabled={!draftTitle.trim()}
        >
          {editingId ? "Save Changes" : "Save Dashboard"}
        </Button>
      </div>

      {/* Body */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Widget palette */}
        <WidgetPalette />

        {/* Canvas */}
        <div
          ref={(el) => {
            containerRef.current = el;
            dropRef(el);
          }}
          className={`flex-1 min-w-0 overflow-y-auto p-4 transition-colors ${
            isOver ? "bg-blue-950/20" : ""
          }`}
        >
          {isOver && (
            <div className="pointer-events-none absolute inset-4 rounded-xl border-2 border-dashed border-blue-500/40 z-10" />
          )}

          {editingWidgets.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 gap-4 text-slate-500">
              <div className="w-20 h-20 rounded-2xl bg-[#161b27] border-2 border-dashed border-[#2a3347] flex items-center justify-center">
                <span className="text-3xl opacity-30">+</span>
              </div>
              <p className="text-sm">Drag widgets here or use AI generation →</p>
            </div>
          ) : (
            <DashboardGrid
              widgets={editingWidgets}
              isEditing
              containerWidth={containerRef.current?.clientWidth ?? 900}
            />
          )}
        </div>

        {/* Right panel — NL generator */}
        <div
          className={`flex flex-col border-l border-[#1e2332] bg-[#0d111b] shrink-0 transition-all duration-200 ${
            rightPanelOpen ? "w-72" : "w-10"
          }`}
        >
          <button
            onClick={() => setRightPanelOpen((o) => !o)}
            className="flex items-center justify-center h-10 border-b border-[#1e2332] text-slate-500 hover:text-slate-300 hover:bg-[#1e2332] transition-colors shrink-0"
            aria-label={rightPanelOpen ? "Collapse panel" : "Expand AI panel"}
          >
            {rightPanelOpen ? (
              <ChevronRight size={16} />
            ) : (
              <ChevronLeft size={16} />
            )}
          </button>

          {rightPanelOpen && (
            <div className="flex flex-col flex-1 p-4 gap-4 overflow-y-auto">
              {/* NL Generator */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-2">
                  <Wand2 size={14} className="text-blue-400" />
                  <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    AI Generation
                  </p>
                </div>
                <p className="text-[11px] text-slate-500 leading-relaxed">
                  Describe the dashboard you want to build. The AI will create
                  widgets automatically.
                </p>

                <textarea
                  value={nlPrompt}
                  onChange={(e) => setNLPrompt(e.target.value)}
                  placeholder="e.g. Show me a sales dashboard with revenue trends, top products by region, and a KPI card for monthly growth..."
                  rows={5}
                  className="w-full rounded-md bg-[#1e2332] border border-[#2a3347] text-slate-200 text-xs px-3 py-2 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500/60 resize-none"
                />

                {nlError && (
                  <div className="flex items-start gap-2 p-2.5 rounded-md bg-red-900/20 border border-red-800/40">
                    <AlertCircle size={13} className="text-red-400 shrink-0 mt-0.5" />
                    <p className="text-[11px] text-red-300">{nlError}</p>
                  </div>
                )}

                <Button
                  size="sm"
                  onClick={handleGenerate}
                  disabled={!nlPrompt.trim()}
                  loading={isGenerating}
                  leftIcon={
                    isGenerating ? (
                      <Loader2 size={13} className="animate-spin" />
                    ) : (
                      <Wand2 size={13} />
                    )
                  }
                  className="w-full"
                >
                  {isGenerating ? "Generating..." : "Generate Dashboard"}
                </Button>
              </div>

              <div className="w-full h-px bg-[#1e2332]" />

              {/* Dashboard metadata */}
              <div className="flex flex-col gap-3">
                <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                  Settings
                </p>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs text-slate-400">Description</label>
                  <textarea
                    value={draftDescription}
                    onChange={(e) => setDraftDescription(e.target.value)}
                    placeholder="Optional description..."
                    rows={3}
                    className="w-full rounded-md bg-[#1e2332] border border-[#2a3347] text-slate-200 text-xs px-3 py-2 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500/60 resize-none"
                  />
                </div>
              </div>

              {/* Hints */}
              <div className="mt-auto p-3 rounded-lg bg-blue-950/30 border border-blue-900/30">
                <p className="text-[10px] text-blue-300/70 leading-relaxed">
                  <strong className="text-blue-300">Tip:</strong> Be specific about metrics, time
                  ranges, and chart types. The AI uses your connected data
                  sources to generate relevant widgets.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
