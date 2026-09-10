# JalRakshak AI — Web Application (`web/`)

> [!NOTE]
> This directory is reserved for the **JalRakshak Web Frontend application** (e.g. Next.js, React, or Vite).
> Frontend engineers will implement and deploy the client dashboard within this boundary.

---

## Architectural & Integration Rules

1. **Backend-Only Communication**:
   - The web frontend must communicate **exclusively** with the backend service (typically running on `:8000`).
   - The web app consumes REST endpoints and WebSocket channels exposed by `backend/app/api/`.

2. **No Direct ML Imports**:
   - The frontend must **never** import internal ML Python modules or attempt direct execution of numerical models.
   - All rainfall forecasts, flood hazard assessments, risk matrices, and citizen reports are served as serialized JSON through backend contracts.

3. **Zero Third-Party AI / Provider Exposure**:
   - The frontend must **never** contain external AI credentials (e.g., `GROQ_API_KEY`, `NVIDIA_API_KEY`).
   - UI components must **never** display provider branding (e.g., "Groq Result", "NVIDIA Nemotron", "LLM Fallback").
   - Display truthful, clean JalRakshak domain concepts:
     - **Rainfall Forecast**: Expected intensity bands, horizons (30, 60, 90, 120 min), trend, confidence.
     - **Flood Risk**: Categorical risk (LOW, MODERATE, HIGH, SEVERE), dominant factors, action recommendations.
     - **Water Depth**: Water depth in meters (`depth_m`) is displayed **only** when genuine hydrodynamic solver output is available; otherwise it remains unpopulated/hidden.

4. **Shared Contracts**:
   - Refer to `shared/contracts/openapi.yaml` and `shared/contracts/websocket-events.json` for API schemas and payload contracts.
