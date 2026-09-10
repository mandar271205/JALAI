"use client";
// ============================================================================
// Login Page — Supabase JWT Auth (Production) + Mock RBAC (Development Only)
// ============================================================================
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Droplets, Shield, ChevronDown, Lock, Mail, AlertTriangle } from "lucide-react";
import { useAuthStore } from "@/store";
import { ROLE_DISPLAY } from "@/lib/utils";
import type { UserRole } from "@/types";

const ROLES: Array<{ role: UserRole; description: string }> = [
  { role: "DISASTER_MANAGER", description: "Full operational control + approval authority" },
  { role: "ALERT_APPROVER", description: "Alert workflow approval + publication" },
  { role: "ANALYST", description: "Intelligence analysis + report review" },
  { role: "MUNICIPAL_OFFICER", description: "Incident management + resource allocation" },
  { role: "FIELD_RESPONDER", description: "Task execution + evidence submission" },
  { role: "ADMIN", description: "System administration" },
  { role: "ML_ADMIN", description: "ML system monitoring" },
];

export default function LoginPage() {
  const router = useRouter();
  const { login, loginWithSupabaseAuth, isLoading } = useAuthStore();
  
  // Real Supabase credentials state
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);

  // Dev mock state
  const [selectedRole, setSelectedRole] = useState<UserRole>("DISASTER_MANAGER");
  const [open, setOpen] = useState(false);

  // Flag: mock auth is only permitted when explicitly enabled in dev
  const isMockAuthEnabled =
    process.env.NEXT_PUBLIC_ENABLE_MOCK_AUTH === "true" ||
    process.env.NODE_ENV === "development";

  const handleRealLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError(null);
    try {
      await loginWithSupabaseAuth(email, password);
      router.push("/command-center");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Authentication failed";
      setAuthError(msg);
    }
  };

  const handleMockLogin = () => {
    login(selectedRole);
    router.push("/command-center");
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 flex items-center justify-center p-4">
      {/* Background grid */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff08_1px,transparent_1px),linear-gradient(to_bottom,#ffffff08_1px,transparent_1px)] bg-[size:48px_48px]" />

      <div className="relative w-full max-w-md">
        {/* Card */}
        <div className="bg-white/10 backdrop-blur-xl rounded-2xl border border-white/20 shadow-2xl p-8">
          {/* Logo */}
          <div className="flex items-center gap-3 mb-6">
            <div className="w-12 h-12 rounded-xl bg-blue-500 flex items-center justify-center shadow-lg shadow-blue-500/30">
              <Droplets className="w-7 h-7 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">JalRakshak AI</h1>
              <p className="text-xs text-blue-300">Command Center Authentication</p>
            </div>
          </div>

          {/* Real Supabase Login Form */}
          <form onSubmit={handleRealLogin} className="space-y-4 mb-6">
            <div>
              <label className="block text-xs font-medium text-blue-200 mb-1.5">
                Official Email
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-blue-300 absolute left-3.5 top-3" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="officer@jalrakshak.gov.in"
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-white/10 border border-white/20 text-white placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-blue-200 mb-1.5">
                Secure Password
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 text-blue-300 absolute left-3.5 top-3" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-white/10 border border-white/20 text-white placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
              </div>
            </div>

            {authError && (
              <div className="p-3 rounded-lg bg-red-500/20 border border-red-500/40 text-xs text-red-200 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                <span>{authError}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading || !email || !password}
              className="w-full py-3 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold text-sm shadow-lg shadow-blue-600/30 transition-all duration-200"
            >
              {isLoading ? "Authenticating via Supabase..." : "Sign In with Supabase Auth"}
            </button>
          </form>

          {/* Development Mock Auth (Explicitly Gated & Badged) */}
          {isMockAuthEnabled ? (
            <div className="pt-5 border-t border-white/15">
              <div className="mb-4 p-2.5 rounded-lg bg-amber-500/15 border border-amber-400/30 flex items-start gap-2">
                <Shield className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-[11px] font-semibold text-amber-300 uppercase tracking-wider">
                    Development Mock Auth Harness
                  </p>
                  <p className="text-[11px] text-amber-400/80 mt-0.5">
                    Simulates RBAC roles locally without external Supabase credentials. Disabled in strict production mode.
                  </p>
                </div>
              </div>

              <div className="mb-4">
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Simulate Role Identity
                </label>
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setOpen(!open)}
                    className="w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl bg-white/10 border border-white/20 text-white text-sm hover:bg-white/15 transition-colors"
                  >
                    <span>{ROLE_DISPLAY[selectedRole] || selectedRole}</span>
                    <ChevronDown className={`w-4 h-4 text-blue-300 transition-transform ${open ? "rotate-180" : ""}`} />
                  </button>

                  {open && (
                    <div className="absolute bottom-full left-0 right-0 mb-1 rounded-xl bg-slate-800 border border-white/20 shadow-2xl z-20 max-h-56 overflow-y-auto">
                      {ROLES.map(({ role, description }) => (
                        <button
                          type="button"
                          key={role}
                          onClick={() => { setSelectedRole(role); setOpen(false); }}
                          className={`w-full px-3.5 py-2 text-left hover:bg-white/10 transition-colors ${selectedRole === role ? "bg-blue-600/20" : ""}`}
                        >
                          <p className="text-xs font-medium text-white">{ROLE_DISPLAY[role]}</p>
                          <p className="text-[10px] text-blue-300">{description}</p>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <button
                type="button"
                onClick={handleMockLogin}
                className="w-full py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-white/20 text-slate-200 font-medium text-xs transition-colors"
              >
                Access via Mock Role Simulation
              </button>
            </div>
          ) : (
            <div className="pt-4 border-t border-white/10 text-center">
              <p className="text-xs text-slate-400">
                Mock Auth Disabled (<code className="text-slate-300">NEXT_PUBLIC_ENABLE_MOCK_AUTH=false</code>). Production Supabase Auth required.
              </p>
            </div>
          )}

          <p className="text-center text-[11px] text-blue-400/60 mt-5">
            NeuroBots · SIH26071 · Municipal Corporation of Greater Mumbai
          </p>
        </div>
      </div>
    </div>
  );
}

