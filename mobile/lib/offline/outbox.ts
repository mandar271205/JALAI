import * as Crypto from "expo-crypto";
import * as SQLite from "expo-sqlite";
import { syncApi } from "@/lib/api";
export type QueueStatus = "PENDING" | "SYNCING" | "SYNCED" | "FAILED";
export type QueuedMutation = {
  mutation_id: string;
  action: string;
  payload: Record<string, unknown>;
  client_timestamp: string;
  retry_count: number;
  status: QueueStatus;
};
let dbPromise: ReturnType<typeof SQLite.openDatabaseAsync> | undefined;
const db = () =>
  (dbPromise ??= SQLite.openDatabaseAsync("jalrakshak-mobile.db"));
export async function initOutbox() {
  const d = await db();
  await d.execAsync(
    "CREATE TABLE IF NOT EXISTS outbox (mutation_id TEXT PRIMARY KEY NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL, client_timestamp TEXT NOT NULL, retry_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'PENDING'); CREATE TABLE IF NOT EXISTS cache (cache_key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL, saved_at TEXT NOT NULL);",
  );
}
export async function enqueue(
  action: string,
  payload: Record<string, unknown>,
) {
  if (
    ![
      "VERIFY_LOCATION",
      "MEASURE_DEPTH",
      "ROAD_BLOCKED",
      "DRAIN_BLOCKED",
      "ROAD_REOPENED",
      "COMPLETE_TASK",
    ].includes(action)
  )
    throw new Error("This operation is not approved for offline sync.");
  await initOutbox();
  const item: QueuedMutation = {
    mutation_id: Crypto.randomUUID(),
    action,
    payload,
    client_timestamp: new Date().toISOString(),
    retry_count: 0,
    status: "PENDING",
  };
  const d = await db();
  await d.runAsync(
    "INSERT INTO outbox VALUES (?, ?, ?, ?, ?, ?)",
    item.mutation_id,
    item.action,
    JSON.stringify(item.payload),
    item.client_timestamp,
    0,
    "PENDING",
  );
  return item;
}
export async function listQueue() {
  await initOutbox();
  const rows = await (
    await db()
  ).getAllAsync<Omit<QueuedMutation, "payload"> & { payload: string }>(
    "SELECT * FROM outbox WHERE status != 'SYNCED' ORDER BY client_timestamp",
  );
  return rows.map((r) => ({
    ...r,
    payload: JSON.parse(r.payload),
  })) as QueuedMutation[];
}
export async function flushQueue(clientId: string) {
  const items = await listQueue();
  if (!items.length) return { acknowledged: 0 };
  const d = await db();
  for (const item of items)
    await d.runAsync(
      "UPDATE outbox SET status = ? WHERE mutation_id = ?",
      "SYNCING",
      item.mutation_id,
    );
  try {
    const response = await syncApi.batch({
      client_id: clientId,
      sync_version: 1,
      client_timestamp: new Date().toISOString(),
      mutations: items.map(({ mutation_id, action, payload }) => ({
        mutation_id,
        entity_type: "RESPONDER_TASK",
        entity_id: payload.task_id,
        base_version: payload.base_version,
        action,
        data: payload.data ?? {},
      })),
    });
    for (const item of items)
      await d.runAsync(
        "UPDATE outbox SET status = ? WHERE mutation_id = ?",
        "SYNCED",
        item.mutation_id,
      );
    return response;
  } catch (e) {
    for (const item of items)
      await d.runAsync(
        "UPDATE outbox SET status = ?, retry_count = retry_count + 1 WHERE mutation_id = ?",
        "FAILED",
        item.mutation_id,
      );
    throw e;
  }
}
export async function cacheSet(key: string, value: unknown) {
  await initOutbox();
  await (
    await db()
  ).runAsync(
    "INSERT OR REPLACE INTO cache VALUES (?, ?, ?)",
    key,
    JSON.stringify(value),
    new Date().toISOString(),
  );
}
export async function cacheGet<T>(key: string) {
  await initOutbox();
  const row = await (
    await db()
  ).getFirstAsync<{ value: string }>(
    "SELECT value FROM cache WHERE cache_key = ?",
    key,
  );
  return row ? (JSON.parse(row.value) as T) : null;
}
