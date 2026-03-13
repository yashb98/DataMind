/**
 * DigitalWorkersPage — Digital Workers roster placeholder.
 * Day 15: Placeholder for Phase 6 Digital Workers UI.
 *
 * Protocols: A2A (Phase 6)
 * SOLID: SRP — placeholder only
 */
"use client";

import { Users, Clock } from "lucide-react";
import { Badge } from "@/components/ui/Badge";

const WORKERS = [
  { name: "Aria", role: "Senior Data Analyst", llm: "Claude Sonnet 4", sla: "< 30s", status: "active" },
  { name: "Max", role: "ETL & Data Engineer", llm: "codestral:22b", sla: "< 60s", status: "active" },
  { name: "Luna", role: "Financial Risk Analyst", llm: "DeepSeek-R1:32b", sla: "< 2min", status: "active" },
  { name: "Atlas", role: "Data Scientist", llm: "Claude Sonnet 4", sla: "< 5min", status: "idle" },
  { name: "Nova", role: "Forecast Analyst", llm: "DeepSeek-R1:32b", sla: "< 3min", status: "idle" },
  { name: "Sage", role: "Causal Researcher", llm: "DeepSeek-R1:32b", sla: "< 5min", status: "idle" },
  { name: "Echo", role: "Report Writer", llm: "Claude Sonnet 4", sla: "< 2min", status: "active" },
  { name: "Iris", role: "Compliance Analyst", llm: "llama3.3:70b", sla: "< 2min", status: "active" },
  { name: "Rex", role: "NLP Specialist", llm: "llama3.3:70b", sla: "< 90s", status: "idle" },
  { name: "Geo", role: "Geospatial Analyst", llm: "llama3.3:70b", sla: "< 60s", status: "idle" },
  { name: "Swift", role: "Real-Time Monitor", llm: "Phi-3.5-mini", sla: "< 5s", status: "active" },
  { name: "Quant", role: "Quantum Optimiser", llm: "DeepSeek-R1:32b + D-Wave", sla: "< 10min", status: "idle" },
] as const;

const avatarColors: Record<string, string> = {
  Aria: "bg-purple-600/30 text-purple-300 border-purple-700/40",
  Max: "bg-orange-600/30 text-orange-300 border-orange-700/40",
  Luna: "bg-blue-600/30 text-blue-300 border-blue-700/40",
  Atlas: "bg-green-600/30 text-green-300 border-green-700/40",
  Nova: "bg-yellow-600/30 text-yellow-300 border-yellow-700/40",
  Sage: "bg-emerald-600/30 text-emerald-300 border-emerald-700/40",
  Echo: "bg-pink-600/30 text-pink-300 border-pink-700/40",
  Iris: "bg-cyan-600/30 text-cyan-300 border-cyan-700/40",
  Rex: "bg-red-600/30 text-red-300 border-red-700/40",
  Geo: "bg-teal-600/30 text-teal-300 border-teal-700/40",
  Swift: "bg-sky-600/30 text-sky-300 border-sky-700/40",
  Quant: "bg-violet-600/30 text-violet-300 border-violet-700/40",
};

export default function AgentsPage() {
  const active = WORKERS.filter((w) => w.status === "active").length;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 rounded-lg bg-blue-600/10 border border-blue-700/30">
          <Users size={20} className="text-blue-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-slate-100">Digital Workers</h1>
          <p className="text-xs text-slate-500">
            {active} active · {WORKERS.length} total — A2A protocol (Phase 6)
          </p>
        </div>
        <Badge variant="warning" className="ml-auto">
          Coming in Phase 6
        </Badge>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {WORKERS.map((worker) => (
          <div
            key={worker.name}
            className="flex items-center gap-4 p-4 rounded-xl bg-[#161b27] border border-[#1e2332] hover:border-blue-700/40 transition-colors"
          >
            <div
              className={`w-10 h-10 rounded-full border flex items-center justify-center font-bold text-sm shrink-0 ${avatarColors[worker.name]}`}
            >
              {worker.name[0]}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-slate-200">
                  {worker.name}
                </span>
                <Badge
                  variant={worker.status === "active" ? "success" : "muted"}
                  dot
                  className="text-[10px]"
                >
                  {worker.status}
                </Badge>
              </div>
              <p className="text-xs text-slate-500 truncate">{worker.role}</p>
              <div className="flex items-center gap-1 mt-1">
                <Clock size={10} className="text-slate-600" />
                <span className="text-[10px] text-slate-600">{worker.sla}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
