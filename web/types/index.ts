// ============================================================================
// JalRakshak AI — Complete Domain TypeScript Types
// Typed against real backend schemas (backend/app/api/v1/*)
// ============================================================================

// ------ Auth / Users -------------------------------------------------------
export type UserRole =
  | "CITIZEN"
  | "FIELD_RESPONDER"
  | "ANALYST"
  | "ALERT_APPROVER"
  | "MUNICIPAL_OFFICER"
  | "DISASTER_MANAGER"
  | "ADMIN"
  | "SUPER_ADMIN"
  | "ML_ADMIN";

export interface AuthUser {
  user_id: string;
  email: string | null;
  role: UserRole;
  metadata: Record<string, unknown>;
}

export interface AuthSession {
  user: AuthUser;
  token: string;
  expiresAt?: string;
}

// ------ Risk / Hazard -------------------------------------------------------
export type RiskLevel = "LOW" | "MODERATE" | "HIGH" | "SEVERE";

export interface RiskCell {
  h3_cell_id?: string;
  cell_id?: string;
  latitude?: number;
  longitude?: number;
  risk_level: RiskLevel;
  hazard_score?: number;
  exposure_score?: number;
  vulnerability_score?: number;
  composite_risk_score?: number;
  confidence?: number;
  data_quality?: number;
  rainfall_rate_mm_h?: number;
  ward_id?: string;
  ward_name?: string;
  valid_time?: string;
  forecast_horizon_min?: number;
  reasoning?: string;
  top_factors?: string[];
}

export interface RiskCellCollection {
  type: "RiskCellCollection";
  bbox: string | null;
  count: number;
  features: RiskCell[];
}

export interface RiskCellsResponse {
  total: number;
  limit: number;
  offset: number;
  valid_time: string;
  model_version: string;
  data_version: string;
  confidence: number;
  items: RiskCell[];
}

export interface CellTimeline {
  h3_cell_id: string;
  model_version: string;
  data_version: string;
  valid_time: string;
  confidence: number;
  timeline: Array<{
    time_offset_min: number;
    risk_level: RiskLevel;
    depth_m: number | null;
    probability: number;
  }>;
}

// ------ Dashboard -----------------------------------------------------------
export interface DashboardKPIs {
  high_severe_risk_cells_count: number;
  active_incidents_count: number;
  unverified_reports_count: number;
  critical_assets_at_risk_count: number;
  active_alerts_count: number;
  active_responders_count: number;
}

export interface CityRiskStatus {
  city_max_risk_level: RiskLevel;
  peak_rainfall_rate_mm_h: number;
  affected_wards: string[];
  lead_time_minutes: number;
  summary: string;
}

export interface ModelHealth {
  database_connected: boolean;
  radar_feed_status: string;
  groq_primary_available: boolean;
  groq_vision_available: boolean;
  rainfall_winner_frozen: boolean;
  fno_validated: boolean;
  operational_mode: string;
}

export interface DashboardSummary {
  generated_at: string;
  kpis: DashboardKPIs;
  city_risk_status: CityRiskStatus;
  model_health: ModelHealth;
  recent_incidents: Incident[];
  recent_alerts: Alert[];
  recent_reports: FieldReport[];
}

// ------ Incidents -----------------------------------------------------------
export type IncidentStatus =
  | "OPEN"
  | "DETECTED"
  | "ACKNOWLEDGED"
  | "DISPATCHED"
  | "ON_SCENE"
  | "RESOLVED"
  | "CLOSED"
  | "PENDING";

export type IncidentSeverity = "LOW" | "MODERATE" | "HIGH" | "SEVERE" | "CRITICAL";

export interface IncidentTimelineEvent {
  event_id: string;
  incident_id: string;
  actor_id: string;
  previous_status: string | null;
  new_status: string;
  reason: string;
  created_at: string;
}

export interface Incident {
  incident_id: string;
  title: string;
  category?: string;
  status: IncidentStatus;
  severity: IncidentSeverity | string;
  latitude?: number;
  longitude?: number;
  ward_id?: string;
  description?: string;
  reporter_id?: string;
  created_at?: string;
  updated_at?: string;
  timeline?: IncidentTimelineEvent[];
  linked_report_ids?: string[];
  assigned_responder_id?: string;
}

