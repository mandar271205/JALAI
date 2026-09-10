"use client";
// Route: /risk — Risk Grid Explorer
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ShieldAlert } from "lucide-react";
import { riskApi } from "@/lib/api/risk";
import {
  PageHeader, RiskBadge, ConfidenceBar, EmptyState, LoadingSkeleton, ErrorState,
} from "@/components/common";
import { getMumbaiBboxString } from "@/lib/utils";

export default function RiskPage() {
  const [selectedCell, setSelectedCell] = useState<string | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["risk-cells"],
    queryFn: () => riskApi.getCells({ bbox: getMumbaiBboxString(), limit: 200 }),
    refetchInterval: 30_000,
  });

  const { data: timeline } = useQuery({
    queryKey: ["cell-timeline", selectedCell],
    queryFn: () => riskApi.getCellTimeline(selectedCell!),
    enabled: !!selectedCell,
  });

  return (
    <div>
      <PageHeader
        title="Risk Grid"
        description="H3 cell risk model — click a cell to view its forecast timeline"
      />
      <div className="page-content">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Risk cells list */}
          <div className="lg:col-span-2 jr-card">
            <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-800">
                Risk Cells {data && <span className="text-gray-400 font-normal ml-1">({data.total})</span>}
              </h2>
              {data && (
                <div className="flex items-center gap-2 text-xs text-gray-400">
                  <span>{data.model_version}</span>
                  <ConfidenceBar value={data.confidence} className="w-24" />
                </div>
              )}
            </div>

            {isLoading ? (
              <div className="p-4 space-y-2">
                {[...Array(8)].map((_, i) => <LoadingSkeleton key={i} className="h-10 w-full" />)}
              </div>
            ) : isError ? (
              <ErrorState message="Failed to load risk cells" onRetry={refetch} />
            ) : !data?.items?.length ? (
              <EmptyState
                title="No risk data"
                message="Risk model has not produced output for this area"
                icon={<ShieldAlert className="w-5 h-5" />}
              />
            ) : (
              <div className="overflow-y-auto max-h-96 divide-y divide-gray-50">
                {data.items.map((cell, i) => (
                  <button
                    key={cell.h3_cell_id || i}
                    onClick={() => setSelectedCell(cell.h3_cell_id || "")}
                    className={`w-full flex items-center gap-3 px-5 py-3 text-left hover:bg-gray-50 transition-colors ${selectedCell === cell.h3_cell_id ? "bg-blue-50" : ""}`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="font-mono text-xs text-gray-500 truncate">
                        {cell.h3_cell_id || cell.cell_id || `cell-${i}`}
                      </div>
                      <div className="text-xs text-gray-400">{cell.ward_name || "—"}</div>
                    </div>
                    <RiskBadge level={cell.risk_level} />
                    <span className="text-xs text-gray-400">
                      {cell.composite_risk_score?.toFixed(2) ?? "—"}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Timeline panel */}
          <div className="jr-card">
            <div className="px-5 py-3 border-b border-gray-100">
              <h2 className="text-sm font-semibold text-gray-800">Cell Timeline</h2>
            </div>
            {!selectedCell ? (
              <EmptyState
                title="Select a cell"
                message="Click any risk cell to view its forecast timeline"
              />
            ) : !timeline ? (
              <div className="p-4 space-y-2">
                {[...Array(4)].map((_, i) => <LoadingSkeleton key={i} className="h-10 w-full" />)}
              </div>
            ) : (
              <div className="p-4">
                <div className="text-xs text-gray-500 font-mono mb-3 truncate">{timeline.h3_cell_id}</div>
                <div className="space-y-2">
                  {timeline.timeline.map((t) => (
                    <div key={t.time_offset_min} className="flex items-center gap-2">
                      <span className="w-14 text-xs text-gray-500">T+{t.time_offset_min}m</span>
                      <RiskBadge level={t.risk_level} />
                      <ConfidenceBar value={t.probability} className="flex-1" />
                    </div>
                  ))}
                </div>
                <div className="mt-4 pt-3 border-t border-gray-100 text-xs text-gray-400">
                  <p>Model: {timeline.model_version}</p>
                  <p>Confidence: {(timeline.confidence * 100).toFixed(0)}%</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
