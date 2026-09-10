import { useSession } from "@/store/session";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,
  ) {
    super(message);
  }
}
const baseUrl = (
  process.env.EXPO_PUBLIC_API_URL ?? "http://10.0.2.2:8000/api/v1"
).replace(/\/$/, "");

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const session = useSession.getState().session;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  if (session?.token) headers.set("Authorization", `Bearer ${session.token}`);
  if (session?.mock) {
    headers.set("X-Mock-User", session.userId);
    headers.set("X-Mock-Role", session.role);
  }
  headers.set("X-Device-OS", "mobile");
  headers.set("X-Client-Version", "1.0.0");
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers,
      signal: controller.signal,
    });
    const text = await response.text();
    let body: unknown;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = text;
    }
    if (!response.ok) {
      const detail =
        typeof body === "object" && body && "detail" in body
          ? String((body as { detail: unknown }).detail)
          : `Request failed (${response.status})`;
      throw new ApiError(response.status, detail, body);
    }
    return body as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if ((error as Error).name === "AbortError")
      throw new ApiError(0, "The request timed out.");
    throw new ApiError(
      0,
      "Network unavailable. Showing cached data when possible.",
    );
  } finally {
    clearTimeout(timeout);
  }
}

export const get = <T>(path: string) => api<T>(path);
export const send = <T>(
  path: string,
  method: "POST" | "PATCH" | "DELETE",
  payload?: unknown,
) =>
  api<T>(path, {
    method,
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
export function userMessage(error: unknown) {
  if (!(error instanceof ApiError)) return "Something went wrong.";
  return (
    (
      {
        401: "Your session expired. Please sign in again.",
        403: "You do not have permission for this action.",
        404: "The requested item was not found.",
        409: "This item changed. Refresh and try again.",
        422: error.message,
        429: "Too many requests. Please wait and retry.",
        500: "The service encountered an error.",
        503: "Live service is temporarily degraded.",
      } as Record<number, string>
    )[error.status] ?? error.message
  );
}