export interface IncidentCollection {
  type: "IncidentCollection";
  bbox: string | null;
  count: number;
  features: Incident[];
}

// ------ Citizen Reports -----------------------------------------------------
export type ReportVerificationStatus =
  | "DRAFT"
  | "PENDING"
  | "AI_VERIFIED"
  | "HUMAN_VERIFIED"
  | "CORROBORATED"
  | "PARTIALLY_SUPPORTED"
  | "LOW_EVIDENCE"
  | "REJECTED"
  | "REVIEWED";

export interface VisualCorroboration {
  water_visible: boolean;
  visual_severity: string;
  visual_support_score: number;
  /** STRICT: Must remain null — never fabricate */
  exact_depth_m: null;
  observations: string[];
}

export interface FieldReport {
  report_id: string;
  citizen_id: string;
  latitude: number;
  longitude: number;
  description: string;
  image_url: string | null;
  verification_status: ReportVerificationStatus;
  ai_confidence: number | null;
  /** STRICT: Must remain null — never fabricate from citizen photo */
  estimated_water_depth_cm: null;
  visual_corroboration: VisualCorroboration | null;
  weather_context?: {
    local_risk_level?: RiskLevel;
    rainfall_support?: boolean;
  };
  created_at?: string;
  incident_id?: string | null;
}

export interface FieldReportCollection {
  type: "FieldReportCollection";
  bbox: string | null;
  count: number;
  features: FieldReport[];
}

// ------ Alerts --------------------------------------------------------------
export type AlertStatus = "DRAFT" | "APPROVED" | "PUBLISHED" | "BROADCAST" | "EXPIRED" | "CANCELLED";
export type AlertSeverity = "Extreme" | "Severe" | "Moderate" | "Minor" | "Unknown";

export interface Alert {
  alert_id: string;
  status: AlertStatus;
  headline: string;
  description?: string;
  instruction?: string;
  severity: AlertSeverity | string;
  urgency?: string;
  certainty?: string;
  area_description: string;
  ward_id?: string | null;
  source_risk_snapshot?: Record<string, unknown>;
  confidence?: number;
  created_by?: string;
  created_at?: string;
  approved_by?: string | null;
  approved_at?: string | null;
  sent_at?: string | null;
  cap_xml?: string | null;
}

export interface AlertCollection {
  type: "AlertCollection";
  bbox: string | null;
  count: number;
  features: Alert[];
}

// ------ Critical Assets -----------------------------------------------------
export type AssetStatus = "NORMAL" | "AT_RISK" | "INUNDATED" | "OFFLINE";
export type AssetType = "HOSPITAL" | "POWER_SUBSTATION" | "FIRE_STATION" | "RELIEF_SHELTER" | string;

export interface CriticalAsset {
  asset_id?: string;
  id?: string;
  name: string;
  asset_type: AssetType;
  category?: string;
  status: AssetStatus | string;
  risk_level?: RiskLevel;
  latitude: number;
  longitude: number;
  ward_id?: string;
  capacity?: number;
  current_occupancy?: number;
  contact?: string;
  nearby_incident_id?: string | null;
  active_alert_id?: string | null;
}

export interface CriticalAssetCollection {
  type: "CriticalAssetCollection";
  bbox: string | null;
  count: number;
  features: CriticalAsset[];
}

export interface CriticalAssetsResponse {
  total: number;
  limit: number;
  offset: number;
  items: CriticalAsset[];
}

// ------ Responders ----------------------------------------------------------
export type TaskStatus =
  | "ASSIGNED"
  | "ACKNOWLEDGED"
  | "EN_ROUTE"
  | "ON_SCENE"
  | "COMPLETED"
  | "BLOCKED";

export interface ResponderTask {
  task_id: string;
  incident_id: string;
  responder_id: string;
  task_type: string;
  priority: "HIGH" | "MEDIUM" | "LOW" | string;
  status: TaskStatus | string;
  instructions?: string;
  latitude?: number;
  longitude?: number;
  assigned_at?: string;
  updated_at?: string;
  evidence_url?: string | null;
  measured_depth_cm?: number | null;
  notes?: string | null;
  version?: number;
}

// ------ Weather / Sources ---------------------------------------------------
export type SourceStatus = "HEALTHY" | "DEGRADED" | "UNAVAILABLE" | "NOT_CONFIGURED" | "HISTORICAL_ONLY";

