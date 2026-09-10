# JalRakshak AI — 22-Route Web Command Center Implementation Matrix

Authoritative documentation of all 22 web routes implemented in `jalrakshak-ai/web/app/`, mapping each route to its backend API endpoints, WebSocket event channels, Role-Based Access Control (RBAC) tiers, and scientific validation constraints.

---

## 1. Complete 22-Route Mapping Table

| # | Route Path | Screen Title | Primary Backend Endpoints | Role Privileges | Realtime Channel | Scientific Gate / Safety Rule |
|---|---|---|---|---|---|---|
| 1 | `/login` | Authentication & Mock Portal | JWT / `X-Mock-Role` | PUBLIC | — | Allows instantaneous zero-friction role switching for evaluation. |
| 2 | `/command-center` | Multi-Agency Command Center | `GET /api/v1/dashboard/summary` | ANALYST+ | `telemetry.heartbeat`, `risk.cell.updated`, `alert.published` | Real-time KPI summaries; authoritative city hazard gauge. |
| 3 | `/map` | Live Situation Map | `GET /api/v1/map/{risk,incidents,reports,assets,alerts}` | Any Auth | `risk.cell.updated`, `incident.updated` | Vector & raster tile overlays (`/tiles/nowcast`, `/tiles/risk`); bounding box sync. |
| 4 | `/rainfall` | Rainfall Intelligence | `GET /api/v1/nowcast/manifest`, `GET /weather/current` | Any Auth | `model.run.completed` | Displays radar nowcasting without uncalibrated extrapolation. |
| 5 | `/flood` | Flood Susceptibility | `GET /api/v1/tiles/risk/{z}/{x}/{y}.png`, `/map/risk` | Any Auth | `risk.cell.updated` | STRICT: Never displays unverified water depth; displays risk classification. |
| 6 | `/risk` | H3 Dynamic Risk Grid | `GET /api/v1/risk/cells`, `GET /risk/{h3}/timeline` | Any Auth | `risk.cell.updated` | Hexagonal spatial indexing with 15-minute predictive risk vectors. |
| 7 | `/incidents` | Incident Command Queue | `GET, POST /api/v1/incidents` | Any Auth | `incident.created`, `incident.updated` | Live incident lifecycle tracking (OPEN $\rightarrow$ DETECTED $\rightarrow$ RESOLVED). |
| 8 | `/incidents/[id]` | Incident Tactical Workbench | `GET /api/v1/incidents/{id}`, `POST .../transition` | Any Auth | `incident.updated` | Transition state machine with mandatory justification audit notes. |
| 9 | `/reports` | Citizen Reports Queue | `GET /api/v1/reports`, `POST .../review` | Any Auth | `report.received`, `report.verified` | Corroboration verification; strictly isolates monocular photo evidence from numerical depth. |
| 10 | `/reports/[id]` | Report Detail & Moderation | `GET /api/v1/reports/{id}`, `POST .../review` | ANALYST+ | `report.verified` | Groq Vision corroboration score display; analyst manual verification actions. |
| 11 | `/assets` | Critical Infrastructure | `GET /api/v1/assets` | Any Auth | `risk.cell.updated` | Hospitals, substations, and shelters filtered by proximity danger index. |
| 12 | `/alerts` | Alert Dissemination Hub | `GET /api/v1/map/alerts`, `GET /alerts/{id}/cap.xml` | Any Auth | `alert.published` | Two-person authorization rule enforcement (ANALYST draft $\rightarrow$ APPROVER publish). |
| 13 | `/alerts/new` | Draft Emergency Alert | `POST /api/v1/alerts/draft` | ANALYST+ | — | CAP 1.2 syntax generation; minimum confidence score threshold $\ge 0.5$. |
| 14 | `/alerts/[id]` | CAP 1.2 XML Inspector | `GET /alerts/{id}/cap.xml`, `POST .../approve`, `/publish` | ALERT_APPROVER+ | `alert.published` | Live XML payload review, copy to clipboard, and instant broadcast fanout. |
| 15 | `/responders` | Field Responders & Tasks | `GET, POST /api/v1/responders/tasks`, `POST .../action` | DISPATCHER+ | `RESPONDER_LOCATION_UPDATE` | Dispatch tactical units; records physical ground-truth sensor water depth. |
| 16 | `/analytics` | Operational Analytics | Composed from `/dashboard/summary`, `/incidents`, `/reports` | Any Auth | — | Honest labeling: Dynamically aggregated metrics without synthetic fabrication. |
| 17 | `/explainability` | AI Explainability & SHAP | `GET /api/v1/risk/cells`, `GET /models/status` | Any Auth | — | Global feature attribution weights (radar 38%, DEM 26%, soil 21%, drain 15%). |
| 18 | `/sources` | Weather Feeds & Ingestion | `GET /api/v1/weather/current`, `GET /weather/sources/status` | Any Auth | `source.degraded` | Ingestion stream synchronization health (IMD Radar, NASA GPM, IoT gauges). |
| 19 | `/system` | ML Diagnostics & Health | `GET /api/v1/models/status`, `GET /models/health` | ADMIN / ANALYST | `model.run.completed` | Pipelined model latency telemetry, memory allocation, and database pooler health. |
| 20 | `/runs` | Provenance & Replay | `GET /api/v1/replay/manifest`, `POST /replay/sessions` | Any Auth | — | Deterministic time-series replay with variable playback speeds (1x-10x) and IoU/RMSE metrics. |
| 21 | `/audit` | Immutable Audit Ledger | `GET /api/v1/audit/logs` | DISASTER_MANAGER+ | — | Tamper-evident ledger tracking transitions, trace IDs, and actor signatures. |
| 22 | `/settings` | Command Preferences | Local Storage + `useAuthStore` | PUBLIC | — | Instantaneous role simulation switcher, audio siren preferences, 3D terrain tilt. |

---

## 2. Realtime WebSocket Architecture (`/api/v1/live`)

- **Protocol**: Native WebSocket connection with automatic exponential reconnect (1s $\rightarrow$ 30s).
- **Heartbeat**: Bi-directional ping/pong every 25 seconds.
- **Event Deduplication**: 5,000ms rolling deduplication window via message hashing.
- **Reactive Handlers**: All query hooks subscribe to specific event types and trigger TanStack Query cache invalidations automatically without page reloads.

---

## 3. Scientific Integrity & Claim Gates

1. **Monocular Water Depth Policy**: Under no circumstances will a citizen photograph produce a numerical `water_depth_cm` metric. Only physical IoT telemetry and calibrated hydrodynamic numerical simulations are permitted to claim depth.
2. **Alert Dissemination Rule**: Draft alerts cannot be published by the authoring analyst; an independent designated `ALERT_APPROVER` or `DISASTER_MANAGER` must review the CAP 1.2 XML payload.
3. **Derived Metrics Labeling**: Analytics derived from operational logs are explicitly stamped as **VERIFIED REPO AGGREGATION** to guarantee transparency.
