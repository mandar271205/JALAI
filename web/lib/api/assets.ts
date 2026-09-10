// ============================================================================
// Assets API Service
// Wraps: GET /api/v1/assets
// ============================================================================
import { apiClient, buildUrl } from "./client";
import type { CriticalAssetsResponse } from "@/types";

export const assetsApi = {
  list: (params?: {
    asset_type?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<CriticalAssetsResponse> =>
    apiClient.get<CriticalAssetsResponse>(buildUrl("/api/v1/assets", params || {})),

  create: (payload: {
    name: string;
    asset_type?: string;
    ward_id?: string;
    latitude: number;
    longitude: number;
    status?: string;
    risk_level?: string;
    inundation_threshold_m?: number;
  }): Promise<unknown> => apiClient.post("/api/v1/assets", payload),
};
