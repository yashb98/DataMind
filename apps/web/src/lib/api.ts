/**
 * api — HTTP client for DataMind dashboard-api service.
 * Day 15: Dashboard UI foundation.
 *
 * Protocols: None (REST over fetch)
 * SOLID: SRP — all API calls centralised here; DIP — components depend on this module, not fetch directly
 */
import type {
  DashboardConfig,
  CreateDashboardRequest,
  UpdateDashboardRequest,
  NLToDashboardRequest,
  NLToDashboardResponse,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_DASHBOARD_API_URL ?? "http://localhost:8110";

class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // ignore parse errors
    }
    throw new ApiError(detail, res.status);
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Dashboards
// ---------------------------------------------------------------------------

export async function fetchDashboards(
  tenantId: string,
): Promise<DashboardConfig[]> {
  return request<DashboardConfig[]>(
    `/api/v1/dashboards?tenant_id=${encodeURIComponent(tenantId)}`,
  );
}

export async function fetchDashboard(
  id: string,
  tenantId: string,
): Promise<DashboardConfig> {
  return request<DashboardConfig>(
    `/api/v1/dashboards/${encodeURIComponent(id)}?tenant_id=${encodeURIComponent(tenantId)}`,
  );
}

export async function createDashboard(
  body: CreateDashboardRequest,
): Promise<DashboardConfig> {
  return request<DashboardConfig>("/api/v1/dashboards", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateDashboard(
  id: string,
  body: UpdateDashboardRequest,
): Promise<DashboardConfig> {
  return request<DashboardConfig>(`/api/v1/dashboards/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteDashboard(
  id: string,
  tenantId: string,
): Promise<void> {
  return request<void>(
    `/api/v1/dashboards/${encodeURIComponent(id)}?tenant_id=${encodeURIComponent(tenantId)}`,
    { method: "DELETE" },
  );
}

// ---------------------------------------------------------------------------
// NL → Dashboard
// ---------------------------------------------------------------------------

export async function nlToDashboard(
  body: NLToDashboardRequest,
): Promise<NLToDashboardResponse> {
  return request<NLToDashboardResponse>("/api/v1/nl-to-dashboard", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export async function exportDashboard(
  id: string,
  tenantId: string,
  format: "pdf" | "pptx" = "pdf",
): Promise<Blob> {
  const url = `${API_BASE}/api/v1/dashboards/${encodeURIComponent(id)}/export?tenant_id=${encodeURIComponent(tenantId)}&format=${format}`;
  const res = await fetch(url);
  if (!res.ok) throw new ApiError(`Export failed: HTTP ${res.status}`, res.status);
  return res.blob();
}

export { ApiError };
