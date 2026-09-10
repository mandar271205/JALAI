"use client";
// ============================================================================
// Rainfall Intelligence — Nowcast manifest + current weather conditions
// Route: /rainfall
// Backend: GET /api/v1/nowcast/manifest + /api/v1/weather/current + /api/v1/weather/sources/status
// ============================================================================
import { useQuery } from "@tanstack/react-query";
import { CloudRain, Wifi, AlertCircle, Clock } from "lucide-react";
import { rainfallApi, sourcesApi } from "@/lib/api/system";
import {
  PageHeader, KpiCard, EmptyState, ErrorState, LoadingSkeleton,
  StatusBadge, ConfidenceBar, DataFreshnessBadge,
} from "@/components/common";
import { formatMmH, formatPercent, qualityLabel } from "@/lib/utils";

export default function RainfallPage() {
  const { data: nowcast, isLoading: nowLoading, isError: nowError } = useQuery({
    queryKey: ["nowcast"],
    queryFn: rainfallApi.getNowcastManifest,
    refetchInterval: 60_000,
  });

  const { data: weather, isLoading: wxLoading } = useQuery({
    queryKey: ["weather"],
    queryFn: sourcesApi.getCurrentWeather,
    refetchInterval: 60_000,
  });

  const { data: sources, isLoading: srcLoading } = useQuery({
    queryKey: ["weather-sources"],
    queryFn: sourcesApi.getSourcesStatus,
    refetchInterval: 120_000,
  });

  return (
    <div>
      <PageHeader
        title="Rainfall Intelligence"
        description="Nowcast manifest, forecast horizons, and data source health"
        badge={weather && <DataFreshnessBadge isoTime={weather.timestamp} />}
      />

      <div className="page-content">
        {/* Current conditions */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KpiCard
            label="Avg Rainfall Rate"
            value={formatMmH(weather?.average_rainfall_rate_mm_h ?? null)}
            icon={<CloudRain className="w-4 h-4" />}
          />
          <KpiCard
            label="Max Recorded"
            value={weather ? `${weather.max_recorded_rainfall_mm.toFixed(0)} mm` : "—"}
            icon={<CloudRain className="w-4 h-4" />}
          />
          <KpiCard
            label="Active Stations"
            value={weather?.active_stations ?? "—"}
            icon={<Wifi className="w-4 h-4" />}
          />
          <KpiCard
            label="Model Confidence"
            value={formatPercent(weather?.confidence ?? null)}
            icon={<AlertCircle className="w-4 h-4" />}
          />
        </div>

        {/* Weather summary */}
        {weather && (
          <div className="jr-card p-4">
            <p className="text-sm text-gray-700">{weather.summary}</p>
            <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
              <span>Model: {weather.model_version}</span>
              <span>Data: {weather.data_version}</span>
            </div>
          </div>
        )}

        {/* Nowcast horizons */}
        <div className="jr-card">
          <div className="px-5 py-3 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-gray-800">Forecast Horizons</h2>
          </div>
          {nowLoading ? (
            <div className="p-4 space-y-3">
              {[...Array(4)].map((_, i) => <LoadingSkeleton key={i} className="h-8 w-full" />)}
            </div>
          ) : nowError ? (
            <ErrorState message="Nowcast manifest unavailable" />
          ) : !nowcast?.horizons?.length ? (
            <EmptyState title="No forecast horizons" message="Nowcast model has not run yet" icon={<Clock className="w-5 h-5" />} />
          ) : (
            <div className="divide-y divide-gray-50">
              {nowcast.horizons.map((h) => (
                <div key={h.offset_min} className="flex items-center gap-4 px-5 py-3">
                  <div className="w-20">
                    <span className="text-sm font-medium text-gray-800">T+{h.offset_min}min</span>
                  </div>
                  <div className="flex-1">
                    <ConfidenceBar value={h.confidence} />
                  </div>
                  <div className="text-xs text-gray-500 w-20 text-right">
                    Quality: {qualityLabel(h.quality_score)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Data sources */}
        <div className="jr-card">
          <div className="px-5 py-3 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-gray-800">Data Sources</h2>
          </div>
          {srcLoading ? (
            <div className="p-4 space-y-3">
              {[...Array(3)].map((_, i) => <LoadingSkeleton key={i} className="h-10 w-full" />)}
            </div>
          ) : !sources?.length ? (
            <EmptyState title="No sources" message="No weather data sources configured" />
          ) : (
            <div className="divide-y divide-gray-50">
              {sources.map((src) => (
                <div key={src.source_id} className="flex items-center gap-4 px-5 py-3">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-800">{src.name || src.source_id}</p>
                    <p className="text-xs text-gray-500">{src.source_type} · {src.coverage || "—"}</p>
                  </div>
                  <StatusBadge status={src.status} />
                  {src.latency_seconds && (
                    <span className="text-xs text-gray-400">{src.latency_seconds}s latency</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Scientific disclaimer */}
        <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
          <p className="text-xs text-blue-600 font-medium">Scientific Note</p>
          <p className="text-xs text-blue-500 mt-1">
            GPM IMERG data provides satellite precipitation estimates — this is NOT radar reflectivity.
            Quality Score reflects data freshness and source agreement, not rainfall certainty.
            Water depth is never estimated from rainfall rates — only validated hydrodynamic output is displayed.
          </p>
        </div>
      </div>
    </div>
  );
}
