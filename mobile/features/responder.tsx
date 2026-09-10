import { useEffect, useState } from "react";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlatList, StyleSheet, Text, TextInput, View } from "react-native";
import {
  ClipboardCheck,
  MapPin,
  Radio,
  ShieldAlert,
} from "lucide-react-native";
import {
  Button,
  Card,
  Metric,
  OfflineBanner,
  Screen,
  StateView,
  StatusBadge,
  Unavailable,
} from "@/components/ui";
import { RecordCard, recordId } from "@/components/record";
import { QueryState } from "@/components/query-state";
import { responderApi } from "@/lib/api";
import { colors } from "@/lib/theme";
import {
  enqueue,
  flushQueue,
  listQueue,
  type QueuedMutation,
} from "@/lib/offline/outbox";
import { useOnline } from "@/hooks/use-online";
import { useSession } from "@/store/session";
import { IncidentDetailScreen } from "./citizen";

export function ResponderDashboard() {
  const router = useRouter();
  const online = useOnline();
  const q = useQuery({
    queryKey: ["tasks"],
    queryFn: () => responderApi.tasks(),
  });
  const tasks = q.data ?? [];
  const count = (s: string) => tasks.filter((t) => t.status === s).length;
  return (
    <Screen
      title="Field operations"
      subtitle="Responder task and connectivity overview"
    >
      {!online ? <OfflineBanner /> : null}
      <QueryState query={q}>
        <View style={s.metrics}>
          <Metric label="Assigned" value={count("ASSIGNED")} />
          <Metric label="En route" value={count("EN_ROUTE")} />
          <Metric label="On scene" value={count("ON_SCENE")} />
          <Metric label="Completed" value={count("COMPLETED")} />
        </View>
        <Card title="Current dispatch">
          <Radio color={colors.high} />
          <Text style={s.body}>
            {tasks.length
              ? "Open the assigned task list for verified instructions."
              : "No tasks currently assigned."}
          </Text>
        </Card>
        <Button
          label="Open assigned tasks"
          onPress={() => router.push("/(responder)/tasks")}
        />
        <Button
          secondary
          label="Offline sync"
          onPress={() => router.push("/(responder)/sync")}
        />
      </QueryState>
    </Screen>
  );
}
export function TasksScreen() {
  const router = useRouter();
  const q = useQuery({
    queryKey: ["tasks"],
    queryFn: () => responderApi.tasks(),
  });
  return (
    <Screen
      title="Assigned tasks"
      subtitle="Statuses are backend-authoritative"
      scroll={false}
    >
      <QueryState query={q} empty={!q.data?.length}>
        <FlatList
          data={q.data ?? []}
          keyExtractor={recordId}
          contentContainerStyle={{ gap: 10, paddingBottom: 30 }}
          renderItem={({ item }) => (
            <RecordCard
              kind="Task"
              item={item}
              onPress={() =>
                router.push(`/(responder)/tasks/${recordId(item)}`)
              }
            />
          )}
        />
      </QueryState>
    </Screen>
  );
}
export function TaskDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const online = useOnline();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["tasks"],
    queryFn: () => responderApi.tasks(),
  });
  const task = q.data?.find((x) => recordId(x) === id);
  const [notes, setNotes] = useState("");
  const action = useMutation({
    mutationFn: async (a: string) => {
      const version = Number(task?.version ?? 1);
      if (!online)
        return enqueue(a, {
          task_id: id,
          base_version: version,
          data: { notes },
        });
      return responderApi.action(id, a, version, { notes });
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
  if (q.isLoading)
    return (
      <Screen title="Task">
        <StateView state="loading" />
      </Screen>
    );
  if (!task)
    return (
      <Screen title="Task">
        <StateView
          state="empty"
          message="Task not found or no longer assigned."
        />
      </Screen>
    );
  return (
    <Screen
      title={String(task.task_type ?? "Field task")}
      subtitle={`Task ${id}`}
    >
      {!online ? <OfflineBanner /> : null}
      <RecordCard item={task} kind="Task" />
      <Card title="Instructions">
        <Text style={s.body}>
          {String(task.instructions ?? "No extra instructions supplied.")}
        </Text>
        <Text style={s.caption}>
          <MapPin size={13} /> {String(task.latitude ?? "—")},{" "}
          {String(task.longitude ?? "—")}
        </Text>
      </Card>
      <TextInput
        value={notes}
        onChangeText={setNotes}
        multiline
        style={s.input}
        placeholder="Operational notes"
      />
      <Button
        label="Start travel / verify location"
        onPress={() => action.mutate("VERIFY_LOCATION")}
      />
      <Button
        secondary
        label="Record on scene"
        onPress={() => action.mutate("MEASURE_DEPTH")}
      />
      <Button
        label="Complete task"
        onPress={() => action.mutate("COMPLETE_TASK")}
      />
      {action.error ? (
        <Text style={s.error}>{(action.error as Error).message}</Text>
      ) : null}
      <Text style={s.caption}>
        Offline actions use mutation IDs and optimistic base versions. The
        server may return a merge conflict instead of overwriting newer state.
      </Text>
    </Screen>
  );
}
export function ResponderIncidentScreen() {
  return <IncidentDetailScreen responder />;
}
export function FieldEvidenceScreen() {
  return (
    <Screen
      title="Field evidence"
      subtitle="Capture UI is ready; submission remains unavailable"
    >
      <Unavailable
        title="Dedicated responder evidence upload missing"
        detail="The backend has no responder field-evidence upload contract. Citizen upload endpoints are not reused silently. Photos and notes cannot be marked submitted until a dedicated authorized endpoint exists."
      />
      <Card>
        <ClipboardCheck color={colors.teal} />
        <Text style={s.body}>
          Task actions can include an existing evidence URL, measured depth
          entered by a trained responder, and notes. This app does not estimate
          depth from an image.
        </Text>
      </Card>
    </Screen>
  );
}
export function SyncScreen() {
  const session = useSession((x) => x.session);
  const online = useOnline();
  const [items, setItems] = useState<QueuedMutation[]>([]);
  const [error, setError] = useState("");
  const load = () => void listQueue().then(setItems);
  useEffect(load, []);
  async function sync() {
    try {
      setError("");
      await flushQueue(session?.userId ?? "unknown");
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <Screen title="Offline sync" subtitle="Safe responder mutations only">
      {!online ? <OfflineBanner pending={items.length} /> : null}
      <View style={s.metrics}>
        <Metric
          label="Pending"
          value={items.filter((x) => x.status === "PENDING").length}
        />
        <Metric
          label="Failed"
          value={items.filter((x) => x.status === "FAILED").length}
        />
      </View>
      {!items.length ? (
        <StateView state="empty" message="No actions waiting to sync." />
      ) : (
        items.map((x) => (
          <Card key={x.mutation_id}>
            <View style={s.between}>
              <Text style={s.body}>{x.action.replaceAll("_", " ")}</Text>
              <StatusBadge value={x.status} />
            </View>
            <Text style={s.caption}>
              {new Date(x.client_timestamp).toLocaleString()} · retry{" "}
              {x.retry_count}
            </Text>
          </Card>
        ))
      )}
      {error ? <Text style={s.error}>{error}</Text> : null}
      <Button
        label="Sync now"
        disabled={!online || !items.length}
        onPress={() => void sync()}
      />
    </Screen>
  );
}
export function ResponderProfile() {
  const router = useRouter();
  const signOut = useSession((s) => s.signOut);
  return (
    <Screen title="Responder profile" subtitle="Secure field session">
      <Card>
        <ShieldAlert color={colors.teal} />
        <StatusBadge value="FIELD RESPONDER" />
      </Card>
      <Button
        secondary
        label="Offline sync"
        onPress={() => router.push("/(responder)/sync")}
      />
      <Button
        label="Log out"
        onPress={() =>
          void signOut().then(() => router.replace("/(auth)/login"))
        }
      />
    </Screen>
  );
}
const s = StyleSheet.create({
  metrics: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  body: { color: colors.ink, fontSize: 14, lineHeight: 21 },
  caption: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  input: {
    minHeight: 100,
    textAlignVertical: "top",
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 14,
    padding: 12,
    color: colors.ink,
    backgroundColor: "#fff",
  },
  error: { color: colors.severe, fontWeight: "700" },
  between: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
});
