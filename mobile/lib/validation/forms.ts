import { z } from "zod";
export const loginSchema = z.object({
  identifier: z.string().min(2, "Enter your email or identifier"),
  password: z.string().min(4, "Password must contain at least 4 characters"),
  role: z.enum(["CITIZEN", "FIELD_RESPONDER"]),
});
export const reportSchema = z.object({
  category: z.enum([
    "FLOODING",
    "WATERLOGGING",
    "DRAIN_OVERFLOW",
    "ROAD_BLOCKAGE",
    "OTHER",
  ]),
  severity: z.enum(["LOW", "MODERATE", "HIGH", "SEVERE"]),
  description: z.string().min(8).max(1000),
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
});
export const watchSchema = z.object({
  label: z.string().min(2).max(60),
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
  risk_threshold: z.enum(["LOW", "MODERATE", "HIGH", "SEVERE"]),
  notify_push: z.boolean(),
});
