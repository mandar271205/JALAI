import * as Crypto from "expo-crypto";
import * as FileSystem from "expo-file-system/legacy";
import { reportsApi, uploadBinary } from "@/lib/api";
export type EvidenceAsset = {
  uri: string;
  fileName?: string | null;
  mimeType?: string | null;
  fileSize?: number;
};
export async function submitSignedReport(input: {
  category: string;
  severity: string;
  description: string;
  latitude: number;
  longitude: number;
  evidence?: EvidenceAsset;
  onProgress?: (v: number) => void;
}) {
  const draft = await reportsApi.draft({
    category: input.category,
    severity: input.severity,
    description: input.description,
    latitude: input.latitude,
    longitude: input.longitude,
  });
  const reportId = String(draft.report_id);
  if (!input.evidence) return { reportId, draft, submitted: false };
  const evidence = input.evidence;
  const info = await FileSystem.getInfoAsync(evidence.uri);
  const size =
    evidence.fileSize ?? (info.exists && "size" in info ? info.size : 0);
  const contentType = evidence.mimeType ?? "image/jpeg";
  if (!["image/jpeg", "image/png", "image/webp"].includes(contentType))
    throw new Error("Choose a JPEG, PNG, or WebP image.");
  if (!size || size > 10_485_760)
    throw new Error("Image must be between 1 byte and 10 MB.");
  const intent = await reportsApi.intent(reportId, {
    filename: evidence.fileName ?? `evidence-${Date.now()}.jpg`,
    content_type: contentType,
    file_size_bytes: size,
  });
  const bytes = new Uint8Array(await (await fetch(evidence.uri)).arrayBuffer());
  const digest = await Crypto.digest(
    Crypto.CryptoDigestAlgorithm.SHA256,
    bytes,
  );
  const checksum = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  await uploadBinary(
    String(intent.presigned_url),
    evidence.uri,
    contentType,
    input.onProgress,
  );
  const complete = await reportsApi.complete(reportId, {
    upload_id: intent.upload_id,
    sha256_checksum: checksum,
    content_type: contentType,
  });
  return { reportId, draft, complete, submitted: true };
}
