# JalRakshak AI — Frontend & Client Integration Guide

This guide is designed for **Web and Mobile developers** integrating their client applications with the JalRakshak platform. It provides clear, pragmatic instructions without requiring knowledge of internal scientific ML pipelines.

---

## 1. Quick Architecture Overview

```
┌─────────────────┐       ┌───────────────────┐
│  Web Dashboard  │       │ Mobile Citizen App│
│     (web/)      │       │     (mobile/)     │
└────────┬────────┘       └─────────┬─────────┘
         │                          │
         │   HTTP REST / WebSocket  │
         ▼                          ▼
┌─────────────────────────────────────────────┐
│          Backend Platform Gateway           │
│        (backend/ on port 8000)              │
└──────────────────────┬──────────────────────┘
                       │
                       │   Authenticated Inter-Service
                       ▼
┌─────────────────────────────────────────────┐
│             ML Inference Service            │
│          (src/ on port 8001)                │
└─────────────────────────────────────────────┘
```

> [!IMPORTANT]
> Client applications interact **exclusively** with the Backend Gateway (`http://localhost:8000`).
> Never call the ML inference service (`:8001`) or external AI providers (Groq/NVIDIA) directly from client code.

---

## 2. Setting Up Your Client Workspace

### Adding Web Code (`web/`)
1. Initialize your web application framework (e.g. Next.js, Vite + React) directly inside `web/`:
   ```bash
   cd web
   # Example: npx create-next-app@latest . --typescript --tailwind --eslint
   ```
2. Configure your environment file `web/.env.local`:
   ```ini
   NEXT_PUBLIC_API_URL=http://localhost:8000
   NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
   ```

### Adding Mobile Code (`mobile/`)
1. Initialize your mobile framework (e.g. Flutter or React Native) inside `mobile/`:
   ```bash
   cd mobile
   # Example: flutter create .
   ```
2. Configure your base API endpoint to point to your development backend host:
   ```dart
   const String kApiBaseUrl = 'http://10.0.2.2:8000'; // For Android Emulator
   ```

---

## 3. Core API Endpoints for Clients

All public endpoints are documented in `shared/contracts/openapi.yaml`.

### A. Health & System Readiness
Check if the backend platform is operational:
```http
GET /health
```
**Response (200 OK):**
```json
{
  "status": "ok",
  "service": "jalrakshak-backend",
  "timestamp": "2026-09-10T05:30:00Z"
}
```

---

### B. Rainfall Forecast
Retrieve the quantitative nowcast and operational risk assessment:
```http
POST /api/v1/weather/nowcast
Authorization: Bearer <user_or_guest_token>
Content-Type: application/json

{
  "latitude": 19.0760,
  "longitude": 72.8777
}
```
**Response (200 OK):**
```json
{
  "location": {"latitude": 19.0760, "longitude": 72.8777},
  "severity": "HIGH",
  "trend": "INCREASING",
  "confidence": 0.88,
  "forecast_horizons_minutes": [30, 60, 90, 120],
  "expected_intensity_band_mm_h": {
    "min": 35.0,
    "max": 55.0
  },
  "summary": "Heavy convective precipitation detected over Dharavi catchment.",
  "recommended_action": "Deploy mobile pumps to low-lying rail culverts.",
  "key_factors": [
    "High optical-flow advection vector",
    "Precipitable water anomaly in GFS"
  ]
}
```

---

### C. Flood Risk Assessment
Retrieve the flood hazard risk classification:
```http
POST /api/v1/flood/inundation
Authorization: Bearer <user_or_guest_token>
Content-Type: application/json

{
  "latitude": 19.0435,
  "longitude": 72.8562
}
```
**Response (200 OK):**
```json
{
  "location": {"latitude": 19.0435, "longitude": 72.8562},
  "risk_level": "SEVERE",
  "confidence": 0.82,
  "depth_m": null,
  "dominant_factors": [
    "Elevation below 3m high-tide datum",
    "Slope < 1.0 degree poor gravity drainage",
    "Critical hospital access corridor"
  ],
  "summary": "Severe local drainage inundation expected due to low-lying topography.",
  "recommended_action": "Pre-position evacuation rescue boats and issue red alert."
}
```
> [!NOTE]
> `depth_m` is numerical water depth in meters. It will be `null` unless calibrated hydrodynamic sensor/model data is available. Frontend UI should display "Depth sensor pending / Risk: SEVERE" when `depth_m` is `null`.

---

### D. Comprehensive Area Risk
Fetch combined Hazard $\times$ Exposure $\times$ Vulnerability index:
```http
POST /api/v1/risk/evaluate
Authorization: Bearer <user_or_guest_token>
Content-Type: application/json

{
  "latitude": 19.0760,
  "longitude": 72.8777,
  "radius_km": 5.0
}
```
**Response (200 OK):**
```json
{
  "risk_score": 0.78,
  "risk_tier": "HIGH",
  "exposure_index": 0.85,
  "vulnerability_index": 0.72,
  "hazard_index": 0.78,
  "critical_infrastructure_at_risk": [
    {"name": "Sion Railway Station Culvert", "type": "transit"},
    {"name": "LTMG Hospital Access Road", "type": "medical"}
  ],
  "recommended_interventions": [
    "Activate floodgates at Mithi river outfall",
    "Divert traffic from LBS Marg"
  ]
}
```

---

### E. Model & Scientific Operational Status
Check the status of underlying ML and physics pipelines:
```http
GET /api/v1/models/status
```
**Response (200 OK):**
```json
{
  "rainfall_model_available": false,
  "rainfall_model_status": "TRAINING_PAUSED_FOR_DEMO",
  "flood_model_available": false,
  "flood_model_status": "EXPERIMENTAL_SIMULATION_READY",
  "ai_inference_enabled": true,
  "active_source_mode": "PROVISIONAL_AI",
  "service_health": "HEALTHY"
}
```

---

## 4. Submitting Citizen Flood Reports

Mobile applications can allow citizens to submit geo-tagged ground-truth observations:
```http
POST /api/v1/reports
Authorization: Bearer <citizen_token>
Content-Type: application/json

{
  "latitude": 19.0435,
  "longitude": 72.8562,
  "claimed_depth_category": "KNEE_DEEP",
  "text": "Water logging near Sion station bus stop, drainage overflowing.",
  "image_metadata": {
    "camera_model": "Pixel 8",
    "timestamp": "2026-09-10T05:25:00Z"
  }
}
```
**Response (201 Created):**
```json
{
  "report_id": "rep_9a8b7c6d",
  "status": "RECEIVED",
  "corroboration_state": "PENDING_VERIFICATION"
}
```

---

## 5. UI Guidelines & Presentation Rules

- **Zero LLM Branding**: Never show "Groq", "NVIDIA", "GPT", "Nemotron", or "AI Fallback". The app branding is strictly **JalRakshak AI**.
- **Truthful Confidence**: Display the confidence score (0.0 to 1.0) alongside risk categories.
- **Null Depth Handling**: Never invent or display a fabricated number like "1.2m" when `depth_m` is `null`. Display categorical severity ("HIGH WATER RISK") instead.
