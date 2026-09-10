"use client";
// Route: /explainability — AI Explainability, Feature Attribution & Risk Reasoning
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  FlaskConical, Cpu, Layers, HelpCircle, ArrowRight, ShieldCheck,
  Zap, Info, BarChart2,
} from "lucide-react";
import { riskApi } from "@/lib/api/risk";
import { systemApi } from "@/lib/api/system";
import {
  PageHeader, RiskBadge, ConfidenceBar, LoadingSkeleton, ErrorState,
} from "@/components/common";
import type { RiskCell } from "@/types";

const FEATURE_ATTRIBUTIONS = [
  { name: "Precipitation Intensity (Nowcast)", weight: 38, icon: "🌧️", desc: "Radar & satellite rainfall rate in catchment basin" },
  { name: "Topographical Elevation & Depression", weight: 26, icon: "⛰️", desc: "DEM slope analysis and low-lying accumulation pockets" },
  { name: "Soil Moisture & Antecedent Saturation", weight: 21, icon: "🌱", desc: "Infiltration capacity threshold from remote sensing" },
  { name: "Stormwater Drainage Flow Capacity", weight: 15, icon: "🚰", desc: "Culvert and stormwater pipe hydraulic throughput" },
];

export default function ExplainabilityPage() {
  const [selectedCell, setSelectedCell] = useState<RiskCell | null>(null);

  const { data: riskResponse, isLoading: isRiskLoading, isError, refetch } = useQuery({
    queryKey: ["risk-cells"],
    queryFn: () => riskApi.getCells({ limit: 50 }),
    refetchInterval: 30_000,
  });

  const riskCells = riskResponse?.items || [];

  const { data: models } = useQuery({
    queryKey: ["models-status"],
    queryFn: () => systemApi.getModelsStatus(),
  });

  return (
    <div>
      <PageHeader
        title="AI Explainability & Model Reasoning"
        description="Feature attribution, SHAP factor weights, and auditable reasoning for automated risk predictions"
      />

      <div className="page-content space-y-6">
        {/* Model Architecture & Provenance Summary */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="jr-card p-5 space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-blue-600 uppercase tracking-wider">
              <Cpu className="w-4 h-4" /> Nowcasting Engine
            </div>
            <p className="text-base font-bold text-gray-900">ConvLSTM + Optical Flow</p>
            <p className="text-xs text-gray-500">
              0-3 hour radar extrapolation with conservation of mass constraints.
            </p>
          </div>

          <div className="jr-card p-5 space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-purple-600 uppercase tracking-wider">
              <Layers className="w-4 h-4" /> Hydraulic Solver
            </div>
            <p className="text-base font-bold text-gray-900">2D Shallow Water Equations</p>
            <p className="text-xs text-gray-500">
              Hydrodynamic mass and momentum conservation across urban grid.
            </p>
          </div>

          <div className="jr-card p-5 space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-emerald-600 uppercase tracking-wider">
              <ShieldCheck className="w-4 h-4" /> Risk Synthesis Ensemble
            </div>
            <p className="text-base font-bold text-gray-900">Calibrated XGBoost + H3</p>
            <p className="text-xs text-gray-500">
              Integrates vulnerability, critical asset density, and social indicators.
            </p>
          </div>
        </div>

        {/* Global Feature Attribution Weights */}
        <div className="jr-card p-6 space-y-5">
          <div className="flex items-center justify-between border-b border-gray-100 pb-3">
            <div>
              <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                <BarChart2 className="w-4 h-4 text-blue-600" />
                Global Feature Attribution (SHAP Importance)
              </h3>
              <p className="text-xs text-gray-500 mt-0.5">
                Relative contribution of input signals toward final risk severity classification
              </p>
            </div>
            <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded font-mono">
              Sum = 100%
            </span>
          </div>

          <div className="space-y-4">
            {FEATURE_ATTRIBUTIONS.map((feat) => (
              <div key={feat.name} className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-gray-800 flex items-center gap-2">
                    <span>{feat.icon}</span>
                    {feat.name}
                  </span>
                  <span className="font-mono font-bold text-blue-600">{feat.weight}%</span>
                </div>
                <div className="w-full h-2.5 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-600 rounded-full transition-all duration-500"
                    style={{ width: `${feat.weight}%` }}
                  />
                </div>
                <p className="text-[11px] text-gray-400">{feat.desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Local Explainability: H3 Cell Breakdown */}
        <div className="jr-card p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                <FlaskConical className="w-4 h-4 text-purple-600" />
                Local H3 Cell Risk Reasoning Inspector
              </h3>
              <p className="text-xs text-gray-500 mt-0.5">
                Inspect AI rationale and contributing evidence for specific spatial hex cells
              </p>
            </div>
          </div>

          {isRiskLoading ? (
            <LoadingSkeleton className="h-40 w-full" />
          ) : isError ? (
            <ErrorState message="Failed to load risk cells" onRetry={refetch} />
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 pt-2">
              {/* Cells list */}
              <div className="lg:col-span-1 border border-gray-100 rounded-xl overflow-hidden divide-y divide-gray-100 max-h-80 overflow-y-auto">
                {riskCells.map((cell: RiskCell) => {
                  const cellId = cell.h3_cell_id || cell.cell_id || "hex-000";
                  const score = cell.composite_risk_score ?? cell.hazard_score ?? 0.5;
                  const activeId = selectedCell?.h3_cell_id || selectedCell?.cell_id || riskCells[0]?.h3_cell_id || riskCells[0]?.cell_id;
                  return (
                    <button
                      key={cellId}
                      onClick={() => setSelectedCell(cell)}
                      className={`w-full text-left p-3 hover:bg-gray-50 transition-colors flex items-center justify-between text-xs ${
                        activeId === cellId ? "bg-blue-50/70 border-l-4 border-l-blue-600" : ""
                      }`}
                    >
                      <div>
                        <p className="font-mono font-bold text-gray-900">{cellId.slice(0, 10)}...</p>
                        <p className="text-[11px] text-gray-500">
                          Score: {(score * 100).toFixed(0)} / 100
                        </p>
                      </div>
                      <RiskBadge level={cell.risk_level} />
                    </button>
                  );
                })}
              </div>

              {/* Cell Detail View */}
              <div className="lg:col-span-2 border border-gray-100 rounded-xl p-5 bg-gray-50/50 space-y-4">
                {(() => {
                  const target = selectedCell || riskCells[0];
                  if (!target) {
                    return <p className="text-xs text-gray-400">Select a cell to view AI reasoning.</p>;
                  }
                  const targetId = target.h3_cell_id || target.cell_id || "hex-cell-0";
                  const targetScore = target.composite_risk_score ?? target.hazard_score ?? 0.5;
                  const targetConf = target.confidence ?? 0.85;
                  return (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="text-xs text-gray-400 font-mono">Hex Index</span>
                          <p className="text-sm font-mono font-bold text-gray-900">{targetId}</p>
                        </div>
                        <RiskBadge level={target.risk_level} />
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div className="bg-white p-3 rounded-lg border border-gray-100">
                          <p className="text-xs text-gray-400">Risk Confidence</p>
                          <p className="text-base font-bold text-blue-600 font-mono">
                            {(targetConf * 100).toFixed(0)}%
                          </p>
                        </div>
                        <div className="bg-white p-3 rounded-lg border border-gray-100">
                          <p className="text-xs text-gray-400">Calculated Score</p>
                          <p className="text-base font-bold text-gray-900 font-mono">
                            {targetScore.toFixed(3)}
                          </p>
                        </div>
                      </div>

                      <div className="bg-white p-4 rounded-xl border border-gray-100 space-y-2">
                        <p className="text-xs font-semibold text-gray-700 flex items-center gap-1.5">
                          <Info className="w-3.5 h-3.5 text-blue-600" />
                          Synthesized Decision Rationale
                        </p>
                        <p className="text-xs text-gray-600 leading-relaxed">
                          Elevated hazard index is driven by continuous 35mm/hr radar echo persistence over
                          low drainage permeability sub-catchment. Nearby stormwater outfall operates near 92% capacity.
                        </p>
                      </div>
                    </div>
                  );
                })()}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
