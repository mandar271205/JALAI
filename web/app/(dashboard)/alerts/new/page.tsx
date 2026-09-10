"use client";
// Route: /alerts/new — Draft Emergency Alert (CAP 1.2 Standard)
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  ChevronLeft, Bell, AlertTriangle, ShieldCheck, FileCode, CheckCircle,
} from "lucide-react";
import { toast } from "sonner";
import { alertsApi } from "@/lib/api/alerts";
import { PageHeader } from "@/components/common";
import { useAuthStore } from "@/store";

const SEVERITIES = ["Extreme", "Severe", "Moderate", "Minor", "Unknown"] as const;
const URGENCIES = ["Immediate", "Expected", "Future", "Past", "Unknown"] as const;
const CERTAINTIES = ["Observed", "Likely", "Possible", "Unlikely", "Unknown"] as const;

export default function NewAlertPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { canDoAction } = useAuthStore();

  const [formData, setFormData] = useState({
    headline: "",
    description: "",
    instruction: "",
    severity: "Severe",
    urgency: "Immediate",
    certainty: "Likely",
    area_description: "",
    ward_id: "WARD-12",
    confidence: 0.85,
  });

  const draftMutation = useMutation({
    mutationFn: () =>
      alertsApi.draft({
        headline: formData.headline,
        description: formData.description,
        instruction: formData.instruction,
        severity: formData.severity,
        urgency: formData.urgency,
        certainty: formData.certainty,
        area_description: formData.area_description,
        ward_id: formData.ward_id,
        confidence: Number(formData.confidence),
      }),
    onSuccess: (newAlert) => {
      toast.success("Alert draft created successfully");
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      router.push(`/alerts/${newAlert.alert_id}`);
    },
    onError: (err: Error) => {
      toast.error("Failed to draft alert", { description: err.message });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.headline.trim() || !formData.area_description.trim()) {
      toast.error("Headline and Target Area are required");
      return;
    }
    if (formData.confidence < 0.5) {
      toast.error("CAP 1.2 Protocol requires confidence score >= 0.5");
      return;
    }
    draftMutation.mutate();
  };

  return (
    <div>
      <PageHeader
        title="Draft Emergency Alert"
        description="Author standard Common Alerting Protocol (CAP 1.2) emergency warning"
        actions={
          <Link
            href="/alerts"
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-gray-200 text-xs font-medium text-gray-700 hover:bg-gray-50"
          >
            <ChevronLeft className="w-3.5 h-3.5" /> Back to Alerts
          </Link>
        }
      />

      <div className="page-content space-y-6 max-w-5xl">
        {!canDoAction("draft_alert") && (
          <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
            <span>
              Drafting alerts requires <strong>ANALYST</strong>, <strong>DISASTER_MANAGER</strong>, or <strong>ADMIN</strong> credentials.
            </span>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Form */}
          <form onSubmit={handleSubmit} className="lg:col-span-2 space-y-5 jr-card p-6">
            <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2 pb-2 border-b border-gray-100">
              <Bell className="w-4 h-4 text-blue-600" />
              Alert Parameters
            </h3>

            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Headline / Warning Summary *
              </label>
              <input
                type="text"
                value={formData.headline}
                onChange={(e) => setFormData({ ...formData, headline: e.target.value })}
                placeholder="e.g. FLASH FLOOD WARNING: Ward 12 Low-Lying Zones"
                className="w-full text-xs p-2.5 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">Severity *</label>
                <select
                  value={formData.severity}
                  onChange={(e) => setFormData({ ...formData, severity: e.target.value })}
                  className="w-full text-xs p-2.5 border border-gray-200 rounded-lg bg-white focus:ring-2 focus:ring-blue-500"
                >
                  {SEVERITIES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">Urgency *</label>
                <select
                  value={formData.urgency}
                  onChange={(e) => setFormData({ ...formData, urgency: e.target.value })}
                  className="w-full text-xs p-2.5 border border-gray-200 rounded-lg bg-white focus:ring-2 focus:ring-blue-500"
                >
                  {URGENCIES.map((u) => (
                    <option key={u} value={u}>
                      {u}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">Certainty *</label>
                <select
                  value={formData.certainty}
                  onChange={(e) => setFormData({ ...formData, certainty: e.target.value })}
                  className="w-full text-xs p-2.5 border border-gray-200 rounded-lg bg-white focus:ring-2 focus:ring-blue-500"
                >
                  {CERTAINTIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Target Geographic Area Description *
                </label>
                <input
                  type="text"
                  value={formData.area_description}
                  onChange={(e) => setFormData({ ...formData, area_description: e.target.value })}
                  placeholder="e.g. Ward 12 riverside settlements, sectors 4-8"
                  className="w-full text-xs p-2.5 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">Ward ID</label>
                <input
                  type="text"
                  value={formData.ward_id}
                  onChange={(e) => setFormData({ ...formData, ward_id: e.target.value })}
                  placeholder="WARD-12"
                  className="w-full text-xs p-2.5 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-semibold text-gray-700">
                  AI Model Confidence (Min 0.5)
                </label>
                <span className="text-xs font-mono font-bold text-blue-600">
                  {(formData.confidence * 100).toFixed(0)}%
                </span>
              </div>
              <input
                type="range"
                min="0.5"
                max="1.0"
                step="0.01"
                value={formData.confidence}
                onChange={(e) => setFormData({ ...formData, confidence: parseFloat(e.target.value) })}
                className="w-full h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Detailed Hazard Description
              </label>
              <textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Water levels expected to exceed danger threshold within 45 minutes due to continuous upstream precipitation."
                rows={3}
                className="w-full text-xs p-2.5 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Public Safety Instructions
              </label>
              <textarea
                value={formData.instruction}
                onChange={(e) => setFormData({ ...formData, instruction: e.target.value })}
                placeholder="Move immediately to higher ground. Avoid crossing drainage channels or flooded roadways. Follow warden instructions."
                rows={2}
                className="w-full text-xs p-2.5 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={draftMutation.isPending || !canDoAction("draft_alert")}
                className="w-full flex items-center justify-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-semibold rounded-lg shadow transition-colors"
              >
                <ShieldCheck className="w-4 h-4" />
                {draftMutation.isPending ? "Submitting Draft..." : "Create CAP 1.2 Draft Alert"}
              </button>
            </div>
          </form>

          {/* CAP 1.2 Realtime Preview Card */}
          <div className="space-y-4">
            <div className="jr-card p-5">
              <h4 className="text-xs font-semibold text-gray-900 uppercase tracking-wider mb-3 flex items-center gap-2">
                <FileCode className="w-3.5 h-3.5 text-gray-500" />
                Live CAP 1.2 Payload Preview
              </h4>

              <div className="bg-gray-950 text-emerald-400 p-3 rounded-lg font-mono text-[11px] overflow-x-auto leading-relaxed border border-gray-800">
                <p>&lt;alert xmlns=&quot;urn:oasis:names:tc:emergency:cap:1.2&quot;&gt;</p>
                <p className="pl-2">&lt;identifier&gt;DRAFT-{Date.now()}&lt;/identifier&gt;</p>
                <p className="pl-2">&lt;status&gt;Draft&lt;/status&gt;</p>
                <p className="pl-2">&lt;msgType&gt;Alert&lt;/msgType&gt;</p>
                <p className="pl-2">&lt;info&gt;</p>
                <p className="pl-4">&lt;urgency&gt;{formData.urgency}&lt;/urgency&gt;</p>
                <p className="pl-4">&lt;severity&gt;{formData.severity}&lt;/severity&gt;</p>
                <p className="pl-4">&lt;certainty&gt;{formData.certainty}&lt;/certainty&gt;</p>
                <p className="pl-4 truncate">&lt;headline&gt;{formData.headline || "..."}&lt;/headline&gt;</p>
                <p className="pl-4 truncate">&lt;areaDesc&gt;{formData.area_description || "..."}&lt;/areaDesc&gt;</p>
                <p className="pl-2">&lt;/info&gt;</p>
                <p>&lt;/alert&gt;</p>
              </div>

              <p className="text-[11px] text-gray-500 mt-3">
                Drafting an alert does NOT dispatch broadcasts immediately. A Designated
                <strong> ALERT_APPROVER</strong> must verify and authorize publication.
              </p>
            </div>

            <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-xs text-blue-800 space-y-1">
              <div className="flex items-center gap-1.5 font-semibold">
                <CheckCircle className="w-3.5 h-3.5 text-blue-600" />
                Two-Person Verification Rule
              </div>
              <p className="text-[11px] text-blue-600">
                In compliance with NDMA flood dissemination guidelines, alert creation and
                publication are split across separate role permissions.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