export interface WeatherSource {
  source_id: string;
  name?: string;
  source_type: string;
  status: SourceStatus | string;
  last_successful_ingestion?: string;
  latency_seconds?: number;
  freshness_seconds?: number;
  missing_percentage?: number;
  quality_score?: number;
  coverage?: string;
  operational_role?: string;
}

export interface CurrentWeather {
  timestamp: string;
  summary: string;
  average_rainfall_rate_mm_h: number;
  max_recorded_rainfall_mm: number;
  active_stations: number;
  model_version: string;
  data_version: string;
  confidence: number;
}

// ------ Models / System Status ----------------------------------------------
export type SystemComponentStatus = "HEALTHY" | "DEGRADED" | "UNAVAILABLE";

export interface ModelHealth2 {
  model_type: string;
  model_version: string;
  data_version: string;
  latest_run_id: string;
  latest_run_time: string;
  inference_duration_ms: number;
  status: SystemComponentStatus;
  degraded: boolean;
}

export interface SystemHealthResponse {
  status: SystemComponentStatus;
  timestamp: string;
  degraded_mode: boolean;
  fallback_state: string;
  sources_health: WeatherSource[];
  models_health: ModelHealth2[];
  aggregation_summary: {
    overall_source_quality: number;
    average_missing_percentage: number;
    max_source_latency_seconds: number;
    average_inference_duration_ms: number;
    all_systems_operational: boolean;
  };
}

export interface ModelsStatus {
  status: string;
  orchestrator_mode: string;
  models: {
    nowcasting: { name: string; version: string; status: string; last_run: string | null };
    inundation: { name: string; version: string; status: string; last_run: string | null };
    vision_verification: { name: string; version: string; status: string };
  };
}

// ------ Nowcast / Replay ----------------------------------------------------
export interface NowcastManifest {
  model_version?: string;
  generated_at?: string;
  horizons?: Array<{
    offset_min: number;
    confidence: number;
    quality_score: number;
  }>;
  data_quality?: number;
  source_freshness_seconds?: number;
  fallback_active?: boolean;
}

export interface ReplayManifest {
  event_name?: string;
  event_date?: string;
  timesteps?: Array<{
    timestamp: string;
    weather?: Record<string, unknown>;
    risk_summary?: Record<string, unknown>;
  }>;
  predicted_vs_observed_metrics?: {
    rmse?: number;
    iou?: number;
    brier_score?: number;
    f1_score?: number;
  };
}

// ------ Audit ---------------------------------------------------------------
export interface AuditLog {
  log_id: string;
  actor_id: string;
  actor_role: string;
  action: string;
  target_entity: string;
  target_id: string;
  before_state?: Record<string, unknown>;
  after_state?: Record<string, unknown>;
  before_hash?: string;
  after_hash?: string;
  trace_id?: string;
  created_at: string;
}

// ------ WebSocket Events ---------------------------------------------------
export type WsEventType =
  | "telemetry.heartbeat"
  | "risk.cell.updated"
  | "RISK_CELL_UPDATE"
  | "incident.created"
  | "INCIDENT_CREATED"
  | "incident.updated"
  | "INCIDENT_STATUS_CHANGED"
  | "alert.published"
  | "ALERT_BROADCAST"
  | "report.received"
  | "FIELD_REPORT_SUBMITTED"
  | "report.verified"
  | "source.degraded"
  | "model.run.completed"
  | "RESPONDER_LOCATION_UPDATE";

export interface WsEvent {
  event: WsEventType | string;
  timestamp: string;
  payload: Record<string, unknown>;
  event_id?: number;
}

// ------ API Common ----------------------------------------------------------
export interface ApiError {
  detail: string;
  status_code?: number;
}

export interface PaginatedResponse<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

// ------ UI State -----------------------------------------------------------
export type ConnectionStatus = "CONNECTED" | "RECONNECTING" | "DISCONNECTED" | "DEGRADED";

export interface Notification {
  id: string;
  type: WsEventType | string;
  title: string;
  message: string;
  severity?: RiskLevel | AlertSeverity | string;
  entityType?: "alert" | "incident" | "report" | "system";
  entityId?: string;
  timestamp: string;
  read: boolean;
}
