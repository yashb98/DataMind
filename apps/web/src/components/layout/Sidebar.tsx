/**
 * Sidebar — Navigation sidebar with collapsible mobile support.
 * Day 15: Dashboard UI shell.
 *
 * Protocols: None
 * SOLID: SRP — navigation only
 */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Wand2,
  Users,
  Database,
  FileText,
  Home,
  BrainCircuit,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
  badge?: string;
}

const navItems: NavItem[] = [
  { href: "/", label: "Overview", icon: Home },
  { href: "/dashboard", label: "Dashboards", icon: LayoutDashboard },
  { href: "/builder", label: "Builder", icon: Wand2 },
  { href: "/agents", label: "Digital Workers", icon: Users, badge: "12" },
  { href: "/data", label: "Data Sources", icon: Database },
  { href: "/reports", label: "Reports", icon: FileText },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        "flex flex-col h-screen sticky top-0 border-r border-[#1e2332] bg-[#0d111b]",
        "transition-all duration-200 shrink-0",
        collapsed ? "w-16" : "w-56",
      )}
    >
      {/* Logo */}
      <div
        className={cn(
          "flex items-center gap-2.5 h-14 px-4 border-b border-[#1e2332] shrink-0",
          collapsed && "justify-center px-0",
        )}
      >
        <BrainCircuit className="text-blue-400 shrink-0" size={22} />
        {!collapsed && (
          <span className="font-bold text-slate-100 tracking-tight text-base truncate">
            DataMind
          </span>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-2 py-2 text-sm font-medium",
                "transition-colors group",
                isActive
                  ? "bg-blue-600/20 text-blue-400"
                  : "text-slate-400 hover:text-slate-200 hover:bg-[#1e2332]",
                collapsed && "justify-center px-0",
              )}
              title={collapsed ? item.label : undefined}
            >
              <Icon
                size={18}
                className={cn(
                  "shrink-0",
                  isActive ? "text-blue-400" : "text-slate-500 group-hover:text-slate-300",
                )}
              />
              {!collapsed && (
                <>
                  <span className="truncate flex-1">{item.label}</span>
                  {item.badge && (
                    <span className="ml-auto text-xs bg-[#1e2332] text-slate-400 rounded px-1.5 py-0.5">
                      {item.badge}
                    </span>
                  )}
                </>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed((c) => !c)}
        className={cn(
          "flex items-center justify-center h-10 border-t border-[#1e2332]",
          "text-slate-500 hover:text-slate-300 hover:bg-[#1e2332] transition-colors",
        )}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? (
          <ChevronRight size={16} />
        ) : (
          <ChevronLeft size={16} />
        )}
      </button>
    </aside>
  );
}
