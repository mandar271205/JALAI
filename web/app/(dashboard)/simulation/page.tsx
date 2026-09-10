"use client";
// ============================================================================
// Scenario & Field Simulation Studio
// Route: /simulation
// Interactive multi-domain simulation and live data injection workspace
// ============================================================================
import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Sparkles, CloudRain, AlertTriangle, FileWarning, MapPin,
  Waves, CheckCircle2, RotateCcw, ArrowRight, Compass,
  Layers, ShieldAlert, Activity, ExternalLink, SlidersHorizontal,
  Flame, FileCheck, Building2
} from "lucide-react";
import { toast } from "sonner";
import { simulationApi } from "@/lib/api/simulation";
import { incidentsApi } from "@/lib/api/incidents";
import { reportsApi } from "@/lib/api/reports";
import { assetsApi } from "@/lib/api/assets";
import { PageHeader, LoadingSkeleton } from "@/components/common";

const PRESET_SCENARIOS = [
  {
    name: "Dharavi 140mm/h Cloudburst",
    ward: "DHARAVI",
    rainfall_rate_mm_h: 140.0,
    high_tide_m: 4.4,
    asset_at_risk: "Mithi River Culvert Pumping Stn",
    badge: "CRITICAL MONSOON",
    color: "from-red-600 to-rose-700",
  },
  {
    name: "Andheri Subway Inundation",
    ward: "ANDHERI",
    rainfall_rate_mm_h: 110.0,
    high_tide_m: 3.8,
    asset_at_risk: "Andheri Subway Pumping Station",
    badge: "TRANSIT CHOKE",
    color: "from-amber-600 to-orange-700",
  },
  {
    name: "Kurla Basin River Surge",
    ward: "KURLA",
    rainfall_rate_mm_h: 125.0,
    high_tide_m: 4.2,
    asset_at_risk: "Kurla West Low-Lying Settlement",
    badge: "RIVER BACKFLOW",
    color: "from-purple-600 to-indigo-700",
  },
  {
    name: "Marine Drive Tidal Backflow",
    ward: "DADAR",
    rainfall_rate_mm_h: 85.0,
    high_tide_m: 4.8,
    asset_at_risk: "Hajiali Sea Outfall Gravity Sluice",
    badge: "EXTREME SPRING TIDE",
    color: "from-blue-600 to-cyan-700",
  },
];

const MUMBAI_INCIDENT_PRESETS = [
  {
    title: "Severe Waterlogging near Dadar West Railway Station",
    ward_id: "G-North",
    severity: "P1_CRITICAL",
    latitude: 19.0183,
    longitude: 72.8428,
    notes: "Traffic halted. Water entering railway booking hall, ~0.6m depth.",
  },
  {
    title: "Mithi River Level Critical at Kurla Bridge",
    ward_id: "L",
    severity: "P1_CRITICAL",
    latitude: 19.0657,
    longitude: 72.8797,
    notes: "River overflowing bank. 15 commercial units waterlogged.",
  },
  {
    title: "Andheri Subway Vehicular Stagnation",
    ward_id: "K-West",
    severity: "P2_HIGH",
    latitude: 19.1197,
    longitude: 72.8397,
    notes: "Both subway bores flooded. Auxiliary diesel pump #2 deployed.",
  },
  {
    title: "Hindmata Flyover Junction Inundation",
    ward_id: "F-South",
    severity: "P2_HIGH",
    latitude: 19.0112,
    longitude: 72.8445,
    notes: "Stormwater drain bottleneck. Traffic diversion active.",
  },
];

