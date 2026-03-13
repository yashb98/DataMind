/**
 * useNLDashboard — NL → Dashboard hook.
 * Day 15: AI-powered dashboard generation.
 *
 * Protocols: MCP (calls orchestration-engine which calls mcp-visualization)
 * SOLID: SRP — NL generation concerns separated from CRUD
 */
"use client";

import { useState, useCallback } from "react";
import { nlToDashboard, ApiError } from "@/lib/api";
import { useDashboardStore } from "@/store/dashboard";
import type { NLToDashboardResponse } from "@/lib/types";

interface UseNLDashboardReturn {
  generate: (prompt: string) => Promise<NLToDashboardResponse | null>;
  isGenerating: boolean;
  error: string | null;
  lastResult: NLToDashboardResponse | null;
  clearError: () => void;
}

export function useNLDashboard(): UseNLDashboardReturn {
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<NLToDashboardResponse | null>(
    null,
  );

  const {
    tenantId,
    setIsGenerating,
    isGenerating,
    setWidgets,
    setDraftTitle,
    setDraftDescription,
  } = useDashboardStore();

  const clearError = useCallback(() => setError(null), []);

  const generate = useCallback(
    async (prompt: string): Promise<NLToDashboardResponse | null> => {
      if (!prompt.trim()) {
        setError("Please enter a prompt.");
        return null;
      }
      setError(null);
      setIsGenerating(true);

      try {
        const result = await nlToDashboard({
          tenant_id: tenantId,
          prompt: prompt.trim(),
        });

        setLastResult(result);

        // Populate builder with generated widgets
        setWidgets(result.widgets);
        setDraftTitle(result.title);
        setDraftDescription(result.description);

        return result;
      } catch (err) {
        if (err instanceof ApiError) {
          setError(err.message);
        } else if (err instanceof Error) {
          setError(err.message);
        } else {
          setError("Unknown error generating dashboard.");
        }
        return null;
      } finally {
        setIsGenerating(false);
      }
    },
    [tenantId, setIsGenerating, setWidgets, setDraftTitle, setDraftDescription],
  );

  return { generate, isGenerating, error, lastResult, clearError };
}
