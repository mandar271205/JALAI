"use client";
// Route: /alerts/[id] — Alert Workflow & CAP 1.2 Dissemination Inspector
import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  ChevronLeft, Bell, CheckCircle2, Send, Copy, Download,
  AlertTriangle, ShieldAlert, FileCode, Check, Radio,
} from "lucide-react";
import { toast } from "sonner";
import { alertsApi } from "@/lib/api/alerts";
import { PageHeader, StatusBadge, Timestamp } from "@/components/common";
import { useAuthStore } from "@/store";
import type { Alert } from "@/types";

export default function AlertDetailPage() {
  const params = useParams();
  const router = useRouter();
  const alertId = params?.id as string;
  const { canDoAction } = useAuthStore();
  const queryClient = useQueryClient();
  const [copied, setCopied] = useState(false);

  // Fetch list of alerts to find this one
  const { data: alertData, isLoading } = useQuery({
    queryKey: ["alerts"],
    queryFn: () => alertsApi.list(),
  });

  const alertItem = alertData?.features?.find(
    (a: Alert) => a.alert_id === alertId,
  );

  // Fetch CAP XML
  const { data: capXml, isLoading: xmlLoading } = useQuery({
    queryKey: ["alert-cap-xml", alertId],
    queryFn: () => alertsApi.getCapXml(alertId),
    enabled: !!alertId,
    retry: 1,
  });

  const approveMutation = useMutation({
    mutationFn: () => alertsApi.approve(alertId),
    onSuccess: () => {
      toast.success("Alert approved. Ready for publication.");
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      queryClient.invalidateQueries({ queryKey: ["alert-cap-xml", alertId] });
    },
    onError: (err: Error) => toast.error("Approval failed", { description: err.message }),
  });

  const publishMutation = useMutation({
    mutationFn: () => alertsApi.publish(alertId),
    onSuccess: (res) => {
      toast.success("Alert published successfully via CAP 1.2!", {
        description: `Broadcast fanout complete at ${new Date(res.sent_at).toLocaleTimeString()}`,
      });
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      queryClient.invalidateQueries({ queryKey: ["alert-cap-xml", alertId] });
    },
    onError: (err: Error) => toast.error("Publishing failed", { description: err.message }),
  });

  const copyXml = () => {
    if (capXml) {
      navigator.clipboard.writeText(capXml);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      toast.info("CAP 1.2 XML copied to clipboard");
    }
  };

  const status = alertItem?.status || "DRAFT";
  const headline = alertItem?.headline || `Emergency Alert ${alertId.slice(0, 8)}`;

  return (
    <div>
      <PageHeader
        title={headline}
        description="Common Alerting Protocol (CAP 1.2) review, authorization, and broadcast pipeline"
        actions={
          <div className="flex items-center gap-2">
            <Link
              href="/alerts"
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-gray-200 text-xs font-medium text-gray-700 hover:bg-gray-50"
            >
              <ChevronLeft className="w-3.5 h-3.5" /> All Alerts
            </Link>
          </div>
        }
      />

      <div className="page-content space-y-6">
        {/* State Machine Status Bar */}
        <div className="jr-card p-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-gray-100 pb-5">
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <StatusBadge status={status} />
                <span className="text-xs font-mono text-gray-400">ID: {alertId}</span>
              </div>
              <h2 className="text-lg font-bold text-gray-900">{headline}</h2>
              {alertItem?.area_description && (
                <p className="text-xs text-gray-600 mt-1">
                  Target Zone: <span className="font-semibold">{alertItem.area_description}</span>
                </p>
              )}
            </div>

            {/* Actions depending on state */}
            <div className="flex items-center gap-3">
              {status === "DRAFT" && canDoAction("approve_alert") && (
                <button
                  onClick={() => approveMutation.mutate()}
                  disabled={approveMutation.isPending}
                  className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  {approveMutation.isPending ? "Approving..." : "Approve Alert"}
                </button>
              )}

              {status === "APPROVED" && canDoAction("publish_alert") && (
                <button
                  onClick={() => publishMutation.mutate()}
                  disabled={publishMutation.isPending}
                  className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
                >
                  <Send className="w-4 h-4" />
                  {publishMutation.isPending ? "Publishing..." : "Publish Broadcast"}
                </button>
              )}

              {status === "PUBLISHED" && (
                <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-50 text-emerald-700 text-xs font-medium rounded-lg border border-emerald-200">
                  <Radio className="w-3.5 h-3.5 animate-pulse" />
                  Live On Air & Mobile App
                </div>
              )}
            </div>
          </div>

          {/* Workflow Steps Indicator */}
          <div className="grid grid-cols-3 gap-4 pt-5">
            <div
              className={`p-3 rounded-xl border ${
                status === "DRAFT"
                  ? "bg-amber-50 border-amber-200 text-amber-900"
                  : "bg-gray-50 border-gray-100 text-gray-700"
              }`}
            >
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider">
                <span className="w-5 h-5 rounded-full bg-white flex items-center justify-center text-[10px] shadow-sm">
                  1
                </span>
                Drafted
              </div>
              <p className="text-[11px] text-gray-500 mt-1">Authored by Analyst</p>
            </div>

            <div
              className={`p-3 rounded-xl border ${
                status === "APPROVED"
                  ? "bg-blue-50 border-blue-200 text-blue-900"
                  : status === "PUBLISHED"
                  ? "bg-emerald-50/50 border-emerald-100 text-gray-700"
                  : "bg-gray-50 border-gray-100 text-gray-400"
              }`}
            >
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider">
                <span className="w-5 h-5 rounded-full bg-white flex items-center justify-center text-[10px] shadow-sm">
                  2
                </span>
                Approved
              </div>
              <p className="text-[11px] text-gray-500 mt-1">Verified by Approver</p>
            </div>

            <div
              className={`p-3 rounded-xl border ${
                status === "PUBLISHED"
                  ? "bg-emerald-50 border-emerald-200 text-emerald-900"
                  : "bg-gray-50 border-gray-100 text-gray-400"
              }`}
            >
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider">
                <span className="w-5 h-5 rounded-full bg-white flex items-center justify-center text-[10px] shadow-sm">
                  3
                </span>
                Published
              </div>
              <p className="text-[11px] text-gray-500 mt-1">CAP Fanout & Public Push</p>
            </div>
          </div>
        </div>

        {/* CAP 1.2 XML Inspector */}
        <div className="jr-card p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileCode className="w-4 h-4 text-purple-600" />
              <h3 className="text-sm font-semibold text-gray-900">CAP 1.2 XML Document</h3>
            </div>
            {capXml && (
              <button
                onClick={copyXml}
                className="flex items-center gap-1 px-2.5 py-1 text-xs border border-gray-200 rounded-md hover:bg-gray-50 text-gray-700"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                {copied ? "Copied" : "Copy XML"}
              </button>
            )}
          </div>

          <div className="bg-gray-950 text-emerald-400 p-4 rounded-xl font-mono text-xs overflow-x-auto leading-relaxed border border-gray-800 max-h-96">
            {xmlLoading ? (
              <p className="text-gray-500">Loading XML payload from backend...</p>
            ) : capXml ? (
              <pre>{capXml}</pre>
            ) : (
              <div className="text-gray-500 py-4 text-center">
                <p>CAP XML payload will be generated once alert is compiled.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
