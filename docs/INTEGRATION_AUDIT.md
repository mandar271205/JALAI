# JalRakshak AI — System Integration Audit
**Project**: JalRakshak AI — Smart India Hackathon 2026 (SIH26071)  
**Theme**: Disaster Management / Extreme Urban Flood Risk  
**Date**: September 9, 2026  
**Auditor**: Senior Backend + ML Platform Integration Engineer  
**Status**: GATE A Complete (Ready for Implementation)

---

## Executive Summary

This document establishes the authoritative architecture and contract audit for integrating the two independent JalRakshak AI codebases:
1. **`jalrakshak-ml-starter/`**: Authoritative source for ML logic, scientific assumptions, meteorological ingestion (NASA GPM, NOAA GFS), PySTEPS nowcasting baseline, fusion, provenance, and QC.
2. **`sih backend/`**: Authoritative source for application architecture, async FastAPI platform, PostgreSQL/PostGIS database, Supabase authentication, OASIS CAP 1.2 alerts, incident state machine, and citizen reporting.

The integration strategy is a **resilient decoupled service architecture via HTTP REST**:
- The backend interacts with ML solely through its existing `MLProvider` abstraction (`app/integrations/ml/`).
- The ML codebase will expose a lightweight, typed FastAPI serving layer (`src/jalrakshak_ml/serving/app.py`) running on `http://localhost:8001`.
- A 3-state circuit breaker with fallback ensures the backend is **100% operational** even if the ML service is offline, degraded, or timing out.

---

## 1. Backend Architecture Discovered

| Component | Discovered Technology / Pattern | Source File Evidence |
| :--- | :--- | :--- |
| **Language & Runtime** | Python 3.11+ / 3.12+ (tested on Python 3.14.7 via uv) | `backend/pyproject.toml:6` |
| **Web Framework** | FastAPI 0.111.0, Starlette, Uvicorn (standard) | `backend/pyproject.toml:8-9` |
| **Dependency Manager** | `uv` package manager with `pyproject.toml` and `uv.lock` | `backend/pyproject.toml`, `backend/uv.lock` |
| **Application Entrypoint** | `app.main:app` with async lifespan context manager | `backend/app/main.py:40-65` |
| **Routing Structure** | Modular router prefixed `/api/v1` with 18 domain routers + WebSocket | `backend/app/api/v1/router.py:24-43` |
| **API Versioning** | Explicit `/api/v1/` route prefixing | `backend/app/api/v1/router.py:24` |
| **Database & ORM** | SQLAlchemy 2.0.30 (asyncpg / aiosqlite), GeoAlchemy2, Shapely | `backend/app/db/session.py`, `backend/app/db/models.py` |
| **Database Entities** | `User`, `WeatherSource`, `ModelRun`, `RiskCell`, `Incident`, `IncidentEvent`, `FieldReport`, `FieldReportUpload`, `Alert`, `CriticalAsset`, `ResponderTask`, `WatchLocation`, `AuditLog`, `OutboxEvent` | `backend/app/db/models.py:27-340` |
| **Authentication & RBAC** | Supabase JWT with mock fallback; 6 roles: `CITIZEN`, `FIRST_RESPONDER`, `ANALYST`, `ALERT_APPROVER`, `MUNICIPAL_OFFICER`, `ADMIN` | `backend/app/core/security.py:28-44` |
| **Config Management** | `pydantic-settings` BaseSettings loading `.env` and `../.env` | `backend/app/core/config.py:6-56` |
| **Incident Workflow** | State machine: `DETECTED` $\rightarrow$ `OPEN` $\rightarrow$ `ACKNOWLEDGED` $\rightarrow$ `MITIGATING` $\rightarrow$ `RESOLVED` $\rightarrow$ `CLOSED` (or `DISMISSED` with mandatory reason) | `backend/app/domains/incidents/state_machine.py:16-51` |
| **Alert Workflow** | 3-step lifecycle: `DRAFT` $\rightarrow$ `APPROVE` $\rightarrow$ `PUBLISH`. Human authorization required; OASIS CAP 1.2 XML serialization | `backend/app/api/v1/alerts.py:20-140` |
| **Object Storage** | MinIO / AWS S3 client with presigned URLs for direct client uploads | `backend/app/integrations/object_store/` |
| **ML Integration** | `MLProvider` abstract interface, `StubMLProvider` with fixtures, `HttpMLProvider` with 3-state `CircuitBreaker` | `backend/app/integrations/ml/` |
| **Automated Tests** | 81 tests passing (100% pass rate in baseline audit) | `backend/tests/` (81/81 passed) |

