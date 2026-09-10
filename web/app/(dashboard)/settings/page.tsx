"use client";
// Route: /settings — Operational Settings & Role Simulation Hub
import { useState } from "react";
import {
  Settings, Shield, Bell, Map, Sliders, Volume2, Save,
  CheckCircle2, RefreshCw, UserCheck, Smartphone,
} from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common";
import { useAuthStore } from "@/store";
import { ROLE_DISPLAY } from "@/lib/utils";
import type { UserRole } from "@/types";

const ALL_ROLES: UserRole[] = [
  "CITIZEN",
  "FIELD_RESPONDER",
  "ANALYST",
  "ALERT_APPROVER",
  "MUNICIPAL_OFFICER",
  "DISASTER_MANAGER",
  "ADMIN",
  "SUPER_ADMIN",
];

export default function SettingsPage() {
  const { user, login } = useAuthStore();
  const currentRole = user?.role || "DISASTER_MANAGER";
  const [selectedRole, setSelectedRole] = useState<UserRole>(currentRole);

  // Local settings state
  const [audioAlerts, setAudioAlerts] = useState(true);
  const [autoRefreshSec, setAutoRefreshSec] = useState(30);
  const [mapPitch3D, setMapPitch3D] = useState(true);
  const [highContrastRisk, setHighContrastRisk] = useState(false);

  const handleRoleChange = (newRole: UserRole) => {
    setSelectedRole(newRole);
    login(newRole);
    toast.success(`Role switched to ${ROLE_DISPLAY[newRole] || newRole}`, {
      description: "Permissions and command privileges dynamically updated.",
    });
  };

  const handleSavePreferences = () => {
    toast.success("Operational preferences saved locally");
  };

  return (
    <div>
      <PageHeader
        title="Settings & Operational Preferences"
        description="Role simulation, notification triggers, map rendering layers, and telemetry refresh frequencies"
      />

      <div className="page-content space-y-6 max-w-4xl">
        {/* Role Simulator Card (Key for Multi-Role Operations) */}
        <div className="jr-card p-6 space-y-4">
          <div className="flex items-center justify-between border-b border-gray-100 pb-3">
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-blue-600" />
              <h3 className="text-sm font-semibold text-gray-900">
                Command Role & RBAC Simulator
              </h3>
            </div>
            <span className="text-xs font-mono bg-blue-50 text-blue-700 px-2.5 py-0.5 rounded-full font-bold">
              Active: {currentRole}
            </span>
          </div>

          <p className="text-xs text-gray-500">
            Switch between authority levels to test two-person alert authorizations, moderation queues,
            and disaster management controls.
          </p>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 pt-1">
            {ALL_ROLES.map((r) => {
              const isSelected = currentRole === r;
              return (
                <button
                  key={r}
                  onClick={() => handleRoleChange(r)}
                  className={`p-3 rounded-xl text-left border transition-all text-xs ${
                    isSelected
                      ? "border-blue-600 bg-blue-50/60 shadow-xs ring-1 ring-blue-600"
                      : "border-gray-200 hover:border-gray-300 bg-white"
                  }`}
                >
                  <p className="font-semibold text-gray-900 truncate">{ROLE_DISPLAY[r] || r}</p>
                  <p className="text-[10px] text-gray-500 font-mono mt-0.5">{r}</p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Audio & Alert Thresholds */}
        <div className="jr-card p-6 space-y-5">
          <div className="flex items-center gap-2 border-b border-gray-100 pb-3">
            <Bell className="w-4 h-4 text-amber-600" />
            <h3 className="text-sm font-semibold text-gray-900">Critical Alarm Triggers</h3>
          </div>

          <div className="space-y-4 text-xs">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-gray-800">Acoustic Siren on P1 Incident</p>
                <p className="text-gray-500">Play alert chime when a critical flash flood incident is spawned</p>
              </div>
              <input
                type="checkbox"
                checked={audioAlerts}
                onChange={(e) => setAudioAlerts(e.target.checked)}
                className="w-4 h-4 text-blue-600 rounded cursor-pointer"
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-gray-800">Background Telemetry Poll Interval</p>
                <p className="text-gray-500">Query frequency for situational updates when WebSocket is offline</p>
              </div>
              <select
                value={autoRefreshSec}
                onChange={(e) => setAutoRefreshSec(Number(e.target.value))}
                className="p-1.5 border border-gray-200 rounded-md bg-white font-mono"
              >
                <option value={15}>15 seconds</option>
                <option value={30}>30 seconds</option>
                <option value={60}>60 seconds</option>
              </select>
            </div>
          </div>
        </div>

        {/* GIS Map & Visualization Settings */}
        <div className="jr-card p-6 space-y-5">
          <div className="flex items-center gap-2 border-b border-gray-100 pb-3">
            <Map className="w-4 h-4 text-emerald-600" />
            <h3 className="text-sm font-semibold text-gray-900">GIS Display & 3D Terrain</h3>
          </div>

          <div className="space-y-4 text-xs">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-gray-800">Enable 3D Topographical Tilt</p>
                <p className="text-gray-500">Allow pitch rotation in MapLibre for basin elevation inspection</p>
              </div>
              <input
                type="checkbox"
                checked={mapPitch3D}
                onChange={(e) => setMapPitch3D(e.target.checked)}
                className="w-4 h-4 text-blue-600 rounded cursor-pointer"
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-gray-800">High-Contrast Hexagon Mesh</p>
                <p className="text-gray-500">Sharper borders for H3 spatial hex cells on map view</p>
              </div>
              <input
                type="checkbox"
                checked={highContrastRisk}
                onChange={(e) => setHighContrastRisk(e.target.checked)}
                className="w-4 h-4 text-blue-600 rounded cursor-pointer"
              />
            </div>
          </div>

          <div className="pt-2 border-t border-gray-100 flex justify-end">
            <button
              onClick={handleSavePreferences}
              className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
            >
              <Save className="w-3.5 h-3.5" /> Save Preferences
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
