/**
 * Providers — Root client providers (QueryClient, DnD).
 * Day 15: Dashboard UI foundation.
 *
 * Protocols: None
 * SOLID: SRP — provider wiring only; no business logic
 */
"use client";

import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DndProvider } from "react-dnd";
import { HTML5Backend } from "react-dnd-html5-backend";

interface ProvidersProps {
  children: ReactNode;
}

export function Providers({ children }: ProvidersProps) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 2,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <DndProvider backend={HTML5Backend}>{children}</DndProvider>
    </QueryClientProvider>
  );
}
