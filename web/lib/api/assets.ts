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
};
