"use client";
// Route: /audit — Immutable Audit Log & Compliance Ledger
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ScrollText, Shield, Filter, Search, Lock, User,
  Clock, Hash, FileCode, CheckCircle2,
} from "lucide-react";
import { auditApi } from "@/lib/api/audit";
import {
  PageHeader, StatusBadge, EmptyState, LoadingSkeleton, ErrorState, Timestamp,
} from "@/components/common";
import { useAuthStore } from "@/store";
import type { AuditLog } from "@/types";

const ACTION_FILTERS = [
  "",
  "ALERT_PUBLISHED",
  "ALERT_APPROVED",
  "REPORT_REVIEWED",
  "INCIDENT_TRANSITIONED",
  "TASK_ASSIGNED",
];

export default function AuditLogPage() {
  const { user, canDoAction } = useAuthStore();
  const [actionFilter, setActionFilter] = useState("");
  const [searchTerm, setSearchTerm] = useState("");

  const { data: logs, isLoading, isError, refetch } = useQuery({
    queryKey: ["audit-logs", actionFilter],
    queryFn: () => auditApi.listLogs({ action: actionFilter || undefined, limit: 100 }),
    refetchInterval: 20_000,
  });

  const filteredLogs = logs?.filter((log: AuditLog) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      log.action?.toLowerCase().includes(term) ||
      log.actor_id?.toLowerCase().includes(term) ||
      log.target_entity?.toLowerCase().includes(term) ||
      log.trace_id?.toLowerCase().includes(term)
    );
  });

  return (
    <div>
      <PageHeader
        title="Audit Log & Compliance Trail"
        description="Tamper-evident operational ledger tracking all emergency authorizations, transitions, and reviews"
        actions={
          <div className="flex items-center gap-2">
            <span className="text-xs bg-emerald-50 text-emerald-700 px-3 py-1.5 rounded-lg font-medium flex items-center gap-1.5">
              <Lock className="w-3.5 h-3.5" /> Append-Only Vault
            </span>
          </div>
        }
      />

      <div className="page-content space-y-6">
        {/* Permission Gate Warning if citizen / low role */}
        {!["DISASTER_MANAGER", "ADMIN", "SUPER_ADMIN"].includes(user?.role || "") && (
          <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800 flex items-center gap-2">
            <Shield className="w-4 h-4 text-amber-600 flex-shrink-0" />
            <span>
              <strong>Restricted Access:</strong> Audit logs contain sensitive chain-of-custody data. Full details are strictly visible to <strong>DISASTER_MANAGER</strong> and <strong>ADMIN</strong> roles.
            </span>
          </div>
        )}

        {/* Filter and Search Bar */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="flex items-center gap-1.5 flex-wrap">
            <Filter className="w-3.5 h-3.5 text-gray-400" />
            {ACTION_FILTERS.map((act) => (
              <button
                key={act}
                onClick={() => setActionFilter(act)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                  actionFilter === act
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                {act || "All Actions"}
              </button>
            ))}
          </div>

          <div className="relative">
            <Search className="w-3.5 h-3.5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search actor, entity, trace..."
              className="pl-8 pr-3 py-1.5 text-xs border border-gray-200 rounded-lg w-64 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
        </div>

        {/* Audit Log Table */}
        <div className="jr-card">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {[...Array(6)].map((_, i) => (
                <LoadingSkeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : isError ? (
            <ErrorState message="Could not fetch audit log records" onRetry={refetch} />
          ) : !filteredLogs?.length ? (
            <EmptyState
              title="No Audit Entries"
              message="No recorded ledger events match the active search criteria."
              icon={<ScrollText className="w-6 h-6 text-gray-400" />}
            />
          ) : (
            <div className="divide-y divide-gray-100 text-xs">
              <div className="bg-gray-50/80 px-5 py-2.5 font-semibold text-gray-500 uppercase tracking-wider text-[10px] grid grid-cols-12 gap-2">
                <span className="col-span-3">Timestamp</span>
                <span className="col-span-3">Action</span>
                <span className="col-span-2">Actor</span>
                <span className="col-span-2">Target Entity</span>
                <span className="col-span-2 text-right">Trace ID</span>
              </div>

              {filteredLogs.map((log: AuditLog) => (
                <div
                  key={log.log_id || `${log.created_at}-${log.action}`}
                  className="px-5 py-3.5 grid grid-cols-12 gap-2 items-center hover:bg-gray-50/50 transition-colors"
                >
                  <div className="col-span-3 flex items-center gap-1.5 text-gray-600">
                    <Clock className="w-3.5 h-3.5 text-gray-400" />
                    <Timestamp iso={log.created_at} />
                  </div>

                  <div className="col-span-3">
                    <span className="font-semibold text-gray-900 font-mono text-[11px] bg-gray-100 px-2 py-0.5 rounded">
                      {log.action}
                    </span>
                  </div>

                  <div className="col-span-2 flex items-center gap-1.5 text-gray-700">
                    <User className="w-3.5 h-3.5 text-gray-400" />
                    <span className="truncate">{log.actor_id || "System Worker"}</span>
                  </div>

                  <div className="col-span-2 text-gray-600 truncate font-mono text-[11px]">
                    {log.target_entity || "—"}
                  </div>

                  <div className="col-span-2 text-right">
                    <span className="font-mono text-[10px] text-gray-400 bg-gray-50 px-1.5 py-0.5 rounded">
                      {log.trace_id ? log.trace_id.slice(0, 8) : "tr-local"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
