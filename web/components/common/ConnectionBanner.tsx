"use client";
// ============================================================================
// ConnectionBanner — Fixed bottom banner for WebSocket status
// ============================================================================
import { useConnectionStatus } from "@/hooks/useRealtime";
import { cn } from "@/lib/cn";
import { Wifi, WifiOff, RefreshCw, AlertTriangle } from "lucide-react";
import { realtimeManager } from "@/lib/realtime/websocket";

export function ConnectionBanner() {
  const status = useConnectionStatus();

  if (status === "CONNECTED") return null;

  const config = {
    RECONNECTING: {
      icon: <RefreshCw className="w-3.5 h-3.5 animate-spin" />,
      text: "Reconnecting to live feed…",
      cls: "bg-amber-100 text-amber-800 border border-amber-200",
    },
    DEGRADED: {
      icon: <AlertTriangle className="w-3.5 h-3.5" />,
      text: "Live feed unavailable — showing cached data",
      cls: "bg-orange-100 text-orange-800 border border-orange-200",
    },
    DISCONNECTED: {
      icon: <WifiOff className="w-3.5 h-3.5" />,
      text: "Not connected",
      cls: "bg-gray-100 text-gray-700 border border-gray-200",
    },
  }[status] || null;

  if (!config) return null;

  return (
    <div className={cn("connection-banner", config.cls)}>
      {config.icon}
      <span>{config.text}</span>
      {status === "DEGRADED" && (
        <button
          onClick={() => realtimeManager.connect()}
          className="ml-2 underline hover:no-underline"
        >
          Retry
        </button>
      )}
    </div>
  );
}
