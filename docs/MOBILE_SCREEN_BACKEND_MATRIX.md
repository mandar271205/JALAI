# JalRakshak AI — Mobile Screen Backend Matrix (19 Screens)

---

## Overview

This matrix maps all 19 screens of the **JalRakshak Mobile Experience** (encompassing both Citizen and Field Responder user journeys) to their corresponding backend endpoints under `/api/v1`.

---

## Part A: Citizen Mobile App Screens (13 Screens)

| # | Screen Name | Route / View | Backend Endpoint(s) | Method | Auth Level | Offline Strategy |
|---|---|---|---|---|---|---|
| **01** | **Onboarding & Permissions** | `/onboarding` | `/api/v1/devices/push-token` | `POST` | Public / Token | Registers device push token with Expo/FCM |
| **02** | **Citizen Home (Single-Call Boot)** | `/home` | `/api/v1/mobile/home` | `GET` | `CITIZEN` | Renders cached state; displays offline badge if no network |
| **03** | **Interactive Flood & Risk Map** | `/map` | `/api/v1/map/risk`<br>`/api/v1/tiles/nowcast/{z}/{x}/{y}.png`<br>`/api/v1/tiles/risk/{z}/{x}/{y}.png` | `GET` | `CITIZEN` | Offline vector MBTiles / GeoJSON fallback cache |
| **04** | **Rainfall Outlook & Radar** | `/rainfall` | `/api/v1/nowcast/manifest`<br>`/api/v1/risk/timeseries` | `GET` | `CITIZEN` | Displays +30m, +60m, +90m, +120m cached projection |
| **05** | **Emergency Alerts Feed** | `/alerts` | `/api/v1/alerts`<br>`/api/v1/map/alerts` | `GET` | `CITIZEN` | Persistent local SQLite cache of emergency broadcasts |
| **06** | **Alert Detail & Action Steps** | `/alerts/:id` | `/api/v1/alerts/{id}` | `GET` | `CITIZEN` | Full instructions (evacuation zones, shelters) available offline |
| **07** | **Report Flood: Details & Location** | `/report/new` | `/api/v1/reports/draft` | `POST` | `CITIZEN` | Outbox queue if offline; assigns temporary local UUID |
| **08** | **Report Flood: Photo Upload** | `/report/upload` | `/api/v1/reports/{id}/uploads`<br>`PUT [presigned_url]` | `POST`, `PUT` | `CITIZEN` | Uploads binary direct to S3; retries automatically |
| **09** | **Report Flood: Status & Verification** | `/report/status/:id` | `/api/v1/reports/{id}/uploads/complete`<br>`/api/v1/reports/{id}/status` | `POST`, `GET` | `CITIZEN` | Displays Groq Vision status (`AI_VERIFIED`, `exact_depth_m: null`) |
| **10** | **My Submissions & History** | `/my-reports` | `/api/v1/reports?citizen_id={me}` | `GET` | `CITIZEN` | Reads local submissions store; syncs with server |
| **11** | **Safe Evacuation Navigator** | `/routes/safe` | `/api/v1/routes/elevation-aware` | `POST` | `CITIZEN` | Computes high-ground route avoiding severe inundation cells |
| **12** | **Family Safe Zones (Watch Locations)** | `/watch-locations` | `/api/v1/watch-locations`<br>`/api/v1/watch-locations/{id}` | `GET`, `POST`, `PATCH`, `DELETE` | `CITIZEN` | Local cache; alerts user when family zone exceeds risk threshold |
| **13** | **Emergency Contacts & Helplines** | `/helplines` | `/api/v1/assets/critical?category=emergency` | `GET` | `CITIZEN` | Bundled static directory of BMC / NDRF / Police helplines |

---

## Part B: Responder Mobile App Screens (6 Screens)

| # | Screen Name | Route / View | Backend Endpoint(s) | Method | Auth Level | Offline Strategy |
|---|---|---|---|---|---|---|
| **14** | **Responder Task Queue (Missions)** | `/responder/tasks` | `/api/v1/responders/available`<br>`/api/v1/incidents?status=OPEN` | `GET` | `RESPONDER` | Persistent cached dispatch queue with priority sorting |
| **15** | **Mission Navigation & Tactical Route** | `/responder/mission/:id`| `/api/v1/incidents/{id}`<br>`/api/v1/routes/elevation-aware` | `GET`, `POST` | `RESPONDER` | Offline turn-by-turn routing with topographic ridge preference |
| **16** | **Mission Execution & Status Updates** | `/responder/task/:id/update` | `/api/v1/responders/tasks/{id}/status`<br>`/api/v1/incidents/{id}/status` | `POST`, `PATCH` | `RESPONDER` | Outbox pattern (`EN_ROUTE`, `ON_SCENE`, `RESCUE_COMPLETED`) |
| **17** | **Field Verification & Citizen Corroboration** | `/responder/verify-reports` | `/api/v1/map/reports`<br>`/api/v1/reports/{id}/review` | `GET`, `POST` | `RESPONDER` | Responders on scene confirm or dismiss crowd reports |
| **18** | **Offline Queue & Sync Dashboard** | `/responder/sync` | `/api/v1/sync/mutations` | `POST` | `RESPONDER` | Displays pending outbound queue count and flushes batch |
| **19** | **Profile & Device Battery Saver** | `/responder/settings` | `/api/v1/devices/push-token/{id}`<br>`/api/v1/optimization/profile` | `DELETE`, `GET` | `RESPONDER` | Configures low-bandwidth GPS intervals and logs out |

---

## Core Operational Endpoints & Examples

### 1. Single-Call Home Aggregation
- `GET /api/v1/mobile/home?lat=19.0760&lon=72.8777`
- Aggregates location ward, current risk, 4-step rainfall projection (+30/+60/+90/+120 mins), top 5 active emergency alerts, and user watch locations in $<30\text{ms}$.

### 2. Direct Signed Media Upload
- Step 1: `POST /api/v1/reports/draft` $\rightarrow$ `report_id`
- Step 2: `POST /api/v1/reports/{report_id}/uploads` $\rightarrow$ `presigned_url` (15-min validity)
- Step 3: `PUT [presigned_url]` (direct binary upload to MinIO/S3)
- Step 4: `POST /api/v1/reports/{report_id}/uploads/complete` $\rightarrow$ triggers Groq Vision (`qwen/qwen3.8-27b`) analysis and dual-layer verification engine.

### 3. Elevation-Aware Safe Routing
- `POST /api/v1/routes/elevation-aware`
- Accepts origin and destination; returns safe path that actively penalizes submerged street segments.
