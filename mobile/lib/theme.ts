export const colors = {
  ink: "#123047",
  muted: "#607789",
  canvas: "#F4FAFC",
  surface: "#FFFFFF",
  line: "#DCEBF0",
  blue: "#1677A8",
  teal: "#087E78",
  aqua: "#DFF5F3",
  low: "#2E8B57",
  moderate: "#B7791F",
  high: "#D65A1F",
  severe: "#C53030",
  dangerSoft: "#FFF1F0",
} as const;
export const riskColor = (value?: string) =>
  ({
    LOW: colors.low,
    MODERATE: colors.moderate,
    HIGH: colors.high,
    SEVERE: colors.severe,
  })[String(value).toUpperCase()] ?? colors.muted;
