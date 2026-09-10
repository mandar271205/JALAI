"use client";
// ============================================================================
// AppShell — Main layout wrapper for authenticated pages
// ============================================================================
import { useEffect } from "react";
import { Sidebar } from "./Sidebar";
import { TopHeader } from "./TopHeader";
import { ConnectionBanner } from "@/components/common/ConnectionBanner";
import { useGlobalRealtime } from "@/hooks/useRealtime";
import { useAuthStore } from "@/store";

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const { isAuthenticated } = useAuthStore();

  // Wire global realtime events (incidents, alerts, reports, risk)
  useGlobalRealtime();

  if (!isAuthenticated) {
    return null; // Auth redirect is handled at route level
  }

  return (
    <div className="flex h-screen bg-jr-gray-50 overflow-hidden">
      {/* Fixed sidebar */}
      <Sidebar />

      {/* Main content area */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* Top header */}
        <TopHeader />

        {/* Scrollable page content */}
        <main className="flex-1 overflow-y-auto scrollbar-thin">
          {children}
        </main>
      </div>

      {/* Realtime connection status banner */}
      <ConnectionBanner />
    </div>
  );
}
