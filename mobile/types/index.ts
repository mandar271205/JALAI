export type UserRole = "CITIZEN" | "FIELD_RESPONDER";
export type RiskLevel = "LOW" | "MODERATE" | "HIGH" | "SEVERE" | "UNKNOWN";
export type AppSession = {
  token?: string;
  userId: string;
  email?: string;
  role: UserRole;
  mock: boolean;
};
export type ApiRecord = Record<string, unknown>;
export type RainfallHorizon = {
  lead_time_minutes: number;
  rainfall_rate_mm_h: number | null;
  category?: string;
  trend?: string;
  confidence?: number | null;
};
export type MobileHome = {
  location?: {
    latitude: number;
    longitude: number;
    ward_id?: string;
    radius_km?: number;
  };
  current_risk?: {
    risk_level: RiskLevel;
    risk_score?: number;
    summary?: string;
    confidence?: number;
    is_fallback?: boolean;
  };
  rainfall_outlook?: RainfallHorizon[];
  active_alerts?: ApiRecord[];
  nearby_incidents?: ApiRecord[];
  nearby_reports?: ApiRecord[];
  watched_locations?: ApiRecord[];
  system_status?: {
    timestamp?: string;
    operational_mode?: string;
    is_radar_available?: boolean;
    provisional_model_fallback?: boolean;
  };
};
