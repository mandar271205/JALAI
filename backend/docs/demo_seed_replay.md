# JalRakshak AI — Demo Seeding & Historical Replay Guide

This guide describes how to run the automated demonstration dataset and simulate the historical Mumbai Cloudburst event without external API credentials.

---

## 1. Static Demo Fixtures

The repository includes frozen demo fixtures in `contracts/fixtures/demo-event/`:
- `weather-sources.json`: 4 operational feeds (IMD Radar Colaba, INSAT-3DR, MCGM rain gauges, IMD GFS NWP).
- `incidents.json`: Real-world flooded locations (Hindmata, Kurla West, Milan Subway, BKC).
- `critical-assets.json`: Hospitals, pumping stations, and arterial bridges with threshold flood tolerances.
- `nowcast-manifest.json`: Precipitation UNet model output tile references and forecast timestamps.
- `inundation-manifest.json`: Hydrodynamic shallow water simulation extents.

---

## 2. Running the Mumbai 26 July Historical Replay

The backend contains an immutable virtual-clock historical replay engine (`/api/v1/replay`).

### Step 1: Create a Replay Session
```bash
curl -X POST "http://localhost:8000/api/v1/replay/sessions" \
  -H "Content-Type: application/json" \
  -H "X-Mock-Role: ANALYST" \
  -d '{"playback_speed": 1.0}'
```
Response:
```json
{
  "session_id": "c71a39fd-d439-4ce8-b0a3-ee10df66d526",
  "replay_id": "mumbai_cloudburst_20250726",
  "status": "PAUSED",
  "simulated_time": "2025-07-26T06:00:00Z",
  "start_time": "2025-07-26T06:00:00Z",
  "end_time": "2025-07-26T18:00:00Z",
  "playback_speed": 1.0,
  "is_replay_isolated": true
}
```

### Step 2: Step Forward or Play Virtual Clock
```bash
curl -X POST "http://localhost:8000/api/v1/replay/sessions/{session_id}/control" \
  -H "Content-Type: application/json" \
  -H "X-Mock-Role: ANALYST" \
  -d '{"action": "STEP_FORWARD"}'
```

### Step 3: Scrub Directly to Peak Inundation (12:00 UTC)
```bash
curl -X POST "http://localhost:8000/api/v1/replay/sessions/{session_id}/scrub" \
  -H "Content-Type: application/json" \
  -H "X-Mock-Role: ANALYST" \
  -d '{"timestamp": "2025-07-26T12:00:00Z"}'
```

### Step 4: Fetch Temporal Slice & Ground-Truth Calibration Metrics
```bash
curl -X GET "http://localhost:8000/api/v1/replay/sessions/{session_id}/state" \
  -H "X-Mock-Role: ANALYST"
```
The state payload returns:
- Synchronized radar rainfall ($110\text{ mm/hr}$)
- Hydrodynamic water depth ($1.45\text{ m}$)
- 82 active H3 risk cells
- Active field reports and critical incidents
- Precomputed raster and vector tile paths
- ML predicted-vs-observed metrics ($0.12\text{ m}$ depth RMSE, $88\%$ extent IoU).

### Isolation Guarantee
Replay sessions run in isolated state (`is_replay_isolated=True`). Replaying historical scenarios **never** alters live database records or triggers citizen alerts.
