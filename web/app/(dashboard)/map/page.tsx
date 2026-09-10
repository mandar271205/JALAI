"use client";
// ============================================================================
// Live Situation Map — Full-viewport GIS map with all operational layers
// Route: /map
// Backend: /api/v1/map/* + /api/v1/tiles/*
// ============================================================================
import dynamic from "next/dynamic";
import { PageHeader } from "@/components/common";

// MapCanvas must be dynamic-imported (no SSR — MapLibre is client-only)
const MapCanvas = dynamic(() => import("@/components/map/MapCanvas"), {
  ssr: false,
  loading: () => (
    <div className="flex-1 flex items-center justify-center bg-gray-100 text-sm text-gray-400">
      Loading map…
    </div>
  ),
});

export default function MapPage() {
  return (
    <div className="flex flex-col h-full">
      <PageHeader
        title="Live Situation Map"
        description="Real-time spatial view of risk, incidents, reports, and assets"
      />
      <div className="flex-1 min-h-0">
        <MapCanvas />
      </div>
    </div>
  );
}
