# JalRakshak AI — Monorepo Architecture & Repository Structure

This document outlines the standardized monorepo layout of JalRakshak AI, defining the structural boundaries, ownership, and responsibilities for all system components.

---

## High-Level Monorepo Structure

```
jalrakshak/
│
├── backend/                      # Backend API Gateway & Platform Services
│   ├── app/                      # Application source (FastAPI)
│   │   ├── api/                  # Versioned HTTP & WebSocket route handlers
│   │   ├── core/                 # Config, security, JWT auth, logging
│   │   ├── db/                   # SQLAlchemy async engine, base model, session
│   │   ├── domains/              # Domain logic (alerts, incidents, reports, risk)
│   │   ├── integrations/         # Upstream clients (ML service, CAP, notifications)
│   │   ├── realtime/             # WebSocket connection manager & Redis pub/sub
│   │   └── workers/              # Asynchronous background tasks
│   ├── migrations/               # Alembic database schema migrations
│   └── tests/                    # Backend integration & unit test suite
│
├── ml/                           # Machine Learning & Physical Simulation Architecture
│   ├── README.md                 # Domain architecture guide
│   └── (src/jalrakshak_ml/)      # Production Python package
│       ├── deep_nowcast/         # Numerical rainfall models (ConvLSTM, PySTEPS, UNet)
│       ├── flood/                # Hydrodynamics (LISFLOOD-FP 8.0.3, FloodFNO, domain)
│       ├── risk/                 # Risk engine (Exposure, Vulnerability, H x E x V)
│       ├── citizen/              # Multimodal report corroboration engine
│       ├── geospatial/           # DEM elevation, slope, and OSM infrastructure pipelines
│       ├── decision_support/     # 3-Model AI Fallback (Groq + NVIDIA NIM failover/verifier)
│       └── serving/              # FastAPI ML inference service (/internal/v1/...)
│
├── web/                          # Future Web Frontend Dashboard (Placeholder)
│   └── README.md                 # Architecture, API consumer rules, and setup guide
│
├── mobile/                       # Future Mobile Application (Placeholder)
│   └── README.md                 # Architecture, citizen reporting, and offline rules
│
├── shared/                       # Cross-Platform Language-Agnostic Assets
│   ├── contracts/                # OpenAPI specs (public & ML internal), WebSocket events
│   ├── schemas/                  # JSON Schemas for request/response validation
│   ├── constants/                # System-wide severity, risk, and horizon constants
│   └── README.md                 # Shared contracts documentation
│
├── infra/                        # Infrastructure, Containers, and Deployment
│   ├── docker/                   # Dockerfiles for Backend and ML services
│   ├── compose/                  # Docker Compose orchestration configurations
│   └── deployment/               # Deployment guides and production topology
│
├── data/                         # Data Manifests, Metadata, and Verification Records
│   ├── metadata/                 # Dataset manifests and split registries
│   └── README.md                 # Data sourcing and license guidelines
│
├── docs/                         # Engineering, Architecture, and Audit Documentation
│   ├── REPOSITORY_STRUCTURE.md   # This document
│   ├── INTEGRATION_GUIDE.md      # Web & Mobile developer onboarding guide
│   ├── REVIEW_DELETE_CANDIDATES.md# Detailed table of quarantined files
│   └── INTEGRATION_AUDIT.md      # Inter-service contract audit report
│
├── reports/                      # Scientific Benchmarks, Forensic Audits, and Reports
│   ├── DECISION_SUPPORT_AI_FALLBACK.md # 3-Model AI fallback architecture report
│   ├── phase11_flood_forensic_audit.md # Hydrodynamic physics evidence audit
│   └── phase11_reproducibility_manifest.json # Complete reproducible research ledger
│
├── _to_review_delete/            # Quarantined Candidates for Manual Review
│   ├── README.md                 # Absolute no-delete policy and review workflow
│   ├── review_manifest.json      # Cryptographic candidate ledger
│   ├── legacy/flood/             # Defective Phase 10 dataset builder (preserved)
│   └── temp/                     # Scratch scripts, empty logs, duplicate notebooks
│
├── .env.example                  # Unified environment template with placeholders
├── docker-compose.yml            # Monorepo multi-container local startup
├── pyproject.toml                # Root Python package build configuration
└── README.md                     # Root project introduction and quickstart
```

---

## Component Boundaries & Invariants

1. **Frontend Isolation**:
   - `web/` and `mobile/` consume backend HTTP/WebSocket endpoints exclusively.
   - They **never** import Python code, communicate directly with the ML service, or hold external AI API keys.

2. **Backend Platform**:
   - `backend/` handles database persistence (PostgreSQL/PostGIS), authentication, citizen reports, incident dispatch, and alerting.
   - It orchestrates requests to the ML service via `backend/app/integrations/ml/http_provider.py` with circuit breakers.

3. **ML & Scientific Integrity**:
   - `ml/` (implemented via `src/jalrakshak_ml/`) executes numerical nowcasts, flood hydrodynamics, and deterministic risk matrices.
   - AI decision support (Groq GPT-OSS-120B + NVIDIA Nemotron 30B/550B) provides interpretation and provisional assessments when numerical models are unavailable.
   - AI outputs **never** override numerical/physics ground truth and **never** invent physical water depth (`depth_m`).

4. **No-Delete Quarantine**:
   - Files are never permanently deleted from source control.
   - Redundant or legacy items are quarantined in `_to_review_delete/` with entries in `review_manifest.json`.
