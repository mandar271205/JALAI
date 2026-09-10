"use client";
// ============================================================================
// Sidebar Navigation
// ============================================================================
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Map, CloudRain, Waves, AlertTriangle,
  FileWarning, MapPin, Bell, Users, BarChart3, FlaskConical,
  Database, Server, PlaySquare, ScrollText, Settings,
  LogOut, Droplets, ShieldAlert, Sparkles,
} from "lucide-react";
import { useAuthStore } from "@/store";
import { useConnectionStatus } from "@/hooks/useRealtime";
import { ROLE_DISPLAY } from "@/lib/utils";
import { cn } from "@/lib/cn";

const NAV_GROUPS = [
  {
    label: "Command",
    items: [
      { href: "/command-center", icon: LayoutDashboard, label: "Command Center" },
      { href: "/simulation", icon: Sparkles, label: "Scenario & Field Studio" },
      { href: "/map", icon: Map, label: "Live Situation Map" },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { href: "/rainfall", icon: CloudRain, label: "Rainfall Intelligence" },
      { href: "/flood", icon: Waves, label: "Flood Susceptibility" },
      { href: "/risk", icon: ShieldAlert, label: "Risk Grid" },
    ],
  },
  {
    label: "Operations",
    items: [
      { href: "/incidents", icon: AlertTriangle, label: "Incidents" },
      { href: "/reports", icon: FileWarning, label: "Citizen Reports" },
      { href: "/assets", icon: MapPin, label: "Critical Assets" },
      { href: "/alerts", icon: Bell, label: "Alerts" },
      { href: "/responders", icon: Users, label: "Responders" },
    ],
  },
  {
    label: "Analysis",
    items: [
      { href: "/analytics", icon: BarChart3, label: "Analytics" },
      { href: "/explainability", icon: FlaskConical, label: "AI Explainability" },
    ],
  },
  {
    label: "System",
    items: [
      { href: "/sources", icon: Database, label: "Data Sources" },
      { href: "/system", icon: Server, label: "System Health" },
      { href: "/runs", icon: PlaySquare, label: "Model Runs" },
      { href: "/audit", icon: ScrollText, label: "Audit Log" },
      { href: "/settings", icon: Settings, label: "Settings" },
    ],
  },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuthStore();
  const connStatus = useConnectionStatus();

  return (
    <aside className="w-60 flex flex-col flex-shrink-0 bg-white border-r border-gray-200 h-full">
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-gray-100">
        <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center flex-shrink-0">
          <Droplets className="w-5 h-5 text-white" />
        </div>
        <div>
          <p className="text-sm font-bold text-gray-900">JalRakshak AI</p>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span
              className={cn(
                "w-1.5 h-1.5 rounded-full",
                connStatus === "CONNECTED" && "bg-emerald-500",
                connStatus === "RECONNECTING" && "bg-amber-400 animate-pulse",
                connStatus === "DEGRADED" && "bg-orange-500",
                connStatus === "DISCONNECTED" && "bg-gray-300",
              )}
            />
            <span className="text-xs text-gray-400">
              {connStatus === "CONNECTED" ? "Live" : connStatus}
            </span>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto scrollbar-thin py-3 px-3">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="mb-5">
            <p className="jr-section-title px-2 mb-1.5">{group.label}</p>
            {group.items.map(({ href, icon: Icon, label }) => {
              const isActive = pathname === href || pathname.startsWith(`${href}/`);
              return (
                <Link
                  key={href}
                  href={href}
                  prefetch={true}
                  className={cn(
                    "sidebar-nav-item",
                    isActive && "active",
                  )}
                >
                  <Icon className="w-4 h-4 flex-shrink-0" />
                  <span className="truncate">{label}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* User section */}
      <div className="border-t border-gray-100 p-3">
        <div className="flex items-center gap-2 px-2 py-2 rounded-lg bg-gray-50 mb-2">
          <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0">
            <span className="text-xs font-semibold text-blue-700">
              {(user?.email?.[0] || user?.user_id?.[0] || "U").toUpperCase()}
            </span>
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold text-gray-800 truncate">
              {user?.email || user?.user_id || "Unknown"}
            </p>
            <p className="text-xs text-gray-500 truncate">
              {ROLE_DISPLAY[user?.role || ""] || user?.role}
            </p>
          </div>
        </div>
        <button
          onClick={logout}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-gray-500 hover:text-red-600 hover:bg-red-50 transition-colors"
        >
          <LogOut className="w-3.5 h-3.5" />
          Sign out
        </button>
      </div>
    </aside>
  );
}
