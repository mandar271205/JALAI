// ============================================================================
// Simulation API Service
// Wraps: /api/v1/simulation/*
// ============================================================================
import { apiClient } from "./client";

export interface SimulationInjectPayload {
  scenario_name?: string;
  ward_id?: string;
  ward?: string;
  rainfall_rate_mm_h: number;
  tide_level_m?: number;
  high_tide_m?: number;
  risk_level?: string;
  affected_asset?: string;
  asset_at_risk?: string;
}

export interface SimulationState {
  is_active: boolean;
  scenario_id: string | null;
  scenario_name: string | null;
  ward_id: string | null;
  ward_name: string | null;
  h3_cell_id?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  rainfall_rate_mm_h: number | null;
  max_recorded_rainfall_mm: number | null;
  tide_level_m: number;
  risk_level: string;
  affected_asset: string | null;
  injected_at: string | null;
  incident_id?: string | null;
  ai_briefing?: {
    scenario_title: string;
    executive_summary: string;
    hazard_summary: string;
    hydrodynamic_analysis: string;
    drainage_exceedance_ratio: number;
    affected_asset: string;
    action_plan: string[];
    confidence_score: number;
    synthesized_at: string;
    model_used: string;
  } | null;
}

export interface SimulationResponse {
  status: string;
  message: string;
  simulation: SimulationState;
}

export const simulationApi = {
  getStatus: (): Promise<SimulationState> =>
    apiClient.get<SimulationState>("/api/v1/simulation/status"),

  inject: (payload: SimulationInjectPayload): Promise<SimulationResponse> =>
    apiClient.post<SimulationResponse>("/api/v1/simulation/inject", payload),

  reset: (): Promise<{ status: string; message: string }> =>
    apiClient.post<{ status: string; message: string }>("/api/v1/simulation/reset", {}),
};
