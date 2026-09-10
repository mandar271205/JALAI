// ============================================================================
// System / Models / Weather / Sources API Services
// Wraps: /api/v1/models/*, /api/v1/weather/*, /api/v1/nowcast/*, /api/v1/replay/*
// ============================================================================
import { apiClient } from "./client";
import type {
  ModelsStatus,
  SystemHealthResponse,
  CurrentWeather,
  WeatherSource,
  NowcastManifest,
  ReplayManifest,
} from "@/types";

// ---- Models / System status ------------------------------------------------
export const systemApi = {
  getModelsStatus: (): Promise<ModelsStatus> =>
    apiClient.get<ModelsStatus>("/api/v1/models/status"),

  getSystemHealth: (): Promise<SystemHealthResponse> =>
    apiClient.get<SystemHealthResponse>("/api/v1/models/health"),
};

// ---- Weather / Sources -----------------------------------------------------
export const sourcesApi = {
  getCurrentWeather: (): Promise<CurrentWeather> =>
    apiClient.get<CurrentWeather>("/api/v1/weather/current"),

  getSourcesStatus: (): Promise<WeatherSource[]> =>
    apiClient.get<WeatherSource[]>("/api/v1/weather/sources/status"),
};

// ---- Nowcast (rainfall intelligence) ---------------------------------------
export const rainfallApi = {
  getNowcastManifest: (): Promise<NowcastManifest> =>
    apiClient.get<NowcastManifest>("/api/v1/nowcast/manifest"),
};

// ---- Replay / Run Provenance -----------------------------------------------
export const runsApi = {
  getManifest: (): Promise<ReplayManifest> =>
    apiClient.get<ReplayManifest>("/api/v1/replay/manifest"),

  getMetrics: (): Promise<{
    rmse?: number;
    iou?: number;
    brier_score?: number;
    f1_score?: number;
  }> => apiClient.get("/api/v1/replay/metrics"),

  createSession: (payload?: { playback_speed?: number }): Promise<{
    session_id: string;
    status: string;
  }> => apiClient.post("/api/v1/replay/sessions", payload || {}),
};
