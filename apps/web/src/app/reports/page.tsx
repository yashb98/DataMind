/**
 * ReportsPage — Report generation placeholder.
 * Day 15: Placeholder for mcp-report-generator UI (Phase 5).
 *
 * Protocols: MCP (mcp-report-generator)
 * SOLID: SRP — placeholder only
 */
"use client";

import { FileText } from "lucide-react";
import { Badge } from "@/components/ui/Badge";

export default function ReportsPage() {
  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 rounded-lg bg-blue-600/10 border border-blue-700/30">
          <FileText size={20} className="text-blue-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-slate-100">Reports</h1>
          <p className="text-xs text-slate-500">
            WeasyPrint PDF + PPTX with Merkle provenance
          </p>
        </div>
        <Badge variant="warning" className="ml-auto">
          Phase 5 — Days 22-23
        </Badge>
      </div>

      <div className="flex flex-col items-center justify-center py-20 gap-4 text-slate-500">
        <div className="p-6 rounded-2xl bg-[#161b27] border-2 border-dashed border-[#2a3347]">
          <FileText size={40} className="text-slate-600" />
        </div>
        <p className="text-sm font-medium text-slate-400">
          Report generation coming in Phase 5
        </p>
        <p className="text-xs text-center text-slate-600 max-w-sm">
          Echo (Report Writer) will generate PDF and PPTX reports with Merkle
          chain provenance via mcp-report-generator.
        </p>
      </div>
    </div>
  );
}