---

## 2. ML Architecture Discovered

| Component | Discovered Technology / Pattern | Source File Evidence |
| :--- | :--- | :--- |
| **Package Structure** | Python package `jalrakshak_ml` in `src/jalrakshak_ml/` | `jalrakshak-ml-starter/pyproject.toml` |
| **Environment** | Python 3.11.16 conda env (`jalrakshak`) with PyTorch 2.14, GDAL 3.12, pysteps 1.21.5, rasterio, xarray, zarr | Conda env `jalrakshak` |
| **Operational Baseline** | **pySTEPS Lucas-Kanade optical flow** (`PystepsNowcast`). Strongest overall validated deterministic nowcasting baseline. | `src/jalrakshak_ml/nowcast/pysteps_adapter.py:11-108` |
| **Research Models** | UNet-ConvGRU, ConvLSTM v3, ST-Attention; currently in Phase 4E validation tournament (NOT production models). | `src/jalrakshak_ml/deep_nowcast/` |
| **Ingestion & Replay** | GPM IMERG V07 (~0.1°), NOAA GFS (0.25° rich fields: u10, v10, t2m, rh2m, sp, CAPE, PWAT, prate). Replayed to 256x256 Mumbai grid. | `src/jalrakshak_ml/gfs_replay/`, `src/jalrakshak_ml/weather/` |
| **Data Contracts** | `MeteorologicalField`, `MultiSourceWeatherFrame`, `NowcastResult`, `ForecastResult` | `src/jalrakshak_ml/weather/contracts.py`, `src/jalrakshak_ml/nowcast/contracts.py` |
| **Quality Control (QC)** | Distinct `quality_score` (data completeness/health [0, 1]) strictly separated from model `confidence` | `src/jalrakshak_ml/weather/contracts.py:34-36` |
| **Spatial Reference** | API coords: `EPSG:4326`; Canonical projected grid: `EPSG:32643`; 256x256 grid | `src/jalrakshak_ml/weather/contracts.py:60-62` |
| **Serving Layer Status** | Directory `src/jalrakshak_ml/serving/` exists with only `__init__.py` | `src/jalrakshak_ml/serving/` |
| **Existing OpenAPI** | `contracts/internal-ml-openapi.yaml` specifying internal v1 routes | `contracts/internal-ml-openapi.yaml:12-58` |

---

## 3. Existing API Contracts

### Backend Public API (`contracts/openapi.yaml`)
Key endpoints consuming or presenting ML intelligence:
- `GET /api/v1/weather/current`: Current weather conditions & radar/satellite snapshot.
- `GET /api/v1/weather/sources/status`: Ingestion status, quality scores, and latencies.
- `GET /api/v1/nowcast/manifest`: Latest precipitation nowcast raster manifest (COG URL, valid bounds, lead time).
- `GET /api/v1/inundation/manifest`: Latest hydrodynamic flood depth raster manifest (depth COG, velocity COG, max depth).
- `GET /api/v1/risk/cells`: Scored H3 cells with risk levels (`LOW`, `MODERATE`, `HIGH`, `SEVERE`), depths, rainfall rates.
- `GET /api/v1/risk/{h3_cell}/timeline`: 0 to 90 min risk forecast for a specific H3 cell.
- `POST /api/v1/reports/upload-finalize`: Completes citizen upload and invokes ML vision verification.
- `GET /api/v1/models/status`: Active models, versions, and health.

---

## 4. Existing ML Contracts & Route Differences

There is a minor routing convention difference between the ML specification and the backend HTTP client:

