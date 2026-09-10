"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle, FileWarning, Bell, MapPin, Users, Activity,
  ArrowRight, CloudRain, TrendingUp, Clock, Zap, RotateCcw, Sparkles,
} from "lucide-react";
import Link from "next/link";
import { dashboardApi } from "@/lib/api/dashboard";
import { simulationApi } from "@/lib/api/simulation";
import {
  KpiCard, KpiCardSkeleton, ErrorState, RiskBadge,
  StatusBadge, Timestamp, PageHeader, DataFreshnessBadge,
} from "@/components/common";
import { formatMmH, formatNumber } from "@/lib/utils";
import ScenarioSimulatorModal from "@/components/simulator/ScenarioSimulatorModal";

export default function CommandCenterPage() {
  const [isSimulatorOpen, setIsSimulatorOpen] = useState(false);

  const {
    data: summary,
    isLoading,
    isError,
    error,
    refetch,
    dataUpdatedAt,
  } = useQuery({
    queryKey: ["dashboard"],
    queryFn: dashboardApi.getSummary,
    refetchInterval: 60_000, // Auto-refresh every 60s
  });

  const { data: simStatus, refetch: refetchSim } = useQuery({
    queryKey: ["simulation-status"],
    queryFn: simulationApi.getStatus,
    refetchInterval: 10_000,
  });

  return (
    <div>
      <PageHeader
        title="Command Center"
        description="Real-time operational overview — Mumbai Metropolitan Region"
        badge={
          summary && (
            <span className="flex items-center gap-1.5 text-xs text-gray-400">
              <DataFreshnessBadge isoTime={summary.generated_at} />
            </span>
          )
        }
        actions={
          <div className="flex items-center gap-2">
            <Link
              href="/simulation"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold shadow-sm transition-all"
            >
              <Sparkles className="w-3.5 h-3.5" />
              Scenario Studio
            </Link>
            <button
              onClick={() => setIsSimulatorOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-slate-900 text-xs font-bold shadow-sm shadow-amber-500/20 transition-all cursor-pointer"
            >
              <Zap className="w-3.5 h-3.5 fill-slate-900" />
              ⚡ Quick Preset
            </button>
            <Link
              href="/map"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 text-white text-xs font-medium hover:bg-slate-950 transition-colors"
            >
              <MapPin className="w-3.5 h-3.5" />
              Live Map
            </Link>
          </div>
        }
      />

      <div className="page-content">
        {/* Active Simulation Indicator Banner */}
        {simStatus?.is_active && (
          <div className="rounded-xl border border-amber-300 bg-amber-50/90 p-3.5 flex flex-wrap items-center justify-between gap-3 animate-in fade-in">
            <div className="flex items-center gap-2.5">
              <span className="flex h-2.5 w-2.5 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-rose-500"></span>
              </span>
              <div>
                <p className="text-xs font-bold text-amber-950">
                  ACTIVE SIMULATION: {simStatus.scenario_name} ({simStatus.ward_name})
                </p>
                <p className="text-[11px] text-amber-800">
                  Precipitation: <strong>{simStatus.rainfall_rate_mm_h} mm/h</strong> · Tide:{" "}
                  <strong>{simStatus.tide_level_m}m</strong> · Threat to: {simStatus.affected_asset}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setIsSimulatorOpen(true)}
                className="px-2.5 py-1 rounded-md text-xs font-semibold bg-white border border-amber-200 text-amber-900 hover:bg-amber-100 transition-colors"
              >
                View AI Briefing
              </button>
              <button
                onClick={async () => {
                  await simulationApi.reset();
                  refetchSim();
                  refetch();
                }}
                className="px-2.5 py-1 rounded-md text-xs font-semibold bg-amber-200 text-amber-950 hover:bg-amber-300 transition-colors"
              >
                Reset
              </button>
            </div>
          </div>
        )}

        {/* City Risk Banner */}
        {summary && (
          <div className="jr-card p-5 flex items-start gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-2">
                <RiskBadge level={summary.city_risk_status.city_max_risk_level} className="text-sm px-3 py-1" />
                <span className="text-xs text-gray-400 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  Lead time: {summary.city_risk_status.lead_time_minutes}min
                </span>
              </div>
              <p className="text-sm text-gray-700 font-medium mb-1">
                {summary.city_risk_status.summary}
              </p>
              <div className="flex items-center gap-4 text-xs text-gray-500">
                <span>
                  <CloudRain className="w-3.5 h-3.5 inline mr-1 text-blue-500" />
                  Peak: {formatMmH(summary.city_risk_status.peak_rainfall_rate_mm_h)}
                </span>
                <span>
                  {summary.city_risk_status.affected_wards.length} wards affected
                </span>
              </div>
            </div>
            <div className="text-right flex-shrink-0">
              <p className="text-xs text-gray-400">Model Status</p>
              <StatusBadge
                status={summary.model_health.operational_mode}
                className="mt-1"
              />
            </div>
          </div>
        )}

        {/* KPI Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          {isLoading ? (
            Array.from({ length: 6 }).map((_, i) => <KpiCardSkeleton key={i} />)
          ) : isError ? (
            <div className="col-span-full">
              <ErrorState
                message={(error as Error)?.message || "Failed to load dashboard data"}
                onRetry={refetch}
              />
            </div>
          ) : summary ? (
            <>
              <KpiCard
                label="High / Severe Risk Cells"
                value={formatNumber(summary.kpis.high_severe_risk_cells_count)}
                icon={<Activity className="w-4 h-4" />}
                variant={summary.kpis.high_severe_risk_cells_count > 20 ? "danger" : summary.kpis.high_severe_risk_cells_count > 5 ? "warning" : "default"}
              />
              <KpiCard
                label="Active Incidents"
                value={formatNumber(summary.kpis.active_incidents_count)}
                icon={<AlertTriangle className="w-4 h-4" />}
                variant={summary.kpis.active_incidents_count > 0 ? "warning" : "default"}
              />
              <KpiCard
                label="Unverified Reports"
                value={formatNumber(summary.kpis.unverified_reports_count)}
                icon={<FileWarning className="w-4 h-4" />}
              />
              <KpiCard
                label="Assets at Risk"
                value={formatNumber(summary.kpis.critical_assets_at_risk_count)}
                icon={<MapPin className="w-4 h-4" />}
                variant={summary.kpis.critical_assets_at_risk_count > 0 ? "warning" : "default"}
              />
              <KpiCard
                label="Active Alerts"
                value={formatNumber(summary.kpis.active_alerts_count)}
                icon={<Bell className="w-4 h-4" />}
                variant={summary.kpis.active_alerts_count > 0 ? "danger" : "default"}
              />
              <KpiCard
                label="Active Responders"
                value={formatNumber(summary.kpis.active_responders_count)}
                icon={<Users className="w-4 h-4" />}
                variant="success"
              />
            </>
          ) : null}
        </div>

        {/* Recent Incidents + Alerts in 2 columns */}
        {summary && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Recent Incidents */}
            <div className="jr-card">
              <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
                <h2 className="text-sm font-semibold text-gray-800">Recent Incidents</h2>
                <Link href="/incidents" className="text-xs text-blue-600 hover:underline flex items-center gap-1">
                  View all <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
              <div className="divide-y divide-gray-50">
                {summary.recent_incidents.length === 0 ? (
                  <p className="text-xs text-gray-400 text-center py-6">No recent incidents</p>
                ) : (
                  summary.recent_incidents.slice(0, 5).map((incident) => (
                    <Link
                      key={incident.incident_id}
                      href={`/incidents/${incident.incident_id}`}
                      className="flex items-start gap-3 px-5 py-3 hover:bg-gray-50 transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-800 truncate">{incident.title}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <StatusBadge status={incident.status} />
                          <RiskBadge level={incident.severity as string} />
                        </div>
                      </div>
                      <Timestamp iso={incident.created_at} relative className="flex-shrink-0" />
                    </Link>
                  ))
                )}
              </div>
            </div>

            {/* Recent Alerts */}
            <div className="jr-card">
              <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
                <h2 className="text-sm font-semibold text-gray-800">Recent Alerts</h2>
                <Link href="/alerts" className="text-xs text-blue-600 hover:underline flex items-center gap-1">
                  Manage <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
              <div className="divide-y divide-gray-50">
                {summary.recent_alerts.length === 0 ? (
                  <p className="text-xs text-gray-400 text-center py-6">No recent alerts</p>
                ) : (
                  summary.recent_alerts.slice(0, 5).map((alert) => (
                    <div key={alert.alert_id} className="flex items-start gap-3 px-5 py-3">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-800 truncate">{alert.headline}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <StatusBadge status={alert.status} />
                          <span className="text-xs text-gray-500">{alert.severity}</span>
                        </div>
                      </div>
                      <Timestamp iso={alert.created_at} relative className="flex-shrink-0" />
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

        {/* Model Health */}
        {summary && (
          <div className="jr-card p-5">
            <h2 className="text-sm font-semibold text-gray-800 mb-3">Model Health</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-xs text-gray-500">Database</p>
                <StatusBadge
                  status={summary.model_health.database_connected ? "HEALTHY" : "UNAVAILABLE"}
                  className="mt-1"
                />
              </div>
              <div>
                <p className="text-xs text-gray-500">Groq Vision</p>
                <StatusBadge
                  status={summary.model_health.groq_vision_available ? "HEALTHY" : "UNAVAILABLE"}
                  className="mt-1"
                />
              </div>
              <div>
                <p className="text-xs text-gray-500">Rainfall Model</p>
                <StatusBadge
                  status={summary.model_health.rainfall_winner_frozen ? "HEALTHY" : "NOT_CONFIGURED"}
                  className="mt-1"
                />
              </div>
              <div>
                <p className="text-xs text-gray-500">FNO Validated</p>
                <StatusBadge
                  status={summary.model_health.fno_validated ? "HEALTHY" : "DEGRADED"}
                  className="mt-1"
                />
              </div>
            </div>
            <p className="text-xs text-gray-400 mt-3">
              Operational mode: <strong>{summary.model_health.operational_mode}</strong>
            </p>
          </div>
        )}

        {/* Refresh timestamp */}
        {dataUpdatedAt > 0 && (
          <p className="text-xs text-gray-400 text-right">
            Last updated: <Timestamp iso={new Date(dataUpdatedAt).toISOString()} relative />
            · Auto-refreshes every 60s
          </p>
        )}
      </div>

      {/* Scenario Simulator Modal */}
      <ScenarioSimulatorModal
        isOpen={isSimulatorOpen}
        onClose={() => setIsSimulatorOpen(false)}
      />
    </div>
  );
}
