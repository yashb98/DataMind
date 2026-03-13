/**
 * dashboard store — Zustand global state for dashboard builder and viewer.
 * Day 15: Dashboard UI foundation.
 *
 * Protocols: None
 * SOLID: SRP — UI state only, no side effects; OCP — extend slices without touching existing ones
 */
"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { DashboardConfig, WidgetConfig } from "@/lib/types";

interface DashboardStore {
  // -------------------------------------------------------------------------
  // Active dashboard (viewer)
  // -------------------------------------------------------------------------
  activeDashboard: DashboardConfig | null;
  setActiveDashboard: (d: DashboardConfig | null) => void;

  // -------------------------------------------------------------------------
  // Builder state
  // -------------------------------------------------------------------------
  editingWidgets: WidgetConfig[];
  addWidget: (w: WidgetConfig) => void;
  updateWidget: (id: string, updates: Partial<WidgetConfig>) => void;
  removeWidget: (id: string) => void;
  setWidgets: (ws: WidgetConfig[]) => void;

  // Draft dashboard title / description in builder
  draftTitle: string;
  setDraftTitle: (t: string) => void;
  draftDescription: string;
  setDraftDescription: (d: string) => void;

  // -------------------------------------------------------------------------
  // NL generation
  // -------------------------------------------------------------------------
  nlPrompt: string;
  setNLPrompt: (p: string) => void;
  isGenerating: boolean;
  setIsGenerating: (v: boolean) => void;

  // -------------------------------------------------------------------------
  // Theme
  // -------------------------------------------------------------------------
  theme: "dark" | "light";
  toggleTheme: () => void;

  // -------------------------------------------------------------------------
  // Tenant
  // -------------------------------------------------------------------------
  tenantId: string;
  setTenantId: (id: string) => void;

  // -------------------------------------------------------------------------
  // Builder editing mode
  // -------------------------------------------------------------------------
  isEditing: boolean;
  setIsEditing: (v: boolean) => void;
}

export const useDashboardStore = create<DashboardStore>()(
  persist(
    (set) => ({
      // -----------------------------------------------------------------------
      // Active dashboard
      // -----------------------------------------------------------------------
      activeDashboard: null,
      setActiveDashboard: (d) => set({ activeDashboard: d }),

      // -----------------------------------------------------------------------
      // Builder
      // -----------------------------------------------------------------------
      editingWidgets: [],
      addWidget: (w) =>
        set((s) => ({ editingWidgets: [...s.editingWidgets, w] })),
      updateWidget: (id, updates) =>
        set((s) => ({
          editingWidgets: s.editingWidgets.map((w) =>
            w.widget_id === id ? { ...w, ...updates } : w,
          ),
        })),
      removeWidget: (id) =>
        set((s) => ({
          editingWidgets: s.editingWidgets.filter(
            (w) => w.widget_id !== id,
          ),
        })),
      setWidgets: (ws) => set({ editingWidgets: ws }),

      draftTitle: "Untitled Dashboard",
      setDraftTitle: (t) => set({ draftTitle: t }),
      draftDescription: "",
      setDraftDescription: (d) => set({ draftDescription: d }),

      // -----------------------------------------------------------------------
      // NL generation
      // -----------------------------------------------------------------------
      nlPrompt: "",
      setNLPrompt: (p) => set({ nlPrompt: p }),
      isGenerating: false,
      setIsGenerating: (v) => set({ isGenerating: v }),

      // -----------------------------------------------------------------------
      // Theme
      // -----------------------------------------------------------------------
      theme: "dark",
      toggleTheme: () =>
        set((s) => ({ theme: s.theme === "dark" ? "light" : "dark" })),

      // -----------------------------------------------------------------------
      // Tenant
      // -----------------------------------------------------------------------
      tenantId:
        (typeof process !== "undefined" &&
          process.env.NEXT_PUBLIC_TENANT_ID) ||
        "default_tenant",
      setTenantId: (id) => set({ tenantId: id }),

      // -----------------------------------------------------------------------
      // Editing mode
      // -----------------------------------------------------------------------
      isEditing: false,
      setIsEditing: (v) => set({ isEditing: v }),
    }),
    {
      name: "datamind-dashboard",
      // Only persist theme preference and tenant id
      partialize: (s) => ({ theme: s.theme, tenantId: s.tenantId }),
    },
  ),
);
