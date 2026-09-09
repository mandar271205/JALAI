# JalRakshak AI — Role-Based Access Control (RBAC) Matrix

The system enforces strict server-side authorization and region-scoped permissions across 8 distinct user roles.

---

## 1. Role Definitions

| Role Identifier | Description & Primary Responsibilities |
| :--- | :--- |
| `CITIZEN` | Public user; submits geotagged field reports, views published alerts, and requests advisory routes. |
| `FIELD_RESPONDER` | Ground emergency personnel; receives assigned rescue/inspection tasks, reports water depths, and submits closure evidence. |
| `ANALYST` | Geospatial and weather data specialist; drafts alerts, triggers nowcast runs, and evaluates historical benchmark replays. |
| `ALERT_APPROVER` | Authorized official with regional sign-off authority; reviews and publishes OASIS CAP 1.2 emergency alerts. |
| `MUNICIPAL_OFFICER` | City operations commander; transitions incident statuses, verifies reports, and reviews municipal asset states. |
| `DISASTER_MANAGER` | District disaster management authority (DDMA) commander; generates and approves emergency resource allocation plans. |
| `ML_ADMIN` | Technical machine learning lead; deploys, benchmarks, and updates internal AI model versions and fallback modes. |
| `SUPER_ADMIN` | Root system administrator; full global oversight, administrative settings, and cross-region emergency override. |

---

## 2. Permissions Matrix

| Resource / Endpoint | `CITIZEN` | `FIELD_RESPONDER` | `ANALYST` | `ALERT_APPROVER` | `MUNICIPAL_OFFICER` | `DISASTER_MANAGER` | `ML_ADMIN` | `SUPER_ADMIN` |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **View Risk & Weather APIs** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Submit Field Report (Draft/Upload)** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Request Lower-Risk Routing** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Manage Personal Watch Locations** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **View Assigned Tasks** | ❌ | ✅ (Own) | ❌ | ❌ | ✅ (All) | ✅ (All) | ❌ | ✅ (All) |
| **Complete Task / Record Depth** | ❌ | ✅ | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ |
| **Draft CAP Alert** | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ | ❌ | ✅ |
| **Approve / Publish CAP Alert** | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ | ✅ |
| **Human Review / Override Report** | ❌ | ❌ | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ |
| **Transition Incident Status** | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ |
| **Generate Optimization Plan** | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ | ✅ |
| **Approve & Dispatch Resource Plan** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| **Historical Replay Controls** | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Model Version Activation** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| **Inspect Cryptographic Audit Logs**| ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| **Cross-Region Access Override** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

---

## 3. Regional Scoping Rules
- Operations involving ward or municipal boundaries enforce **regional scoping** (`enforce_regional_access`).
- Officers and Responders assigned to `region: "mumbai"` cannot modify incidents or approve alerts in `region: "pune"`.
- `SUPER_ADMIN` and global `ADMIN` bypass regional constraints for disaster response continuity.
