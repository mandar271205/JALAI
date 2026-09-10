# JalRakshak AI — Web Command Dashboard Screen Matrix (13 Screens)

---

## Architecture Overview

The JalRakshak Web Command Dashboard provides municipal disaster authorities (BMC / MCGM, SDRF, Fire Services, Police) with situational awareness, predictive intelligence, and operational command tools during urban flood emergencies.
Every web screen connects exclusively to domain-isolated endpoints under `/api/v1` with server-enforced RBAC.

---

## Screen Mapping Matrix

| # | Screen Name | Route / Path | Backend Endpoint(s) | HTTP Method | Min Role Required | Real-time Channel | Fallback / Offline Behavior |
|---|---|---|---|---|---|---|---|
| **01** | **Executive Command Dashboard** | `/dashboard` | `/api/v1/dashboard/summary` | `GET` | `ANALYST` | `/ws/live` (`ALERT_BROADCAST`, `INCIDENT_CREATED`) | Serves cached summary with `is_fallback: true` badge |
| **02** | **GIS Flood Map Explorer** | `/map` | `/api/v1/map/risk`<br>`/api/v1/tiles/nowcast/{z}/{x}/{y}.png`<br>`/api/v1/tiles/risk/{z}/{x}/{y}.png` | `GET` | `ANALYST` | `/ws/live` (`RISK_CELL_UPDATE`) | Renders Vector H3 boundaries with offline local GeoJSON |
| **03** | **Incident Management Console** | `/incidents` | `/api/v1/incidents`<br>`/api/v1/map/incidents` | `GET`, `POST` | `MUNICIPAL_OFFICER` | `/ws/live` (`INCIDENT_STATUS_CHANGED`) | Local storage cache; syncs upon reconnect |
| **04** | **Incident Detail & Timeline** | `/incidents/:id` | `/api/v1/incidents/{id}`<br>`/api/v1/incidents/{id}/events`<br>`/api/v1/incidents/{id}/status` | `GET`, `PATCH` | `MUNICIPAL_OFFICER` | `/ws/live` | Shows full event history with immutable timestamps |
| **05** | **Emergency Alert Studio** | `/alerts` | `/api/v1/alerts`<br>`/api/v1/alerts/draft`<br>`/api/v1/alerts/{id}/approve`<br>`/api/v1/alerts/{id}/broadcast` | `GET`, `POST` | `ALERT_APPROVER` | `/ws/live` (`ALERT_BROADCAST`) | Two-person authorization gate enforced server-side |
| **06** | **CAP 1.2 Protocol Feed** | `/alerts/cap` | `/api/v1/alerts/{id}/cap.xml`<br>`/api/v1/map/alerts` | `GET` | `CITIZEN` (Public) | None | Standard Oasis CAP 1.2 XML feed for NDMA / Google Public Alerts |
| **07** | **Citizen Report Review Desk** | `/reports` | `/api/v1/reports`<br>`/api/v1/reports/{id}`<br>`/api/v1/reports/{id}/review` | `GET`, `POST` | `ANALYST` | `/ws/live` (`FIELD_REPORT_SUBMITTED`) | Displays Groq Vision analysis badges & verification breakdown |
| **08** | **Responder Dispatch Board** | `/responders` | `/api/v1/responders/available`<br>`/api/v1/responders/dispatch` | `GET`, `POST` | `MUNICIPAL_OFFICER` | `/ws/live` (`RESPONDER_LOCATION_UPDATE`) | Real-time GPS location pin updates on map |
| **09** | **Critical Asset Monitor** | `/assets` | `/api/v1/assets/critical`<br>`/api/v1/assets/critical/{id}/risk`<br>`/api/v1/map/assets` | `GET` | `ANALYST` | `/ws/live` | Proximity hazard calculation against hospitals & substations |
| **10** | **Historical Scenario Replay** | `/replay` | `/api/v1/replay/session`<br>`/api/v1/replay/scrub` | `POST` | `ANALYST` | None | Time-travel scrub controller with cached 15-min frames |
| **11** | **AI & Model Diagnostics** | `/diagnostics` | `/api/v1/models/status`<br>`/api/v1/weather/gpm`<br>`/api/v1/weather/gfs` | `GET` | `ADMIN` | None | Displays model provider health (Groq, NVIDIA, PostGIS) |
| **12** | **Audit Trail Explorer** | `/audit` | `/api/v1/audit/logs`<br>`/api/v1/audit/logs/verify-chain` | `GET` | `ADMIN` | None | Cryptographic SHA-256 tamper-proof ledger validation |
| **13** | **System & Resource Config** | `/settings` | `/api/v1/optimization/profile`<br>`/api/v1/devices/push-token` | `GET`, `POST` | `ADMIN` | None | Manages low-power mode, compute budgeting, and push tokens |

---

## Detailed Payload Contract Highlights

### Screen 01: Executive Command Dashboard
- **Request**: `GET /api/v1/dashboard/summary`
- **Response**: Aggregated KPI counts (`high_severe_risk_cells_count`, `active_incidents_count`, `unverified_reports_count`, `critical_assets_at_risk_count`, `active_alerts_count`, `active_responders_count`), peak rainfall rate, affected wards, and top 5 recent events.

### Screen 05: Emergency Alert Broadcasting
- **Workflow**:
  1. `POST /api/v1/alerts/draft` (Analyst drafts alert headline, severity, urgency, instruction, polygon).
  2. `POST /api/v1/alerts/{id}/approve` (Alert Approver signs off).
  3. `POST /api/v1/alerts/{id}/broadcast` (Triggers CAP XML generation, WebSocket fanout, and mobile push notifications).

### Screen 07: Citizen Report Review Desk
- **Request**: `GET /api/v1/reports?status=AI_VERIFIED&limit=50`
- **Item Schema**:
  ```json
  {
    "report_id": "rep-9b1d...",
    "citizen_id": "cit-8821",
    "latitude": 19.0728,
    "longitude": 72.8711,
    "description": "Rising water under railway bridge",
    "image_url": "http://localhost:9000/jalrakshak/reports/report_upl-a24c.jpg",
    "verification_status": "AI_VERIFIED",
    "ai_confidence": 0.88,
    "estimated_water_depth_cm": null,
    "visual_corroboration": {
      "water_visible": true,
      "visual_severity": "HIGH",
      "visual_support_score": 0.85,
      "exact_depth_m": null,
      "observations": ["Water level reaches car bumpers"]
    }
  }
  ```
- **Override Action**: `POST /api/v1/reports/{id}/review` (`{"status": "HUMAN_VERIFIED", "notes": "CCTV verified"}`).
