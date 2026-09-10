"use client";
// Route: /reports/[id] — Citizen Report Detail & Moderation
import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  ChevronLeft, CheckCircle, XCircle, ShieldCheck, MapPin,
  Clock, AlertTriangle, User, Image as ImageIcon, Send, Sparkles,
} from "lucide-react";
import { toast } from "sonner";
import { reportsApi } from "@/lib/api/reports";
import {
  PageHeader, StatusBadge, ConfidenceBar, EmptyState, LoadingSkeleton,
  ErrorState, Timestamp,
} from "@/components/common";
import { useAuthStore } from "@/store";

export default function ReportDetailPage() {
  const params = useParams();
  const router = useRouter();
  const reportId = params?.id as string;
  const { canDoAction } = useAuthStore();
  const queryClient = useQueryClient();
  const [reviewNotes, setReviewNotes] = useState("");

  const { data: report, isLoading, isError, refetch } = useQuery({
    queryKey: ["report", reportId],
    queryFn: () => reportsApi.get(reportId),
    enabled: !!reportId,
    refetchInterval: 15_000,
  });

  const reviewMutation = useMutation({
    mutationFn: ({ status, notes }: { status: string; notes?: string }) =>
      reportsApi.review(reportId, { status, notes }),
    onSuccess: (_, { status }) => {
      toast.success(`Report marked as ${status}`);
      setReviewNotes("");
      queryClient.invalidateQueries({ queryKey: ["report", reportId] });
      queryClient.invalidateQueries({ queryKey: ["reports"] });
    },
    onError: (err: Error) => {
      toast.error("Moderation review failed", { description: err.message });
    },
  });

  if (isLoading) {
    return (
      <div className="p-6 space-y-4">
        <LoadingSkeleton className="h-8 w-48" />
        <LoadingSkeleton className="h-64 w-full" />
        <LoadingSkeleton className="h-48 w-full" />
      </div>
    );
  }

  if (isError || !report) {
    return (
      <div className="p-6">
        <Link
          href="/reports"
          className="inline-flex items-center gap-1.5 text-xs text-blue-600 hover:underline mb-4"
        >
          <ChevronLeft className="w-3.5 h-3.5" /> Back to Citizen Reports
        </Link>
        <ErrorState message="Could not load report details" onRetry={refetch} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={`Report ${report.report_id.slice(0, 8)}`}
        description="Detailed verification, AI corroboration, and supervisor action"
        actions={
          <Link
            href="/reports"
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-gray-200 text-xs font-medium text-gray-700 hover:bg-gray-50"
          >
            <ChevronLeft className="w-3.5 h-3.5" /> Back to Queue
          </Link>
        }
      />

      <div className="page-content space-y-6">
        {/* Top Info Banner */}
        <div className="jr-card p-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-gray-100 pb-5">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <StatusBadge status={report.verification_status} />
                <span className="text-xs text-gray-400 font-mono">ID: {report.report_id}</span>
                {report.incident_id && (
                  <Link
                    href={`/incidents/${report.incident_id}`}
                    className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded font-medium hover:underline"
                  >
                    Linked Incident #{report.incident_id.slice(0, 6)}
                  </Link>
                )}
              </div>
              <p className="text-lg font-semibold text-gray-900 leading-snug">
                {report.description || "Citizen field report submission"}
              </p>
            </div>

            {/* Quick stats / coordinates */}
            <div className="flex items-center gap-4 text-xs text-gray-600 bg-gray-50 px-4 py-2 rounded-xl">
              <div className="flex items-center gap-1.5">
                <MapPin className="w-4 h-4 text-blue-500" />
                <span className="font-mono">
                  {report.latitude.toFixed(5)}, {report.longitude.toFixed(5)}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <Clock className="w-4 h-4 text-gray-400" />
                <Timestamp iso={report.created_at} />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-5">
            <div>
              <p className="jr-section-title mb-1">Reporter</p>
              <p className="text-sm font-medium text-gray-800 flex items-center gap-1.5">
                <User className="w-3.5 h-3.5 text-gray-400" />
                {report.citizen_id || "Anonymous Citizen"}
              </p>
            </div>
            <div>
              <p className="jr-section-title mb-1">AI Confidence</p>
              {report.ai_confidence !== null && report.ai_confidence !== undefined ? (
                <div className="flex items-center gap-2">
                  <ConfidenceBar value={report.ai_confidence} className="w-28" />
                  <span className="text-xs font-mono font-medium text-gray-700">
                    {(report.ai_confidence * 100).toFixed(0)}%
                  </span>
                </div>
              ) : (
                <span className="text-xs text-gray-400">Not assessed</span>
              )}
            </div>
            <div>
              <p className="jr-section-title mb-1">Estimated Water Depth</p>
              <p className="text-xs text-amber-700 bg-amber-50 rounded px-2 py-1 inline-block">
                Protected by Scientific Gate (Hydrodynamic sensor required)
              </p>
            </div>
          </div>
        </div>

        {/* AI Corroboration and Evidence Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Visual Corroboration details */}
          <div className="jr-card p-6">
            <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2 mb-4">
              <Sparkles className="w-4 h-4 text-purple-600" />
              AI Visual Corroboration Engine
            </h3>
            {report.visual_corroboration ? (
              <div className="space-y-4">
                <div className="p-3 bg-purple-50/50 border border-purple-100 rounded-lg">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-purple-900 font-medium">Visual Severity Tag</span>
                    <span className="text-xs font-bold uppercase tracking-wider text-purple-700">
                      {report.visual_corroboration.visual_severity}
                    </span>
                  </div>
                  <p className="text-xs text-purple-800">
                    Confidence: {((report.visual_corroboration.visual_support_score ?? 0.8) * 100).toFixed(0)}%
                  </p>
                </div>

                <div>
                  <p className="text-xs font-medium text-gray-700 mb-2">Detected Visual Features:</p>
                  <div className="flex flex-wrap gap-2">
                    {report.visual_corroboration.observations.map((obs, idx) => (
                      <span
                        key={idx}
                        className="px-2.5 py-1 bg-gray-100 text-gray-700 rounded-md text-xs font-medium"
                      >
                        {obs}
                      </span>
                    ))}
                  </div>
                </div>

                <p className="text-xs text-gray-500 italic">
                  Corroboration verifies surface water pooling, debris, or submerged obstacles
                  without inferring numerical water depth.
                </p>
              </div>
            ) : (
              <div className="p-6 text-center text-gray-400 bg-gray-50 rounded-xl">
                <ImageIcon className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                <p className="text-xs">No visual imagery attached or corroboration pending.</p>
              </div>
            )}
          </div>

          {/* Review & Moderation Panel */}
          <div className="jr-card p-6">
            <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2 mb-4">
              <ShieldCheck className="w-4 h-4 text-blue-600" />
              Moderation & Review Decision
            </h3>

            {canDoAction("review_report") ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">
                    Reviewer Notes (Optional)
                  </label>
                  <textarea
                    value={reviewNotes}
                    onChange={(e) => setReviewNotes(e.target.value)}
                    placeholder="Provide justification or field validation notes..."
                    rows={3}
                    className="w-full text-xs p-2.5 border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>

                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={() =>
                      reviewMutation.mutate({ status: "HUMAN_VERIFIED", notes: reviewNotes })
                    }
                    disabled={reviewMutation.isPending}
                    className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
                  >
                    <CheckCircle className="w-4 h-4" />
                    Approve & Verify
                  </button>
                  <button
                    onClick={() =>
                      reviewMutation.mutate({ status: "CORROBORATED", notes: reviewNotes })
                    }
                    disabled={reviewMutation.isPending}
                    className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
                  >
                    <ShieldCheck className="w-4 h-4" />
                    Corroborate
                  </button>
                  <button
                    onClick={() =>
                      reviewMutation.mutate({ status: "REJECTED", notes: reviewNotes })
                    }
                    disabled={reviewMutation.isPending}
                    className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
                  >
                    <XCircle className="w-4 h-4" />
                    Reject Report
                  </button>
                </div>
              </div>
            ) : (
              <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800">
                You are currently viewing with a role that does not have moderation permissions
                (requires ANALYST, DISASTER_MANAGER, or ADMIN).
              </div>
            )}
          </div>
        </div>

        {/* Scientific Safety Notice */}
        <div className="p-4 bg-blue-50 border border-blue-100 rounded-xl flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 text-blue-600 flex-shrink-0 mt-0.5" />
          <div className="text-xs text-blue-700 space-y-1">
            <p className="font-semibold">Hydrological Integrity Policy</p>
            <p>
              Citizen photos provide crowd-sourced situational awareness and corroboration. Water
              depth and flow velocity metrics are strictly calculated via hydrodynamic modeling and
              in-situ telemetry sensors.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
