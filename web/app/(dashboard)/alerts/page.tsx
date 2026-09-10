"use client";
// Route: /alerts — Alert Workflow Hub (Draft → Approve → Publish)
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Bell, Plus, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { alertsApi } from "@/lib/api/alerts";
import {
  PageHeader, StatusBadge, EmptyState, LoadingSkeleton, ErrorState, Timestamp, ConfidenceBar,
} from "@/components/common";
import { useAuthStore } from "@/store";

export default function AlertsPage() {
  const { canDoAction } = useAuthStore();
  const queryClient = useQueryClient();

  const { data: alertData, isLoading, isError, refetch } = useQuery({
    queryKey: ["alerts"],
    queryFn: () => alertsApi.list(),
    refetchInterval: 30_000,
  });

  const approveMutation = useMutation({
    mutationFn: (alertId: string) => alertsApi.approve(alertId),
    onSuccess: () => {
      toast.success("Alert approved");
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
    onError: (err: Error) => toast.error("Approval failed", { description: err.message }),
  });

  const publishMutation = useMutation({
    mutationFn: (alertId: string) => alertsApi.publish(alertId),
    onSuccess: () => {
      toast.success("Alert published and broadcast");
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
    onError: (err: Error) => toast.error("Publish failed", { description: err.message }),
  });

  const alerts = alertData?.features || [];

  return (
    <div>
      <PageHeader
        title="Alert Management"
        description="Draft, approve, and publish CAP-formatted emergency alerts"
        actions={
          canDoAction("draft_alert") && (
            <Link
              href="/alerts/new"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              Draft Alert
            </Link>
          )
        }
      />

      <div className="page-content">
        {isLoading ? (
          <div className="jr-card">
            <div className="p-4 space-y-3">
              {[...Array(4)].map((_, i) => <LoadingSkeleton key={i} className="h-20 w-full" />)}
            </div>
          </div>
        ) : isError ? (
          <ErrorState message="Failed to load alerts" onRetry={refetch} />
        ) : !alerts.length ? (
          <EmptyState
            title="No alerts"
            message="No alerts have been issued. Compose a new alert to begin the workflow."
            icon={<Bell className="w-5 h-5" />}
          />
        ) : (
          <div className="jr-card divide-y divide-gray-50">
            {alerts.map((alert) => (
              <div key={alert.alert_id} className="px-5 py-4">
                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <StatusBadge status={alert.status} />
                      <span className="badge bg-gray-100 text-gray-600">{alert.severity}</span>
                      <Timestamp iso={alert.created_at} relative />
                    </div>
                    <p className="text-sm font-semibold text-gray-900">{alert.headline}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{alert.area_description}</p>
                    {alert.confidence != null && (
                      <ConfidenceBar value={alert.confidence} className="w-40 mt-1.5" />
                    )}
                  </div>

                  {/* Workflow actions */}
                  <div className="flex flex-col gap-1.5 flex-shrink-0">
                    {alert.status === "DRAFT" && canDoAction("approve_alert") && (
                      <button
                        onClick={() => approveMutation.mutate(alert.alert_id)}
                        disabled={approveMutation.isPending}
                        className="px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
                      >
                        Approve
                      </button>
                    )}
                    {alert.status === "APPROVED" && canDoAction("publish_alert") && (
                      <button
                        onClick={() => publishMutation.mutate(alert.alert_id)}
                        disabled={publishMutation.isPending}
                        className="px-3 py-1.5 rounded-lg bg-red-600 text-white text-xs font-medium hover:bg-red-700 disabled:opacity-50 transition-colors"
                      >
                        Publish
                      </button>
                    )}
                    <Link
                      href={`/alerts/${alert.alert_id}`}
                      className="px-3 py-1.5 rounded-lg bg-gray-100 text-gray-700 text-xs font-medium hover:bg-gray-200 transition-colors text-center"
                    >
                      Details
                    </Link>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
