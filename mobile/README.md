# JalRakshak AI — Mobile Application (`mobile/`)

> [!NOTE]
> This directory is reserved for the **JalRakshak Mobile Application** (e.g. Flutter or React Native).
> Mobile engineers will implement citizen alerts, field reporting, and offline-first sync within this boundary.

---

## Architectural & Integration Rules

1. **Backend-Only Communication**:
   - The mobile client interacts **strictly** with the JalRakshak backend API gateway.
   - The client never interacts directly with internal numerical pipelines or third-party AI endpoints.

2. **Zero Credentials in Binary**:
   - The mobile application bundle must **never** include Groq, NVIDIA NIM, database, or ML serving secrets.
   - All access to backend endpoints uses authenticated citizen or responder session tokens.

3. **Field Reporting & Citizen Submissions**:
   - Citizen ground-truth reports (photo metadata, geo-coordinates, flood observation text) are submitted via `POST /api/v1/reports`.
   - Free text is sanitized on the backend against prompt injection; client should transmit structured geo-tagged payloads.

4. **Offline Resilience**:
   - In accordance with JalRakshak edge principles, the mobile app should cache the latest local hazard tiles and emergency guidance for disconnected operation during extreme weather.

5. **Shared Contracts**:
   - Refer to `shared/contracts/openapi.yaml` for client contracts and schema definitions.
