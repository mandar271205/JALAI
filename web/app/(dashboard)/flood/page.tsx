"use client";
// Route: /flood — Flood Susceptibility
import { useQuery } from "@tanstack/react-query";
import { Waves, AlertTriangle } from "lucide-react";
import { riskApi } from "@/lib/api/risk";
import {
  PageHeader, RiskBadge, ConfidenceBar, EmptyState, LoadingSkeleton, ErrorState,
} from "@/components/common";
import { formatPercent, getMumbaiBboxString } from "@/lib/utils";

export default function FloodPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["risk-cells-flood"],
    queryFn: () => riskApi.getCells({ bbox: getMumbaiBboxString(), limit: 100 }),
    refetchInterval: 60_000,
  });

  return (
    <div>
      <PageHeader
        title="Flood Susceptibility"
        description="Composite risk grid — hazard × exposure × vulnerability (model v1.2.0-hydro)"
      />
      <div className="page-content">
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-xs text-amber-700">
          <strong>Scientific Gate:</strong> Water depth (depth_m) is displayed only when genuine hydrodynamic solver output is available.
          These susceptibility scores reflect composite risk — not measured inundation depth.
        </div>

        <div className="jr-card">
          <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-800">
              Risk Cells {data && <span className="text-gray-400 font-normal">({data.total} total)</span>}
            </h2>
            {data && <ConfidenceBar value={data.confidence} className="w-32" />}
          </div>

          {isLoading ? (
            <div className="p-4 space-y-2">
              {[...Array(5)].map((_, i) => <LoadingSkeleton key={i} className="h-12 w-full" />)}
            </div>
          ) : isError ? (
            <ErrorState message="Could not load flood susceptibility data" onRetry={refetch} />
          ) : !data?.items?.length ? (
            <EmptyState
              title="No risk cells"
              message="No flood susceptibility data available for current viewport"
              icon={<Waves className="w-5 h-5" />}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full data-table">
                <thead>
                  <tr>
                    <th className="text-left">Cell / Ward</th>
                    <th className="text-left">Risk Level</th>
                    <th className="text-right">Hazard</th>
                    <th className="text-right">Exposure</th>
                    <th className="text-right">Vulnerability</th>
                    <th className="text-right">Rainfall (mm/h)</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((cell, i) => (
                    <tr key={cell.h3_cell_id || cell.cell_id || i}>
                      <td>
                        <div className="font-mono text-xs text-gray-500">
                          {cell.h3_cell_id || cell.cell_id || "—"}
                        </div>
                        <div className="text-xs text-gray-400">{cell.ward_name || cell.ward_id || "—"}</div>
                      </td>
                      <td><RiskBadge level={cell.risk_level} /></td>
                      <td className="text-right text-sm">{cell.hazard_score?.toFixed(2) ?? "—"}</td>
                      <td className="text-right text-sm">{cell.exposure_score?.toFixed(2) ?? "—"}</td>
                      <td className="text-right text-sm">{cell.vulnerability_score?.toFixed(2) ?? "—"}</td>
                      <td className="text-right text-sm">{cell.rainfall_rate_mm_h?.toFixed(1) ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
