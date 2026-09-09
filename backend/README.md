# JalRakshak AI — Backend + Platform Engineering

**Smart India Hackathon 2026** | **Problem Statement**: SIH26071  
**Theme**: Disaster Management  
**Team**: NeuroBots (Subteam 2: Backend + Platform Engineering)

---

## Executive Summary

**JalRakshak AI** is an operational backend platform designed to ingest high-volume multi-source meteorological telemetry (radar, satellite, automated rain gauges, numerical weather prediction models), coordinate real-time precipitation nowcasting and hydrodynamic inundation models, disseminate standardized OASIS CAP 1.2 emergency alerts, provide flood-aware routing for first responders, and optimize emergency resource allocations during extreme urban flood events.

Built as a high-performance **modular monolith**, the backend guarantees strict architectural boundaries: public clients interact exclusively through secure API gateways, while internal machine learning inference engines and databases remain isolated behind resilient circuit breakers.

---

## Key System Capabilities

- **High-Resolution Geospatial Risk Engine**: Uber H3 discrete global grid system (Resolution 8-9) with PostGIS GIST spatial indexing for sub-50ms bounding box queries.
- **Resilient ML Integration**: HTTP-based orchestration implementing `internal-ml-openapi.yaml` with automated 3-state circuit breaking and fallback to offline demo caches.
- **OASIS CAP 1.2 Emergency Alerts**: Multi-stage state machine (`DRAFT` $\rightarrow$ `APPROVED` $\rightarrow$ `PUBLISHED`), standard XML serialization, and push notification fan-out.
- **Google OR-Tools Emergency Resource Optimization**: Mixed-integer programming (MIP) to optimally allocate dewatering pumps, rescue teams, and relief shelters without auto-dispatching (mandating human authorization).
- **Citizen Field Reports**: 3-step direct presigned S3 upload, AI vision classification, automated incident correlation, and human review override.
- **Advisory Lower-Risk Routing**: Dijkstra cost model heavily penalizing waterlogged segments and excluding submerged roads (always labeled *"advisory only; not guaranteed safe"*).
- **Offline-First Synchronization**: Batch mutation processing (`POST /api/v1/sync/batch`) with client-id idempotency and conflict resolution.
- **Deterministic Historical Replay**: Virtual-clock replay benchmark (Mumbai 26 July Cloudburst) with time scrubbing, precomputed tile manifests, and predicted-vs-observed accuracy metrics.
- **Append-Only Cryptographic Audit System**: Tamper-evident SHA-256 before/after hashing for state changes.
- **Full-Stack Observability**: OpenTelemetry distributed tracing (`trace_id`), Prometheus metrics export (`GET /metrics`), and 7 pre-configured Grafana dashboards.

---

## Architecture Overview

```
                      +-----------------------------+
                      |   Mobile Apps & Web Client   |
                      +--------------+--------------+
                                     |
                           (HTTPS / WSS / REST)
                                     |
                                     v
                      +--------------+--------------+
                      |     Nginx Reverse Proxy     |
                      |  (TLS / Rate Limits / WS)   |
                      +--------------+--------------+
                                     |
         +---------------------------+---------------------------+
         |                           |                           |
         v                           v                           v
+------------------+       +-------------------+       +-------------------+
|  FastAPI Backend |       | TiTiler COG Tiles |       | pg_tileserv (MVT) |
| (Core Platform)  |       | (Raster Depth)    |       | (Vector Risk)     |
+--------+---------+       +---------+---------+       +---------+---------+
         |                           |                           |
         +-------------+-------------+---------------------------+
                       |
                       v
     +-----------------+-----------------+
     | PostgreSQL 16 + PostGIS Spatial DB |
     | Redis 7 (Cache & Streams)         |
     | MinIO / S3 Private Storage        |
     | Celery Async Workers & Beat       |
     +-----------------+-----------------+
                       |
         (HTTP REST + Circuit Breaker)
                       |
                       v
     +-----------------+-----------------+
     |    Internal ML Inference Service  |
     |  (Precipitation / Hydrodynamics)  |
     +-----------------------------------+
```

---

## Quickstart Guide

### 1. Local Python Development
```bash
# 1. Clone repository
cd jalrakshak/backend

# 2. Set up virtual environment using uv or venv
uv venv
source .venv/bin/activate

# 3. Install dependencies
uv pip install -e ".[dev]"

# 4. Run automated test suite
pytest -v

# 5. Start development server
uvicorn app.main:app --reload --port 8000
```

### 2. Multi-Container Docker Compose Stack
```bash
# Copy placeholder configuration
cp .env.example .env

# Launch complete 12-service stack
docker compose up -d --build

# Run database migrations
docker compose exec backend alembic upgrade head

# Access services:
# - API & Docs: http://localhost:8000/docs
# - Prometheus: http://localhost:9090
# - Grafana:    http://localhost:3000 (admin / admin)
# - MinIO:      http://localhost:9001
```

---

## Detailed Documentation Directory

Comprehensive platform documentation is maintained in [`docs/`](file:///Users/jayshinde/Documents/sih%20/docs):
- [Architecture & System Design](file:///Users/jayshinde/Documents/sih%20/docs/architecture.md)
- [API Usage & Curl Quickstart](file:///Users/jayshinde/Documents/sih%20/docs/api_usage.md)
- [RBAC Role Matrix](file:///Users/jayshinde/Documents/sih%20/docs/role_matrix.md)
- [Demo Seeding & Historical Replay](file:///Users/jayshinde/Documents/sih%20/docs/demo_seed_replay.md)
- [Troubleshooting & Runbook](file:///Users/jayshinde/Documents/sih%20/docs/troubleshooting.md)
- [Production Deployment Guide](file:///Users/jayshinde/Documents/sih%20/docs/deployment.md)

---

## Definition of Done Verification

| Capability Area | Status | Verification Summary |
| :--- | :---: | :--- |
| **OpenAPI / Schemas** | ✅ Verified | 44 OpenAPI endpoints, 12 JSON schemas validated |
| **PostgreSQL / PostGIS** | ✅ Verified | 5 Alembic migrations; clean schema generation from zero |
| **Object Storage (S3/MinIO)** | ✅ Verified | Presigned direct uploads with private bucket protection |
| **Weather Ingestion** | ✅ Verified | 4 telemetry adapters with `source.degraded` fail-safe |
| **Raster & Vector Tiles** | ✅ Verified | TiTiler COG & pg_tileserv MVT manifests with caching |
| **ML Integration** | ✅ Verified | Circuit breaker, timeout, retry, and fallback to stub |
| **Incidents State Machine** | ✅ Verified | 7 lifecycle states, mandatory dismissal reasons, timeline |
| **CAP 1.2 Alerts** | ✅ Verified | OASIS standard XML serializer & push notification retry |
| **Resource Optimization** | ✅ Verified | Google OR-Tools MIP solver; human approval required |
| **Historical Replay** | ✅ Verified | Virtual clock, pause/play/scrub, predicted-vs-observed metrics |
| **Cryptographic Audit** | ✅ Verified | SHA-256 before/after hashing across critical actions |
| **Security Hardening** | ✅ Verified | HSTS/CSP headers, rate limiting (429), 10MB limit (413), MIME checks |
| **Observability** | ✅ Verified | OpenTelemetry tracing, Prometheus `/metrics`, Grafana dashboards |
| **CI/CD Pipeline** | ✅ Verified | GitHub Actions 5-stage workflow (`.github/workflows/ci.yml`) |
| **Automated Tests** | ✅ Verified | **81 / 81 tests passing** across unit, integration, and security suites |
