"use client";
// Route: /flood — Flood Susceptibility
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Waves, AlertTriangle, Sparkles } from "lucide-react";
import { riskApi } from "@/lib/api/risk";
import { simulationApi } from "@/lib/api/simulation";
import {
  PageHeader, RiskBadge, ConfidenceBar, EmptyState, LoadingSkeleton, ErrorState,
} from "@/components/common";
import { formatPercent, getMumbaiBboxString } from "@/lib/utils";

export default function FloodPage() {
  const { data: simStatus } = useQuery({
    queryKey: ["simulation-status"],
    queryFn: () => simulationApi.getStatus(),
    refetchInterval: 5_000,
  });

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["risk-cells-flood"],
    queryFn: () => riskApi.getCells({ bbox: getMumbaiBboxString(), limit: 100 }),
    refetchInterval: 30_000,
  });

  const activeSim = simStatus?.is_active ? simStatus : null;

  return (
    <div>
      <PageHeader
        title="Flood Susceptibility"
        description="Composite risk grid — hazard × exposure × vulnerability (model v1.2.0-hydro)"
        actions={
          <Link
            href="/simulation"
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors"
          >
            <Sparkles className="w-3.5 h-3.5" />
            Scenario Studio
          </Link>
        }
      />
      <div className="page-content space-y-4">
        {activeSim && (
          <div className="p-3.5 rounded-xl border border-red-200 bg-gradient-to-r from-red-50 via-amber-50 to-orange-50 flex items-center justify-between shadow-xs">
            <div className="flex items-center gap-2.5 text-xs text-red-900">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-600" />
              </span>
              <span>
                <strong>ACTIVE SIMULATION INJECTION:</strong> Ward{" "}
                <span className="font-bold underline">
                  {activeSim.ward_name || activeSim.ward_id || "Target Ward"}
                </span>{" "}
                is under a simulated{" "}
                <span className="font-mono font-bold">{activeSim.rainfall_rate_mm_h} mm/h</span> cloudburst surge
                (Tide: {activeSim.tide_level_m}m). The primary risk cell below is updated dynamically.
              </span>
            </div>
            <Link
              href="/simulation"
              className="px-2.5 py-1 text-xs font-semibold bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors flex-shrink-0"
            >
              Adjust Scenario
            </Link>
          </div>
        )}

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
                  {data.items.map((cell, i) => {
                    const isSimCell = String(cell.cell_id || cell.h3_cell_id || "").startsWith("sim-");
                    return (
                      <tr
                        key={cell.h3_cell_id || cell.cell_id || i}
                        className={isSimCell ? "bg-red-50/60 border-l-4 border-l-red-500 font-medium" : ""}
                      >
                        <td>
                          <div className="flex items-center gap-1.5">
                            <span className="font-mono text-xs text-gray-700">
                              {cell.h3_cell_id || cell.cell_id || "—"}
                            </span>
                            {isSimCell && (
                              <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-700">
                                SIMULATED
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-gray-500">{cell.ward_name || cell.ward_id || "—"}</div>
                        </td>
                        <td><RiskBadge level={cell.risk_level} /></td>
                        <td className="text-right text-sm">{cell.hazard_score?.toFixed(2) ?? "—"}</td>
                        <td className="text-right text-sm">{cell.exposure_score?.toFixed(2) ?? "—"}</td>
                        <td className="text-right text-sm">{cell.vulnerability_score?.toFixed(2) ?? "—"}</td>
                        <td className="text-right text-sm font-mono font-bold">
                          {cell.rainfall_rate_mm_h?.toFixed(1) ?? "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
