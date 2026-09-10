# JalRakshak Mobile Frontend Implementation Matrix

Audit date: 2026-09-10. Client root: `mobile/`. Runtime data comes only from the public backend `/api/v1` surface. `READY` means the route and backend capability exist; `PARTIAL` means the screen is complete but an explicitly identified backend/native dependency remains unavailable.

| # | Screen | Route | Role | Status | Components / data states | Actual backend endpoints | Push / offline | Test note |
|---:|---|---|---|---|---|---|---|---|
| 1 | Login | `/(auth)/login` | Both | PARTIAL | Validation, password reveal, loading/error, role redirect | No token-issuance route; backend only validates JWT or mock headers | SecureStore session; expired-session copy | Production identity provider required |
| 2 | Onboarding / Permissions | `/(citizen)/onboarding` | Citizen | READY | Contextual location, notification, camera explanations | Device registration occurs only after opt-in | Reduced capability supported | Manual permission smoke |
| 3 | Home Dashboard | `/(citizen)/(tabs)/home` | Citizen | READY | Risk, rainfall horizons, quick actions; loading/error/degraded/empty | `GET /mobile/home` | Query cache / offline banner | Backend integration regression |
| 4 | Live Risk Map | `/(citizen)/(tabs)/map` | Citizen | PARTIAL | Layer controls, legend, detail state | `GET /map/risk`, `/map/incidents`, `/map/reports`, `/map/alerts` | Cached query state | Native map rendering needs dev build |
| 5 | Rain Forecast | `/(citizen)/rainfall` | Citizen | READY | +30/+60/+90/+120 slots, quality vs confidence | `GET /mobile/home` | Cached last response | Empty when provider has no horizons |
| 6 | Flood Risk | `/(citizen)/flood` | Citizen | READY | Risk/action guidance, no depth fabrication | `GET /mobile/home`, `/risk/cells` | Cached response | Exact depth unavailable state |
| 7 | Alerts / History | `/(citizen)/(tabs)/alerts` | Citizen | READY | Active/recent/expired UI, list states | `GET /map/alerts` | Poll/cache; push category | Backend has no read-state persistence |
| 8 | Alert Detail | `/(citizen)/alerts/[id]` | Citizen | PARTIAL | Severity, instruction, area/timing | Derived from `GET /map/alerts`; no public `GET /alerts/{id}` | `alert_id` deep link | Missing detail endpoint documented |
| 9 | Report Flood | `/(citizen)/(tabs)/report` | Citizen | READY | Category, severity, description, GPS, evidence, review | `POST /reports/draft` | Local UI draft is not called submitted | Service tests |
| 10 | Camera / Gallery | `/(citizen)/report-capture` | Citizen | READY | Camera preview, retake, gallery selection | No AI call from device | Contextual permissions | Physical-device smoke required |
| 11 | Submission Success | `/(citizen)/reports/success` | Citizen | READY | Draft vs submitted distinction | Result of signed upload flow | No false submission | Route smoke |
| 12 | Verification Status | `/(citizen)/reports/[id]` | Citizen | READY | Polling, evidence card, exact depth unavailable | `GET /reports/{id}`, `/reports/{id}/status` | `report_id` deep link | Null-depth regression |
| 13 | Nearby Incidents | `/(citizen)/incidents` | Citizen | READY | Virtualized list states | `GET /incidents` | Cached query | API test |
| 14 | Incident Detail | `/(citizen)/incidents/[id]` | Citizen | READY | Public-safe summary/timeline | `GET /incidents/{id}` | `incident_id` deep link | Backend currently returns fallback record for unknown ID |
| 15 | Watch Locations | `/(citizen)/watch-locations` | Citizen | READY | List/add/edit/delete navigation | `GET /watch-locations` | Cached query | CRUD backend regression |
| 16 | Add/Edit Watch Location | `/(citizen)/watch-locations/edit` | Citizen | READY | Coordinates, GPS, threshold, push toggle | `POST/PATCH/DELETE /watch-locations` | Online mutation | No fake geocoding |
| 17 | Profile | `/(citizen)/(tabs)/profile` | Citizen | PARTIAL | Session identity/role | No profile endpoint | Secure session only | Editing intentionally unavailable |
| 18 | Settings | `/(citizen)/settings` | Citizen | READY | Privacy, permissions, data freshness, logout | Device unregister architecture | Local | Smoke |
| 19 | Notification Preferences | `/(citizen)/notification-preferences` | Citizen | PARTIAL | Categories, permission, honest persistence status | `POST/DELETE /devices/push-token`; no preferences endpoint | Native push requires credentials | No inert persisted toggles |
| R1 | Responder Dashboard | `/(responder)/dashboard` | Responder | READY | Counts, connectivity, current dispatch | `GET /responders/tasks` | Cached tasks/offline banner | Role-scoped by backend |
| R2 | Assigned Tasks | `/(responder)/tasks` | Responder | READY | Virtualized task list/status | `GET /responders/tasks` | Cached | API test |
| R3 | Task Detail | `/(responder)/tasks/[id]` | Responder | READY | Instructions, notes, real actions | `POST /responders/tasks/{id}/action` | SQLite outbox + optimistic version | Only backend-supported actions |
| R4 | Responder Incident | `/(responder)/incidents/[id]` | Responder | READY | Operational context | `GET /incidents/{id}` | Cached | Authorization remains backend-owned |
| R5 | Field Evidence | `/(responder)/evidence` | Responder | PARTIAL | Honest unavailable state | Dedicated responder upload endpoint MISSING | Not queued | Citizen endpoint is not reused |
| R6 | Offline Sync | `/(responder)/sync` | Responder | READY | Pending/syncing/failed, retry | `POST /sync/batch` | UUID idempotency + base version | Uses actual batch schema |

