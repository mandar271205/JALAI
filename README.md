# JalRakshak AI — Unified Monorepo Platform

**JalRakshak AI** is an operational urban flood and rainfall intelligence platform integrating high-resolution meteorological nowcasting, hydrodynamic physics simulations, multi-criteria risk intelligence, and a resilient 3-model backend AI decision-support layer.

---

## 1. Monorepo Components

The repository is structured into clear, decoupled domains for cross-functional engineering:

| Component | Directory | Responsibility | Technology Stack |
| :--- | :--- | :--- | :--- |
| **Backend Gateway** | [`backend/`](file:///c:/Users/sawan/OneDrive/Desktop/JALAI/jalrakshak-ai/backend) | Public API gateway, DB persistence, citizen reports, alerts, WebSocket broadcast | FastAPI, SQLAlchemy Async, PostGIS, Redis |
| **Scientific ML & Physics** | [`ml/`](file:///c:/Users/sawan/OneDrive/Desktop/JALAI/jalrakshak-ai/ml) / [`src/`](file:///c:/Users/sawan/OneDrive/Desktop/JALAI/jalrakshak-ai/src) | Rainfall nowcast, LISFLOOD-FP 8.0.3, FloodFNO, risk engine, Groq/NVIDIA AI fallback | PyTorch, PySTEPS, NumPy, Rasterio, Uvicorn |
| **Web Application** | [`web/`](file:///c:/Users/sawan/OneDrive/Desktop/JALAI/jalrakshak-ai/web) | Client dashboard for municipal authorities and citizens *(Integration ready)* | Next.js / React / TypeScript |
| **Mobile Application** | [`mobile/`](file:///c:/Users/sawan/OneDrive/Desktop/JALAI/jalrakshak-ai/mobile) | Citizen emergency alerts, field responder reporting, offline cached maps *(Integration ready)* | Flutter / React Native |
| **Shared Contracts** | [`shared/`](file:///c:/Users/sawan/OneDrive/Desktop/JALAI/jalrakshak-ai/shared) | Language-agnostic OpenAPI specs, JSON schemas, system constants, WebSocket events | OpenAPI 3.1, JSONSchema |
| **Infrastructure** | [`infra/`](file:///c:/Users/sawan/OneDrive/Desktop/JALAI/jalrakshak-ai/infra) | Multi-container Docker Compose definitions, Dockerfiles, and deployment guides | Docker, Compose |
| **Review & Quarantine** | [`_to_review_delete/`](file:///c:/Users/sawan/OneDrive/Desktop/JALAI/jalrakshak-ai/_to_review_delete) | Quarantined deletion candidates for manual review *(Absolute No-Delete Policy)* | Markdown, JSON Ledger |

---

## 2. Environment Configuration

1. Copy the unified environment template:
   ```bash
   cp .env.example .env
   ```
2. Configure credentials in `.env`:
   - **Backend**: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`
   - **ML Service**: `ML_SERVICE_URL=http://localhost:8001`, `ML_AUTH_TOKEN=dev-ml-token`
   - **Groq Primary AI (Model 1)**: `GROQ_API_KEY=gsk_...` (Model: `openai/gpt-oss-120b`)
   - **NVIDIA NIM Fast Failover & Heavy Verifier (Models 2 & 3)**: `NVIDIA_API_KEY=nvapi-...`
     - Model 2: `nvidia/nemotron-3.5-lightning-30b-a3b`
     - Model 3: `nvidia/nemotron-3-ultra-550b-a55b`

---

## 3. Local Development Startup

### Option A: Complete Multi-Container Stack (Docker Compose)
Run database, cache, backend platform, and ML inference service together:
```bash
docker compose up --build
```
- **Backend API Gateway**: `http://localhost:8000/docs`
- **ML Serving Service**: `http://localhost:8001/docs`

### Option B: Local Native Development
1. **Activate the Conda ML environment**:
   ```bash
   conda activate jalrakshak
   pip install -e .
   ```
2. **Start the ML Inference Service**:
   ```bash
   uvicorn jalrakshak_ml.serving.app:app --host 0.0.0.0 --port 8001 --reload
   ```
3. **Start the Backend Service** (in a separate terminal):
   ```bash
   cd backend
   uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

---

## 4. Frontend & Mobile Team Integration

Team members integrating Web or Mobile applications should review the complete guide in [`docs/INTEGRATION_GUIDE.md`](file:///c:/Users/sawan/OneDrive/Desktop/JALAI/jalrakshak-ai/docs/INTEGRATION_GUIDE.md).

### Crucial Integration Rules:
- **Single Point of Contact**: Frontend applications consume the Backend Platform (`http://localhost:8000`) exclusively.
- **Zero Exposed AI Credentials**: Never store Groq or NVIDIA keys in client apps.
- **Truthful Provenance**: Display JalRakshak risk and forecast domain metrics. Never show third-party provider names (e.g. "Groq result", "Nemotron").
- **Depth Sanctity**: Water depth (`depth_m`) is `null` unless calibrated hydrodynamic sensors are online. Do not invent depth measurements.

---

## 5. Review Folder Policy (`_to_review_delete/`)

To guarantee **zero accidental data loss**, this repository enforces an **Absolute No-Delete Rule**.
- Redundant scripts, duplicate notebooks, empty logs, and legacy defect builders are moved to `_to_review_delete/`.
- Every quarantined item is cataloged in `_to_review_delete/review_manifest.json` and [`docs/REVIEW_DELETE_CANDIDATES.md`](file:///c:/Users/sawan/OneDrive/Desktop/JALAI/jalrakshak-ai/docs/REVIEW_DELETE_CANDIDATES.md).
- The repository owner will inspect and approve any final manual deletions.

---

## 6. Testing & Quality Assurance

Run the comprehensive test suite:
```bash
pytest tests/test_decision_support.py -v
pytest tests/test_serving_integration.py -v
pytest tests/test_phase9_flood_physics_path.py -v
pytest tests/test_phase4e_final_stack.py -v
```

Linting and compilation checks:
```bash
ruff check .
python -m compileall src tests shared -q
```
