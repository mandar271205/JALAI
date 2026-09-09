# JalRakshak AI — API Usage Reference & Quickstart

All API routes are prefixed under `/api/v1`. Authentication uses standard `Authorization: Bearer <JWT>` headers. For local development and testing, mock identity headers (`X-Mock-User` and `X-Mock-Role`) can be used.

---

## 1. Geospatial Risk & Weather Telemetry

### Fetch Current Weather Conditions
```bash
curl -X GET "http://localhost:8000/api/v1/weather/current" \
  -H "Accept: application/json"
```

### Query Risk Cells by Bounding Box and Timestamp
```bash
curl -X GET "http://localhost:8000/api/v1/risk/cells?bbox=72.80,18.90,72.95,19.20&limit=50" \
  -H "Accept: application/json"
```

### Query Temporal Risk Progression for an H3 Cell
```bash
curl -X GET "http://localhost:8000/api/v1/risk/886189254dfffff/timeline" \
  -H "Accept: application/json"
```

---

## 2. Citizen Field Reports (3-Step Direct Signed Upload)

### Step 1: Create Draft Report Metadata
```bash
curl -X POST "http://localhost:8000/api/v1/reports/draft" \
  -H "Content-Type: application/json" \
  -H "X-Mock-Role: CITIZEN" \
  -d '{
    "latitude": 19.0178,
    "longitude": 72.8478,
    "description": "Severe waterlogging near railway bridge, approx 45cm depth"
  }'
```

### Step 2: Request Direct S3 Upload Intent
```bash
curl -X POST "http://localhost:8000/api/v1/reports/upload-intent" \
  -H "Content-Type: application/json" \
  -H "X-Mock-Role: CITIZEN" \
  -d '{
    "report_id": "rep-abc-001",
    "filename": "water_level_marker.jpg",
    "content_type": "image/jpeg",
    "file_size_bytes": 1048576
  }'
```

### Step 3: Finalize Upload and Trigger Async AI Vision Verification
```bash
curl -X POST "http://localhost:8000/api/v1/reports/upload-finalize" \
  -H "Content-Type: application/json" \
  -H "X-Mock-Role: CITIZEN" \
  -d '{
    "upload_id": "rep-abc-001",
    "sha256_checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }'
```

---

## 3. Incident Management & Human Review Override

### Transition Incident Lifecycle
```bash
curl -X POST "http://localhost:8000/api/v1/incidents/inc-p4-001/transition" \
  -H "Content-Type: application/json" \
  -H "X-Mock-Role: MUNICIPAL_OFFICER" \
  -d '{
    "target_status": "OPEN",
    "reason": "Verified waterlogging causing traffic blockage.",
    "notes": "Emergency dewatering pump deployed."
  }'
```

---

## 4. Emergency Resource Optimization (Google OR-Tools)

### Generate Resource Allocation Recommendation
```bash
curl -X POST "http://localhost:8000/api/v1/optimization/recommend" \
  -H "Content-Type: application/json" \
  -H "X-Mock-Role: DISASTER_MANAGER" \
  -d '{
    "pumps": [
      {"pump_id": "P-01", "name": "500 LPS Submersible", "capacity_lps": 500, "latitude": 19.018, "longitude": 72.848}
    ],
    "teams": [
      {"team_id": "T-01", "name": "NDRF Quick Response", "team_size": 10, "latitude": 19.020, "longitude": 72.850}
    ],
    "shelters": [
      {"shelter_id": "S-01", "name": "Dharavi Community Center", "capacity": 200, "current_occupancy": 50, "latitude": 19.040, "longitude": 72.860}
    ],
    "incidents": [
      {"incident_id": "inc-01", "title": "Hindmata Underpass", "category": "WATERLOGGING", "severity": "CRITICAL", "latitude": 19.0178, "longitude": 72.8478, "zone_risk_score": 0.85}
    ]
  }'
```

### Authorize & Dispatch Response Plan (Creates Cryptographic Audit Event)
```bash
curl -X POST "http://localhost:8000/api/v1/optimization/approve-plan" \
  -H "Content-Type: application/json" \
  -H "X-Mock-Role: DISASTER_MANAGER" \
  -d '{
    "plan_id": "plan-opt-999",
    "approval_notes": "Immediate deployment approved by Municipal Commissioner.",
    "suggested_allocation_plan": {
      "team_allocations": [
        {"team_id": "T-01", "assigned_incident_id": "inc-01"}
      ]
    }
  }'
```

---

## 5. Historical Replay & Calibration

### Create Virtual-Clock Replay Session
```bash
curl -X POST "http://localhost:8000/api/v1/replay/sessions" \
  -H "Content-Type: application/json" \
  -H "X-Mock-Role: ANALYST" \
  -d '{"playback_speed": 2.0}'
```

### Control Playback & Scrub
```bash
curl -X POST "http://localhost:8000/api/v1/replay/sessions/{session_id}/control" \
  -H "Content-Type: application/json" \
  -H "X-Mock-Role: ANALYST" \
  -d '{"action": "PLAY"}'
```

---

## 6. Real-time WebSocket Stream (`WS /api/v1/live`)

Connect using a WebSocket client (e.g. wscat):
```bash
wscat -c "ws://localhost:8000/api/v1/live?last_event_id=0"
```

Emitted operational events:
- `risk.cell.updated`
- `incident.created` / `incident.updated`
- `report.received` / `report.verified`
- `alert.drafted` / `alert.published`
- `source.degraded`
- `model.run.completed`
- `field.task.updated`
