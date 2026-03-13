/**
 * useDashboards — React Query hooks for dashboard CRUD.
 * Day 15: Dashboard UI foundation.
 *
 * Protocols: None
 * SOLID: SRP — data fetching logic isolated from UI components
 */
"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchDashboards,
  fetchDashboard,
  createDashboard,
  updateDashboard,
  deleteDashboard,
  exportDashboard,
} from "@/lib/api";
import type {
  CreateDashboardRequest,
  UpdateDashboardRequest,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------
const keys = {
  all: (tenantId: string) => ["dashboards", tenantId] as const,
  one: (id: string, tenantId: string) =>
    ["dashboards", tenantId, id] as const,
};

// ---------------------------------------------------------------------------
// List
// ---------------------------------------------------------------------------
export function useDashboards(tenantId: string) {
  return useQuery({
    queryKey: keys.all(tenantId),
    queryFn: () => fetchDashboards(tenantId),
    enabled: Boolean(tenantId),
    staleTime: 30_000,
    retry: 2,
  });
}

// ---------------------------------------------------------------------------
// Single
// ---------------------------------------------------------------------------
export function useDashboard(id: string, tenantId: string) {
  return useQuery({
    queryKey: keys.one(id, tenantId),
    queryFn: () => fetchDashboard(id, tenantId),
    enabled: Boolean(id) && Boolean(tenantId),
    staleTime: 15_000,
    retry: 2,
  });
}

// ---------------------------------------------------------------------------
// Create
// ---------------------------------------------------------------------------
export function useCreateDashboard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateDashboardRequest) => createDashboard(body),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: keys.all(data.tenant_id) });
    },
  });
}

// ---------------------------------------------------------------------------
// Update
// ---------------------------------------------------------------------------
export function useUpdateDashboard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: UpdateDashboardRequest }) =>
      updateDashboard(id, body),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: keys.all(data.tenant_id) });
      qc.setQueryData(keys.one(data.dashboard_id, data.tenant_id), data);
    },
  });
}

// ---------------------------------------------------------------------------
// Delete
// ---------------------------------------------------------------------------
export function useDeleteDashboard(tenantId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteDashboard(id, tenantId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.all(tenantId) });
    },
  });
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------
export function useExportDashboard() {
  return useMutation({
    mutationFn: ({
      id,
      tenantId,
      format,
    }: {
      id: string;
      tenantId: string;
      format?: "pdf" | "pptx";
    }) => exportDashboard(id, tenantId, format),
    onSuccess: (blob, variables) => {
      const ext = variables.format ?? "pdf";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `dashboard-${variables.id}.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
    },
  });
}
