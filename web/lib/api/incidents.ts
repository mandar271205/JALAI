// ============================================================================
// Incidents API Service
// Wraps: GET/POST /api/v1/incidents, /api/v1/incidents/{id}/transition
// ============================================================================
import { apiClient, buildUrl } from "./client";
import type { Incident } from "@/types";

export const incidentsApi = {
  list: (params?: {
    status?: string;
    severity?: string;
    ward_id?: string;
  }): Promise<Incident[]> =>
    apiClient.get<Incident[]>(buildUrl("/api/v1/incidents", params || {})),

  get: (incidentId: string): Promise<Incident> =>
    apiClient.get<Incident>(`/api/v1/incidents/${incidentId}`),

  create: (payload: {
    title: string;
    category?: string;
    latitude: number;
    longitude: number;
    severity?: string;
    ward_id?: string;
    notes?: string;
  }): Promise<Incident> =>
    apiClient.post<Incident>("/api/v1/incidents", payload),

  transition: (
    incidentId: string,
    payload: { target_status: string; reason?: string; notes?: string },
  ): Promise<{ status: string; event: unknown; audit_event: unknown }> =>
    apiClient.post(`/api/v1/incidents/${incidentId}/transition`, payload),
};
