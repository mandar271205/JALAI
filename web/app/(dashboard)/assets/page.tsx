"use client";
// Route: /assets — Critical Infrastructure Status
import { useQuery } from "@tanstack/react-query";
import { MapPin, Filter } from "lucide-react";
import { useState } from "react";
import { assetsApi } from "@/lib/api/assets";
import {
  PageHeader, RiskBadge, StatusBadge, EmptyState, LoadingSkeleton, ErrorState,
} from "@/components/common";

const ASSET_TYPES = ["", "HOSPITAL", "POWER_SUBSTATION", "FIRE_STATION", "RELIEF_SHELTER"];
const STATUSES = ["", "NORMAL", "AT_RISK", "INUNDATED", "OFFLINE"];

export default function AssetsPage() {
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["assets", typeFilter, statusFilter],
    queryFn: () => assetsApi.list({ asset_type: typeFilter || undefined, status: statusFilter || undefined }),
    refetchInterval: 60_000,
  });

  return (
    <div>
      <PageHeader
        title="Critical Assets"
        description="Real-time status of hospitals, substations, fire stations, and shelters"
      />

      <div className="page-content">
        {/* Filters */}
        <div className="flex items-center gap-3 flex-wrap">
          <Filter className="w-4 h-4 text-gray-400" />
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}
            className="text-xs rounded-lg border border-gray-200 px-2 py-1.5 bg-white text-gray-700">
            {ASSET_TYPES.map((t) => <option key={t} value={t}>{t || "All Types"}</option>)}
          </select>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
            className="text-xs rounded-lg border border-gray-200 px-2 py-1.5 bg-white text-gray-700">
            {STATUSES.map((s) => <option key={s} value={s}>{s || "All Statuses"}</option>)}
          </select>
        </div>

        {/* Summary counts */}
        {data && (
          <div className="grid grid-cols-4 gap-3">
            {["HOSPITAL", "POWER_SUBSTATION", "FIRE_STATION", "RELIEF_SHELTER"].map((type) => {
              const count = data.items.filter((a) => a.asset_type === type).length;
              const atRisk = data.items.filter((a) => a.asset_type === type && a.status !== "NORMAL").length;
              return (
                <div key={type} className="jr-card p-4">
                  <p className="text-xs text-gray-500 mb-1">{type.replace(/_/g, " ")}</p>
                  <p className="text-2xl font-bold text-gray-900">{count}</p>
                  {atRisk > 0 && <p className="text-xs text-red-600 font-medium">{atRisk} at risk</p>}
                </div>
              );
            })}
          </div>
        )}

        {/* Assets table */}
        <div className="jr-card">
          {isLoading ? (
            <div className="p-4 space-y-2">
              {[...Array(6)].map((_, i) => <LoadingSkeleton key={i} className="h-12 w-full" />)}
            </div>
          ) : isError ? (
            <ErrorState message="Failed to load critical assets" onRetry={refetch} />
          ) : !data?.items?.length ? (
            <EmptyState title="No assets" message="No assets match current filters" icon={<MapPin className="w-5 h-5" />} />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full data-table">
                <thead>
                  <tr>
                    <th className="text-left">Name</th>
                    <th className="text-left">Type</th>
                    <th className="text-left">Status</th>
                    <th className="text-left">Risk</th>
                    <th className="text-left">Ward</th>
                    <th className="text-right">Capacity</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((asset, i) => (
                    <tr key={asset.asset_id || asset.id || i}>
                      <td className="font-medium">{asset.name}</td>
                      <td className="text-xs text-gray-500">{asset.asset_type.replace(/_/g, " ")}</td>
                      <td><StatusBadge status={asset.status} /></td>
                      <td>{asset.risk_level ? <RiskBadge level={asset.risk_level} /> : "—"}</td>
                      <td className="text-xs text-gray-500">{asset.ward_id || "—"}</td>
                      <td className="text-right text-sm">
                        {asset.capacity
                          ? `${asset.current_occupancy ?? 0}/${asset.capacity}`
                          : "—"}
                      </td>
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
