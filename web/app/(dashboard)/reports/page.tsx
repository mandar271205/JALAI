"use client";
// Route: /reports — Citizen Reports Moderation Queue
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { FileWarning, CheckCircle, XCircle } from "lucide-react";
import { toast } from "sonner";
import { reportsApi } from "@/lib/api/reports";
import {
  PageHeader, StatusBadge, ConfidenceBar, EmptyState, LoadingSkeleton,
  ErrorState, Timestamp,
} from "@/components/common";
import { useAuthStore } from "@/store";

const STATUS_OPTIONS = ["", "PENDING", "AI_VERIFIED", "HUMAN_VERIFIED", "CORROBORATED", "REJECTED"];

export default function ReportsPage() {
  const { canDoAction } = useAuthStore();
  const [statusFilter, setStatusFilter] = useState("PENDING");
  const queryClient = useQueryClient();

  const { data: reports, isLoading, isError, refetch } = useQuery({
    queryKey: ["reports", statusFilter],
    queryFn: () => reportsApi.list({ status: statusFilter || undefined, limit: 50 }),
    refetchInterval: 30_000,
  });

  const reviewMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      reportsApi.review(id, { status }),
    onSuccess: (_, { status }) => {
      toast.success(`Report ${status.toLowerCase()}`);
      queryClient.invalidateQueries({ queryKey: ["reports"] });
    },
    onError: (err: Error) => toast.error("Review failed", { description: err.message }),
  });

  return (
    <div>
      <PageHeader
        title="Citizen Reports"
        description="AI-corroborated field reports from citizens — moderation queue"
      />

      <div className="page-content">
        {/* Status filter */}
        <div className="flex items-center gap-2">
          {STATUS_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${statusFilter === s ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
            >
              {s || "All"}
            </button>
          ))}
        </div>

        {/* Reports list */}
        <div className="jr-card">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {[...Array(5)].map((_, i) => <LoadingSkeleton key={i} className="h-24 w-full" />)}
            </div>
          ) : isError ? (
            <ErrorState message="Failed to load reports" onRetry={refetch} />
          ) : !reports?.length ? (
            <EmptyState
              title="No reports"
              message="No citizen reports match the current filter"
              icon={<FileWarning className="w-5 h-5" />}
            />
          ) : (
            <div className="divide-y divide-gray-50">
              {reports.map((report) => (
                <div key={report.report_id} className="px-5 py-4">
                  <div className="flex items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <StatusBadge status={report.verification_status} />
                        <Timestamp iso={report.created_at} relative />
                      </div>
                      <p className="text-sm text-gray-800 mb-1">{report.description}</p>
                      <div className="flex items-center gap-4 text-xs text-gray-500">
                        <span className="font-mono">
                          {report.latitude.toFixed(4)}, {report.longitude.toFixed(4)}
                        </span>
                        {report.ai_confidence !== null && report.ai_confidence !== undefined && (
                          <div className="flex items-center gap-1.5">
                            <span>AI:</span>
                            <ConfidenceBar value={report.ai_confidence} className="w-20" />
                          </div>
                        )}
                      </div>

                      {/* Visual corroboration (no depth!) */}
                      {report.visual_corroboration && (
                        <div className="mt-2 p-2 bg-gray-50 rounded-lg text-xs text-gray-600">
                          <span className="font-medium">Visual analysis: </span>
                          {report.visual_corroboration.observations.join(", ") || "—"}
                          <span className="ml-2 text-gray-400">
                            · {report.visual_corroboration.visual_severity}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Review actions (ANALYST+) */}
                    {canDoAction("review_report") &&
                      ["PENDING", "AI_VERIFIED"].includes(report.verification_status) && (
                        <div className="flex flex-col gap-1.5 flex-shrink-0">
                          <button
                            onClick={() => reviewMutation.mutate({ id: report.report_id, status: "HUMAN_VERIFIED" })}
                            className="flex items-center gap-1 px-2 py-1 rounded bg-emerald-50 text-emerald-700 text-xs hover:bg-emerald-100"
                          >
                            <CheckCircle className="w-3 h-3" /> Verify
                          </button>
                          <button
                            onClick={() => reviewMutation.mutate({ id: report.report_id, status: "REJECTED" })}
                            className="flex items-center gap-1 px-2 py-1 rounded bg-red-50 text-red-700 text-xs hover:bg-red-100"
                          >
                            <XCircle className="w-3 h-3" /> Reject
                          </button>
                        </div>
                      )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Scientific gate */}
        <div className="bg-blue-50 border border-blue-100 rounded-xl p-3 text-xs text-blue-600">
          <strong>Scientific Gate:</strong> estimated_water_depth_cm is never populated from citizen photos.
          Only verified hydrodynamic solver output produces depth data. Visual corroboration confirms
          water presence and severity category only.
        </div>
      </div>
    </div>
  );
}