| Functional Capability | Target ML Contract (`jalrakshak-ml-starter`) | Backend HTTP Client Call (`backend/app/integrations/ml/http_provider.py`) | Backend Contract Spec (`contracts/internal-ml-openapi.yaml`) |
| :--- | :--- | :--- | :--- |
| **Health Check** | `GET /health` | (Used in readiness check) | `GET /health` |
| **Rainfall Nowcast** | `POST /internal/v1/nowcast` | `POST /internal/ml/nowcast` | `POST /internal/ml/nowcast` |
| **Inundation Model** | `POST /internal/v1/inundation` | `POST /internal/ml/inundation` | `POST /internal/ml/inundation` |
| **Risk Assessment** | `POST /internal/v1/risk` | `POST /internal/ml/risk-assessment` | `POST /internal/ml/risk-assessment` |
| **Citizen Report Vision**| `POST /internal/v1/report-verification`| `POST /internal/ml/verify-report` | `POST /internal/ml/verify-report` |
| **Model Registry Status**| `GET /internal/v1/models/status` | `GET /api/v1/models/status` | N/A |
| **Run Provenance** | `GET /internal/v1/runs/{run_id}`| N/A | N/A |

### Harmonization Decision:
The ML serving service will expose **BOTH** sets of endpoints:
1. Canonical `/internal/v1/...` routes as specified in Step 3.
2. Route aliases `/internal/ml/...` to maintain 100% backward compatibility with existing teammate backend code without requiring breaking client changes.
3. In `http_provider.py`, prioritize the canonical endpoints with seamless alias support.

---

## 5. Overlapping Functionality

1. **Weather Ingestion Stubs vs Authentic ML Ingestion**:
   - Backend has simulated adapters in `app/domains/weather/adapters/adapters.py` returning static binary strings (`RADAR_BINARY_DOPPLER_SIM`, `WRF_GRIB2_NETCDF_SIM`).
   - ML codebase has authentic pipelines for NASA GPM IMERG and NOAA GFS.
   - **Resolution**: Backend keeps its lightweight simulated adapters for standalone execution; ML service supplies authentic processed observations and nowcasts via the API.
2. **Model Run Metadata**:
   - Backend has a `ModelRun` table (`model_runs` in PostGIS).
   - ML has run metadata in `NowcastResult` / `ForecastResult` / `MeteorologicalField`.
   - **Resolution**: Backend stores the audit record and execution metrics in `model_runs` table when runs are orchestrated; ML service provides `run_id`, `model_version`, `data_version`, and provenance dictionaries.
3. **Demo Fixtures**:
   - Backend has rich JSON fixtures in `contracts/fixtures/demo-event/`.
   - **Resolution**: The ML service fallback and `StubMLProvider` leverage these fixtures, preserving offline demo capability.

---

## 6. Missing Integration Points

1. **ML Service Implementation (`src/jalrakshak_ml/serving/app.py`)**:
   - The ML codebase has no active HTTP server implementation (only `__init__.py`).
   - Needs: FastAPI application with endpoints for `/health`, nowcasting, inundation, risk assessment, report verification, and model status.
2. **Backend Provider Switch**:
   - In `backend/app/integrations/ml/provider.py`:
     ```python
     def get_ml_provider() -> MLProvider:
         # Hardcoded StubMLProvider
         return StubMLProvider()
     ```
   - Needs: Update factory to check `settings.ML_PROVIDER`. If `"service"`, return `HttpMLProvider(base_url=settings.ML_SERVICE_URL, auth_token=settings.ML_SERVICE_TOKEN)`.
3. **ML Inference Adapter**:
   - Adapter in `src/jalrakshak_ml/serving/` that invokes `PystepsNowcast` on current/demo radar-satellite tensors, generates synthetic/calibrated raster manifests, computes H3 risk indices for Mumbai wards, and verifies field photos.

---

## 7. Schema Mismatches & Data Translation

| Dimension | ML Representation | Backend Representation | Translation Strategy |
| :--- | :--- | :--- | :--- |
| **Nowcast Output** | `NowcastResult` (3D NumPy array `[T, H, W]`, `units="mm/h"`) | `NowcastManifest` (`cog_url`, `bounds`, `lead_time_minutes`, `manifest_id`) | ML service saves/serves raster artifact (or provides direct MinIO/local URL) and returns the JSON manifest conforming to `nowcast-manifest.schema.json`. |
| **Risk Representation** | 2D raster / spatial arrays | List of scored H3 cells (`h3_cell_id`, `risk_level`, `confidence`, `flood_depth_m`, `rainfall_rate_mm_h`, `ward_id`) | ML service aggregates spatial grid into canonical H3 resolution 8-9 cells covering Mumbai pilot region. |
| **Flood Depth** | Water depth / flood susceptibility index | `flood_depth_m` (float meters) | **Scientific safety rule**: Only report physical meters if calibrated; otherwise label clearly as relative inundation / flood index. |
| **Quality vs Confidence** | `quality_score` [0, 1] (data health) and `confidence` [0, 1] (model certainty) | Backend `RiskCell.confidence`, `WeatherSource.quality_score` | **Never collapse quality and confidence into one field**. Maintain both explicitly in response payloads. |

