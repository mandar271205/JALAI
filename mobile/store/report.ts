import { create } from "zustand";
import type { EvidenceAsset } from "@/lib/reports/workflow";

export const useReportDraft = create<{
  evidence: EvidenceAsset | null;
  setEvidence: (value: EvidenceAsset | null) => void;
}>((set) => ({ evidence: null, setEvidence: (evidence) => set({ evidence }) }));