export default function SimulationStudioPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"weather" | "incident" | "report" | "asset">("weather");

  // Weather Simulation state
  const [ward, setWard] = useState("DHARAVI");
  const [rainfallRate, setRainfallRate] = useState(135.0);
  const [highTide, setHighTide] = useState(4.2);
  const [assetAtRisk, setAssetAtRisk] = useState("Dharavi Main Outfall Sluice #3");

  // Incident state
  const [incTitle, setIncTitle] = useState("");
  const [incWard, setIncWard] = useState("G-North");
  const [incSeverity, setIncSeverity] = useState("P1_CRITICAL");
  const [incLat, setIncLat] = useState(19.0330);
  const [incLon, setIncLon] = useState(72.8570);
  const [incNotes, setIncNotes] = useState("");

  // Citizen report state
  const [repWard, setRepWard] = useState("G-North");
  const [repDesc, setRepDesc] = useState("Ground floor residential shops waterlogged. Water depth rising rapidly.");
  const [repLat, setRepLat] = useState(19.0350);
  const [repLon, setRepLon] = useState(72.8580);

  // Critical asset state
  const [assetName, setAssetName] = useState("");
  const [assetType, setAssetType] = useState("PUMPING_STATION");
  const [assetWard, setAssetWard] = useState("G-North");
  const [assetLat, setAssetLat] = useState(19.0330);
  const [assetLon, setAssetLon] = useState(72.8570);
  const [assetThreshold, setAssetThreshold] = useState(0.5);

  // Status query
  const { data: statusData, isLoading: isStatusLoading } = useQuery({
    queryKey: ["simulation-status"],
    queryFn: () => simulationApi.getStatus(),
    refetchInterval: 3_000,
  });

  const activeSim = statusData?.is_active ? statusData : null;

  // Mutations
  const injectMutation = useMutation({
    mutationFn: () =>
      simulationApi.inject({
        rainfall_rate_mm_h: rainfallRate,
        ward,
        high_tide_m: highTide,
        asset_at_risk: assetAtRisk,
      }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["simulation-status"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
      queryClient.invalidateQueries({ queryKey: ["map-risk"] });
      queryClient.invalidateQueries({ queryKey: ["map-incidents"] });
      queryClient.invalidateQueries({ queryKey: ["risk-cells-flood"] });
      queryClient.invalidateQueries({ queryKey: ["all-incidents"] });
      toast.success("Scenario Injected Successfully", {
        description: `Ward ${res.simulation.ward_name || res.simulation.ward_id || "Target"} is now operating at ${res.simulation.rainfall_rate_mm_h} mm/h surge.`,
      });
    },
    onError: () => toast.error("Simulation injection failed"),
  });

  const resetMutation = useMutation({
    mutationFn: () => simulationApi.reset(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["simulation-status"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
      queryClient.invalidateQueries({ queryKey: ["map-risk"] });
      queryClient.invalidateQueries({ queryKey: ["risk-cells-flood"] });
      toast.success("System Restored to Baseline", {
        description: "Standard meteorological telemetry and radar feeds restored.",
      });
    },
  });

  const createIncidentMutation = useMutation({
    mutationFn: () =>
      incidentsApi.create({
        title: incTitle || "Emergency Waterlogging Surge",
        ward_id: incWard,
        severity: incSeverity,
        latitude: incLat,
        longitude: incLon,
        notes: incNotes,
      }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["all-incidents"] });
      queryClient.invalidateQueries({ queryKey: ["map-incidents"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
      toast.success("Live Incident Dispatched", {
        description: `${res.title} logged with severity ${res.severity}.`,
      });
      setIncTitle("");
      setIncNotes("");
    },
    onError: () => toast.error("Failed to create incident"),
  });

  const createReportMutation = useMutation({
    mutationFn: () =>
      reportsApi.createDraft({
        latitude: repLat,
        longitude: repLon,
        description: `[Ward ${repWard}] ${repDesc}`,
      }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["all-reports"] });
      queryClient.invalidateQueries({ queryKey: ["map-reports"] });
      toast.success("Citizen Field Report Submitted", {
        description: `Report #${res.report_id?.slice(0, 8)} queued for Vision AI corroboration.`,
      });
    },
    onError: () => toast.error("Failed to submit citizen report"),
  });

  const createAssetMutation = useMutation({
    mutationFn: () =>
      assetsApi.create({
        name: assetName || "Auxiliary Pumping Facility",
        asset_type: assetType,
        ward_id: assetWard,
        latitude: assetLat,
        longitude: assetLon,
        inundation_threshold_m: assetThreshold,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["all-assets"] });
      queryClient.invalidateQueries({ queryKey: ["map-assets"] });
      toast.success("Critical Infrastructure Asset Registered", {
        description: `${assetName} registered in Ward ${assetWard}.`,
      });
      setAssetName("");
    },
    onError: () => toast.error("Failed to register asset"),
  });

  return (
    <div>
      <PageHeader
        title="Scenario Studio & Field Operations App"
        description="Interactive control deck: Inject custom weather scenarios, dispatch emergency incidents, submit citizen reports, and register critical assets with instant whole-system propagation."
      />

      <div className="page-content space-y-6">
        {/* Active Simulation Status Banner */}
        <div className="p-4 rounded-xl border border-gray-200 bg-white shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
              activeSim ? "bg-red-500 text-white animate-pulse" : "bg-blue-50 text-blue-600"
            }`}>
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">
                  Current Simulation Engine State
                </span>
                {activeSim ? (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-700">
                    ● ACTIVE OVERRIDE
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-gray-100 text-gray-600">
                    BASELINE RUN
                  </span>
                )}
              </div>
              <p className="text-sm font-semibold text-gray-900 mt-0.5">
                {activeSim
                  ? `Simulated Storm: Ward ${activeSim.ward_name || activeSim.ward_id || "Target"} @ ${activeSim.rainfall_rate_mm_h} mm/h (Tide: ${activeSim.tide_level_m}m)`
                  : "Normal baseline telemetry operating. No synthetic scenario currently active."}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {activeSim && (
              <button
                onClick={() => resetMutation.mutate()}
                disabled={resetMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                {resetMutation.isPending ? "Resetting…" : "Reset to Baseline"}
              </button>
            )}
            <Link
              href="/command-center"
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-xs transition-colors"
            >
              <span>Command Center</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>

        {/* Tab Selection */}
        <div className="flex items-center gap-2 border-b border-gray-200 pb-2">
          {[
            { id: "weather", label: "🌧️ Weather & Flood Inundation", icon: CloudRain },
            { id: "incident", label: "🚨 Dispatch Live Incident", icon: AlertTriangle },
            { id: "report", label: "📱 Citizen Field Report", icon: FileWarning },
            { id: "asset", label: "🏢 Critical Asset Registrar", icon: Building2 },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
                activeTab === tab.id
                  ? "bg-blue-600 text-white shadow-xs"
                  : "text-gray-600 hover:text-gray-900 hover:bg-gray-100"
              }`}
            >
              <tab.icon className="w-4 h-4" />
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* TAB 1: Weather & Flood Inundation Simulator */}
        {activeTab === "weather" && (
          <div className="space-y-6 animate-fade-in">
            {/* Quick Presets */}
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">
                1-Click Preset Scenarios (SIH Demo Recommended)
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                {PRESET_SCENARIOS.map((p) => (
                  <button
                    key={p.name}
                    onClick={() => {
                      setWard(p.ward);
                      setRainfallRate(p.rainfall_rate_mm_h);
                      setHighTide(p.high_tide_m);
                      setAssetAtRisk(p.asset_at_risk);
                    }}
                    className="p-3.5 rounded-xl border border-gray-200 bg-white hover:border-blue-400 hover:shadow-xs transition-all text-left group"
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-blue-50 text-blue-700">
                        {p.badge}
                      </span>
                      <span className="font-mono text-xs font-bold text-gray-700">
                        {p.rainfall_rate_mm_h} mm/h
                      </span>
                    </div>
                    <p className="text-xs font-semibold text-gray-900 group-hover:text-blue-600 transition-colors">
                      {p.name}
                    </p>
                    <p className="text-[11px] text-gray-400 mt-1 truncate">
                      {p.ward} • Tide: {p.high_tide_m}m
                    </p>
                  </button>
                ))}
              </div>
            </div>

            {/* Custom Input Controls */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="jr-card p-5 space-y-4">
                <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                  <SlidersHorizontal className="w-4 h-4 text-blue-600" />
                  Custom Scenario Controls
                </h3>

                {/* Target Ward */}
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-700">Target Ward</label>
                  <select
                    value={ward}
                    onChange={(e) => setWard(e.target.value)}
                    className="w-full text-xs rounded-lg border border-gray-200 p-2 font-semibold bg-white"
                  >
                    <option value="DHARAVI">Ward G-North (Dharavi / Mithi Basin)</option>
                    <option value="ANDHERI">Ward K-West (Andheri Subway / Transit Hub)</option>
                    <option value="KURLA">Ward L (Kurla Sloped Basin / BKC)</option>
                    <option value="DADAR">Ward F-North (Dadar / Hindmata)</option>
                    <option value="BANDRA">Ward H-West (Bandra Coastline)</option>
                    <option value="CHEMBUR">Ward M-West (Chembur Lowlands)</option>
                  </select>
                </div>

                {/* Rainfall Rate Slider */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-gray-700">Rainfall Intensity</span>
                    <span className="font-mono font-bold text-blue-700 text-sm">
                      {rainfallRate.toFixed(1)} mm/h
                    </span>
                  </div>
                  <input
                    type="range"
                    min="10"
                    max="180"
                    step="5"
                    value={rainfallRate}
                    onChange={(e) => setRainfallRate(parseFloat(e.target.value))}
                    className="w-full accent-blue-600"
                  />
                  <div className="flex justify-between text-[10px] text-gray-400 font-mono">
                    <span>10 mm/h (Light)</span>
                    <span>75 mm/h (Heavy)</span>
                    <span>140 mm/h (Cloudburst)</span>
                    <span>180 mm/h (Extreme)</span>
                  </div>
                </div>

                {/* High Tide Slider */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-gray-700">Astronomical High Tide</span>
                    <span className="font-mono font-bold text-cyan-700 text-sm">
                      {highTide.toFixed(2)} meters
                    </span>
                  </div>
                  <input
                    type="range"
                    min="1.8"
                    max="4.8"
                    step="0.1"
                    value={highTide}
                    onChange={(e) => setHighTide(parseFloat(e.target.value))}
                    className="w-full accent-cyan-600"
                  />
                  <div className="flex justify-between text-[10px] text-gray-400 font-mono">
                    <span>1.8m (Neap Tide)</span>
                    <span>3.2m (Normal)</span>
                    <span>4.4m (Spring Surge)</span>
                    <span>4.8m (Extreme Hazard)</span>
                  </div>
                </div>

                {/* At Risk Asset */}
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-700">At-Risk Infrastructure Asset</label>
                  <input
                    type="text"
                    value={assetAtRisk}
                    onChange={(e) => setAssetAtRisk(e.target.value)}
                    placeholder="e.g. Milan Subway Aux Pumping Station"
                    className="w-full text-xs rounded-lg border border-gray-200 p-2 font-medium bg-white"
                  />
                </div>

                <div className="pt-2 flex items-center gap-3">
                  <button
                    onClick={() => injectMutation.mutate()}
                    disabled={injectMutation.isPending}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold shadow-xs transition-colors"
                  >
                    <Sparkles className="w-4 h-4" />
                    {injectMutation.isPending ? "Injecting Live Scenario…" : "⚡ Inject Live Scenario"}
                  </button>
                  {activeSim && (
                    <button
                      onClick={() => resetMutation.mutate()}
                      disabled={resetMutation.isPending}
                      className="px-3 py-2.5 text-xs font-semibold text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                    >
                      Reset
                    </button>
                  )}
                </div>
              </div>

              {/* AI Real-time Briefing Card */}
              <div className="jr-card p-5 space-y-4 bg-gradient-to-br from-slate-900 via-slate-850 to-blue-950 text-white">
                <div className="flex items-center justify-between border-b border-white/10 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                    <h4 className="text-xs font-bold uppercase tracking-wider text-blue-300">
                      Automated AI Operational Synthesis
                    </h4>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/10 text-slate-300">
                    HYDRODYNAMIC REASONER
                  </span>
                </div>

                <div className="space-y-3 text-xs leading-relaxed text-slate-200">
                  <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                    <p className="text-[11px] font-semibold text-amber-400 mb-1">
                      DRAINAGE CAPACITY EXCEEDANCE
                    </p>
                    <p>
                      Simulated rate of <strong className="text-white">{rainfallRate} mm/h</strong> generates a runoff
                      exceedance ratio of{" "}
                      <strong className="text-amber-300">
                        {(rainfallRate / 75.0).toFixed(2)}x
                      </strong>{" "}
                      against Mumbai's standard 75mm/h design limit.
                    </p>
                  </div>

                  <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                    <p className="text-[11px] font-semibold text-cyan-400 mb-1">
                      HYDRODYNAMIC BACKFLOW IMPACT
                    </p>
                    <p>
                      At <strong className="text-white">{highTide}m</strong> tide level, sea outfall flap gates will be
                      mechanically closed. Gravity discharge to Arabian Sea will cease, causing sloped backflow into Ward{" "}
                      <strong className="text-white">{ward}</strong>.
                    </p>
                  </div>

                  <div className="p-3 rounded-lg bg-white/5 border border-white/10">
                    <p className="text-[11px] font-semibold text-emerald-400 mb-1">
                      RECOMMENDED EMERGENCY SOP
                    </p>
                    <p>
                      Immediate activation of auxiliary diesel dewatering pumps at{" "}
                      <strong className="text-white">{assetAtRisk}</strong>. Dispatch NDRF water rescue boat team to
                      low-lying arterial choke points.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: Dispatch Live Incident */}
        {activeTab === "incident" && (
          <div className="space-y-6 animate-fade-in">
            {/* Quick 1-Click Incident Presets */}
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">
                1-Click Incident Templates (Auto-fills Location & Notes)
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                {MUMBAI_INCIDENT_PRESETS.map((item) => (
                  <button
                    key={item.title}
                    onClick={() => {
                      setIncTitle(item.title);
                      setIncWard(item.ward_id);
                      setIncSeverity(item.severity);
                      setIncLat(item.latitude);
                      setIncLon(item.longitude);
                      setIncNotes(item.notes);
                    }}
                    className="p-3.5 rounded-xl border border-gray-200 bg-white hover:border-red-400 hover:shadow-xs transition-all text-left group"
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                        item.severity === "P1_CRITICAL" ? "bg-red-100 text-red-700" : "bg-orange-100 text-orange-700"
                      }`}>
                        {item.severity}
                      </span>
                      <span className="text-[10px] font-mono text-gray-500">Ward {item.ward_id}</span>
                    </div>
                    <p className="text-xs font-semibold text-gray-900 group-hover:text-red-600 transition-colors line-clamp-2">
                      {item.title}
                    </p>
                  </button>
                ))}
              </div>
            </div>

            <div className="jr-card p-5 max-w-2xl space-y-4">
              <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-red-600" />
                Dispatch New Emergency Incident
              </h3>

              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-700">Incident Headline</label>
                <input
                  type="text"
                  value={incTitle}
                  onChange={(e) => setIncTitle(e.target.value)}
                  placeholder="e.g. Flash Flood Waterlogging near Dadar West"
                  className="w-full text-xs rounded-lg border border-gray-200 p-2 font-semibold bg-white"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-700">Ward ID</label>
                  <input
                    type="text"
                    value={incWard}
                    onChange={(e) => setIncWard(e.target.value)}
                    className="w-full text-xs rounded-lg border border-gray-200 p-2 bg-white font-mono"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-700">Severity</label>
                  <select
                    value={incSeverity}
                    onChange={(e) => setIncSeverity(e.target.value)}
                    className="w-full text-xs rounded-lg border border-gray-200 p-2 bg-white font-semibold"
                  >
                    <option value="P1_CRITICAL">P1 - Critical (Immediate Threat)</option>
                    <option value="P2_HIGH">P2 - High (Significant Stagnation)</option>
                    <option value="P3_MEDIUM">P3 - Medium (Moderate Waterlogging)</option>
                    <option value="P4_LOW">P4 - Low (Nuisance Runoff)</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-700">Latitude</label>
                  <input
                    type="number"
                    step="0.0001"
                    value={incLat}
                    onChange={(e) => setIncLat(parseFloat(e.target.value))}
                    className="w-full text-xs rounded-lg border border-gray-200 p-2 bg-white font-mono"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-700">Longitude</label>
                  <input
                    type="number"
                    step="0.0001"
                    value={incLon}
                    onChange={(e) => setIncLon(parseFloat(e.target.value))}
                    className="w-full text-xs rounded-lg border border-gray-200 p-2 bg-white font-mono"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-700">Operational Notes</label>
                <textarea
                  rows={3}
                  value={incNotes}
                  onChange={(e) => setIncNotes(e.target.value)}
                  placeholder="Details for disaster management teams..."
                  className="w-full text-xs rounded-lg border border-gray-200 p-2 bg-white"
                />
              </div>

              <button
                onClick={() => createIncidentMutation.mutate()}
                disabled={createIncidentMutation.isPending || !incTitle}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white rounded-lg text-xs font-bold shadow-xs transition-colors"
              >
                <Flame className="w-4 h-4" />
                {createIncidentMutation.isPending ? "Dispatching Incident…" : "🚨 Dispatch Incident & Broadcast"}
              </button>
            </div>
          </div>
        )}

        {/* TAB 3: Citizen Field Report Submitter */}
        {activeTab === "report" && (
          <div className="space-y-6 animate-fade-in max-w-2xl">
            <div className="jr-card p-5 space-y-4">
              <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                <FileWarning className="w-4 h-4 text-amber-600" />
                Submit Citizen Field Evidence Report
              </h3>
              <p className="text-xs text-gray-500">
                Submitted reports are automatically ingested, placed on the GIS Map, and evaluated via
                Groq Multimodal Vision AI for waterlogging corroboration.
              </p>

              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-700">Ward</label>
                <select
                  value={repWard}
                  onChange={(e) => setRepWard(e.target.value)}
                  className="w-full text-xs rounded-lg border border-gray-200 p-2 font-semibold bg-white"
                >
                  <option value="G-North">Ward G-North (Dharavi / Dadar)</option>
                  <option value="K-West">Ward K-West (Andheri West)</option>
                  <option value="L">Ward L (Kurla East / West)</option>
                  <option value="F-South">Ward F-South (Parel / Lalbaug)</option>
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-700">Citizen Observation / Description</label>
                <textarea
                  rows={3}
                  value={repDesc}
                  onChange={(e) => setRepDesc(e.target.value)}
                  className="w-full text-xs rounded-lg border border-gray-200 p-2 bg-white font-medium"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-700">Latitude</label>
                  <input
                    type="number"
                    step="0.0001"
                    value={repLat}
                    onChange={(e) => setRepLat(parseFloat(e.target.value))}
                    className="w-full text-xs rounded-lg border border-gray-200 p-2 bg-white font-mono"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-700">Longitude</label>
                  <input
                    type="number"
                    step="0.0001"
                    value={repLon}
                    onChange={(e) => setRepLon(parseFloat(e.target.value))}
                    className="w-full text-xs rounded-lg border border-gray-200 p-2 bg-white font-mono"
                  />
                </div>
              </div>

              <button
                onClick={() => createReportMutation.mutate()}
                disabled={createReportMutation.isPending}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-bold shadow-xs transition-colors"
              >
                <FileCheck className="w-4 h-4" />
                {createReportMutation.isPending ? "Submitting Report…" : "📱 Submit Citizen Report"}
              </button>
            </div>
          </div>
        )}

        {/* TAB 4: Critical Asset Registrar */}
        {activeTab === "asset" && (
          <div className="space-y-6 animate-fade-in max-w-2xl">
            <div className="jr-card p-5 space-y-4">
              <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                <Building2 className="w-4 h-4 text-purple-600" />
                Register Critical Municipal Asset
              </h3>

              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-700">Asset Facility Name</label>
                <input
                  type="text"
                  value={assetName}
                  onChange={(e) => setAssetName(e.target.value)}
                  placeholder="e.g. Milan Subway Pumping Station #4"
                  className="w-full text-xs rounded-lg border border-gray-200 p-2 font-semibold bg-white"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-700">Asset Type</label>
                  <select
                    value={assetType}
                    onChange={(e) => setAssetType(e.target.value)}
                    className="w-full text-xs rounded-lg border border-gray-200 p-2 bg-white font-semibold"
                  >
                    <option value="PUMPING_STATION">Pumping Station</option>
                    <option value="HOSPITAL">Major Hospital</option>
                    <option value="POWER_SUBSTATION">Power Substation</option>
                    <option value="FIRE_STATION">Fire Station</option>
                    <option value="RELIEF_SHELTER">Relief Shelter</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-700">Ward ID</label>
                  <input
                    type="text"
                    value={assetWard}
                    onChange={(e) => setAssetWard(e.target.value)}
                    className="w-full text-xs rounded-lg border border-gray-200 p-2 bg-white font-mono"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-700">Latitude</label>
                  <input
                    type="number"
                    step="0.0001"
                    value={assetLat}
                    onChange={(e) => setAssetLat(parseFloat(e.target.value))}
                    className="w-full text-xs rounded-lg border border-gray-200 p-2 bg-white font-mono"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-700">Longitude</label>
                  <input
                    type="number"
                    step="0.0001"
                    value={assetLon}
                    onChange={(e) => setAssetLon(parseFloat(e.target.value))}
                    className="w-full text-xs rounded-lg border border-gray-200 p-2 bg-white font-mono"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-700">Inundation Threshold (Meters)</label>
                <input
                  type="number"
                  step="0.05"
                  value={assetThreshold}
                  onChange={(e) => setAssetThreshold(parseFloat(e.target.value))}
                  className="w-full text-xs rounded-lg border border-gray-200 p-2 bg-white font-mono"
                />
              </div>

              <button
                onClick={() => createAssetMutation.mutate()}
                disabled={createAssetMutation.isPending || !assetName}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg text-xs font-bold shadow-xs transition-colors"
              >
                <Building2 className="w-4 h-4" />
                {createAssetMutation.isPending ? "Registering Asset…" : "🏢 Register Asset in Inventory"}
              </button>
            </div>
          </div>
        )}

        {/* Quick Launch Output Deck */}
        <div className="border-t border-gray-200 pt-6">
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">
            Inspect Output Across Unified Web Application (Live Reaction)
          </p>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {[
              { href: "/map", label: "Live Situation Map", icon: Compass, color: "text-blue-600 bg-blue-50" },
              { href: "/command-center", label: "Command Center", icon: Activity, color: "text-red-600 bg-red-50" },
              { href: "/flood", label: "Flood Susceptibility", icon: Waves, color: "text-cyan-600 bg-cyan-50" },
              { href: "/analytics", label: "Dynamic Analytics", icon: Layers, color: "text-purple-600 bg-purple-50" },
              { href: "/incidents", label: "Incident Operations", icon: AlertTriangle, color: "text-amber-600 bg-amber-50" },
              { href: "/reports", label: "Citizen Reports", icon: FileWarning, color: "text-emerald-600 bg-emerald-50" },
            ].map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="p-3 rounded-xl border border-gray-200 bg-white hover:border-gray-400 hover:shadow-xs transition-all flex flex-col items-center text-center group"
              >
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-2 ${link.color}`}>
                  <link.icon className="w-4 h-4" />
                </div>
                <span className="text-xs font-semibold text-gray-800 group-hover:text-blue-600 transition-colors">
                  {link.label}
                </span>
                <span className="text-[10px] text-gray-400 mt-0.5 flex items-center gap-1">
                  View Live <ExternalLink className="w-2.5 h-2.5" />
                </span>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
