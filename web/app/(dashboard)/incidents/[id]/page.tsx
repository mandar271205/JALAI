"use client";
// Route: /incidents/[id] — Incident Detail + Transition
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { incidentsApi } from "@/lib/api/incidents";
import {
  PageHeader, RiskBadge, StatusBadge, LoadingSkeleton, ErrorState, Timestamp,
} from "@/components/common";
import { useAuthStore } from "@/store";

const TRANSITIONS: Record<string, string[]> = {
  OPEN: ["ACKNOWLEDGED", "DISPATCHED"],
  DETECTED: ["ACKNOWLEDGED", "DISPATCHED"],
  ACKNOWLEDGED: ["DISPATCHED", "CLOSED"],
  DISPATCHED: ["ON_SCENE", "CLOSED"],
  ON_SCENE: ["RESOLVED", "CLOSED"],
  RESOLVED: ["CLOSED"],
};

export default function IncidentDetailPage() {
  const params = useParams();
  const id = params?.id as string;
  const { canDoAction } = useAuthStore();
  const queryClient = useQueryClient();
  const [transitionTarget, setTransitionTarget] = useState("");
  const [reason, setReason] = useState("");

  const { data: incident, isLoading, isError, refetch } = useQuery({
    queryKey: ["incident", id],
    queryFn: () => incidentsApi.get(id),
    enabled: !!id,
  });

  const transitionMutation = useMutation({
    mutationFn: () => incidentsApi.transition(id, { target_status: transitionTarget, reason }),
    onSuccess: () => {
      toast.success(`Incident transitioned to ${transitionTarget}`);
      queryClient.invalidateQueries({ queryKey: ["incident", id] });
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      setTransitionTarget("");
      setReason("");
    },
    onError: (err: Error) => toast.error("Transition failed", { description: err.message }),
  });

  if (isLoading) return (
    <div className="page-content">
      {[...Array(3)].map((_, i) => <LoadingSkeleton key={i} className="h-20 w-full" />)}
    </div>
  );

  if (isError || !incident) return (
    <div className="page-content">
      <ErrorState message="Incident not found or unavailable" onRetry={refetch} />
    </div>
  );

  const availableTransitions = TRANSITIONS[incident.status] || [];

  return (
    <div>
      <PageHeader
        title={incident.title}
        description={`Incident ID: ${incident.incident_id}`}
        badge={
          <div className="flex items-center gap-2">
            <StatusBadge status={incident.status} />
            <RiskBadge level={incident.severity as string} />
          </div>
        }
        actions={
          <Link href="/incidents" className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700">
            <ArrowLeft className="w-3.5 h-3.5" />
            Back
          </Link>
        }
      />

      <div className="page-content grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Details */}
        <div className="lg:col-span-2 space-y-4">
          <div className="jr-card p-5">
            <h2 className="text-sm font-semibold text-gray-800 mb-3">Details</h2>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-gray-500">Category</dt><dd className="font-medium">{incident.category || "—"}</dd></div>
              <div><dt className="text-gray-500">Ward</dt><dd className="font-medium">{incident.ward_id || "—"}</dd></div>
              <div><dt className="text-gray-500">Created</dt><dd><Timestamp iso={incident.created_at} /></dd></div>
              <div><dt className="text-gray-500">Updated</dt><dd><Timestamp iso={incident.updated_at} /></dd></div>
              {incident.latitude && (
                <div className="col-span-2">
                  <dt className="text-gray-500">Location</dt>
                  <dd className="font-mono text-xs">{incident.latitude.toFixed(5)}, {incident.longitude?.toFixed(5)}</dd>
                </div>
              )}
            </dl>
            {incident.description && (
              <div className="mt-4 pt-4 border-t border-gray-100">
                <p className="text-xs text-gray-500 mb-1">Description</p>
                <p className="text-sm text-gray-700">{incident.description}</p>
              </div>
            )}
          </div>

          {/* Timeline */}
          {incident.timeline && incident.timeline.length > 0 && (
            <div className="jr-card p-5">
              <h2 className="text-sm font-semibold text-gray-800 mb-3">Status Timeline</h2>
              <div className="space-y-3">
                {incident.timeline.map((event) => (
                  <div key={event.event_id} className="flex items-start gap-3">
                    <div className="w-2 h-2 rounded-full bg-blue-400 mt-1.5 flex-shrink-0" />
                    <div>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={event.new_status} />
                        <Timestamp iso={event.created_at} relative />
                      </div>
                      <p className="text-xs text-gray-500 mt-0.5">{event.reason || "—"}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Actions */}
        <div>
          {canDoAction("transition_incident") && availableTransitions.length > 0 && (
            <div className="jr-card p-5">
              <h2 className="text-sm font-semibold text-gray-800 mb-3">Transition Status</h2>
              <select
                value={transitionTarget}
                onChange={(e) => setTransitionTarget(e.target.value)}
                className="w-full text-sm rounded-lg border border-gray-200 px-3 py-2 bg-white mb-3"
              >
                <option value="">Select new status…</option>
                {availableTransitions.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Reason / notes (optional)"
                rows={2}
                className="w-full text-xs rounded-lg border border-gray-200 px-3 py-2 resize-none mb-3"
              />
              <button
                onClick={() => transitionMutation.mutate()}
                disabled={!transitionTarget || transitionMutation.isPending}
                className="w-full py-2 rounded-lg bg-blue-600 text-white text-xs font-medium disabled:opacity-50 hover:bg-blue-700 transition-colors"
              >
                {transitionMutation.isPending ? "Transitioning…" : "Apply Transition"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
