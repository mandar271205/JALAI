# JalRakshak AI — Troubleshooting & Operations Runbook

This runbook documents operational diagnosis procedures, common failure modes, and automated recovery behaviors.

---

## 1. Machine Learning Provider & Circuit Breaker

### Symptoms
- API responses fall back to default/stubbed outputs.
- Error logs report `CircuitBreakerOpenError` or `ConnectError`.

### Explanation & Behavior
The backend communicates with the ML inference service over HTTP via `HttpMLProvider`. If the internal ML service becomes unreachable or takes longer than the configured timeout:
1. `CircuitBreaker` trips from `CLOSED` $\rightarrow$ `OPEN` after 3 consecutive failures.
2. The backend automatically switches to `StubMLProvider` / offline demo cache.
3. Every 30 seconds, a probe request enters `HALF_OPEN` state. Once the ML service recovers, the circuit resets to `CLOSED`.

### Recovery Action
1. Check the ML service container status:
   ```bash
   docker logs jalrakshak_ml_stub
   ```
2. Verify connectivity:
   ```bash
   curl -I http://localhost:8001/api/v1/internal/health
   ```

---

## 2. Rate Limiting (HTTP 429 Too Many Requests)

### Symptoms
- Client receives HTTP 429 with header `Retry-After: <seconds>`.

### Explanation & Behavior
The backend implements a sliding-window rate limiter (120 requests / 60 seconds) in `RateLimitMiddleware` to prevent DoS attacks.

### Recovery Action
- Respect the `Retry-After` header interval before retrying.
- For load testing scripts, initialize with distributed client IPs or mock auth tokens.

---

## 3. Database Connection Pool Exhaustion

### Symptoms
- Logs report `TimeoutError: QueuePool limit of size 5 overflow 10 reached`.
- `/ready` endpoint reports `"database": "unhealthy"`.

### Explanation & Behavior
FastAPI uses SQLAlchemy asynchronous connection pools (`asyncpg`). Heavy concurrent queries without session cleanup can saturate pool connections.

### Recovery Action
1. Verify active Postgres connections:
   ```sql
   SELECT count(*), state FROM pg_stat_activity GROUP BY state;
   ```
2. Check Prometheus pool gauge:
   ```bash
   curl -s http://localhost:8000/metrics | grep db_pool_connections
   ```
3. In `backend/app/db/session.py`, ensure pool pre-ping and appropriate `pool_size` settings.

---

## 4. Responder Task Conflict (HTTP 409 Conflict)

### Symptoms
- Responder app reports `VERSION_CONFLICT` upon submitting task action.

### Explanation & Behavior
The backend uses optimistic concurrency locking (`version` field) on responder tasks. If two field officers submit updates based on the same prior state, the second update is rejected to prevent race conditions.

### Recovery Action
- The client must re-fetch the latest task state (`GET /api/v1/responders/tasks`), reconcile the evidence/measurements, and re-submit with the updated `base_version`.

---

## 5. Corrupt or Spoofed File Upload (HTTP 422)

### Symptoms
- Citizen upload rejected with `"File spoofing detected"` or `"Malicious content detected"`.

### Explanation & Behavior
The upload pipeline uses `MIMEValidator` to verify binary magic byte signatures (JPEG `\xff\xd8\xff`, PNG, WebP) and scans for embedded malware payloads (`ClamAVStubScanner`).

### Recovery Action
- Ensure the uploaded file is an authentic, unmodified image without prohibited executable wrappers.
