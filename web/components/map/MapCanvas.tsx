"use client";
// ============================================================================
// MapCanvas — Full-viewport MapLibre GL map with JalRakshak operational layers
// ============================================================================
import { useCallback, useRef, useState } from "react";
import Map, { NavigationControl, Source, Layer, type MapRef } from "react-map-gl/maplibre";
import { useQuery } from "@tanstack/react-query";
import { Layers, ToggleLeft, ToggleRight } from "lucide-react";
import { mapApi } from "@/lib/api/map";
import { MUMBAI_CENTER, MUMBAI_ZOOM, getMumbaiBboxString } from "@/lib/utils";
import { cn } from "@/lib/cn";
import type { RiskCell, Incident, FieldReport, CriticalAsset, Alert } from "@/types";

// Layer visibility state
interface LayerState {
  risk: boolean;
  incidents: boolean;
  reports: boolean;
  assets: boolean;
  alerts: boolean;
  nowcastTile: boolean;
}

const DEFAULT_LAYERS: LayerState = {
  risk: true,
  incidents: true,
  reports: true,
  assets: true,
  alerts: false,
  nowcastTile: false,
};

export default function MapCanvas() {
  const mapRef = useRef<MapRef>(null);
  const [layers, setLayers] = useState<LayerState>(DEFAULT_LAYERS);
  const [bbox, setBbox] = useState<string>(getMumbaiBboxString());

  // Fetch map layers
  const { data: riskData } = useQuery({
    queryKey: ["map-risk", bbox],
    queryFn: () => mapApi.getRiskCells({ bbox }),
    enabled: layers.risk,
    staleTime: 30_000,
  });

  const { data: incidentData } = useQuery({
    queryKey: ["map-incidents", bbox],
    queryFn: () => mapApi.getIncidents({ bbox }),
    enabled: layers.incidents,
    staleTime: 30_000,
  });

  const { data: reportData } = useQuery({
    queryKey: ["map-reports", bbox],
    queryFn: () => mapApi.getReports({ bbox }),
    enabled: layers.reports,
    staleTime: 30_000,
  });

  const { data: assetData } = useQuery({
    queryKey: ["map-assets", bbox],
    queryFn: () => mapApi.getAssets({ bbox }),
    enabled: layers.assets,
    staleTime: 60_000,
  });

  const toggleLayer = (key: keyof LayerState) =>
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }));

  // GeoJSON features from API responses
  const riskGeoJson = riskGeoJsonFromCells(riskData?.features || []);
  const incidentGeoJson = pointsGeoJson(
    (incidentData?.features || []).map((f: Incident) => ({
      lat: f.latitude,
      lng: f.longitude,
      id: f.incident_id,
      label: f.title,
      color: severityToColor(f.severity),
    })),
  );
  const reportGeoJson = pointsGeoJson(
    (reportData?.features || []).map((f: FieldReport) => ({
      lat: f.latitude,
      lng: f.longitude,
      id: f.report_id,
      label: f.description?.slice(0, 50),
      color: "#6366F1",
    })),
  );
  const assetGeoJson = pointsGeoJson(
    (assetData?.features || []).map((f: CriticalAsset) => ({
      lat: f.latitude,
      lng: f.longitude,
      id: f.asset_id || f.id || "",
      label: f.name,
      color: assetStatusColor(f.status),
    })),
  );

  return (
    <div className="relative w-full h-full">
      <Map
        ref={mapRef}
        initialViewState={{
          longitude: MUMBAI_CENTER[0],
          latitude: MUMBAI_CENTER[1],
          zoom: MUMBAI_ZOOM,
        }}
        style={{ width: "100%", height: "100%" }}
        mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
        onMoveEnd={(e) => {
          const b = e.target.getBounds();
          setBbox(
            `${b.getWest().toFixed(4)},${b.getSouth().toFixed(4)},${b.getEast().toFixed(4)},${b.getNorth().toFixed(4)}`,
          );
        }}
      >
        <NavigationControl position="bottom-right" />

        {/* Nowcast tile raster layer */}
        {layers.nowcastTile && (
          <Source
            id="nowcast-tiles"
            type="raster"
            tiles={[mapApi.getNowcastTileUrl()]}
            tileSize={256}
          >
            <Layer
              id="nowcast-raster"
              type="raster"
              paint={{ "raster-opacity": 0.6 }}
            />
          </Source>
        )}

        {/* Risk cells */}
        {layers.risk && riskGeoJson.features.length > 0 && (
          <Source id="risk-cells" type="geojson" data={riskGeoJson}>
            <Layer
              id="risk-fill"
              type="fill"
              paint={{
                "fill-color": ["get", "color"],
                "fill-opacity": 0.35,
              }}
            />
            <Layer
              id="risk-outline"
              type="line"
              paint={{
                "line-color": ["get", "color"],
                "line-width": 1,
                "line-opacity": 0.5,
              }}
            />
          </Source>
        )}

        {/* Incidents */}
        {layers.incidents && incidentGeoJson.features.length > 0 && (
          <Source id="incidents" type="geojson" data={incidentGeoJson}>
            <Layer
              id="incidents-circle"
              type="circle"
              paint={{
                "circle-color": ["get", "color"],
                "circle-radius": 8,
                "circle-stroke-color": "#fff",
                "circle-stroke-width": 2,
                "circle-opacity": 0.9,
              }}
            />
          </Source>
        )}

        {/* Reports */}
        {layers.reports && reportGeoJson.features.length > 0 && (
          <Source id="reports" type="geojson" data={reportGeoJson}>
            <Layer
              id="reports-circle"
              type="circle"
              paint={{
                "circle-color": ["get", "color"],
                "circle-radius": 6,
                "circle-stroke-color": "#fff",
                "circle-stroke-width": 1.5,
                "circle-opacity": 0.8,
              }}
            />
          </Source>
        )}

        {/* Assets */}
        {layers.assets && assetGeoJson.features.length > 0 && (
          <Source id="assets" type="geojson" data={assetGeoJson}>
            <Layer
              id="assets-circle"
              type="circle"
              paint={{
                "circle-color": ["get", "color"],
                "circle-radius": 7,
                "circle-stroke-color": "#fff",
                "circle-stroke-width": 2,
              }}
            />
          </Source>
        )}
      </Map>

      {/* Layer Control Panel */}
      <div className="absolute top-4 right-4 bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden z-10 min-w-44">
        <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 border-b border-gray-200">
          <Layers className="w-3.5 h-3.5 text-gray-500" />
          <span className="text-xs font-semibold text-gray-600">Layers</span>
        </div>
        {(Object.entries(layers) as [keyof LayerState, boolean][]).map(([key, active]) => (
          <button
            key={key}
            onClick={() => toggleLayer(key)}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-700 hover:bg-gray-50 transition-colors"
          >
            {active ? (
              <ToggleRight className="w-4 h-4 text-blue-600" />
            ) : (
              <ToggleLeft className="w-4 h-4 text-gray-300" />
            )}
            <span className="capitalize">{key.replace(/([A-Z])/g, " $1").trim()}</span>
          </button>
        ))}
      </div>

      {/* Legend */}
      <div className="absolute bottom-8 left-4 bg-white/95 backdrop-blur-sm rounded-xl shadow border border-gray-200 p-3 z-10">
        <p className="text-xs font-semibold text-gray-600 mb-2">Risk Level</p>
        {[
          { color: "#22C55E", label: "Low" },
          { color: "#F59E0B", label: "Moderate" },
          { color: "#F97316", label: "High" },
          { color: "#EF4444", label: "Severe" },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1.5 mb-1">
            <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: color }} />
            <span className="text-xs text-gray-600">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---- GeoJSON helpers -------------------------------------------------------
function riskGeoJsonFromCells(cells: RiskCell[]) {
  return {
    type: "FeatureCollection" as const,
    features: cells
      .filter((c) => c.latitude && c.longitude)
      .map((c) => ({
        type: "Feature" as const,
        geometry: {
          type: "Point" as const,
          coordinates: [c.longitude!, c.latitude!],
        },
        properties: {
          color: riskLevelToColor(c.risk_level),
          risk_level: c.risk_level,
        },
      })),
  };
}

function pointsGeoJson(
  points: Array<{ lat?: number; lng?: number; id: string; label?: string; color: string }>,
) {
  return {
    type: "FeatureCollection" as const,
    features: points
      .filter((p) => p.lat != null && p.lng != null)
      .map((p) => ({
        type: "Feature" as const,
        geometry: {
          type: "Point" as const,
          coordinates: [p.lng!, p.lat!],
        },
        properties: { id: p.id, label: p.label || "", color: p.color },
      })),
  };
}

function riskLevelToColor(level: string): string {
  const map: Record<string, string> = {
    LOW: "#22C55E",
    MODERATE: "#F59E0B",
    HIGH: "#F97316",
    SEVERE: "#EF4444",
  };
  return map[level] || "#9CA3AF";
}

function severityToColor(severity: string): string {
  const map: Record<string, string> = {
    LOW: "#22C55E",
    MODERATE: "#F59E0B",
    HIGH: "#F97316",
    SEVERE: "#EF4444",
    CRITICAL: "#7C3AED",
  };
  return map[severity] || "#6366F1";
}

function assetStatusColor(status: string): string {
  const map: Record<string, string> = {
    NORMAL: "#22C55E",
    AT_RISK: "#F59E0B",
    INUNDATED: "#EF4444",
    OFFLINE: "#6B7280",
  };
  return map[status] || "#6B7280";
}
