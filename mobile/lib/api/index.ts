import type { ApiRecord, MobileHome } from "@/types";
import { get, send } from "./client";
export const mobileApi = {
  home: (lat = 19.076, lon = 72.8777) =>
    get<MobileHome>(`/mobile/home?lat=${lat}&lon=${lon}&radius_km=5`),
};
export const alertsApi = {
  list: () =>
    get<ApiRecord[]>("/map/alerts").then((x) =>
      Array.isArray(x)
        ? x
        : ((x as unknown as { features?: ApiRecord[] }).features ?? []),
    ),
  detail: (id: string) => get<ApiRecord>(`/alerts/${id}`),
};
export const incidentsApi = {
  list: () => get<ApiRecord[]>("/incidents"),
  detail: (id: string) => get<ApiRecord>(`/incidents/${id}`),
};
export const mapApi = {
  risk: (bbox = "72.75,18.88,73.05,19.28") =>
    get<ApiRecord>(`/map/risk?bbox=${bbox}`),
  incidents: (bbox = "72.75,18.88,73.05,19.28") =>
    get<ApiRecord>(`/map/incidents?bbox=${bbox}`),
  reports: (bbox = "72.75,18.88,73.05,19.28") =>
    get<ApiRecord>(`/map/reports?bbox=${bbox}`),
};
export const watchApi = {
  list: () => get<ApiRecord[]>("/watch-locations"),
  create: (body: unknown) => send<ApiRecord>("/watch-locations", "POST", body),
  update: (id: string, body: unknown) =>
    send<ApiRecord>(`/watch-locations/${id}`, "PATCH", body),
  remove: (id: string) => send<ApiRecord>(`/watch-locations/${id}`, "DELETE"),
};
export const reportsApi = {
  list: () => get<ApiRecord[]>("/reports"),
  draft: (body: unknown) => send<ApiRecord>("/reports/draft", "POST", body),
  intent: (reportId: string, body: unknown) =>
    send<ApiRecord>(`/reports/${reportId}/uploads`, "POST", body),
  complete: (reportId: string, body: unknown) =>
    send<ApiRecord>(`/reports/${reportId}/uploads/complete`, "POST", body),
  detail: (id: string) => get<ApiRecord>(`/reports/${id}`),
  status: (id: string) => get<ApiRecord>(`/reports/${id}/status`),
};
export const responderApi = {
  tasks: (status?: string) =>
    get<ApiRecord[]>(`/responders/tasks${status ? `?status=${status}` : ""}`),
  action: (
    id: string,
    action: string,
    baseVersion: number,
    extra: ApiRecord = {},
  ) =>
    send<ApiRecord>(`/responders/tasks/${id}/action`, "POST", {
      action,
      base_version: baseVersion,
      ...extra,
    }),
};
export const devicesApi = {
  register: (body: unknown) =>
    send<ApiRecord>("/devices/push-token", "POST", body),
  unregister: (id: string) =>
    send<ApiRecord>(`/devices/push-token/${encodeURIComponent(id)}`, "DELETE"),
};
export const syncApi = {
  batch: (body: unknown) => send<ApiRecord>("/sync/batch", "POST", body),
};
export async function uploadBinary(
  url: string,
  uri: string,
  contentType: string,
  onProgress?: (value: number) => void,
) {
  const blob = await (await fetch(uri)).blob();
  onProgress?.(0.1);
  const result = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": contentType },
    body: blob,
  });
  onProgress?.(1);
  if (!result.ok) throw new Error(`Storage upload failed (${result.status})`);
  return result.headers.get("etag");
}