---

## 8. Dependency & Version Conflicts

| Component | Backend Environment | ML Environment | Isolation Strategy |
| :--- | :--- | :--- | :--- |
| **Python Runtime** | Python 3.12 / 3.14 (`backend/.venv`) | Python 3.11.16 Conda (`jalrakshak`) | Separate processes! Backend runs via `uv`, ML service runs via conda `jalrakshak`. |
| **C/C++ Libraries** | None required directly (pure wheels) | GDAL 3.12, eccodes 2.48, libnetcdf | Isolated inside ML conda environment. Backend never imports GDAL or eccodes. |
| **PyTorch / ML** | Not installed in backend | PyTorch 2.14, pysteps 1.21.5 | Isolated inside ML process. Backend stays lightweight and fast. |
| **Pydantic** | Pydantic 2.13+ | Pydantic 2.13+ | Fully compatible JSON contracts over HTTP. |

---

## 9. Environment Variable Requirements

Add to `sih backend/backend/.env.example` and `sih backend/.env`:
```env
# ML Service Connection
ML_SERVICE_URL=http://localhost:8001
ML_SERVICE_TOKEN=dev-ml-token
ML_PROVIDER=service   # Set to 'service' to connect to live ML; 'stub' for offline fallback
```

Add to `jalrakshak-ml-starter/.env.example` (and create `.env` locally without committing secrets):
```env
ML_PORT=8001
ML_HOST=0.0.0.0
ML_AUTH_TOKEN=dev-ml-token
ML_MODEL_VERSION=pysteps-lk-v1
ML_DATA_DIR=data/processed
```

---

## 10. Proposed Integration Architecture

```
                       +-----------------------------+
                       |      Mobile & Web Client    |
                       +--------------+--------------+
                                      |
                                      v
                       +-----------------------------+
                       |    FastAPI Core Backend     |
                       |       (Port 8000)           |
                       +--------------+--------------+
                                      |
                      app/integrations/ml/provider.py
                                      |
                     [ settings.ML_PROVIDER == "service" ]
                                      |
                                      v
                       +-----------------------------+
                       |       HttpMLProvider        |
                       |     (3-State Circuit        |
                       |         Breaker)            |
                       +--------------+--------------+
                                      |
                        HTTP POST / Bearer Token
                       (Timeout: 5.0s, Retries: 2)
                                      |
                                      v
+========================================================================+
|                     FastAPI ML Inference Service                       |
|                       (Port 8001, Conda Env)                           |
+------------------------------------------------------------------------+
| Endpoints:                                                             |
|  - GET  /health                                                        |
|  - POST /internal/v1/nowcast          (Alias: /internal/ml/nowcast)    |
|  - POST /internal/v1/inundation       (Alias: /internal/ml/inundation) |
|  - POST /internal/v1/risk             (Alias: /internal/ml/risk-assess)|
|  - POST /internal/v1/report-verification (Alias: /internal/ml/verify)  |
|  - GET  /internal/v1/models/status                                     |
|  - GET  /internal/v1/runs/{run_id}                                     |
+------------------------------------------------------------------------+
                                      |
                +---------------------+---------------------+
                |                     |                     |
                v                     v                     v
     +--------------------+ +--------------------+ +--------------------+
     |   PystepsNowcast   | | Hydro Flood Model  | | Vision Verifier    |
     |  (Lucas-Kanade OF) | | (Inundation/Depth) | | (Report Classifier)|
     +--------------------+ +--------------------+ +--------------------+
```

---

## 11. Files That Need Modification / Creation

### In `sih backend/`:
1. `backend/app/integrations/ml/provider.py` [MODIFY]: Update `get_ml_provider()` to inspect `settings.ML_PROVIDER` and return `HttpMLProvider` when `"service"`.
2. `backend/app/integrations/ml/http_provider.py` [MODIFY]: Support canonical `/internal/v1/` routes while preserving fallback and circuit breaker.
3. `backend/.env.example` [MODIFY]: Ensure `ML_SERVICE_URL`, `ML_SERVICE_TOKEN`, `ML_PROVIDER` are documented.

