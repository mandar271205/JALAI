// ============================================================================
// Map / GIS API Service
// Wraps: GET /api/v1/map/* (bbox-aware spatial queries)
// ============================================================================
import { apiClient, buildUrl } from "./client";
import type {
  RiskCellCollection,
  IncidentCollection,
  FieldReportCollection,
  CriticalAssetCollection,
  AlertCollection,
} from "@/types";

export const mapApi = {
  getRiskCells: (params: {
    bbox?: string;
    min_level?: string;
  }): Promise<RiskCellCollection> =>
    apiClient.get<RiskCellCollection>(
      buildUrl("/api/v1/map/risk", params),
    ),

  getIncidents: (params: {
    bbox?: string;
    severity?: string;
    status?: string;
  }): Promise<IncidentCollection> =>
    apiClient.get<IncidentCollection>(
      buildUrl("/api/v1/map/incidents", params),
    ),

  getReports: (params: {
    bbox?: string;
    status?: string;
  }): Promise<FieldReportCollection> =>
    apiClient.get<FieldReportCollection>(
      buildUrl("/api/v1/map/reports", params),
    ),

  getAssets: (params: {
    bbox?: string;
    category?: string;
  }): Promise<CriticalAssetCollection> =>
    apiClient.get<CriticalAssetCollection>(
      buildUrl("/api/v1/map/assets", params),
    ),

  getAlerts: (params: {
    bbox?: string;
    severity?: string;
  }): Promise<AlertCollection> =>
    apiClient.get<AlertCollection>(
      buildUrl("/api/v1/map/alerts", params),
    ),

  /** Tile URL builder (for MapLibre raster source) */
  getNowcastTileUrl: () =>
    `${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"}/api/v1/tiles/nowcast/{z}/{x}/{y}.png`,

  getRiskTileUrl: () =>
    `${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"}/api/v1/tiles/risk/{z}/{x}/{y}.png`,
};
