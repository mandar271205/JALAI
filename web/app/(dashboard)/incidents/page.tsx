"use client";
// Route: /incidents — Incident Management Hub
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { AlertTriangle, Plus, Filter } from "lucide-react";
import { toast } from "sonner";
import { incidentsApi } from "@/lib/api/incidents";
import {
  PageHeader, RiskBadge, StatusBadge, EmptyState, LoadingSkeleton, ErrorState, Timestamp,
} from "@/components/common";
import { useAuthStore } from "@/store";

const STATUS_OPTIONS = ["", "OPEN", "DETECTED", "ACKNOWLEDGED", "DISPATCHED", "ON_SCENE", "RESOLVED", "CLOSED"];
const SEVERITY_OPTIONS = ["", "LOW", "MODERATE", "HIGH", "SEVERE", "CRITICAL"];

export default function IncidentsPage() {
  const { canDoAction } = useAuthStore();
  const [statusFilter, setStatusFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");

  const { data: incidents, isLoading, isError, refetch } = useQuery({
    queryKey: ["incidents", statusFilter, severityFilter],
    queryFn: () => incidentsApi.list({ status: statusFilter || undefined, severity: severityFilter || undefined }),
    refetchInterval: 30_000,
  });

  return (
    <div>
      <PageHeader
        title="Incidents"
        description="Active and historical flood incidents across Mumbai"
        actions={
          canDoAction("create_incident") && (
            <Link
              href="/incidents/new"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              New Incident
            </Link>
          )
        }
      />

      <div className="page-content">
        {/* Filters */}
        <div className="flex items-center gap-3 flex-wrap">
          <Filter className="w-4 h-4 text-gray-400" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="text-xs rounded-lg border border-gray-200 px-2 py-1.5 bg-white text-gray-700"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>{s || "All Statuses"}</option>
            ))}
          </select>
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="text-xs rounded-lg border border-gray-200 px-2 py-1.5 bg-white text-gray-700"
          >
            {SEVERITY_OPTIONS.map((s) => (
              <option key={s} value={s}>{s || "All Severities"}</option>
            ))}
          </select>
        </div>

        {/* Incident list */}
        <div className="jr-card">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {[...Array(5)].map((_, i) => <LoadingSkeleton key={i} className="h-16 w-full" />)}
            </div>
          ) : isError ? (
            <ErrorState message="Failed to load incidents" onRetry={refetch} />
          ) : !incidents?.length ? (
            <EmptyState
              title="No incidents"
              message="No incidents match the current filters"
              icon={<AlertTriangle className="w-5 h-5" />}
            />
          ) : (
            <div className="divide-y divide-gray-50">
              {incidents.map((incident) => (
                <Link
                  key={incident.incident_id}
                  href={`/incidents/${incident.incident_id}`}
                  className="flex items-start gap-4 px-5 py-4 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-gray-900">{incident.title}</p>
                    <p className="text-xs text-gray-500 mt-0.5 truncate">{incident.description || "No description"}</p>
                    <div className="flex items-center gap-2 mt-1.5">
                      <StatusBadge status={incident.status} />
                      <RiskBadge level={incident.severity as string} />
                      {incident.ward_id && (
                        <span className="text-xs text-gray-400">Ward: {incident.ward_id}</span>
                      )}
                    </div>
                  </div>
                  <Timestamp iso={incident.created_at} relative className="flex-shrink-0" />
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
