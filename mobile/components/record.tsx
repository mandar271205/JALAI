import { StyleSheet, Text, View } from "react-native";
import type { ApiRecord } from "@/types";
import { colors } from "@/lib/theme";
import { Card, RiskBadge, StatusBadge } from "./ui";
const text = (item: ApiRecord, ...keys: string[]) =>
  keys
    .map((k) => item[k])
    .find((v) => typeof v === "string" || typeof v === "number");
export const recordId = (item: ApiRecord) =>
  String(
    text(
      item,
      "alert_id",
      "incident_id",
      "report_id",
      "task_id",
      "location_id",
      "id",
    ) ?? "unknown",
  );
export function RecordCard({
  item,
  onPress,
  kind,
}: {
  item: ApiRecord;
  onPress?: () => void;
  kind: string;
}) {
  const title = String(
    text(
      item,
      "headline",
      "title",
      "label",
      "task_type",
      "category",
      "description",
    ) ?? kind,
  );
  const meta = text(
    item,
    "area_description",
    "ward_id",
    "location",
    "instructions",
    "created_at",
    "assigned_at",
  );
  const risk = text(item, "severity", "risk_level", "priority");
  return (
    <Card onPress={onPress}>
      <View style={s.top}>
        <Text numberOfLines={2} style={s.title}>
          {title}
        </Text>
        {risk ? <RiskBadge level={String(risk).toUpperCase()} /> : null}
      </View>
      {meta ? (
        <Text numberOfLines={2} style={s.meta}>
          {String(meta)}
        </Text>
      ) : null}
      {item.status || item.verification_status ? (
        <StatusBadge value={item.status ?? item.verification_status} />
      ) : null}
    </Card>
  );
}
const s = StyleSheet.create({
  top: { gap: 10, paddingRight: 18 },
  title: { color: colors.ink, fontWeight: "700", fontSize: 16 },
  meta: { color: colors.muted, fontSize: 13, lineHeight: 19 },
});
