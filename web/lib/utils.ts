// ============================================================================
// Utility functions
// ============================================================================
import type { RiskLevel, AlertSeverity } from "@/types";

// ---- Risk formatting -------------------------------------------------------
export const RISK_COLORS: Record<RiskLevel, { bg: string; text: string; border: string; badge: string }> = {
  LOW: {
    bg: "bg-emerald-50",
    text: "text-emerald-700",
    border: "border-emerald-200",
    badge: "bg-emerald-100 text-emerald-700",
  },
  MODERATE: {
    bg: "bg-amber-50",
    text: "text-amber-700",
    border: "border-amber-200",
    badge: "bg-amber-100 text-amber-700",
  },
  HIGH: {
    bg: "bg-orange-50",
    text: "text-orange-700",
    border: "border-orange-200",
    badge: "bg-orange-100 text-orange-700",
  },
  SEVERE: {
    bg: "bg-red-50",
    text: "text-red-700",
    border: "border-red-200",
    badge: "bg-red-100 text-red-700",
  },
};

export function getRiskColors(level: RiskLevel | string) {
  return RISK_COLORS[level as RiskLevel] || RISK_COLORS.LOW;
}

// ---- Alert severity formatting ---------------------------------------------
export const ALERT_SEVERITY_COLORS: Record<AlertSeverity, string> = {
  Extreme: "bg-red-600 text-white",
  Severe: "bg-red-500 text-white",
  Moderate: "bg-amber-500 text-white",
  Minor: "bg-blue-500 text-white",
  Unknown: "bg-gray-400 text-white",
};

export function getAlertSeverityColor(severity: AlertSeverity | string): string {
  return ALERT_SEVERITY_COLORS[severity as AlertSeverity] || "bg-gray-400 text-white";
}

// ---- Status badge formatting ------------------------------------------------
export const STATUS_COLORS: Record<string, string> = {
  // Incidents
  OPEN: "bg-blue-100 text-blue-700",
  DETECTED: "bg-indigo-100 text-indigo-700",
  ACKNOWLEDGED: "bg-purple-100 text-purple-700",
  DISPATCHED: "bg-cyan-100 text-cyan-700",
  ON_SCENE: "bg-teal-100 text-teal-700",
  RESOLVED: "bg-emerald-100 text-emerald-700",
  CLOSED: "bg-gray-100 text-gray-600",
  PENDING: "bg-yellow-100 text-yellow-700",
  // Alerts
  DRAFT: "bg-gray-100 text-gray-600",
  APPROVED: "bg-blue-100 text-blue-700",
  PUBLISHED: "bg-emerald-100 text-emerald-700",
  BROADCAST: "bg-emerald-100 text-emerald-700",
  EXPIRED: "bg-gray-100 text-gray-500",
  CANCELLED: "bg-red-100 text-red-700",
  // Reports
  AI_VERIFIED: "bg-blue-100 text-blue-700",
  HUMAN_VERIFIED: "bg-emerald-100 text-emerald-700",
  CORROBORATED: "bg-green-100 text-green-700",
  PARTIALLY_SUPPORTED: "bg-amber-100 text-amber-700",
  LOW_EVIDENCE: "bg-orange-100 text-orange-700",
  REJECTED: "bg-red-100 text-red-700",
  REVIEWED: "bg-purple-100 text-purple-700",
  // Tasks
  ASSIGNED: "bg-blue-100 text-blue-700",
  EN_ROUTE: "bg-cyan-100 text-cyan-700",
  COMPLETED: "bg-emerald-100 text-emerald-700",
  BLOCKED: "bg-red-100 text-red-700",
  // System
  HEALTHY: "bg-emerald-100 text-emerald-700",
  DEGRADED: "bg-amber-100 text-amber-700",
  UNAVAILABLE: "bg-red-100 text-red-700",
  NOT_CONFIGURED: "bg-gray-100 text-gray-500",
  HISTORICAL_ONLY: "bg-blue-50 text-blue-600",
};

export function getStatusColor(status: string): string {
  return STATUS_COLORS[status] || "bg-gray-100 text-gray-600";
}

// ---- Date/Time formatting --------------------------------------------------
export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const date = new Date(iso);
    return new Intl.DateTimeFormat("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Asia/Kolkata",
    }).format(date);
  } catch {
    return iso;
  }
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const seconds = Math.floor(diff / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  } catch {
    return "—";
  }
}

// ---- Number formatting -----------------------------------------------------
export function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return new Intl.NumberFormat("en-IN").format(n);
}

export function formatPercent(n: number | null | undefined, decimals = 0): string {
  if (n === null || n === undefined) return "—";
  return `${(n * 100).toFixed(decimals)}%`;
}

export function formatMmH(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `${n.toFixed(1)} mm/h`;
}

// ---- Mumbai bounding box ---------------------------------------------------
export const MUMBAI_BBOX = {
  west: 72.775,
  south: 18.89,
  east: 72.98,
  north: 19.27,
} as const;

export function getMumbaiBboxString(): string {
  return `${MUMBAI_BBOX.west},${MUMBAI_BBOX.south},${MUMBAI_BBOX.east},${MUMBAI_BBOX.north}`;
}

export const MUMBAI_CENTER: [number, number] = [72.8777, 19.076]; // [lng, lat]
export const MUMBAI_ZOOM = 11;

// ---- Viewport bbox debounce helper -----------------------------------------
export function viewportToBbox(bounds: {
  _sw: { lng: number; lat: number };
  _ne: { lng: number; lat: number };
}): string {
  const { _sw, _ne } = bounds;
  return `${_sw.lng.toFixed(4)},${_sw.lat.toFixed(4)},${_ne.lng.toFixed(4)},${_ne.lat.toFixed(4)}`;
}

// ---- Scientific gates (display helpers) ------------------------------------
/**
 * STRICT: Never display estimated_water_depth_cm or exact_depth_m
 * This helper ensures depth values are never shown in the UI
 */
export function safeDepth(depth: null | undefined): null {
  void depth; // suppress unused warning
  return null; // Always null per scientific claim gates
}

export function qualityLabel(score: number | null | undefined): string {
  if (score === null || score === undefined) return "Unknown";
  if (score >= 0.9) return "High";
  if (score >= 0.7) return "Moderate";
  if (score >= 0.5) return "Low";
  return "Very Low";
}

export function confidenceLabel(score: number | null | undefined): string {
  if (score === null || score === undefined) return "Unknown";
  if (score >= 0.9) return "High Confidence";
  if (score >= 0.7) return "Moderate Confidence";
  if (score >= 0.5) return "Low Confidence";
  return "Uncertain";
}

// ---- Role display names ----------------------------------------------------
export const ROLE_DISPLAY: Record<string, string> = {
  CITIZEN: "Citizen",
  FIELD_RESPONDER: "Field Responder",
  ANALYST: "Analyst",
  ALERT_APPROVER: "Alert Approver",
  MUNICIPAL_OFFICER: "Municipal Officer",
  DISASTER_MANAGER: "Disaster Manager",
  ADMIN: "Administrator",
  SUPER_ADMIN: "Super Admin",
  ML_ADMIN: "ML Admin",
};
