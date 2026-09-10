"use client";
// ============================================================================
// TopHeader — Sticky top bar
// ============================================================================
import { Bell, Search, RefreshCw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useNotificationStore } from "@/store";
import { useConnectionStatus } from "@/hooks/useRealtime";
import { cn } from "@/lib/cn";
import { useState } from "react";

export function TopHeader() {
  const queryClient = useQueryClient();
  const { unreadCount } = useNotificationStore();
  const connStatus = useConnectionStatus();
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = async () => {
    setRefreshing(true);
    await queryClient.invalidateQueries();
    setTimeout(() => setRefreshing(false), 800);
  };

  return (
    <header className="flex-shrink-0 flex items-center gap-4 px-6 py-3 bg-white border-b border-gray-200 h-14">
      {/* Left: Global search hint */}
      <div className="flex-1 max-w-sm">
        <button className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-50 border border-gray-200 text-sm text-gray-400 hover:bg-gray-100 transition-colors">
          <Search className="w-4 h-4" />
          <span>Search incidents, reports, alerts…</span>
          <kbd className="ml-auto text-xs bg-white border border-gray-200 px-1.5 py-0.5 rounded text-gray-400">
            ⌘K
          </kbd>
        </button>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-2">
        {/* Connection status chip */}
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium",
            connStatus === "CONNECTED" && "bg-emerald-50 text-emerald-700",
            connStatus === "RECONNECTING" && "bg-amber-50 text-amber-700",
            connStatus === "DEGRADED" && "bg-orange-50 text-orange-700",
            connStatus === "DISCONNECTED" && "bg-gray-50 text-gray-500",
          )}
        >
          <span
            className={cn(
              "w-1.5 h-1.5 rounded-full",
              connStatus === "CONNECTED" && "bg-emerald-500 animate-pulse-slow",
              connStatus === "RECONNECTING" && "bg-amber-400 animate-pulse",
              connStatus === "DEGRADED" && "bg-orange-500",
              connStatus === "DISCONNECTED" && "bg-gray-300",
            )}
          />
          {connStatus === "CONNECTED" ? "Live" : connStatus}
        </span>

        {/* Refresh */}
        <button
          onClick={handleRefresh}
          className="p-2 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
          title="Refresh all data"
        >
          <RefreshCw className={cn("w-4 h-4", refreshing && "animate-spin")} />
        </button>

        {/* Notifications */}
        <button className="relative p-2 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors">
          <Bell className="w-4 h-4" />
          {unreadCount > 0 && (
            <span className="absolute top-1 right-1 w-4 h-4 bg-red-500 text-white text-xs rounded-full flex items-center justify-center font-medium leading-none">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </button>
      </div>
    </header>
  );
}
