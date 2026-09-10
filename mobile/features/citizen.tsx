import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import {
  FlatList,
  Pressable,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import {
  Bell,
  Camera,
  CloudRain,
  MapPin,
  Navigation,
  ShieldCheck,
} from "lucide-react-native";
import {
  alertsApi,
  incidentsApi,
  mapApi,
  mobileApi,
  watchApi,
} from "@/lib/api";
import { colors } from "@/lib/theme";
import {
  Button,
  Card,
  Metric,
  OfflineBanner,
  RiskBadge,
  Screen,
  StatusBadge,
  Unavailable,
} from "@/components/ui";
import { QueryState } from "@/components/query-state";
import { RecordCard, recordId } from "@/components/record";
import { useOnline } from "@/hooks/use-online";
import { requestCurrentLocation } from "@/lib/location/current";
import { registerPush } from "@/lib/notifications/push";
import { useSession } from "@/store/session";
import type { ApiRecord } from "@/types";

const value = (x: ApiRecord | undefined, ...keys: string[]) =>
  keys.map((k) => x?.[k]).find((v) => v != null);
export function HomeScreen() {
  const router = useRouter();
  const online = useOnline();
  const query = useQuery({
    queryKey: ["mobile-home"],
    queryFn: () => mobileApi.home(),
  });
  const home = query.data;
  const risk = home?.current_risk;
  return (
    <Screen
      title="Good morning"
      subtitle={
        home?.location?.ward_id
          ? `Watching ${home.location.ward_id}`
          : "Mumbai pilot area"
      }
    >
      {!online ? <OfflineBanner /> : null}
      {home?.system_status?.operational_mode === "DEMO_FIXTURE" ? (
        <Card>
          <Text style={s.eyebrow}>DEMO FIXTURE · NOT LIVE OPERATIONS</Text>
          <Text style={s.caption}>
            The backend is serving explicitly labeled fallback data.
          </Text>
        </Card>
      ) : null}
      <QueryState query={query}>
        {risk ? (
          <Card>
            <Text style={s.eyebrow}>CURRENT FLOOD RISK</Text>
            <View style={s.between}>
              <RiskBadge level={risk.risk_level} />
              <Text style={s.score}>
                {risk.risk_score == null
                  ? "—"
                  : `${Math.round(risk.risk_score * 100)}%`}
              </Text>
            </View>
            <Text style={s.body}>
              {risk.summary ?? "Risk explanation is unavailable."}
            </Text>
            <Text style={s.caption}>
              Data quality:{" "}
              {risk.is_fallback ? "Fallback / provisional" : "Verified feed"} ·
              Model confidence:{" "}
              {risk.confidence == null
                ? "Unavailable"
                : `${Math.round(risk.confidence * 100)}%`}
            </Text>
          </Card>
        ) : null}
        <Card
          title="Rainfall outlook"
          onPress={() => router.push("/(citizen)/rainfall")}
        >
          <View style={s.metrics}>
            {[30, 60, 90, 120].map((m) => {
              const item = home?.rainfall_outlook?.find(
                (x) => x.lead_time_minutes === m,
              );
              return (
                <Metric
                  key={m}
                  label={`+${m} min`}
                  value={item?.rainfall_rate_mm_h ?? "—"}
                  suffix={item?.rainfall_rate_mm_h == null ? "" : " mm/h"}
                />
              );
            })}
          </View>
        </Card>
        <View style={s.grid}>
          <Quick
            icon={<Bell />}
            label="Active alerts"
            value={home?.active_alerts?.length ?? 0}
            onPress={() => router.push("/(citizen)/(tabs)/alerts")}
          />
          <Quick
            icon={<Navigation />}
            label="Nearby incidents"
            value={home?.nearby_incidents?.length ?? 0}
            onPress={() => router.push("/(citizen)/incidents")}
          />
          <Quick
            icon={<MapPin />}
            label="Saved places"
            value={home?.watched_locations?.length ?? 0}
            onPress={() => router.push("/(citizen)/watch-locations")}
          />
          <Quick
            icon={<Camera />}
            label="Report flooding"
            value="Open"
            onPress={() => router.push("/(citizen)/(tabs)/report")}
          />
        </View>
        <Button
          label="Report Flood / Waterlogging"
          onPress={() => router.push("/(citizen)/(tabs)/report")}
        />
        <Button
          secondary
          label="View Live Risk Map"
          onPress={() => router.push("/(citizen)/(tabs)/map")}
        />
      </QueryState>
    </Screen>
  );
}
function Quick({
  icon,
  label,
  value: v,
  onPress,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={s.quick}>
      <View style={s.icon}>{icon}</View>
      <Text style={s.quickValue}>{v}</Text>
      <Text style={s.caption}>{label}</Text>
    </Pressable>
  );
}
export function RiskMapScreen() {
  const query = useQuery({
    queryKey: ["risk-map"],
    queryFn: () => mapApi.risk(),
  });
  const [layer, setLayer] = useState("Risk");
  return (
    <Screen
      title="Live risk map"
      subtitle="Mobile-safe layers for the Mumbai pilot"
    >
      <View style={s.pills}>
        {["Risk", "Incidents", "Reports", "Alerts"].map((x) => (
          <Pressable
            key={x}
            onPress={() => setLayer(x)}
            style={[s.pill, layer === x && s.pillActive]}
          >
            <Text style={layer === x ? s.pillTextActive : s.caption}>{x}</Text>
          </Pressable>
        ))}
      </View>
      <QueryState query={query}>
        <View style={s.mapPlaceholder}>
          <MapPin color={colors.teal} size={38} />
          <Text style={s.mapTitle}>Canonical Mumbai map</Text>
          <Text style={s.caption}>
            Risk geometry is loaded from `/api/v1/map/risk`. Native map
            rendering requires a development build; no unverified raster values
            are synthesized.
          </Text>
        </View>
        <Card title="Map legend">
          <View style={s.legend}>
            {["LOW", "MODERATE", "HIGH", "SEVERE"].map((x) => (
              <RiskBadge key={x} level={x} />
            ))}
          </View>
        </Card>
        <Card title="Selected area">
          <Text style={s.body}>
            Tap a supported native map cell to view risk, rainfall, alerts and
            update freshness.
          </Text>
          <StatusBadge
            value={`${String((query.data as ApiRecord)?.features ? ((query.data as ApiRecord).features as unknown[]).length : 0)} cells returned`}
          />
        </Card>
      </QueryState>
    </Screen>
  );
}
export function RainfallScreen() {
  const query = useQuery({
    queryKey: ["mobile-home"],
    queryFn: () => mobileApi.home(),
  });
  return (
    <Screen
      title="Rain forecast"
      subtitle="Observed and aligned forecast rates in mm/h"
    >
      <QueryState query={query} empty={!query.data?.rainfall_outlook?.length}>
        {query.data?.rainfall_outlook?.map((x) => (
          <Card key={x.lead_time_minutes}>
            <View style={s.between}>
              <View>
                <Text style={s.eyebrow}>+{x.lead_time_minutes} MINUTES</Text>
                <Text style={s.rain}>
                  {x.rainfall_rate_mm_h ?? "—"} <Text style={s.unit}>mm/h</Text>
                </Text>
              </View>
              <CloudRain color={colors.blue} size={30} />
            </View>
            <Text style={s.body}>
              {x.category ?? "Condition unavailable"} ·{" "}
              {x.trend ?? "trend unavailable"}
            </Text>
            <Text style={s.caption}>
              Model confidence:{" "}
              {x.confidence == null
                ? "Not provided by backend"
                : `${Math.round(x.confidence * 100)}%`}
            </Text>
          </Card>
        ))}
      </QueryState>
      <Card>
        <Text style={s.caption}>
          Data quality and model confidence are separate. Thirty-minute
          alignment does not create new temporal information in coarser GFS
          guidance.
        </Text>
      </Card>
    </Screen>
  );
}
export function FloodRiskScreen() {
  const query = useQuery({
    queryKey: ["mobile-home"],
    queryFn: () => mobileApi.home(),
  });
  const risk = query.data?.current_risk;
  return (
    <Screen
      title="Flood risk"
      subtitle="Decision support, not measured water depth"
    >
      <QueryState query={query}>
        {risk ? (
          <Card>
            <RiskBadge level={risk.risk_level} />
            <Text style={s.big}>
              {risk.summary ?? "No explanation supplied."}
            </Text>
            <Text style={s.body}>
              Avoid low-lying roads, follow authority alerts, and move to higher
              ground when instructed.
            </Text>
          </Card>
        ) : null}
        <Unavailable
          title="Exact water depth unavailable"
          detail="The operational backend does not return calibrated flood depth for this view. Susceptibility is not measured inundation depth, and photo evidence cannot determine exact depth."
        />
      </QueryState>
    </Screen>
  );
}
export function AlertsScreen() {
  const router = useRouter();
  const q = useQuery({ queryKey: ["alerts"], queryFn: alertsApi.list });
  const [tab, setTab] = useState("Active");
  return (
    <Screen
      title="Alerts"
      subtitle="Published public safety notices"
      scroll={false}
    >
      <View style={s.pills}>
        {["Active", "Recent", "Expired"].map((x) => (
          <Pressable
            key={x}
            onPress={() => setTab(x)}
            style={[s.pill, tab === x && s.pillActive]}
          >
            <Text style={tab === x ? s.pillTextActive : s.caption}>{x}</Text>
          </Pressable>
        ))}
      </View>
      <QueryState query={q} empty={!q.data?.length}>
        <FlatList
          data={q.data ?? []}
          keyExtractor={recordId}
          contentContainerStyle={{ gap: 10, paddingBottom: 90 }}
          renderItem={({ item }) => (
            <RecordCard
              kind="Alert"
              item={item}
              onPress={() => router.push(`/(citizen)/alerts/${recordId(item)}`)}
            />
          )}
        />
      </QueryState>
    </Screen>
  );
}
export function AlertDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const q = useQuery({
    queryKey: ["alert", id],
    queryFn: () => alertsApi.detail(id),
    enabled: Boolean(id),
  });
  const a = q.data;
  return (
    <Screen title="Alert detail" subtitle="Authority-issued safety information">
      <QueryState query={q}>
        {a ? (
          <>
            <Card>
              <RiskBadge
                level={String(value(a, "severity") ?? "UNKNOWN").toUpperCase()}
              />
              <Text style={s.big}>
                {String(value(a, "headline", "title") ?? "Alert")}
              </Text>
              <Text style={s.body}>
                {String(
                  value(a, "description", "message") ??
                    "No additional message provided.",
                )}
              </Text>
              <StatusBadge value={value(a, "status")} />
            </Card>
            <Card title="What to do">
              <Text style={s.body}>
                {String(
                  value(a, "instruction", "recommended_action") ??
                    "Follow local authority instructions and avoid low-lying roads.",
                )}
              </Text>
            </Card>
            <Card title="Area and timing">
              <Text style={s.body}>
                {String(
                  value(a, "area_description", "ward_id") ??
                    "Affected area unavailable",
                )}
              </Text>
              <Text style={s.caption}>
                Issued:{" "}
                {String(value(a, "sent_at", "created_at") ?? "Unavailable")} ·
                Expires: {String(value(a, "expires_at") ?? "Unavailable")}
              </Text>
            </Card>
          </>
        ) : null}
      </QueryState>
    </Screen>
  );
}
export function IncidentsScreen() {
  const router = useRouter();
  const q = useQuery({ queryKey: ["incidents"], queryFn: incidentsApi.list });
  return (
    <Screen
      title="Nearby incidents"
      subtitle="Public-safe operational updates"
      scroll={false}
    >
      <QueryState query={q} empty={!q.data?.length}>
        <FlatList
          data={q.data ?? []}
          keyExtractor={recordId}
          contentContainerStyle={{ gap: 10, paddingBottom: 30 }}
          renderItem={({ item }) => (
            <RecordCard
              kind="Incident"
              item={item}
              onPress={() =>
                router.push(`/(citizen)/incidents/${recordId(item)}`)
              }
            />
          )}
        />
      </QueryState>
    </Screen>
  );
}
export function IncidentDetailScreen({
  responder = false,
}: {
  responder?: boolean;
}) {
  const { id } = useLocalSearchParams<{ id: string }>();
  const q = useQuery({
    queryKey: ["incident", id],
    queryFn: () => incidentsApi.detail(id),
    enabled: Boolean(id),
  });
  const a = q.data;
  return (
    <Screen
      title={responder ? "Operational incident" : "Incident detail"}
      subtitle={
        responder
          ? "Responder-authorized context"
          : "Public-safe information only"
      }
    >
      <QueryState query={q}>
        {a ? (
          <>
            <RecordCard item={a} kind="Incident" />
            <Card title="Location">
              <Text style={s.body}>
                {String(
                  value(a, "ward_id", "area_description", "location") ??
                    "Location details unavailable",
                )}
              </Text>
            </Card>
            <Card title="Timeline">
              <Text style={s.body}>
                {Array.isArray(a.timeline) && a.timeline.length
                  ? `${a.timeline.length} public update(s)`
                  : "No public timeline updates."}
              </Text>
            </Card>
            {responder ? (
              <Card title="Linked operational evidence">
                <Text style={s.body}>
                  Only evidence returned by responder-authorized backend
                  responses is shown.
                </Text>
              </Card>
            ) : null}
          </>
        ) : null}
      </QueryState>
    </Screen>
  );
}
export function WatchLocationsScreen() {
  const router = useRouter();
  const q = useQuery({ queryKey: ["watch"], queryFn: watchApi.list });
  return (
    <Screen
      title="Saved locations"
      subtitle="Places you want JalRakshak to watch"
    >
      <Button
        label="Add a location"
        onPress={() => router.push("/(citizen)/watch-locations/edit")}
      />
      <QueryState query={q} empty={!q.data?.length}>
        {q.data?.map((i) => (
          <RecordCard
            key={recordId(i)}
            kind="Watch location"
            item={i}
            onPress={() =>
              router.push({
                pathname: "/(citizen)/watch-locations/edit",
                params: { id: recordId(i) },
              })
            }
          />
        ))}
      </QueryState>
    </Screen>
  );
}
export function WatchEditorScreen() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const router = useRouter();
  const [label, setLabel] = useState("Home");
  const [lat, setLat] = useState("19.0760");
  const [lon, setLon] = useState("72.8777");
  const [notify, setNotify] = useState(true);
  const [message, setMessage] = useState("");
  async function save() {
    try {
      const body = {
        label,
        latitude: Number(lat),
        longitude: Number(lon),
        risk_threshold: "HIGH",
        notify_push: notify,
      };
      if (id) await watchApi.update(id, body);
      else await watchApi.create(body);
      router.back();
    } catch (e) {
      setMessage((e as Error).message);
    }
  }
  return (
    <Screen
      title={id ? "Edit location" : "Add location"}
      subtitle="No address is fabricated when geocoding is unavailable"
    >
      <TextInput
        style={s.input}
        value={label}
        onChangeText={setLabel}
        placeholder="Name"
      />
      <TextInput
        style={s.input}
        value={lat}
        onChangeText={setLat}
        keyboardType="decimal-pad"
        placeholder="Latitude"
      />
      <TextInput
        style={s.input}
        value={lon}
        onChangeText={setLon}
        keyboardType="decimal-pad"
        placeholder="Longitude"
      />
      <View style={s.between}>
        <Text style={s.body}>Push when risk reaches HIGH</Text>
        <Switch value={notify} onValueChange={setNotify} />
      </View>
      {message ? <Text style={s.error}>{message}</Text> : null}
      <Button
        label="Use current location"
        secondary
        onPress={() =>
          void requestCurrentLocation().then((p) => {
            if (p) {
              setLat(String(p.latitude));
              setLon(String(p.longitude));
            }
          })
        }
      />
      <Button label="Save location" onPress={() => void save()} />
    </Screen>
  );
}
export function ProfileScreen() {
  const router = useRouter();
  const session = useSession((s) => s.session);
  return (
    <Screen title="Profile" subtitle="Identity supplied by the backend session">
      <Card>
        <View style={s.avatar}>
          <ShieldCheck color="#fff" />
        </View>
        <Text style={s.big}>{session?.email ?? session?.userId}</Text>
        <StatusBadge value={session?.role} />
      </Card>
      <Button
        label="Saved locations"
        secondary
        onPress={() => router.push("/(citizen)/watch-locations")}
      />
      <Button
        label="Settings"
        secondary
        onPress={() => router.push("/(citizen)/settings")}
      />
    </Screen>
  );
}
export function SettingsScreen() {
  const router = useRouter();
  const signOut = useSession((s) => s.signOut);
  return (
    <Screen title="Settings" subtitle="Privacy, permissions and account">
      <Card title="Data freshness">
        <Text style={s.body}>
          Live screens show backend timestamps and explicit degraded states.
        </Text>
      </Card>
      <Button
        label="Notification preferences"
        secondary
        onPress={() => router.push("/(citizen)/notification-preferences")}
      />
      <Button
        label="App permissions"
        secondary
        onPress={() => router.push("/(citizen)/onboarding")}
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
export function NotificationPreferencesScreen() {
  const session = useSession((s) => s.session);
  const [enabled, setEnabled] = useState(false);
  const [message, setMessage] = useState(
    "Preferences persistence endpoint is not available; this device setting is not synced.",
  );
  async function allow() {
    if (!session) return;
    const result = await registerPush(session.userId);
    setEnabled(result.configured);
    setMessage(
      result.configured
        ? "This device is registered for push."
        : (result.reason ?? "Push unavailable."),
    );
  }
  return (
    <Screen
      title="Notifications"
      subtitle="Permission is requested only when you opt in"
    >
      <Card>
        <View style={s.between}>
          <Text style={s.body}>Important safety notifications</Text>
          <Switch value={enabled} onValueChange={() => void allow()} />
        </View>
        <Text style={s.caption}>{message}</Text>
      </Card>
      {[
        "Risk warning",
        "Alert published",
        "Alert updated",
        "Alert cancelled",
        "Incident update",
        "Report status",
        "System notice",
      ].map((x) => (
        <Card key={x}>
          <Text style={s.body}>{x}</Text>
          <StatusBadge value="Backend preference persistence unavailable" />
        </Card>
      ))}
    </Screen>
  );
}
export function OnboardingScreen() {
  const router = useRouter();
  return (
    <Screen
      title="Your permissions, your choice"
      subtitle="JalRakshak requests access only when a feature needs it."
    >
      <Permission
        icon={<MapPin />}
        title="Location"
        text="Shows risk near you and attaches a report location."
      />
      <Permission
        icon={<Bell />}
        title="Notifications"
        text="Delivers authority-published warnings when configured."
      />
      <Permission
        icon={<Camera />}
        title="Camera & gallery"
        text="Requested only when you choose to add report evidence."
      />
      <Button
        label="Continue"
        onPress={() => router.replace("/(citizen)/(tabs)/home")}
      />
      <Button
        secondary
        label="Not now"
        onPress={() => router.replace("/(citizen)/(tabs)/home")}
      />
    </Screen>
  );
}
function Permission({
  icon,
  title,
  text,
}: {
  icon: React.ReactNode;
  title: string;
  text: string;
}) {
  return (
    <Card>
      <View style={s.permission}>
        {icon}
        <View style={{ flex: 1 }}>
          <Text style={s.big}>{title}</Text>
          <Text style={s.caption}>{text}</Text>
        </View>
      </View>
    </Card>
  );
}
export function NotificationsHistoryScreen() {
  return <AlertsScreen />;
}
const s = StyleSheet.create({
  eyebrow: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 1,
  },
  body: { color: colors.ink, fontSize: 14, lineHeight: 21 },
  caption: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  score: { fontWeight: "800", fontSize: 18, color: colors.ink },
  between: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  metrics: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  quick: {
    width: "48%",
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 16,
    padding: 14,
    gap: 5,
  },
  icon: {
    width: 36,
    height: 36,
    borderRadius: 12,
    backgroundColor: colors.aqua,
    alignItems: "center",
    justifyContent: "center",
  },
  quickValue: { fontSize: 19, fontWeight: "800", color: colors.ink },
  pills: { flexDirection: "row", gap: 7, flexWrap: "wrap" },
  pill: {
    paddingHorizontal: 13,
    paddingVertical: 8,
    borderRadius: 99,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.line,
  },
  pillActive: { backgroundColor: colors.teal, borderColor: colors.teal },
  pillTextActive: { color: "#fff", fontWeight: "700", fontSize: 12 },
  mapPlaceholder: {
    height: 280,
    borderRadius: 20,
    backgroundColor: "#E7F3EF",
    borderWidth: 1,
    borderColor: colors.line,
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    padding: 28,
  },
  mapTitle: { color: colors.ink, fontSize: 18, fontWeight: "800" },
  legend: { flexDirection: "row", gap: 7, flexWrap: "wrap" },
  rain: { color: colors.ink, fontSize: 30, fontWeight: "800" },
  unit: { fontSize: 14, color: colors.muted },
  big: { color: colors.ink, fontWeight: "800", fontSize: 18, lineHeight: 24 },
  input: {
    minHeight: 50,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surface,
    paddingHorizontal: 14,
    color: colors.ink,
  },
  error: { color: colors.severe },
  avatar: {
    width: 54,
    height: 54,
    borderRadius: 18,
    backgroundColor: colors.teal,
    alignItems: "center",
    justifyContent: "center",
  },
  permission: { flexDirection: "row", gap: 14, alignItems: "center" },
});
