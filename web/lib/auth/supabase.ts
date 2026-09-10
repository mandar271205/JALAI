// ============================================================================
// JalRakshak AI — Supabase Auth Client (Public Anon Integration)
// STRICT SECURITY RULES:
// 1. NEVER import or reference SUPABASE_SERVICE_ROLE_KEY or SUPABASE_JWT_SECRET.
// 2. Uses only public NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.
// 3. Tokens are transmitted as Authorization: Bearer <JWT> to FastAPI backend.
// ============================================================================

import type { AuthUser, UserRole } from "@/types";
import { setAuthToken, clearSession } from "@/lib/api/client";

export const SUPABASE_URL =
  process.env.NEXT_PUBLIC_SUPABASE_URL || "";
export const SUPABASE_ANON_KEY =
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";
export const ENABLE_MOCK_AUTH =
  process.env.NEXT_PUBLIC_ENABLE_MOCK_AUTH === "true";

export interface SupabaseAuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token: string;
  user: {
    id: string;
    email?: string;
    app_metadata?: {
      role?: string;
      [key: string]: unknown;
    };
    user_metadata?: {
      role?: string;
      [key: string]: unknown;
    };
  };
}

/**
 * Parses role from decoded JWT payload or Supabase User metadata.
 */
export function extractUserRole(rawRole: string | undefined): UserRole {
  if (!rawRole) return "CITIZEN";
  const normalized = rawRole.toUpperCase();
  const validRoles: UserRole[] = [
    "CITIZEN",
    "FIELD_RESPONDER",
    "ANALYST",
    "ALERT_APPROVER",
    "MUNICIPAL_OFFICER",
    "DISASTER_MANAGER",
    "ADMIN",
    "SUPER_ADMIN",
    "ML_ADMIN",
  ];
  return validRoles.includes(normalized as UserRole)
    ? (normalized as UserRole)
    : "CITIZEN";
}

/**
 * Decodes JWT payload without verifying signature (backend verifies HS256).
 */
export function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const base64Url = parts[1];
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );
    return JSON.parse(jsonPayload);
  } catch {
    return null;
  }
}

/**
 * Checks whether a JWT token is expired.
 */
export function isJwtExpired(token: string): boolean {
  const payload = decodeJwtPayload(token);
  if (!payload || typeof payload.exp !== "number") return true;
  const nowInSeconds = Math.floor(Date.now() / 1000);
  return payload.exp <= nowInSeconds;
}

/**
 * Authenticates user via Supabase Auth Password Grant using PUBLIC anon key.
 */
export async function loginWithSupabase(
  email: string,
  pass: string
): Promise<{ user: AuthUser; token: string }> {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY || SUPABASE_ANON_KEY.startsWith("CHANGE_ME")) {
    throw new Error(
      "Supabase Auth credentials not configured (missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY)."
    );
  }

  const endpoint = `${SUPABASE_URL}/auth/v1/token?grant_type=password`;
  const res = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: SUPABASE_ANON_KEY,
    },
    body: JSON.stringify({ email, password: pass }),
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(
      errData.error_description || errData.message || `Authentication failed with status ${res.status}`
    );
  }

  const data: SupabaseAuthResponse = await res.json();
  const token = data.access_token;
  setAuthToken(token);

  const rawRole =
    data.user.app_metadata?.role ||
    data.user.user_metadata?.role ||
    (decodeJwtPayload(token)?.role as string);

  const role = extractUserRole(rawRole);
  const user: AuthUser = {
    user_id: data.user.id,
    email: data.user.email || null,
    role,
    metadata: {
      auth_provider: "supabase",
      expires_at: Date.now() + data.expires_in * 1000,
    },
  };

  return { user, token };
}

/**
 * Restores existing Supabase session from localStorage token if valid.
 */
export function restoreSupabaseSession(): { user: AuthUser; token: string } | null {
  if (typeof window === "undefined") return null;
  const token = localStorage.getItem("jr_token");
  if (!token) return null;

  if (isJwtExpired(token)) {
    clearSession();
    return null;
  }

  const payload = decodeJwtPayload(token);
  if (!payload) {
    clearSession();
    return null;
  }

  const rawRole = (payload.role as string) || (payload.app_metadata as Record<string, string>)?.role;
  const user: AuthUser = {
    user_id: (payload.sub as string) || "usr-unknown",
    email: (payload.email as string) || null,
    role: extractUserRole(rawRole),
    metadata: {
      auth_provider: "supabase",
      exp: payload.exp,
    },
  };

  return { user, token };
}

/**
 * Signs out from Supabase and clears stored tokens.
 */
export async function logoutSupabase(): Promise<void> {
  const token = typeof window !== "undefined" ? localStorage.getItem("jr_token") : null;
  clearSession();

  if (token && SUPABASE_URL && SUPABASE_ANON_KEY && !SUPABASE_ANON_KEY.startsWith("CHANGE_ME")) {
    try {
      await fetch(`${SUPABASE_URL}/auth/v1/logout`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          apikey: SUPABASE_ANON_KEY,
        },
      });
    } catch {
      // Best-effort network logout
    }
  }
}
