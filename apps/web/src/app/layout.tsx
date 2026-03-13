/**
 * RootLayout — App shell with sidebar, topbar, and providers.
 * Day 15: Dashboard UI shell.
 *
 * Protocols: None
 * SOLID: SRP — layout/shell only; DIP — providers injected as children
 */
import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/Providers";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";

export const metadata: Metadata = {
  title: "DataMind — AI-Native Analytics",
  description: "Enterprise AI analytics & digital labor platform",
  icons: { icon: "/favicon.ico" },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#0f1117] text-slate-200 antialiased">
        <Providers>
          <div className="flex h-screen overflow-hidden">
            {/* Sidebar — hidden on mobile via CSS, visible md+ */}
            <div className="hidden md:flex">
              <Sidebar />
            </div>

            {/* Main column */}
            <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
              <TopBar />
              <main className="flex-1 overflow-y-auto">
                {children}
              </main>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