## Actual backend capability audit

| Capability | Status | Evidence / gap |
|---|---|---|
| JWT validation and server-side RBAC | READY | `backend/app/core/security.py`; roles are read from signed claims in non-mock mode |
| Production sign-in/token issuance | MISSING | No `/api/v1/auth/*` route. Mobile cannot mint or directly request privileged credentials. |
| Aggregated mobile home | READY, DEGRADED IN STUB | `GET /api/v1/mobile/home`; patched to identify `DEMO_FIXTURE` and omit invented horizon values |
| Public alert feed | READY | `GET /api/v1/map/alerts` |
| Public alert detail | MISSING | Alert router exposes draft/approve/publish/CAP only |
| Incidents list/detail | READY | `GET /api/v1/incidents`, `GET /api/v1/incidents/{id}` |
| Signed citizen media | READY | Draft → intent → direct PUT → complete → status |
| Watch-location CRUD | READY | POST/GET/PATCH/DELETE |
| Device token lifecycle | READY | POST/DELETE `/api/v1/devices/push-token` |
| Notification preference persistence | MISSING | No preference schema or route |
| Responder tasks/actions | READY | `GET /responders/tasks`, `POST /responders/tasks/{id}/action` |
| Responder evidence upload | MISSING | No dedicated endpoint/contract |
| Offline idempotent sync | READY | Actual route is `POST /api/v1/sync/batch`, not the stale `/sync/mutations` documentation |
| OS push delivery | PARTIAL | Backend provider defaults to console; no FCM/APNs credentials committed |
| Realtime mobile socket | NOT_APPLICABLE | App uses push/query refresh; no invented mobile socket |

## Scientific and privacy boundaries

- `exact_depth_m` is rendered as “Not available” when null. Mobile performs no depth inference.
- GPM is not labeled radar; the home route no longer claims radar availability without provider evidence.
- Coarse NWP alignment is not described as new 30-minute information.
- The client never calls ML, Groq, NVIDIA, PostgreSQL, Supabase service-role, or source weather APIs.
- Demo fixtures remain backend-side and are explicitly surfaced as `DEMO_FIXTURE`, never live operational truth.
