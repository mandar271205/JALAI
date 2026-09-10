// ============================================================================
// Audit API Service
// Wraps: GET /api/v1/audit/logs
// IMPORTANT: Access restricted to DISASTER_MANAGER / SUPER_ADMIN
// ============================================================================
import { apiClient, buildUrl } from "./client";
import type { AuditLog } from "@/types";

export const auditApi = {
  listLogs: (params: {
    action?: string;
    target_entity?: string;
    actor_id?: string;
    trace_id?: string;
    limit?: number;
  }): Promise<AuditLog[]> =>
    apiClient.get<AuditLog[]>(buildUrl("/api/v1/audit/logs", params)),
};
