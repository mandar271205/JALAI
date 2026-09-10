// ============================================================================
// JalRakshak AI — Realtime WebSocket Manager
// Backend endpoint: /api/v1/live (NOT /ws/live - verified from live.py)
// ============================================================================

import type { WsEvent, WsEventType, ConnectionStatus } from "@/types";
import { buildWsUrl } from "@/lib/api/client";

type EventHandler = (event: WsEvent) => void;
type StatusHandler = (status: ConnectionStatus) => void;

const WS_PATH = "/api/v1/live";
const HEARTBEAT_INTERVAL_MS = 30_000;
const BASE_RECONNECT_DELAY_MS = 1_000;
const MAX_RECONNECT_DELAY_MS = 30_000;
const MAX_RECONNECT_ATTEMPTS = 10;
const EVENT_DEDUP_WINDOW_MS = 5_000;

export class RealtimeManager {
  private ws: WebSocket | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  private status: ConnectionStatus = "DISCONNECTED";
  private lastEventId: number | null = null;
  private recentEventIds = new Map<string, number>(); // dedup cache

  private eventHandlers = new Map<string, Set<EventHandler>>();
  private statusHandlers = new Set<StatusHandler>();

  // ---- Public API -----------------------------------------------------------
  connect(lastEventId?: number) {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    this._clearTimers();
    this.lastEventId = lastEventId ?? this.lastEventId;
    this._openConnection();
  }

  disconnect() {
    this.reconnectAttempts = MAX_RECONNECT_ATTEMPTS; // prevent auto-reconnect
    this._clearTimers();
    if (this.ws) {
      this.ws.onclose = null; // prevent reconnect handler
      this.ws.close(1000, "Client disconnect");
      this.ws = null;
    }
    this._setStatus("DISCONNECTED");
  }

  subscribe(eventType: WsEventType | "*", handler: EventHandler): () => void {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, new Set());
    }
    this.eventHandlers.get(eventType)!.add(handler);
    return () => this.eventHandlers.get(eventType)?.delete(handler);
  }

  onStatusChange(handler: StatusHandler): () => void {
    this.statusHandlers.add(handler);
    // Immediately deliver current status
    handler(this.status);
    return () => this.statusHandlers.delete(handler);
  }

  getStatus(): ConnectionStatus {
    return this.status;
  }

  // ---- Private methods -------------------------------------------------------
  private _openConnection() {
    if (typeof window === "undefined") return;

    const url = buildWsUrl(WS_PATH);
    const fullUrl = this.lastEventId
      ? `${url}&last_event_id=${this.lastEventId}`
      : url;

    try {
      this.ws = new WebSocket(fullUrl);
    } catch (err) {
      console.warn("[Realtime] WebSocket creation failed:", err);
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this._setStatus("CONNECTED");
      this._startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      this._handleMessage(event.data);
    };

    this.ws.onclose = (event) => {
      this._clearHeartbeat();
      if (event.code === 1000) {
        // Normal close — do not reconnect
        this._setStatus("DISCONNECTED");
      } else {
        this._setStatus("RECONNECTING");
        this._scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      // onclose will fire after onerror
      this._setStatus("RECONNECTING");
    };
  }

  private _handleMessage(raw: string) {
    let msg: WsEvent;
    try {
      msg = JSON.parse(raw);
    } catch {
      console.warn("[Realtime] Failed to parse message:", raw);
      return;
    }

    // Track event IDs for reconnect
    if (msg.event_id !== undefined && typeof msg.event_id === "number") {
      this.lastEventId = msg.event_id;
    }

    // Deduplication using event_id or composite key
    const dedupKey = this._buildDedupKey(msg);
    const now = Date.now();
    if (this.recentEventIds.has(dedupKey)) {
      const seenAt = this.recentEventIds.get(dedupKey)!;
      if (now - seenAt < EVENT_DEDUP_WINDOW_MS) return;
    }
    this.recentEventIds.set(dedupKey, now);
    this._pruneDedup(now);

    // Dispatch to typed handlers
    const eventType = (msg.event || "") as WsEventType;
    const handlers = this.eventHandlers.get(eventType);
    if (handlers) handlers.forEach((h) => h(msg));

    // Wildcard handlers
    const wildcardHandlers = this.eventHandlers.get("*");
    if (wildcardHandlers) wildcardHandlers.forEach((h) => h(msg));
  }

  private _buildDedupKey(msg: WsEvent): string {
    if (msg.event_id !== undefined) return String(msg.event_id);
    const payload = msg.payload || {};
    const entityId =
      payload["alert_id"] ||
      payload["incident_id"] ||
      payload["report_id"] ||
      "";
    return `${msg.event}:${entityId}:${msg.timestamp}`;
  }

  private _pruneDedup(now: number) {
    this.recentEventIds.forEach((seenAt, key) => {
      if (now - seenAt > EVENT_DEDUP_WINDOW_MS) {
        this.recentEventIds.delete(key);
      }
    });
  }

  private _startHeartbeat() {
    this._clearHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "ping", timestamp: new Date().toISOString() }));
      }
    }, HEARTBEAT_INTERVAL_MS);
  }

  private _clearHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private _scheduleReconnect() {
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      this._setStatus("DEGRADED");
      return;
    }

    const delay = Math.min(
      BASE_RECONNECT_DELAY_MS * Math.pow(2, this.reconnectAttempts),
      MAX_RECONNECT_DELAY_MS,
    );
    this.reconnectAttempts++;

    console.info(`[Realtime] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    this.reconnectTimer = setTimeout(() => this._openConnection(), delay);
  }

  private _clearTimers() {
    this._clearHeartbeat();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private _setStatus(status: ConnectionStatus) {
    if (this.status === status) return;
    this.status = status;
    this.statusHandlers.forEach((h) => h(status));
  }
}

// Singleton instance — shared across the application
export const realtimeManager = new RealtimeManager();
