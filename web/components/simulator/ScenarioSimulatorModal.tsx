"use client";

import { useState, useEffect } from "react";
import {
  X,
  Zap,
  RotateCcw,
  CloudRain,
  Waves,
  AlertTriangle,
  Building2,
  CheckCircle2,
  MapPin,
  Send,
  Loader2,
  Info,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { simulationApi, type SimulationInjectPayload, type SimulationState } from "@/lib/api/simulation";

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

const PRESETS: Array<{
  name: string;
  icon: string;
  ward_id: string;
  rainfall: number;
  tide: number;
  risk: string;
  asset: string;
}> = [
  {
    name: "Extreme Monsoon Cloudburst",
    icon: "⛈️",
    ward_id: "WARD-08-KURLA",
    rainfall: 125,
    tide: 3.8,
    risk: "SEVERE",
    asset: "Kurla Railway Car Shed & CST Road Bridge",
  },
  {
    name: "Mithi River Tidal Surge",
    icon: "🌊",
    ward_id: "WARD-12-DHARAVI",
    rainfall: 95,
    tide: 4.8,
    risk: "SEVERE",
    asset: "Dharavi 110kV Electrical Substation",
  },
  {
    name: "King's Circle Drainage Failure",
    icon: "⚠️",
    ward_id: "WARD-04-DADAR",
    rainfall: 80,
    tide: 2.2,
    risk: "HIGH",
    asset: "King's Circle Railway Underpass",
  },
  {
    name: "Andheri West Flash Flood",
    icon: "🏙️",
    ward_id: "WARD-K-WEST-ANDHERI",
    rainfall: 110,
    tide: 2.0,
    risk: "SEVERE",
    asset: "Andheri Subway & S.V. Road Junction",
  },
];

const WARDS = [
  { id: "WARD-08-KURLA", name: "Kurla (Ward L - Central)" },
  { id: "WARD-12-DHARAVI", name: "Dharavi (Ward G/North - Mithi River)" },
  { id: "WARD-04-DADAR", name: "Dadar (Ward F/North - Low-Lying)" },
  { id: "WARD-K-WEST-ANDHERI", name: "Andheri West (Ward K/West)" },
  { id: "WARD-H-EAST-BANDRA", name: "Bandra East / BKC (Ward H/East)" },
  { id: "WARD-A-COLABA", name: "Colaba / Fort (Ward A - Coastal)" },
];

export default function ScenarioSimulatorModal({ isOpen, onClose }: Props) {
  const queryClient = useQueryClient();

  // Current simulation status
  const { data: simStatus, refetch: refetchStatus } = useQuery({
    queryKey: ["simulation-status"],
    queryFn: simulationApi.getStatus,
    enabled: isOpen,
  });

  const [scenarioName, setScenarioName] = useState("Extreme Monsoon Cloudburst");
  const [wardId, setWardId] = useState("WARD-08-KURLA");
  const [rainfallRate, setRainfallRate] = useState(115);
  const [tideLevel, setTideLevel] = useState(3.8);
  const [riskLevel, setRiskLevel] = useState("SEVERE");
  const [assetName, setAssetName] = useState("Kurla Railway Car Shed & CST Road Bridge");

  // Sync state if active simulation already exists
  useEffect(() => {
    if (simStatus?.is_active) {
      setScenarioName(simStatus.scenario_name || "Custom Scenario");
      if (simStatus.ward_id) setWardId(simStatus.ward_id);
      if (simStatus.rainfall_rate_mm_h) setRainfallRate(simStatus.rainfall_rate_mm_h);
      if (simStatus.tide_level_m) setTideLevel(simStatus.tide_level_m);
      if (simStatus.risk_level) setRiskLevel(simStatus.risk_level);
      if (simStatus.affected_asset) setAssetName(simStatus.affected_asset);
    }
  }, [simStatus]);

  // Inject mutation
  const injectMutation = useMutation({
    mutationFn: (payload: SimulationInjectPayload) => simulationApi.inject(payload),
    onSuccess: () => {
      refetchStatus();
      // Invalidate relevant React Query caches
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["map-risk"] });
      queryClient.invalidateQueries({ queryKey: ["map-incidents"] });
      queryClient.invalidateQueries({ queryKey: ["weather-current"] });
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  // Reset mutation
  const resetMutation = useMutation({
    mutationFn: simulationApi.reset,
    onSuccess: () => {
      refetchStatus();
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["map-risk"] });
      queryClient.invalidateQueries({ queryKey: ["map-incidents"] });
      queryClient.invalidateQueries({ queryKey: ["weather-current"] });
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  const handlePresetSelect = (p: typeof PRESETS[0]) => {
    setScenarioName(p.name);
    setWardId(p.ward_id);
    setRainfallRate(p.rainfall);
    setTideLevel(p.tide);
    setRiskLevel(p.risk);
    setAssetName(p.asset);
  };

  const handleInject = () => {
    injectMutation.mutate({
      scenario_name: scenarioName,
      ward_id: wardId,
      rainfall_rate_mm_h: rainfallRate,
      tide_level_m: tideLevel,
      risk_level: riskLevel,
      affected_asset: assetName,
    });
  };

  const handleReset = () => {
    resetMutation.mutate();
  };

  if (!isOpen) return null;

  const briefing = simStatus?.is_active ? simStatus.ai_briefing : injectMutation.data?.simulation?.ai_briefing;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-3xl max-h-[90vh] overflow-y-auto bg-white rounded-2xl shadow-2xl border border-slate-200 flex flex-col">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-gradient-to-r from-blue-50/80 via-white to-indigo-50/80">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center text-white shadow-md shadow-blue-500/20">
              <Zap className="w-5 h-5 text-amber-300 fill-amber-300" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-slate-900">
                  Live Scenario Injection & Dynamic AI Simulator
                </h2>
                {simStatus?.is_active && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-rose-100 text-rose-700 border border-rose-200 animate-pulse">
                    Live Active
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500">
                Override rainfall, tide, and hazard values to watch radar, map hotspots, and AI reasoning react instantly.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-6">
          {/* Quick Presets */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
              ⚡ Quick Scenario Presets
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {PRESETS.map((p) => (
                <button
                  key={p.name}
                  type="button"
                  onClick={() => handlePresetSelect(p)}
                  className={`p-2.5 rounded-xl border text-left transition-all ${
                    scenarioName === p.name
                      ? "border-blue-600 bg-blue-50/80 shadow-sm"
                      : "border-slate-200 hover:border-slate-300 bg-slate-50/50 hover:bg-slate-50"
                  }`}
                >
                  <div className="text-lg mb-1">{p.icon}</div>
                  <p className="text-xs font-bold text-slate-900 line-clamp-1">{p.name}</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">{p.rainfall} mm/h</p>
                </button>
              ))}
            </div>
          </div>

          {/* Configuration Form */}
          <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Scenario Name */}
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Scenario Title
                </label>
                <input
                  type="text"
                  value={scenarioName}
                  onChange={(e) => setScenarioName(e.target.value)}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                  placeholder="e.g. Flash Flood Emergency"
                />
              </div>

              {/* Target Ward */}
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Target Municipal Ward
                </label>
                <select
                  value={wardId}
                  onChange={(e) => {
                    setWardId(e.target.value);
                    const sel = PRESETS.find((p) => p.ward_id === e.target.value);
                    if (sel) setAssetName(sel.asset);
                  }}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  {WARDS.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Rainfall Intensity Slider */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="flex items-center gap-1.5 text-xs font-medium text-slate-700">
                  <CloudRain className="w-4 h-4 text-blue-500" />
                  Precipitation Intensity
                </span>
                <span className="text-xs font-bold px-2 py-0.5 rounded-md bg-blue-100 text-blue-800">
                  {rainfallRate} mm/h
                </span>
              </div>
              <input
                type="range"
                min="10"
                max="180"
                step="5"
                value={rainfallRate}
                onChange={(e) => setRainfallRate(Number(e.target.value))}
                className="w-full accent-blue-600 cursor-pointer h-2 bg-slate-200 rounded-lg"
              />
              <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                <span>10 mm/h (Light)</span>
                <span>50 mm/h (Drainage Max)</span>
                <span>100 mm/h (Cloudburst)</span>
                <span>180 mm/h (Extreme)</span>
              </div>
            </div>

            {/* Tide Level & Risk Level */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">
                  <Waves className="w-3.5 h-3.5 inline mr-1 text-cyan-600" />
                  Arabian Sea Tidal State
                </label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setTideLevel(1.8)}
                    className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-medium border transition-colors ${
                      tideLevel <= 2.5
                        ? "border-blue-600 bg-blue-50 text-blue-700 font-semibold"
                        : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    Normal (1.8m)
                  </button>
                  <button
                    type="button"
                    onClick={() => setTideLevel(4.8)}
                    className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-medium border transition-colors ${
                      tideLevel > 2.5
                        ? "border-rose-500 bg-rose-50 text-rose-700 font-semibold"
                        : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    Spring High Tide (4.8m)
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  <AlertTriangle className="w-3.5 h-3.5 inline mr-1 text-amber-500" />
                  Hazard Level
                </label>
                <select
                  value={riskLevel}
                  onChange={(e) => setRiskLevel(e.target.value)}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white font-semibold"
                >
                  <option value="MODERATE" className="text-amber-600">MODERATE RISK</option>
                  <option value="HIGH" className="text-orange-600">HIGH RISK</option>
                  <option value="SEVERE" className="text-rose-600">SEVERE RISK</option>
                </select>
              </div>
            </div>

            {/* Affected Asset */}
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                <Building2 className="w-3.5 h-3.5 inline mr-1 text-slate-600" />
                Target Critical Infrastructure Asset
              </label>
              <input
                type="text"
                value={assetName}
                onChange={(e) => setAssetName(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                placeholder="e.g. Sion Hospital or Railway Car Shed"
              />
            </div>
          </div>

          {/* Action Trigger Buttons */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleInject}
                disabled={injectMutation.isPending}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white text-xs font-semibold shadow-md shadow-blue-600/20 transition-all disabled:opacity-50"
              >
                {injectMutation.isPending ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Injecting & Generating AI Briefing...
                  </>
                ) : (
                  <>
                    <Zap className="w-4 h-4 text-amber-300 fill-amber-300" />
                    Inject Scenario & Simulate
                  </>
                )}
              </button>

              {simStatus?.is_active && (
                <button
                  type="button"
                  onClick={handleReset}
                  disabled={resetMutation.isPending}
                  className="flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-slate-100 hover:bg-slate-200 active:bg-slate-300 text-slate-700 text-xs font-medium transition-colors disabled:opacity-50"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  Reset to Baseline
                </button>
              )}
            </div>

            {simStatus?.is_active && (
              <span className="text-xs text-emerald-600 flex items-center gap-1 font-medium">
                <CheckCircle2 className="w-4 h-4" />
                Scenario active in telemetry & GIS
              </span>
            )}
          </div>

          {/* Dynamic AI Briefing Card */}
          {briefing && (
            <div className="rounded-xl border border-blue-200 bg-gradient-to-br from-blue-50/60 to-indigo-50/60 p-4 space-y-3 animate-in fade-in duration-300">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-blue-900">
                  <Info className="w-4 h-4 text-blue-600" />
                  AI Operational Briefing & Hydrodynamic Reasoning
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 font-semibold">
                  Confidence: {Math.round(briefing.confidence_score * 100)}%
                </span>
              </div>

              <p className="text-xs text-slate-800 font-semibold leading-relaxed">
                {briefing.executive_summary}
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-slate-600 bg-white/70 p-3 rounded-lg border border-blue-100">
                <div>
                  <span className="font-semibold text-slate-800">Drainage Exceedance: </span>
                  {briefing.hazard_summary}
                </div>
                <div>
                  <span className="font-semibold text-slate-800">Hydrodynamics: </span>
                  {briefing.hydrodynamic_analysis}
                </div>
              </div>

              <div>
                <p className="text-xs font-semibold text-slate-800 mb-1">Recommended Action Protocol (SOP):</p>
                <ul className="space-y-1">
                  {briefing.action_plan.map((action, idx) => (
                    <li key={idx} className="text-xs text-slate-700 flex items-start gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-blue-600 mt-1.5 flex-shrink-0" />
                      <span>{action}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Direct navigation shortcuts */}
              <div className="flex flex-wrap gap-2 pt-2 border-t border-blue-100">
                <Link
                  href="/map"
                  onClick={onClose}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors"
                >
                  <MapPin className="w-3.5 h-3.5" />
                  View Live Red Hotspot on Map
                </Link>
                <Link
                  href="/alerts"
                  onClick={onClose}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium transition-colors"
                >
                  <Send className="w-3.5 h-3.5" />
                  Draft Multi-lingual Alert in Alerts Tab
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
