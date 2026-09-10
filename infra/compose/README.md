# JalRakshak AI — Compose Infrastructure (`infra/compose/`)

This directory contains container orchestration manifests for the JalRakshak AI multi-tier platform.

---

## Service Stacks

1. **Root Orchestration (`docker-compose.yml`)**:
   - Spawns all core dependencies:
     - `postgres` (PostgreSQL 17 / PostGIS)
     - `redis` (In-memory broker and cache)
     - `backend` (FastAPI Platform Gateway on `:8000`)
     - `ml-serving` (ML Inference & Fallback Service on `:8001`)

2. **Usage**:
   ```bash
   # Start the full local stack
   docker compose -f docker-compose.yml up -d

   # Check health
   curl http://localhost:8000/health
   curl http://localhost:8001/health
   ```
