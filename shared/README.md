# JalRakshak AI — Shared System Contracts & Constants (`shared/`)

This directory contains language-agnostic interface specifications, schemas, and constant definitions shared across:
- `backend/` (FastAPI backend platform)
- `ml/` (Scientific ML & decision support)
- `web/` (Client dashboard)
- `mobile/` (Field responder & citizen app)

---

## Directory Contents

- `contracts/`:
  - `openapi.yaml`: Public API specification for Web and Mobile clients.
  - `internal-ml-openapi.yaml`: Private inter-service contract between Backend and ML serving layer.
  - `websocket-events.json`: Real-time emergency alert and sensor update payload formats.
- `schemas/`: JSON Schema definitions for request validation.
- `constants/`: Canonical numerical thresholds, horizons, and operational status codes.
