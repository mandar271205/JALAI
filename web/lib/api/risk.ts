// ============================================================================
// Risk API Service
// Wraps: GET /api/v1/risk/cells, /risk/{h3_cell}/timeline
// ============================================================================
import { apiClient, buildUrl } from "./client";
import type { RiskCellsResponse, CellTimeline } from "@/types";

export const riskApi = {
  getCells: (params: {
    bbox?: string;
    valid_time?: string;
    limit?: number;
    offset?: number;
  }): Promise<RiskCellsResponse> =>
    apiClient.get<RiskCellsResponse>(buildUrl("/api/v1/risk/cells", params)),

  getCellTimeline: (h3Cell: string): Promise<CellTimeline> =>
    apiClient.get<CellTimeline>(`/api/v1/risk/${h3Cell}/timeline`),
};
