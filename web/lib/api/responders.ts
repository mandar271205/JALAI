// ============================================================================
// Responders API Service
// Wraps: GET/POST /api/v1/responders/tasks, /tasks/{id}/action
// ============================================================================
import { apiClient, buildUrl } from "./client";
import type { ResponderTask } from "@/types";

export const respondersApi = {
  listTasks: (params: {
    responder_id?: string;
    status?: string;
  }): Promise<ResponderTask[]> =>
    apiClient.get<ResponderTask[]>(buildUrl("/api/v1/responders/tasks", params)),

  createTask: (payload: {
    incident_id: string;
    responder_id: string;
    task_type?: string;
    priority?: string;
    instructions?: string;
    latitude?: number;
    longitude?: number;
  }): Promise<ResponderTask> =>
    apiClient.post<ResponderTask>("/api/v1/responders/tasks", payload),

  applyAction: (
    taskId: string,
    payload: {
      action: string;
      base_version: number;
      evidence_url?: string;
      measured_depth_cm?: number;
      notes?: string;
    },
  ): Promise<ResponderTask & { audit_event: unknown }> =>
    apiClient.post(`/api/v1/responders/tasks/${taskId}/action`, payload),
};
