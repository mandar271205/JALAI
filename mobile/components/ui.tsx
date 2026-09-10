import type { PropsWithChildren, ReactNode } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { WifiOff, RefreshCw, ChevronRight } from "lucide-react-native";
import { colors, riskColor } from "@/lib/theme";

export function Screen({
  children,
  title,
  subtitle,
  scroll = true,
}: PropsWithChildren<{ title: string; subtitle?: string; scroll?: boolean }>) {
  const body = (
    <View style={s.content}>
      <View style={s.heading}>
        <Text accessibilityRole="header" style={s.title}>
          {title}
        </Text>
        {subtitle ? <Text style={s.subtitle}>{subtitle}</Text> : null}
      </View>
      {children}
    </View>
  );
  return (
    <SafeAreaView style={s.safe} edges={["top"]}>
      {scroll ? (
        <ScrollView
          contentContainerStyle={s.scroll}
          keyboardShouldPersistTaps="handled"
        >
          {body}
        </ScrollView>
      ) : (
        body
      )}
    </SafeAreaView>
  );
}
export function Card({
  children,
  title,
  onPress,
}: PropsWithChildren<{ title?: string; onPress?: () => void }>) {
  const content = (
    <View style={s.card}>
      {title ? <Text style={s.cardTitle}>{title}</Text> : null}
      {children}
      {onPress ? (
        <ChevronRight size={18} color={colors.muted} style={s.chevron} />
      ) : null}
    </View>
  );
  return onPress ? (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => pressed && s.pressed}
    >
      {content}
    </Pressable>
  ) : (
    content
  );
}
export function RiskBadge({ level = "UNKNOWN" }: { level?: string }) {
  return (
    <View
      accessibilityLabel={`Risk ${level}`}
      style={[s.badge, { backgroundColor: `${riskColor(level)}18` }]}
    >
      <View style={[s.dot, { backgroundColor: riskColor(level) }]} />
      <Text style={[s.badgeText, { color: riskColor(level) }]}>{level}</Text>
    </View>
  );
}
export function StatusBadge({ value }: { value?: unknown }) {
  const label = String(value ?? "UNKNOWN").replaceAll("_", " ");
  return (
    <View style={s.status}>
      <Text style={s.statusText}>{label}</Text>
    </View>
  );
}
export function Button({
  label,
  onPress,
  secondary = false,
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  secondary?: boolean;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        s.button,
        secondary && s.buttonSecondary,
        disabled && s.disabled,
        pressed && s.pressed,
      ]}
    >
      <Text style={[s.buttonText, secondary && s.buttonTextSecondary]}>
        {label}
      </Text>
    </Pressable>
  );
}
export function FieldLabel({ children }: PropsWithChildren) {
  return <Text style={s.fieldLabel}>{children}</Text>;
}
export function StateView({
  state,
  message,
  onRetry,
}: {
  state: "loading" | "empty" | "error" | "degraded";
  message?: string;
  onRetry?: () => void;
}) {
  const text =
    message ??
    {
      loading: "Loading verified information…",
      empty: "Nothing to show right now.",
      error: "Unable to load this information.",
      degraded:
        "Live update unavailable. Showing the latest saved information.",
    }[state];
  return (
    <View style={s.state}>
      {state === "loading" ? (
        <ActivityIndicator color={colors.teal} />
      ) : state === "degraded" ? (
        <WifiOff color={colors.moderate} />
      ) : null}
      <Text style={s.stateTitle}>{text}</Text>
      {onRetry ? (
        <Pressable onPress={onRetry} style={s.retry}>
          <RefreshCw size={16} color={colors.teal} />
          <Text style={s.retryText}>Retry</Text>
        </Pressable>
      ) : null}
    </View>
  );
}
export function Metric({
  label,
  value,
  suffix,
}: {
  label: string;
  value: ReactNode;
  suffix?: string;
}) {
  return (
    <View style={s.metric}>
      <Text style={s.metricLabel}>{label}</Text>
      <Text style={s.metricValue}>
        {value}
        {suffix}
      </Text>
    </View>
  );
}
export function OfflineBanner({ pending = 0 }: { pending?: number }) {
  return (
    <View style={s.offline}>
      <WifiOff size={16} color={colors.moderate} />
      <Text style={s.offlineText}>
        Offline · showing last synced data
        {pending ? ` · ${pending} waiting` : ""}
      </Text>
    </View>
  );
}
export function Unavailable({
  title,
  detail,
}: {
  title: string;
  detail: string;
}) {
  return (
    <Card>
      <Text style={s.cardTitle}>{title}</Text>
      <Text style={s.subtitle}>{detail}</Text>
    </Card>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.canvas },
  scroll: { paddingBottom: 36 },
  content: { flex: 1, gap: 14, padding: 18 },
  heading: { marginBottom: 4 },
  title: {
    color: colors.ink,
    fontSize: 28,
    lineHeight: 34,
    fontWeight: "800",
    letterSpacing: -0.5,
  },
  subtitle: { color: colors.muted, fontSize: 14, lineHeight: 21, marginTop: 5 },
  card: {
    position: "relative",
    backgroundColor: colors.surface,
    borderColor: colors.line,
    borderWidth: 1,
    borderRadius: 18,
    padding: 16,
    gap: 8,
    shadowColor: "#173B4F",
    shadowOpacity: 0.06,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
  },
  cardTitle: { color: colors.ink, fontSize: 16, fontWeight: "700" },
  chevron: { position: "absolute", right: 14, top: 16 },
  pressed: { opacity: 0.72 },
  badge: {
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
  badgeText: { fontWeight: "800", fontSize: 12 },
  status: {
    alignSelf: "flex-start",
    backgroundColor: colors.aqua,
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  statusText: { color: colors.teal, fontSize: 11, fontWeight: "700" },
  button: {
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 14,
    paddingHorizontal: 18,
    backgroundColor: colors.teal,
  },
  buttonSecondary: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.teal,
  },
  buttonText: { color: "#fff", fontSize: 15, fontWeight: "700" },
  buttonTextSecondary: { color: colors.teal },
  disabled: { opacity: 0.45 },
  fieldLabel: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "700",
    marginBottom: -6,
  },
  state: {
    minHeight: 150,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    backgroundColor: colors.surface,
    borderRadius: 18,
    borderColor: colors.line,
    borderWidth: 1,
    padding: 22,
  },
  stateTitle: { color: colors.muted, textAlign: "center", lineHeight: 21 },
  retry: { flexDirection: "row", gap: 7, alignItems: "center" },
  retryText: { color: colors.teal, fontWeight: "700" },
  metric: {
    flex: 1,
    minWidth: 92,
    padding: 12,
    backgroundColor: colors.canvas,
    borderRadius: 12,
  },
  metricLabel: { color: colors.muted, fontSize: 11, fontWeight: "600" },
  metricValue: {
    color: colors.ink,
    fontSize: 19,
    fontWeight: "800",
    marginTop: 3,
  },
  offline: {
    flexDirection: "row",
    gap: 8,
    alignItems: "center",
    padding: 10,
    borderRadius: 12,
    backgroundColor: "#FFF8E7",
  },
  offlineText: { color: colors.moderate, fontWeight: "700", fontSize: 12 },
});
