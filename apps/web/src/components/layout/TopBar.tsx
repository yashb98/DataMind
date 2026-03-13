/**
 * TopBar — Top header with tenant/user info and theme toggle.
 * Day 15: Dashboard UI shell.
 *
 * Protocols: None
 * SOLID: SRP — header concerns only
 */
"use client";

import { Bell, Sun, Moon, Search, User } from "lucide-react";
import { useDashboardStore } from "@/store/dashboard";
import { cn } from "@/lib/utils";

interface TopBarProps {
  title?: string;
}

export function TopBar({ title }: TopBarProps) {
  const { theme, toggleTheme, tenantId } = useDashboardStore();

  return (
    <header className="h-14 px-4 flex items-center gap-3 border-b border-[#1e2332] bg-[#0f1117] shrink-0">
      {/* Page title */}
      <div className="flex-1 min-w-0">
        {title && (
          <h1 className="text-sm font-semibold text-slate-200 truncate">
            {title}
          </h1>
        )}
      </div>

      {/* Search hint */}
      <button className="hidden md:flex items-center gap-2 h-8 px-3 rounded-md bg-[#1e2332] border border-[#2a3347] text-slate-500 text-xs hover:border-blue-500/40 hover:text-slate-300 transition-colors">
        <Search size={13} />
        <span>Search...</span>
        <kbd className="ml-2 text-[10px] bg-[#0f1117] px-1.5 py-0.5 rounded border border-[#2a3347] text-slate-600">
          ⌘K
        </kbd>
      </button>

      {/* Tenant badge */}
      <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#1e2332] border border-[#2a3347]">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
        <span className="text-xs text-slate-400 font-mono truncate max-w-24">
          {tenantId}
        </span>
      </div>

      {/* Theme toggle */}
      <button
        onClick={toggleTheme}
        className={cn(
          "flex items-center justify-center w-8 h-8 rounded-md",
          "text-slate-400 hover:text-slate-200 hover:bg-[#1e2332] transition-colors",
        )}
        aria-label="Toggle theme"
      >
        {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
      </button>

      {/* Notifications */}
      <button
        className={cn(
          "flex items-center justify-center w-8 h-8 rounded-md relative",
          "text-slate-400 hover:text-slate-200 hover:bg-[#1e2332] transition-colors",
        )}
        aria-label="Notifications"
      >
        <Bell size={16} />
        <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-blue-500" />
      </button>

      {/* User avatar */}
      <button
        className={cn(
          "flex items-center justify-center w-8 h-8 rounded-full",
          "bg-blue-600/20 border border-blue-700/40 text-blue-400",
          "hover:bg-blue-600/30 transition-colors",
        )}
        aria-label="User menu"
      >
        <User size={15} />
      </button>
    </header>
  );
}
