// ============================================================================
// Dashboard API Service
// Wraps: GET /api/v1/dashboard/summary
// ============================================================================
import { apiClient } from "./client";
import type { DashboardSummary } from "@/types";

export const dashboardApi = {
  getSummary: (): Promise<DashboardSummary> =>
    apiClient.get<DashboardSummary>("/api/v1/dashboard/summary"),
};
