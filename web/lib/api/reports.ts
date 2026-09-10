// ============================================================================
// Reports API Service
// Wraps: GET/POST /api/v1/reports, /api/v1/reports/{id}/review
// ============================================================================
import { apiClient, buildUrl } from "./client";
import type { FieldReport } from "@/types";

export const reportsApi = {
  list: (params: {
    status?: string;
    severity?: string;
    bbox?: string;
    incident_id?: string;
    limit?: number;
    offset?: number;
  }): Promise<FieldReport[]> =>
    apiClient.get<FieldReport[]>(buildUrl("/api/v1/reports", params)),

  get: (reportId: string): Promise<FieldReport> =>
    apiClient.get<FieldReport>(`/api/v1/reports/${reportId}`),

  getStatus: (reportId: string): Promise<{ report_id: string; verification_status: string }> =>
    apiClient.get(`/api/v1/reports/${reportId}/status`),

  review: (
    reportId: string,
    payload: { status: string; notes?: string },
  ): Promise<{ report_id: string; status: string; audit_event: unknown }> =>
    apiClient.post(`/api/v1/reports/${reportId}/review`, payload),

  createDraft: (payload: {
    latitude: number;
    longitude: number;
    description?: string;
    incident_id?: string;
  }): Promise<FieldReport> =>
    apiClient.post<FieldReport>("/api/v1/reports/draft", payload),
};
