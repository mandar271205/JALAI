"use client";
// ============================================================================
// Common UI Components
// ============================================================================
import { cn } from "@/lib/cn";
import { getRiskColors, getStatusColor, formatTimestamp, formatRelative } from "@/lib/utils";
import type { RiskLevel } from "@/types";

// ---- RiskBadge -------------------------------------------------------------
export function RiskBadge({ level, className }: { level: RiskLevel | string; className?: string }) {
  const colors = getRiskColors(level as RiskLevel);
  return (
    <span className={cn("badge", colors.badge, className)}>
      {level}
    </span>
  );
}

// ---- StatusBadge -----------------------------------------------------------
export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const color = getStatusColor(status);
  return (
    <span className={cn("badge", color, className)}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

// ---- ConfidenceBar ---------------------------------------------------------
export function ConfidenceBar({ value, className }: { value: number; className?: string }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 85 ? "bg-emerald-500" :
    pct >= 70 ? "bg-amber-400" :
    pct >= 50 ? "bg-orange-400" :
    "bg-red-400";

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-medium text-gray-600 tabular-nums w-8 text-right">
        {pct}%
      </span>
    </div>
  );
}

// ---- PriorityBadge ---------------------------------------------------------
export function PriorityBadge({ priority, className }: { priority?: string; className?: string }) {
  const p = priority || "P3_MEDIUM";
  const color =
    p.includes("1") || p === "HIGH" || p === "CRITICAL"
      ? "bg-red-100 text-red-700"
      : p.includes("2")
      ? "bg-orange-100 text-orange-700"
      : p.includes("3") || p === "MEDIUM"
      ? "bg-amber-100 text-amber-700"
      : "bg-blue-100 text-blue-700";
  return (
    <span className={cn("badge font-mono", color, className)}>
      {p.replace(/_/g, " ")}
    </span>
  );
}

// ---- KpiCard ---------------------------------------------------------------
interface KpiCardProps {
  label?: string;
  title?: string;
  value: number | string;
  sublabel?: string;
  change?: string;
  trend?: "up" | "down" | "neutral";
  trendValue?: string;
  icon?: React.ReactNode;
  className?: string;
  variant?: "default" | "warning" | "danger" | "success";
}

export function KpiCard({ label, title, value, sublabel, change, icon, className, variant = "default" }: KpiCardProps) {
  const variantStyles: Record<string, string> = {
    default: "bg-white",
    warning: "bg-amber-50",
    danger: "bg-red-50",
    success: "bg-emerald-50",
  };
  const displayTitle = title || label || "";
  const displaySub = sublabel || change;

  return (
    <div className={cn("kpi-card", variantStyles[variant], className)}>
      <div className="flex items-start justify-between">
        <p className="jr-section-title text-gray-500">{displayTitle}</p>
        {icon && (
          <div className="p-2 rounded-lg bg-gray-100 text-gray-600">{icon}</div>
        )}
      </div>
      <div>
        <p className="jr-value-large">{value}</p>
        {displaySub && (
          <p className="text-xs text-gray-500 mt-1">{displaySub}</p>
        )}
      </div>
    </div>
  );
}

// ---- EmptyState -----------------------------------------------------------
interface EmptyStateProps {
  title: string;
  message: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
}

export function EmptyState({ title, message, icon, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-8 text-center">
      {icon && (
        <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mb-4 text-gray-400">
          {icon}
        </div>
      )}
      <h3 className="text-sm font-semibold text-gray-700 mb-1">{title}</h3>
      <p className="text-sm text-gray-500 max-w-xs">{message}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

// ---- ErrorState -----------------------------------------------------------
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-8 text-center">
      <div className="w-10 h-10 rounded-full bg-red-50 flex items-center justify-center mb-3">
        <span className="text-red-500 text-lg">!</span>
      </div>
      <p className="text-sm font-medium text-gray-700 mb-1">Data Unavailable</p>
      <p className="text-xs text-gray-500 mb-3 max-w-xs">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-xs font-medium text-blue-600 hover:text-blue-700"
        >
          Retry
        </button>
      )}
    </div>
  );
}

// ---- LoadingSkeleton -------------------------------------------------------
export function LoadingSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("animate-pulse rounded bg-gray-100", className)} />
  );
}

export function KpiCardSkeleton() {
  return (
    <div className="kpi-card">
      <LoadingSkeleton className="h-4 w-24 mb-3" />
      <LoadingSkeleton className="h-8 w-16 mb-2" />
      <LoadingSkeleton className="h-3 w-20" />
    </div>
  );
}

// ---- Timestamp -------------------------------------------------------------
export function Timestamp({
  iso,
  relative = false,
  className,
}: {
  iso: string | null | undefined;
  relative?: boolean;
  className?: string;
}) {
  const text = relative ? formatRelative(iso) : formatTimestamp(iso);
  const full = formatTimestamp(iso);
  return (
    <time
      dateTime={iso || ""}
      title={full}
      className={cn("text-xs text-gray-500", className)}
    >
      {text}
    </time>
  );
}

// ---- DataFreshnessBadge ----------------------------------------------------
export function DataFreshnessBadge({ isoTime }: { isoTime: string | null | undefined }) {
  if (!isoTime) return null;
  const ageMs = Date.now() - new Date(isoTime).getTime();
  const ageMin = Math.floor(ageMs / 60000);

  const { color, label } =
    ageMin < 5
      ? { color: "text-emerald-600", label: "Fresh" }
      : ageMin < 15
      ? { color: "text-amber-600", label: `${ageMin}m old` }
      : { color: "text-red-600", label: `${ageMin}m old` };

  return (
    <span className={cn("text-xs font-medium", color)}>
      {label}
    </span>
  );
}

// ---- PageHeader -----------------------------------------------------------
export function PageHeader({
  title,
  description,
  actions,
  badge,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  badge?: React.ReactNode;
}) {
  return (
    <div className="page-header">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <h1 className="text-lg font-bold text-gray-900">{title}</h1>
            {badge}
          </div>
          {description && (
            <p className="text-sm text-gray-500">{description}</p>
          )}
        </div>
        {actions && (
          <div className="flex items-center gap-2 ml-4 flex-shrink-0">{actions}</div>
        )}
      </div>
    </div>
  );
}