### In `jalrakshak-ml-starter/`:
1. `src/jalrakshak_ml/serving/__init__.py` [MODIFY]: Expose serving module exports.
2. `src/jalrakshak_ml/serving/schemas.py` [NEW]: Pydantic DTOs for requests and responses matching backend contracts.
3. `src/jalrakshak_ml/serving/service.py` [NEW]: Inference orchestrator coordinating `PystepsNowcast`, H3 risk scoring, and flood manifests.
4. `src/jalrakshak_ml/serving/app.py` [NEW]: FastAPI application with security middleware, health checks, versioned routes, and alias routes.
5. `tests/test_serving_integration.py` [NEW]: End-to-end integration tests verifying ML endpoints and contract adherence.
6. `scripts/start_ml_service.py` [NEW]: Helper runner script to launch the ML service.

---

## 12. Files That Must Remain Untouched

- **Backend core logic**:
  - `backend/app/api/v1/alerts.py` (Human approval gate MUST NOT be automated by ML)
  - `backend/app/domains/incidents/state_machine.py` (Strict incident lifecycle)
  - `backend/app/db/models.py` (Existing database tables and PostGIS geometry)
  - `backend/app/core/security.py` (Supabase authentication and role matrix)
  - All 30 existing backend test files in `backend/tests/`
- **ML core logic**:
  - All Phase 4E rich GFS replay data and scripts (`scripts/prepare_gfs_rich_replay.py`, `src/jalrakshak_ml/gfs_replay/`)
  - Locked test set split catalogs (`data/catalogs/mumbai_rainfall_events_v1.json`)
  - PySTEPS adapter core logic (`src/jalrakshak_ml/nowcast/pysteps_adapter.py`)
  - GFS / GPM ingestion adapters (`src/jalrakshak_ml/weather/`)

---

## 13. Risks & Regressions

| Risk | Likelihood | Impact | Mitigation |
| :--- | :---: | :---: | :--- |
| **ML Service down / unstarted** | High | Low | Circuit breaker trips to `OPEN` and `HttpMLProvider` fast-falls back to `StubMLProvider` with zero user-facing crash. |
| **Slow inference (>5.0s)** | Medium | Low | 5.0-second HTTP timeout; automatic fallback to deterministic stub. |
| **Schema drift / mismatch** | Low | High | All requests and responses are strictly validated against `contracts/schemas/*.schema.json` using `jsonschema` in automated tests. |
| **Locked test data exposure** | Low | Critical | ML serving explicitly uses operational baseline (pySTEPS) or historical demo events; locked test events are never accessed. |
| **Scientific misrepresentation** | Low | High | Manifests clearly specify model versions (`pysteps-lk-v1`), data sources (`GPM_IMERG_V07`), and distinguish `quality_score` from `confidence`. |

---

## 14. Exact Implementation Plan

- [x] **GATE A**: Complete Architecture & Contract Audit (`INTEGRATION_AUDIT.md`)
- [ ] **GATE B**: Implement ML Serving Layer & Schemas (`jalrakshak-ml-starter/src/jalrakshak_ml/serving/`)
  - Implement request/response schemas adhering to `contracts/schemas/`
  - Implement inference coordinator wrapping `PystepsNowcast` and Mumbai H3 risk generation
  - Implement FastAPI app with authentication and both `/internal/v1/` and `/internal/ml/` routes
  - Validate with dedicated pytest suite
- [ ] **GATE C**: Connect Backend `MLProvider` to Live Service
  - Update `get_ml_provider()` in `backend/app/integrations/ml/provider.py`
  - Ensure `HttpMLProvider` works seamlessly with both live service and stub fallback
  - Run all 81 existing backend tests to guarantee 0 regressions
- [ ] **GATE D**: Application Flow Verification
  - Verify nowcast manifest generation flow
  - Verify inundation manifest flow
  - Verify H3 risk cells query and pagination
  - Verify citizen report verification flow
- [ ] **GATE E**: End-to-End Smoke Test & Documentation
  - Execute live backend-to-ML HTTP integration test
  - Verify circuit breaker tripping and recovery
  - Verify all 10 flags and deliverable tables
