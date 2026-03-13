/**
 * DataSourcesPage — Data source connector placeholder.
 * Day 15: Placeholder for mcp-data-connector UI (Phase 2 Days 11-14).
 *
 * Protocols: MCP (mcp-data-connector)
 * SOLID: SRP — placeholder only
 */
"use client";

import { Database } from "lucide-react";
import { Badge } from "@/components/ui/Badge";

const CONNECTORS = [
  { name: "PostgreSQL", icon: "🐘", category: "Database", status: "available" },
  { name: "ClickHouse", icon: "🖱️", category: "OLAP", status: "available" },
  { name: "Snowflake", icon: "❄️", category: "Cloud DW", status: "available" },
  { name: "BigQuery", icon: "🔷", category: "Cloud DW", status: "available" },
  { name: "Redshift", icon: "🔴", category: "Cloud DW", status: "available" },
  { name: "MySQL", icon: "🐬", category: "Database", status: "available" },
  { name: "MongoDB", icon: "🍃", category: "NoSQL", status: "available" },
  { name: "Kafka", icon: "⚡", category: "Streaming", status: "available" },
  { name: "S3 / MinIO", icon: "🪣", category: "Object Storage", status: "available" },
  { name: "Apache Iceberg", icon: "🧊", category: "Lakehouse", status: "available" },
  { name: "Salesforce", icon: "☁️", category: "CRM", status: "coming-soon" },
  { name: "HubSpot", icon: "🟠", category: "CRM", status: "coming-soon" },
] as const;

export default function DataSourcesPage() {
  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 rounded-lg bg-blue-600/10 border border-blue-700/30">
          <Database size={20} className="text-blue-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-slate-100">Data Sources</h1>
          <p className="text-xs text-slate-500">
            80+ connectors via mcp-data-connector
          </p>
        </div>
        <Badge variant="warning" className="ml-auto">
          Phase 2 — Days 11-14
        </Badge>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {CONNECTORS.map((c) => (
          <div
            key={c.name}
            className="flex flex-col gap-2 p-4 rounded-xl bg-[#161b27] border border-[#1e2332] hover:border-blue-700/40 transition-colors"
          >
            <div className="text-2xl">{c.icon}</div>
            <div>
              <p className="text-sm font-semibold text-slate-200">{c.name}</p>
              <p className="text-xs text-slate-500">{c.category}</p>
            </div>
            <Badge
              variant={c.status === "available" ? "success" : "muted"}
              className="text-[10px] w-fit"
            >
              {c.status === "available" ? "Available" : "Soon"}
            </Badge>
          </div>
        ))}
      </div>
    </div>
  );
}
