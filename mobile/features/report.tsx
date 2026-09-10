import { useState } from "react";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import * as ImagePicker from "expo-image-picker";
import { CameraView, useCameraPermissions } from "expo-camera";
import {
  Image,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { ShieldCheck } from "lucide-react-native";
import { Button, Card, Screen, StateView, StatusBadge } from "@/components/ui";
import { colors } from "@/lib/theme";
import { requestCurrentLocation } from "@/lib/location/current";
import { reportsApi } from "@/lib/api";
import { submitSignedReport, type EvidenceAsset } from "@/lib/reports/workflow";
import { QueryState } from "@/components/query-state";
import type { ApiRecord } from "@/types";
import { useReportDraft } from "@/store/report";

const categories = [
  "FLOODING",
  "WATERLOGGING",
  "DRAIN_OVERFLOW",
  "ROAD_BLOCKAGE",
  "OTHER",
];
const severities = ["LOW", "MODERATE", "HIGH", "SEVERE"];
export function ReportScreen() {
  const router = useRouter();
  const [category, setCategory] = useState("WATERLOGGING");
  const [severity, setSeverity] = useState("MODERATE");
  const [description, setDescription] = useState("");
  const [location, setLocation] = useState<{
    latitude: number;
    longitude: number;
  } | null>(null);
  const evidence = useReportDraft((state) => state.evidence);
  const setEvidence = useReportDraft((state) => state.setEvidence);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit() {
    if (description.trim().length < 8) {
      setError("Describe what you can see in at least 8 characters.");
      return;
    }
    if (!location) {
      setError("Confirm a report location before submitting.");
      return;
    }
    try {
      setBusy(true);
      setError("");
      const result = await submitSignedReport({
        category,
        severity,
        description,
        ...location,
        evidence: evidence ?? undefined,
        onProgress: setProgress,
      });
      router.push({
        pathname: "/(citizen)/reports/success",
        params: { id: result.reportId, submitted: String(result.submitted) },
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Screen
      title="Report flooding"
      subtitle="A report is not submitted until the backend confirms it"
    >
      <Card title="1 · What are you seeing?">
        <View style={s.wrap}>
          {categories.map((x) => (
            <Choice
              key={x}
              value={x}
              selected={category === x}
              onPress={() => setCategory(x)}
            />
          ))}
        </View>
      </Card>
      <Card title="2 · Observed severity">
        <View style={s.wrap}>
          {severities.map((x) => (
            <Choice
              key={x}
              value={x}
              selected={severity === x}
              onPress={() => setSeverity(x)}
            />
          ))}
        </View>
      </Card>
      <Card title="3 · Description">
        <TextInput
          accessibilityLabel="Report description"
          multiline
          value={description}
          onChangeText={setDescription}
          style={[s.input, { height: 110, textAlignVertical: "top" }]}
          placeholder="Water covering the road near…"
        />
      </Card>
      <Card title="4 · Location">
        {location ? (
          <Text style={s.body}>
            {location.latitude.toFixed(5)}, {location.longitude.toFixed(5)}
          </Text>
        ) : (
          <Text style={s.caption}>No GPS location selected.</Text>
        )}
        <Button
          secondary
          label="Use my current location"
          onPress={() =>
            void requestCurrentLocation().then((p) =>
              p
                ? setLocation(p)
                : setError("Location permission was not granted."),
            )
          }
        />
      </Card>
      <Card title="5 · Photo evidence">
        {evidence ? (
          <Image source={{ uri: evidence.uri }} style={s.preview} />
        ) : (
          <Text style={s.caption}>
            Optional supporting evidence. Exact depth is never inferred from a
            monocular photo.
          </Text>
        )}
        <View style={s.row}>
          <Button
            secondary
            label="Camera"
            onPress={() => router.push("/(citizen)/report-capture?mode=camera")}
          />
          <Button
            secondary
            label="Gallery"
            onPress={() =>
              void ImagePicker.requestMediaLibraryPermissionsAsync().then(
                async (p) => {
                  if (!p.granted) return;
                  const r = await ImagePicker.launchImageLibraryAsync({
                    mediaTypes: ["images"],
                    quality: 0.8,
                  });
                  if (!r.canceled) setEvidence(r.assets[0]);
                },
              )
            }
          />
        </View>
      </Card>
      {progress > 0 && progress < 1 ? (
        <Text style={s.caption}>Upload {Math.round(progress * 100)}%</Text>
      ) : null}
      {error ? <Text style={s.error}>{error}</Text> : null}
      <Button
        label={busy ? "Submitting…" : "Review & submit"}
        disabled={busy}
        onPress={() => void submit()}
      />
    </Screen>
  );
}
function Choice({
  value,
  selected,
  onPress,
}: {
  value: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={[s.choice, selected && s.selected]}>
      <Text style={selected ? s.selectedText : s.caption}>
        {value.replaceAll("_", " ")}
      </Text>
    </Pressable>
  );
}
export function CaptureScreen() {
  const router = useRouter();
  const [permission, request] = useCameraPermissions();
  const [ref, setRef] = useState<CameraView | null>(null);
  const [asset, setAsset] = useState<EvidenceAsset | null>(null);
  const setEvidence = useReportDraft((state) => state.setEvidence);
  if (!permission)
    return (
      <Screen title="Camera">
        <StateView state="loading" />
      </Screen>
    );
  if (!permission.granted)
    return (
      <Screen
        title="Camera permission"
        subtitle="Requested only because you chose to capture evidence"
      >
        <Button label="Allow camera" onPress={() => void request()} />
        <Button secondary label="Not now" onPress={() => router.back()} />
      </Screen>
    );
  async function capture() {
    const photo = await ref?.takePictureAsync({ quality: 0.8, exif: false });
    if (photo)
      setAsset({
        uri: photo.uri,
        fileName: `field-${Date.now()}.jpg`,
        mimeType: "image/jpeg",
      });
  }
  return (
    <Screen
      title="Evidence camera"
      subtitle="Visual evidence supports a report; it does not prove exact depth."
    >
      {asset ? (
        <>
          <Image source={{ uri: asset.uri }} style={s.camera} />
        <Button
          label="Use photo"
          onPress={() => {
            setEvidence(asset);
            router.back();
          }}
        />
          <Button secondary label="Retake" onPress={() => setAsset(null)} />
        </>
      ) : (
        <>
          <CameraView ref={setRef} style={s.camera} facing="back" />
          <Button label="Take photo" onPress={() => void capture()} />
        </>
      )}
    </Screen>
  );
}
export function ReportSuccessScreen() {
  const { id, submitted } = useLocalSearchParams<{
    id: string;
    submitted: string;
  }>();
  const router = useRouter();
  return (
    <Screen
      title={submitted === "true" ? "Report submitted" : "Draft saved"}
      subtitle={
        submitted === "true"
          ? "Your evidence upload was confirmed."
          : "This report is not submitted until its evidence upload completes."
      }
    >
      <Card>
        <View style={s.center}>
          <ShieldCheck color={colors.teal} size={48} />
          <Text style={s.big}>
            {submitted === "true" ? "Verification pending" : "Draft only"}
          </Text>
          <Text style={s.caption}>Report ID · {id}</Text>
          <Text style={s.body}>
            Your report is checked against location, weather and visual
            evidence. Submission does not guarantee an alert or incident.
          </Text>
        </View>
      </Card>
      <Button
        label="View status"
        onPress={() => router.replace(`/(citizen)/reports/${id}`)}
      />
      <Button
        secondary
        label="Back home"
        onPress={() => router.replace("/(citizen)/(tabs)/home")}
      />
    </Screen>
  );
}
export function ReportStatusScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const q = useQuery({
    queryKey: ["report", id],
    queryFn: () => reportsApi.detail(id),
    refetchInterval: 15_000,
    enabled: Boolean(id),
  });
  const x = q.data;
  return (
    <Screen title="Report status" subtitle="Backend verification state">
      <QueryState query={q}>
        {x ? (
          <>
            <Card>
              <StatusBadge value={x.verification_status ?? x.status} />
              <Text style={s.big}>Report {id}</Text>
              <Text style={s.caption}>
                Submitted{" "}
                {String(x.submitted_at ?? x.created_at ?? "time unavailable")}
              </Text>
            </Card>
            <Card title="Evidence review">
              <Row
                label="Water visible"
                value={nested(x, "visual_corroboration", "water_visible")}
              />
              <Row
                label="Road affected"
                value={nested(x, "visual_corroboration", "road_passability")}
              />
              <Row
                label="Image quality"
                value={nested(x, "visual_corroboration", "image_quality")}
              />
              <Row
                label="Evidence support"
                value={nested(
                  x,
                  "visual_corroboration",
                  "visual_support_score",
                )}
              />
              <Row label="Exact photo depth" value="Not available" />
            </Card>
            {x.incident_id ? (
              <Card title="Linked incident">
                <Text style={s.body}>{String(x.incident_id)}</Text>
              </Card>
            ) : null}
          </>
        ) : null}
      </QueryState>
    </Screen>
  );
}
function nested(x: ApiRecord, a: string, b: string) {
  const v = x[a];
  return typeof v === "object" && v
    ? String((v as ApiRecord)[b] ?? "Not available")
    : "Not available";
}
function Row({ label, value }: { label: string; value: unknown }) {
  return (
    <View style={s.between}>
      <Text style={s.caption}>{label}</Text>
      <Text style={s.body}>{String(value)}</Text>
    </View>
  );
}
const s = StyleSheet.create({
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  choice: {
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 99,
    borderWidth: 1,
    borderColor: colors.line,
  },
  selected: { backgroundColor: colors.teal, borderColor: colors.teal },
  selectedText: { color: "#fff", fontWeight: "700", fontSize: 12 },
  input: {
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 12,
    padding: 12,
    color: colors.ink,
  },
  body: { color: colors.ink, fontSize: 14, lineHeight: 21 },
  caption: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  error: { color: colors.severe, fontWeight: "700" },
  preview: { height: 180, borderRadius: 12, resizeMode: "cover" },
  row: { flexDirection: "row", gap: 8 },
  camera: { height: 420, borderRadius: 18, overflow: "hidden" },
  center: { alignItems: "center", gap: 12 },
  big: { color: colors.ink, fontWeight: "800", fontSize: 19 },
  between: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: 12,
    borderBottomWidth: 1,
    borderColor: colors.line,
    paddingVertical: 7,
  },
});
