"use client";
// ============================================================================
// MapCanvas — Full-viewport MapLibre GL map with JalRakshak operational layers
// ============================================================================
import { useCallback, useRef, useState } from "react";
import Map, { NavigationControl, Source, Layer, Popup, type MapRef } from "react-map-gl/maplibre";
import { useQuery } from "@tanstack/react-query";
import { Layers, ToggleLeft, ToggleRight, AlertTriangle, ShieldCheck, MapPin, Building2 } from "lucide-react";
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

const H3_CENTROIDS: Record<string, [number, number]> = {
  "8860145b53fffff": [72.8550, 19.0432], // Dharavi
  "8860145b51fffff": [72.8756, 19.0712], // Kurla
  "8860145b57fffff": [72.8478, 19.0178], // Dadar
  "8860145a33fffff": [72.8397, 19.1197], // Andheri
};

interface PopupInfo {
  longitude: number;
  latitude: number;
  title: string;
  subtitle?: string;
  badgeColor?: string;
  badgeText?: string;
}

export default function MapCanvas() {
  const mapRef = useRef<MapRef>(null);
  const [layers, setLayers] = useState<LayerState>(DEFAULT_LAYERS);
  const [bbox, setBbox] = useState<string>(getMumbaiBboxString());
  const [popupInfo, setPopupInfo] = useState<PopupInfo | null>(null);

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
    (incidentData?.features || []).map((f: any) => ({
      lat: f.latitude ?? f.location?.latitude,
      lng: f.longitude ?? f.location?.longitude,
      id: f.incident_id,
      label: f.title,
      color: severityToColor(f.severity),
      badgeText: f.severity,
      subtitle: `Status: ${f.status || "OPEN"} | Ward: ${f.ward_id || "N/A"}`,
    })),
  );
  const reportGeoJson = pointsGeoJson(
    (reportData?.features || []).map((f: any) => ({
      lat: f.latitude ?? f.location?.latitude,
      lng: f.longitude ?? f.location?.longitude,
      id: f.report_id,
      label: f.description?.slice(0, 60) || "Field Report",
      color: "#6366F1",
      badgeText: f.verification_status || "REPORT",
      subtitle: `Reported by citizen: ${f.citizen_id || "Anonymous"}`,
    })),
  );
  const assetGeoJson = pointsGeoJson(
    (assetData?.features || []).map((f: any) => ({
      lat: f.latitude ?? f.location?.latitude,
      lng: f.longitude ?? f.location?.longitude,
      id: f.asset_id || f.id || "",
      label: f.name,
      color: assetStatusColor(f.status),
      badgeText: f.status || "ASSET",
      subtitle: `Type: ${f.asset_type || "Infrastructure"}`,
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
        interactiveLayerIds={[
          "risk-core",
          "incidents-circle",
          "reports-circle",
          "assets-circle",
        ]}
        onClick={(e) => {
          const f = e.features?.[0];
          if (f && f.geometry.type === "Point") {
            const coords = (f.geometry as any).coordinates;
            const props = f.properties || {};
            setPopupInfo({
              longitude: coords[0],
              latitude: coords[1],
              title: props.label || props.ward_id || "Detail",
              subtitle: props.subtitle || (props.risk_level ? `Risk Zone: ${props.risk_level}` : undefined),
              badgeColor: props.color,
              badgeText: props.badgeText || props.risk_level,
            });
          } else {
            setPopupInfo(null);
          }
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
              id="risk-halo"
              type="circle"
              paint={{
                "circle-color": ["get", "color"],
                "circle-radius": 32,
                "circle-opacity": 0.28,
                "circle-stroke-color": ["get", "color"],
                "circle-stroke-width": 2,
                "circle-stroke-opacity": 0.7,
              }}
            />
            <Layer
              id="risk-core"
              type="circle"
              paint={{
                "circle-color": ["get", "color"],
                "circle-radius": 12,
                "circle-opacity": 0.6,
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 2,
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
                "circle-radius": 9,
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 2.5,
                "circle-opacity": 0.95,
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
                "circle-radius": 7,
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 2,
                "circle-opacity": 0.9,
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
                "circle-radius": 8,
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 2,
                "circle-opacity": 0.9,
              }}
            />
          </Source>
        )}

        {/* Selected Popup */}
        {popupInfo && (
          <Popup
            longitude={popupInfo.longitude}
            latitude={popupInfo.latitude}
            anchor="bottom"
            onClose={() => setPopupInfo(null)}
            closeButton={true}
          >
            <div className="p-2 min-w-44 text-xs font-sans text-gray-800">
              <div className="flex items-center justify-between gap-2 mb-1">
                <p className="font-bold text-sm text-gray-900 leading-tight">
                  {popupInfo.title}
                </p>
                {popupInfo.badgeText && (
                  <span
                    className="px-1.5 py-0.5 rounded text-[10px] font-bold text-white uppercase whitespace-nowrap"
                    style={{ backgroundColor: popupInfo.badgeColor || "#2563EB" }}
                  >
                    {popupInfo.badgeText}
                  </span>
                )}
              </div>
              {popupInfo.subtitle && (
                <p className="text-gray-600 text-[11px] leading-relaxed">
                  {popupInfo.subtitle}
                </p>
              )}
            </div>
          </Popup>
        )}
      </Map>

      {/* Layer Control Panel */}
      <div className="absolute top-4 right-4 bg-white/95 backdrop-blur-sm rounded-xl shadow-lg border border-gray-200 overflow-hidden z-10 min-w-44">
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

      {/* Legend & Stats */}
      <div className="absolute bottom-8 left-4 bg-white/95 backdrop-blur-sm rounded-xl shadow border border-gray-200 p-3 z-10 flex flex-col gap-3 min-w-48">
        <div>
          <p className="text-xs font-semibold text-gray-600 mb-2">Risk Level</p>
          {[
            { color: "#22C55E", label: "Low" },
            { color: "#F59E0B", label: "Moderate" },
            { color: "#F97316", label: "High" },
            { color: "#EF4444", label: "Severe" },
          ].map(({ color, label }) => (
            <div key={label} className="flex items-center gap-1.5 mb-1">
              <span className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
              <span className="text-xs text-gray-600">{label}</span>
            </div>
          ))}
        </div>

        <div className="border-t border-gray-100 pt-2 text-[11px] text-gray-500 flex flex-col gap-1">
          <div className="flex justify-between items-center">
            <span>Risk Zones:</span>
            <span className="font-semibold text-gray-700">{riskGeoJson.features.length}</span>
          </div>
          <div className="flex justify-between items-center">
            <span>Incidents:</span>
            <span className="font-semibold text-gray-700">{incidentGeoJson.features.length}</span>
          </div>
          <div className="flex justify-between items-center">
            <span>Citizen Reports:</span>
            <span className="font-semibold text-gray-700">{reportGeoJson.features.length}</span>
          </div>
          <div className="flex justify-between items-center">
            <span>Critical Assets:</span>
            <span className="font-semibold text-gray-700">{assetGeoJson.features.length}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---- GeoJSON helpers -------------------------------------------------------
function riskGeoJsonFromCells(cells: any[]) {
  return {
    type: "FeatureCollection" as const,
    features: cells
      .map((c) => {
        const lng =
          c.longitude ??
          c.location?.longitude ??
          (c.h3_cell_id ? H3_CENTROIDS[c.h3_cell_id]?.[0] : undefined);
        const lat =
          c.latitude ??
          c.location?.latitude ??
          (c.h3_cell_id ? H3_CENTROIDS[c.h3_cell_id]?.[1] : undefined);
        if (lat == null || lng == null) return null;
        return {
          type: "Feature" as const,
          geometry: {
            type: "Point" as const,
            coordinates: [lng, lat],
          },
          properties: {
            color: riskLevelToColor(c.risk_level),
            risk_level: c.risk_level,
            ward_id: c.ward_id || "Mumbai Cell",
            badgeText: c.risk_level,
            subtitle: `Ward: ${c.ward_id || "Mumbai"} | Rainfall: ${c.rainfall_rate_mm_h ? c.rainfall_rate_mm_h + " mm/h" : "N/A"}`,
          },
        };
      })
      .filter((f): f is NonNullable<typeof f> => f !== null),
  };
}

function pointsGeoJson(
  points: Array<{
    lat?: number;
    lng?: number;
    id: string;
    label?: string;
    color: string;
    subtitle?: string;
    badgeText?: string;
  }>,
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
        properties: {
          id: p.id,
          label: p.label || "",
          color: p.color,
          subtitle: p.subtitle,
          badgeText: p.badgeText,
        },
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
