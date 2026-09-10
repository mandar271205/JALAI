# JalRakshak AI — Deployment & Infrastructure (`infra/`)

This directory contains container configurations and orchestration definitions for running the complete JalRakshak stack.

---

## Services Architecture

| Service | Port | Description | Dockerfile |
| :--- | :--- | :--- | :--- |
| **PostgreSQL / PostGIS** | `5432` | Primary database with spatial extensions | Official `postgis/postgis:16-3.4` |
| **Redis** | `6379` | Pub/Sub event broker & ephemeral caching | Official `redis:7-alpine` |
| **Backend Gateway** | `8000` | FastAPI application platform & business logic | `backend/docker/Dockerfile` |
| **ML Inference Service** | `8001` | Numerical nowcast, flood, risk & AI decision support | `infra/docker/Dockerfile.ml` |

---

## Local Startup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Start all services using Docker Compose:
   ```bash
   docker compose up --build
   ```
3. Verify service health:
   - Backend: `http://localhost:8000/health`
   - ML Serving: `http://localhost:8001/health`
