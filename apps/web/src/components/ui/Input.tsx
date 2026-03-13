/**
 * Input — Reusable input component.
 * Day 15: UI component library.
 *
 * Protocols: None
 * SOLID: OCP — extend via props
 */
"use client";

import { forwardRef } from "react";
import type { InputHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, leftIcon, rightIcon, className, id, ...rest }, ref) => {
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");

    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className="text-sm font-medium text-slate-300"
          >
            {label}
          </label>
        )}
        <div className="relative flex items-center">
          {leftIcon && (
            <span className="absolute left-3 text-slate-400 pointer-events-none">
              {leftIcon}
            </span>
          )}
          <input
            ref={ref}
            id={inputId}
            className={cn(
              "w-full rounded-md bg-[#1e2332] border border-[#2a3347]",
              "text-slate-200 placeholder:text-slate-500",
              "h-9 px-3 text-sm",
              "focus:outline-none focus:ring-2 focus:ring-blue-500/60 focus:border-blue-500/60",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              "transition-colors",
              leftIcon && "pl-9",
              rightIcon && "pr-9",
              error && "border-red-500/60 focus:ring-red-500/60",
              className,
            )}
            {...rest}
          />
          {rightIcon && (
            <span className="absolute right-3 text-slate-400">
              {rightIcon}
            </span>
          )}
        </div>
        {error && <p className="text-xs text-red-400">{error}</p>}
        {hint && !error && <p className="text-xs text-slate-500">{hint}</p>}
      </div>
    );
  },
);

Input.displayName = "Input";
