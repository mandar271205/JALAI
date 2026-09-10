// ============================================================================
// Alerts API Service
// Wraps: POST /api/v1/alerts/draft, /approve, /publish, GET /cap.xml
// ============================================================================
import { apiClient, buildUrl } from "./client";
import type { Alert } from "@/types";

export const alertsApi = {
  /**
   * NOTE: Backend does not have GET /api/v1/alerts (list).
   * Alerts list is retrieved via map/alerts or dashboard summary.
   * We use the map endpoint with no bbox filter as a fallback.
   */
  list: (params?: { status?: string; severity?: string }): Promise<{
    type: string;
    count: number;
    features: Alert[];
  }> =>
    apiClient.get(buildUrl("/api/v1/map/alerts", params || {})),

  /**
   * Create a draft alert (ANALYST+ only)
   * Severity must be: "Extreme" | "Severe" | "Moderate" | "Minor" | "Unknown"
   * Confidence must be >= 0.5
   */
  draft: (payload: {
    headline: string;
    description?: string;
    instruction?: string;
    severity: string;
    urgency?: string;
    certainty?: string;
    area_description: string;
    ward_id?: string;
    confidence?: number;
    source_risk_snapshot?: Record<string, unknown>;
  }): Promise<Alert> => apiClient.post<Alert>("/api/v1/alerts/draft", payload),

  /** Approve a DRAFT alert (ALERT_APPROVER+ only) */
  approve: (alertId: string): Promise<Alert> =>
    apiClient.post<Alert>(`/api/v1/alerts/${alertId}/approve`, {}),

  /** Publish an APPROVED alert — triggers CAP XML, WebSocket fanout, mobile push */
  publish: (alertId: string): Promise<{
    alert_id: string;
    status: string;
    sent_at: string;
    cap_xml_preview: string;
    audit_event: unknown;
  }> => apiClient.post(`/api/v1/alerts/${alertId}/publish`, {}),

  /** Get CAP 1.2 XML for an alert */
  getCapXml: (alertId: string): Promise<string> =>
    apiClient.get<string>(`/api/v1/alerts/${alertId}/cap.xml`, {
      headers: { Accept: "application/xml" },
    }),
};
