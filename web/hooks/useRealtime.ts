"use client";
// ============================================================================
// JalRakshak AI — Realtime WebSocket React Hook
// ============================================================================
import { useEffect, useCallback, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { realtimeManager } from "@/lib/realtime/websocket";
import { useNotificationStore, useAuthStore } from "@/store";
import type { WsEvent, ConnectionStatus, WsEventType, Notification } from "@/types";

// ---- Connection status hook ------------------------------------------------
export function useConnectionStatus(): ConnectionStatus {
  const { isAuthenticated } = useAuthStore();
  const [status, setStatus] = useStateRef<ConnectionStatus>("DISCONNECTED");

  useEffect(() => {
    if (!isAuthenticated) return;
    realtimeManager.connect();
    const unsub = realtimeManager.onStatusChange(setStatus);
    return () => {
      unsub();
    };
  }, [isAuthenticated, setStatus]);

  return status;
}

// ---- Event subscription hook -----------------------------------------------
export function useRealtimeEvent(
  eventType: WsEventType | "*",
  handler: (event: WsEvent) => void,
) {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    const unsub = realtimeManager.subscribe(eventType, (event) =>
      handlerRef.current(event),
    );
    return unsub;
  }, [eventType]);
}

// ---- Global realtime handler — wires events to notifications + query invalidation
export function useGlobalRealtime() {
  const queryClient = useQueryClient();
  const { addNotification } = useNotificationStore();
  const { isAuthenticated } = useAuthStore();

  useEffect(() => {
    if (!isAuthenticated) return;
    realtimeManager.connect();
  }, [isAuthenticated]);

  const handleEvent = useCallback(
    (event: WsEvent) => {
      const eventType = event.event || "";
      const payload = event.payload || {};

      // Route events to notifications + TanStack Query invalidation
      switch (true) {
        case eventType.includes("risk"):
        case eventType === "RISK_CELL_UPDATE": {
          queryClient.invalidateQueries({ queryKey: ["dashboard"] });
          queryClient.invalidateQueries({ queryKey: ["map-risk"] });
          break;
        }

        case eventType.includes("incident.created"):
        case eventType === "INCIDENT_CREATED": {
          queryClient.invalidateQueries({ queryKey: ["incidents"] });
          queryClient.invalidateQueries({ queryKey: ["dashboard"] });
          const notif: Omit<Notification, "id" | "read"> = {
            type: eventType,
            title: "New Incident Detected",
            message: String(payload["title"] || "A new incident has been reported"),
            severity: String(payload["severity"] || "HIGH"),
            entityType: "incident",
            entityId: String(payload["incident_id"] || ""),
            timestamp: event.timestamp,
          };
          addNotification(notif);
          toast.warning(notif.title, { description: notif.message });
          break;
        }

        case eventType.includes("incident"):
        case eventType === "INCIDENT_STATUS_CHANGED": {
          queryClient.invalidateQueries({ queryKey: ["incidents"] });
          break;
        }

        case eventType.includes("alert"):
        case eventType === "ALERT_BROADCAST": {
          queryClient.invalidateQueries({ queryKey: ["alerts"] });
          queryClient.invalidateQueries({ queryKey: ["dashboard"] });
          const notif: Omit<Notification, "id" | "read"> = {
            type: eventType,
            title: "Alert Published",
            message: String(payload["headline"] || "Emergency alert issued"),
            severity: String(payload["severity"] || "Severe"),
            entityType: "alert",
            entityId: String(payload["alert_id"] || ""),
            timestamp: event.timestamp,
          };
          addNotification(notif);
          toast.error(notif.title, { description: notif.message });
          break;
        }

        case eventType.includes("report"):
        case eventType === "FIELD_REPORT_SUBMITTED": {
          queryClient.invalidateQueries({ queryKey: ["reports"] });
          queryClient.invalidateQueries({ queryKey: ["dashboard"] });
          const notif: Omit<Notification, "id" | "read"> = {
            type: eventType,
            title: "New Citizen Report",
            message: "A citizen field report has been received",
            entityType: "report",
            entityId: String(payload["report_id"] || ""),
            timestamp: event.timestamp,
          };
          addNotification(notif);
          toast.info(notif.title, { description: notif.message });
          break;
        }

        case eventType === "source.degraded": {
          const notif: Omit<Notification, "id" | "read"> = {
            type: eventType,
            title: "Data Source Degraded",
            message: String(payload["source_id"] || "A data source has degraded"),
            entityType: "system",
            timestamp: event.timestamp,
          };
          addNotification(notif);
          toast.warning(notif.title, { description: notif.message });
          break;
        }

        default:
          break;
      }
    },
    [queryClient, addNotification],
  );

  useRealtimeEvent("*", handleEvent);
}

// ---- Simple useState + ref pattern for stable setter -----------------------
function useStateRef<T>(initial: T): [T, (v: T) => void] {
  const [, forceUpdate] = useForceUpdate();
  const ref = useRef<T>(initial);
  const set = useCallback((v: T) => {
    ref.current = v;
    forceUpdate();
  }, [forceUpdate]);
  return [ref.current, set];
}

function useForceUpdate() {
  const [count, setCount] = useReact().useState(0);
  const forceUpdate = useCallback(() => setCount((c) => c + 1), [setCount]);
  return [count, forceUpdate] as const;
}

// Workaround for importing React hooks in a utility file
import { useState as useReactState } from "react";
const useReact = () => ({ useState: useReactState });
