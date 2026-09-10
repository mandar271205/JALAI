// ============================================================================
// JalRakshak AI — Central HTTP API Client
// ALL fetch calls go through this module. Never call fetch() directly in components.
// ============================================================================

import { ApiError } from "@/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

// ---- Session helpers -------------------------------------------------------
let _token: string | null = null;
let _mockRole: string | null = null;

export function setAuthToken(token: string | null) {
  _token = token;
  if (typeof window !== "undefined") {
    if (token) localStorage.setItem("jr_token", token);
    else localStorage.removeItem("jr_token");
  }
}

export function setMockRole(role: string) {
  _mockRole = role;
  if (typeof window !== "undefined") localStorage.setItem("jr_mock_role", role);
}

export function getAuthToken(): string | null {
  if (_token) return _token;
  if (typeof window !== "undefined") {
    return localStorage.getItem("jr_token");
  }
  return null;
}

export function getMockRole(): string {
  if (_mockRole) return _mockRole;
  if (typeof window !== "undefined") {
    return localStorage.getItem("jr_mock_role") || "ADMIN";
  }
  return "ADMIN";
}

export function clearSession() {
  _token = null;
  _mockRole = null;
  if (typeof window !== "undefined") {
    localStorage.removeItem("jr_token");
    localStorage.removeItem("jr_mock_role");
  }
}

// ---- Request builder -------------------------------------------------------
function buildHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };

  const token = getAuthToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  } else if (process.env.NEXT_PUBLIC_ENABLE_MOCK_AUTH === "true") {
    // Explicit Dev mock mode only: use X-Mock-Role header
    headers["X-Mock-Role"] = getMockRole();
    headers["X-Mock-User"] = `usr-dev-${getMockRole().toLowerCase()}-001`;
  }

  return headers;
}

// ---- API Error classification -----------------------------------------------
export class JalRakshakApiError extends Error {
  constructor(
    public statusCode: number,
    public detail: string,
    public originalError?: unknown,
  ) {
    super(detail);
    this.name = "JalRakshakApiError";
  }

  get isUnauthorized() {
    return this.statusCode === 401;
  }
  get isForbidden() {
    return this.statusCode === 403;
  }
  get isNotFound() {
    return this.statusCode === 404;
  }
  get isRateLimit() {
    return this.statusCode === 429;
  }
  get isServerError() {
    return this.statusCode >= 500;
  }
}

// ---- Core fetch wrapper ----------------------------------------------------
async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      ...buildHeaders(),
      ...(options.headers || {}),
    },
  });

  // Handle 304 Not Modified (cache)
  if (response.status === 304) {
    return null as T;
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body: ApiError = await response.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }

    const err = new JalRakshakApiError(response.status, detail);

    // 401: trigger session expiry event
    if (response.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("jr:session-expired"));
    }

    throw err;
  }

  // Handle empty body
  const contentType = response.headers.get("content-type");
  if (!contentType || response.status === 204) {
    return null as T;
  }

  if (contentType.includes("application/json")) {
    return response.json() as Promise<T>;
  }

  return response.text() as unknown as T;
}

// ---- Public API methods ----------------------------------------------------
export const apiClient = {
  get: <T>(path: string, init?: RequestInit) =>
    request<T>(path, { method: "GET", ...init }),

  post: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, {
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
      ...init,
    }),

  patch: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, {
      method: "PATCH",
      body: body !== undefined ? JSON.stringify(body) : undefined,
      ...init,
    }),

  put: <T>(path: string, body?: unknown, init?: RequestInit) =>
    request<T>(path, {
      method: "PUT",
      body: body !== undefined ? JSON.stringify(body) : undefined,
      ...init,
    }),

  delete: <T>(path: string, init?: RequestInit) =>
    request<T>(path, { method: "DELETE", ...init }),
};

// ---- URL builder utility ---------------------------------------------------
export function buildUrl(base: string, params: Record<string, string | number | boolean | null | undefined>): string {
  const url = new URL(base, "http://placeholder");
  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });
  return `${url.pathname}${url.search}`;
}

// ---- WebSocket URL builder -------------------------------------------------
export function buildWsUrl(path: string): string {
  const base = API_BASE_URL.replace(/^http/, "ws");
  const token = getAuthToken();
  const params = token ? `?token=${token}` : "";
  return `${base}${path}${params}`;
}
