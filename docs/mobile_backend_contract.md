# JalRakshak AI — Mobile Backend Integration Contract (Citizen & Responder)

---

## 1. Design Principles for Mobile Clients

Mobile applications operating in disaster zones face intermittent network connectivity, power constraints, and critical urgency.
JalRakshak AI backend provides:
1. **Single-Call Home Aggregation (`GET /api/v1/mobile/home`)**: Eliminates waterfall requests on app boot; returns local risk, rainfall outlook, nearby alerts, incidents, and saved locations in a single compressed payload.
2. **Direct-to-Storage Media Offloading**: Photo uploads bypass API server memory via presigned S3 URLs.
3. **Strict Scientific Boundaries**: Monocular smartphone photos cannot measure metric depth (`exact_depth_m = null`).
4. **Offline-First Mutation Outbox**: Actions taken offline (field reports, task updates) queue locally in SQLite and flush idempotently via `POST /api/v1/sync/mutations`.

---

## 2. Authentication & Device Identity

- **Citizen Auth**: Standard JWT Bearer token or anonymous device token.
- **Headers**:
  ```http
  Authorization: Bearer <jwt_token>
  X-Device-OS: android | ios
  X-Client-Version: 1.0.0
  ```

---

## 3. Citizen Mobile API Surface

### 3.1 App Boot Aggregated Home Screen
- **Method / Path**: `GET /api/v1/mobile/home?lat={lat}&lon={lon}&radius_km={radius}`
- **Query Parameters**:
  - `lat`: float (e.g. `19.0760`)
  - `lon`: float (e.g. `72.8777`)
  - `radius_km`: float (default `5.0`)
- **Response Schema (`200 OK`)**:
  ```json
  {
    "location": {
      "latitude": 19.0760,
      "longitude": 72.8777,
      "ward_id": "WARD-12-DHARAVI",
      "radius_km": 5.0
    },
    "current_risk": {
      "risk_level": "MODERATE",
      "risk_score": 0.58,
      "dominant_factors": [
        "High surface runoff",
        "Low-lying catchment drainage"
      ],
      "summary": "Current risk level in WARD-12-DHARAVI is MODERATE with active drainage monitoring.",
      "confidence": 0.85,
      "is_fallback": true
    },
    "rainfall_outlook": [
      {
        "lead_time_minutes": 30,
        "rainfall_rate_mm_h": 35.0,
        "category": "MODERATE",
        "trend": "INCREASING"
      },
      {
        "lead_time_minutes": 60,
        "rainfall_rate_mm_h": 68.5,
        "category": "HEAVY",
        "trend": "INCREASING"
      },
      {
        "lead_time_minutes": 90,
        "rainfall_rate_mm_h": 52.0,
        "category": "HEAVY",
        "trend": "DECREASING"
      },
      {
        "lead_time_minutes": 120,
        "rainfall_rate_mm_h": 24.0,
        "category": "MODERATE",
        "trend": "DECREASING"
      }
    ],
    "active_alerts": [ ... ],
    "nearby_incidents": [ ... ],
    "nearby_reports": [ ... ],
    "watched_locations": [ ... ],
    "system_status": {
      "timestamp": "2026-09-10T02:15:00Z",
      "operational_mode": "LIVE_OPERATIONAL",
      "is_radar_available": true,
      "provisional_model_fallback": true
    }
  }
  ```

---

### 3.2 Citizen Field Report Submission & Photo Upload Flow
The mobile app executes a 3-step signed upload sequence:

1. **Create Draft Report**:
   - `POST /api/v1/reports/draft`
   - Payload: `{"latitude": 19.0728, "longitude": 72.8711, "description": "Water overflowing road"}`
   - Returns: `{"report_id": "rep-9b1d...", "verification_status": "DRAFT"}`

