# JalRakshak Mobile E2E Smoke Checklist

Use an Expo development build for camera, native maps, SecureStore and OS notifications. Start the backend with `AUTH_MODE=mock` only for local smoke tests. Production smoke requires a real identity token. Never use locked rainfall evaluation data.

## Citizen

- [ ] Sign in; verify Citizen role routes to Home.
- [ ] Home loads once and clearly shows `DEMO_FIXTURE`/degraded status when provider fallback is active.
- [ ] Risk has a text label in addition to color; no fabricated exact depth appears.
- [ ] Rainfall screen shows only backend-supplied +30/+60/+90/+120 values, or an empty state.
- [ ] Map opens, layer controls work, and unavailable native rendering is explained.
- [ ] Alerts list opens; alert deep link resolves from the public feed.
- [ ] Report validation rejects short text and missing location.
- [ ] Request GPS contextually; deny once and verify reduced-capability state.
- [ ] Request camera/gallery contextually; capture/select JPEG, PNG or WebP under 10 MB.
- [ ] Create draft; confirm it is not labeled submitted yet.
- [ ] Request presigned intent; PUT binary directly to object storage; retry expired URL by restarting intent flow.
- [ ] Complete upload with SHA-256 of actual file bytes; verify backend confirmation before success screen.
- [ ] Open verification status; ensure null depth reads “Not available”.
- [ ] Add, patch and delete a watch location.
- [ ] Opt into notifications; with missing EAS/FCM config verify honest unavailable reason.
- [ ] Open alert/report/incident deep links.
- [ ] Disable network and verify offline/degraded banner with no fake freshness.
- [ ] Log out; verify secure session removed.

## Field responder

- [ ] Sign in as `FIELD_RESPONDER`; verify responder dashboard route.
- [ ] Load role-scoped task list and open a task.
- [ ] Apply `VERIFY_LOCATION`; verify backend transitions to `EN_ROUTE`.
- [ ] Apply `MEASURE_DEPTH` only for a trained responder observation; verify `ON_SCENE`.
- [ ] Open linked incident context.
- [ ] Verify field-evidence screen does not reuse citizen upload or claim submission.
- [ ] Disable network; queue a supported action with mutation UUID and base version.
- [ ] Reconnect; sync through `/api/v1/sync/batch`; verify accepted/duplicate/conflict handling.
- [ ] Complete task using `COMPLETE_TASK`; verify audit-backed server response.
- [ ] Log out.

## Build and accessibility

- [ ] `npm run typecheck`
- [ ] `npm run lint`
- [ ] `npm test`
- [ ] `npm run export:web`
- [ ] Android development build boots on a physical device/emulator.
- [ ] iOS architecture/config validates (macOS is required for native build).
- [ ] Screen reader announces controls; touch targets and contrast are adequate; reduced-motion setting does not block workflows.
