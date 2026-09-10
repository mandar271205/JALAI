# JalRakshak AI — Frontend Web Command Dashboard / Backend Contract

---

## 1. Specification Overview & Target Audience

This specification defines the authoritative integration contract between the **FastAPI Backend (`/api/v1`)** and the **Authority Web Command Dashboard**.
Target consumers include:
- Municipal Disaster Management Officers (MCGM / BMC)
- Hydrological & Geospatial Analysts
- Emergency Response Coordinators
- System Administrators

---

## 2. Authentication & Role-Based Access Control (RBAC)

All requests must include standard Bearer authorization headers:
```http
Authorization: Bearer <jwt_token>
```

### Role Hierarchy & Capabilities Matrix

| Role | Hierarchy Level | Capabilities | Typical Screens |
|---|---|---|---|
| `CITIZEN` | 1 | Submit reports, view public alerts/risk | Mobile app only |
| `RESPONDER` | 2 | View assigned rescue tasks, update mission status | Mobile responder app |
| `ANALYST` | 3 | Draft alerts, view ML diagnostics, run historical replays | Analyst Workspace, Risk Map |
| `MUNICIPAL_OFFICER` | 4 | Dispatch responders, review citizen reports, manage incidents | Incident Manager, Dispatch Board |
| `ALERT_APPROVER` | 5 | Approve & broadcast emergency CAP alerts | Alert Broadcasting Center |
| `ADMIN` | 6 | Full system control, audit log verification, user management | System Settings, Audit Explorer |

---

## 3. Real-Time WebSocket Channel

### Endpoint: `/ws/live`
Web Dashboard maintains a persistent WebSocket connection to receive sub-second push updates:
- **Connection URL**: `ws://<host>:<port>/ws/live?token=<jwt_token>`
- **Heartbeat Protocol**: Client sends `{"type": "ping"}` every 30 seconds; server responds with `{"type": "pong", "timestamp": "..."}`.
- **Message Types Broadcast by Server**:
  1. `RISK_CELL_UPDATE`: New H3 risk cell calculation available.
  2. `INCIDENT_CREATED` / `INCIDENT_STATUS_CHANGED`: State transitions.
  3. `ALERT_BROADCAST`: High-priority emergency broadcast.
  4. `FIELD_REPORT_SUBMITTED`: New citizen crowd report received.
  5. `RESPONDER_LOCATION_UPDATE`: GPS telemetry from active responders.

---

## 4. Web Command Endpoints

### 4.1 Dashboard Overview & KPIs
- **Method / Path**: `GET /api/v1/dashboard/summary`
- **Authorized Roles**: `ANALYST`, `MUNICIPAL_OFFICER`, `ADMIN`
- **Response Schema (`200 OK`)**:
  ```json
  {
    "generated_at": "2026-09-10T02:15:00Z",
    "kpis": {
      "high_severe_risk_cells_count": 4,
      "active_incidents_count": 8,
      "unverified_reports_count": 12,
      "critical_assets_at_risk_count": 3,
      "active_alerts_count": 2,
      "active_responders_count": 14
    },
    "city_risk_status": {
      "city_max_risk_level": "SEVERE",
      "peak_rainfall_rate_mm_h": 68.5,
      "affected_wards": ["WARD-12-DHARAVI", "WARD-14-KURLA"],
      "lead_time_minutes": 120,
      "summary": "Active flood monitoring across Mumbai metropolitan area."
    },
    "model_health": {
      "database_connected": true,
      "radar_feed_status": "OPERATIONAL",
      "groq_primary_available": true,
      "groq_vision_available": true,
      "rainfall_winner_frozen": false,
      "fno_validated": false,
      "operational_mode": "PROVISIONAL_EVALUATION"
    },
    "recent_incidents": [ ... ],
    "recent_alerts": [ ... ],
    "recent_reports": [ ... ]
  }
  ```

---

### 4.2 Unified GIS Map Layers & Bounding Box Queries
All map endpoints accept standard bounding box queries `bbox=min_lon,min_lat,max_lon,max_lat`.

- **Risk Cells**: `GET /api/v1/map/risk?bbox=...&min_level=MODERATE`
- **Active Incidents**: `GET /api/v1/map/incidents?bbox=...&severity=HIGH`
- **Citizen Reports**: `GET /api/v1/map/reports?bbox=...&status=AI_VERIFIED`
- **Critical Assets**: `GET /api/v1/map/assets?bbox=...&category=hospital`
- **Emergency Alerts**: `GET /api/v1/map/alerts`
- **Nowcast Raster Tiles**: `GET /api/v1/tiles/nowcast/{z}/{x}/{y}.png`
- **Risk Raster Tiles**: `GET /api/v1/tiles/risk/{z}/{x}/{y}.png`

---

### 4.3 Incident Lifecycle Management
- **List Incidents**: `GET /api/v1/incidents?status=OPEN&severity=HIGH`
- **Create Incident**: `POST /api/v1/incidents`
- **Incident Detail**: `GET /api/v1/incidents/{incident_id}`
- **Transition Status**: `PATCH /api/v1/incidents/{incident_id}/status`
  ```json
  {
    "status": "DISPATCHED",
    "reason": "Rescue Team Bravo dispatched to site"
  }
  ```
- **Incident Audit Events**: `GET /api/v1/incidents/{incident_id}/events`

---

### 4.4 Emergency Alert Broadcasting & CAP 1.2 Feed
- **Draft Alert**: `POST /api/v1/alerts/draft` (`ANALYST`, `ADMIN`)
- **Approve Alert**: `POST /api/v1/alerts/{alert_id}/approve` (`ALERT_APPROVER`, `ADMIN`)
- **Broadcast Alert**: `POST /api/v1/alerts/{alert_id}/broadcast` (`ALERT_APPROVER`, `ADMIN`)
- **Cancel Alert**: `POST /api/v1/alerts/{alert_id}/cancel`
- **CAP XML Export**: `GET /api/v1/alerts/{alert_id}/cap.xml` (Oasis Common Alerting Protocol 1.2 compliant XML for NDMA / Google Public Alerts)

---

### 4.5 Citizen Field Report Review
- **List Reports**: `GET /api/v1/reports?status=AI_VERIFIED&limit=50&offset=0`
- **Report Detail**: `GET /api/v1/reports/{report_id}`
- **Human Verification Override**: `POST /api/v1/reports/{report_id}/review`
  ```json
  {
    "status": "HUMAN_VERIFIED",
    "notes": "Verified against traffic camera #14."
  }
  ```

---

### 4.6 Cryptographic Audit Log & Compliance
- **Query Logs**: `GET /api/v1/audit/logs?target_entity=ALERT&limit=100`
- **Verify Hash Chain**: `GET /api/v1/audit/logs/verify-chain`
  - Returns `{"is_valid": true, "verified_blocks": 154}` validating SHA-256 tamper-proof chain.