2. **Acquire Upload Intent**:
   - `POST /api/v1/reports/{report_id}/uploads`
   - Payload: `{"filename": "photo.jpg", "content_type": "image/jpeg", "file_size_bytes": 1024000}`
   - Returns: `{"upload_id": "upl-a24c...", "presigned_url": "https://...", "object_key": "..."}`

3. **Direct Binary Upload to S3**:
   - Client sends HTTP `PUT` directly to `presigned_url` with binary file bytes.

4. **Complete & Trigger AI Vision Corroboration**:
   - `POST /api/v1/reports/{report_id}/uploads/complete`
   - Payload: `{"upload_id": "upl-a24c...", "sha256_checksum": "..."}`
   - Returns: `{"verification_status": "AI_VERIFIED", "visual_corroboration": { ... }}`

5. **Polling Status Query**:
   - `GET /api/v1/reports/{report_id}/status`
   - Lightweight status check for status badge updates.

---

### 3.3 Push Notifications & Device Token Management
- **Register Token**: `POST /api/v1/devices/push-token`
  ```json
  {
    "token": "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]",
    "device_os": "android",
    "device_id": "pixel-7-device-uid"
  }
  ```
- **Unregister Token (on Logout)**: `DELETE /api/v1/devices/push-token/{device_id}`

---

### 3.4 Watch Locations (Safe Zones)
Allows citizens to monitor family members, residences, or workplaces:
- **Create**: `POST /api/v1/watch-locations`
  ```json
  {
    "label": "Home - Dharavi",
    "latitude": 19.0435,
    "longitude": 72.8562,
    "risk_threshold": "HIGH",
    "notify_push": true
  }
  ```
- **List**: `GET /api/v1/watch-locations`
- **Update**: `PATCH /api/v1/watch-locations/{id}` (`{"risk_threshold": "SEVERE"}`)
- **Delete**: `DELETE /api/v1/watch-locations/{id}`

---

## 4. Responder Mobile API Surface

### 4.1 Dispatch & Task Execution
- **Get Available Tasks**: `GET /api/v1/responders/available`
- **Accept / Dispatch Mission**: `POST /api/v1/responders/dispatch`
  ```json
  {
    "task_id": "task-bravoteam-001",
    "responder_id": "resp-ndrf-12",
    "status": "EN_ROUTE"
  }
  ```
- **Update Mission Status**: `POST /api/v1/responders/tasks/{task_id}/status`
  ```json
  {
    "status": "ON_SCENE",
    "notes": "Arrived at Hindmata flyover. Commencing evacuation."
  }
  ```

---

### 4.2 Elevation-Aware & Flood-Avoidance Routing
- **Method / Path**: `POST /api/v1/routes/elevation-aware`
- **Purpose**: Calculates shortest driving or walking path that avoids severe inundation risk cells and prefers elevated terrain / ridges.
- **Request Body**:
  ```json
  {
    "origin": {"latitude": 19.0178, "longitude": 72.8478},
    "destination": {"latitude": 19.0760, "longitude": 72.8777},
    "vehicle_type": "EMERGENCY_AMBULANCE",
    "max_acceptable_risk": "LOW"
  }
  ```
- **Response**: GeoJSON LineString coordinates, elevation profile, avoided flooded segments, and estimated transit time.

---

### 4.3 Offline Mutation Sync Protocol
When a responder operates in a flooded area with lost cellular reception:
1. Mutations are persisted to local SQLite outbox with a unique `mutation_id` (UUIDv4) and client timestamp.
2. When cellular or Wi-Fi reconnects, client flushes queue via:
   - `POST /api/v1/sync/mutations`
   - Payload:
     ```json
     {
       "device_id": "rugged-tablet-04",
       "mutations": [
         {
           "mutation_id": "7b0d9124-...",
           "action": "UPDATE_TASK_STATUS",
           "payload": {"task_id": "task-01", "status": "COMPLETED"},
           "client_timestamp": "2026-09-10T02:05:00Z"
         }
       ]
     }
     ```
3. Backend performs idempotent conflict resolution and returns acknowledgment IDs.
