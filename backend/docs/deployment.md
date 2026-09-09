# JalRakshak AI — Production Deployment Guide

This guide details multi-container deployment, TLS termination, storage setup, and production checklist requirements.

---

## 1. Single-Node Docker Compose Deployment

### Step 1: Clone Repository & Configure Environment
```bash
git clone <repo_url> jalrakshak
cd jalrakshak
cp .env.example .env
```
Edit `.env` to supply production secrets:
- `POSTGRES_PASSWORD`: High-entropy database password.
- `MINIO_ACCESS_KEY` & `MINIO_SECRET_KEY`: Private storage credentials.
- `SUPABASE_JWT_SECRET`: Minimum 32-character secret matching Supabase Auth.
- `APP_SECRET`: Cryptographic session secret.
- `APP_ENV`: Set to `production`.
- `AUTH_MODE`: Set to `supabase`.

### Step 2: Launch Stack
```bash
docker compose up -d --build
```
This boots all 12 services:
- `nginx` (Port 80/443)
- `backend` (FastAPI, internal port 8000)
- `db` (PostgreSQL 16 + PostGIS, port 5432)
- `redis` (Port 6379)
- `minio` (S3 storage, port 9000/9001)
- `celery_worker` & `celery_beat` (Async job processing)
- `titiler` (Raster map tiles)
- `pg_tileserv` (Vector map tiles)
- `ml_stub` (Internal inference provider)
- `prometheus` (Port 9090)
- `grafana` (Port 3000)

### Step 3: Run Database Migrations
```bash
docker compose exec backend alembic upgrade head
```

### Step 4: Verify System Readiness
```bash
curl http://localhost/ready
```
Expected output:
```json
{
  "ready": true,
  "environment": "production",
  "dependencies": {
    "database": "healthy",
    "redis": "healthy",
    "object_store": "healthy"
  }
}
```

---

## 2. TLS & SSL Termination Configuration

In `docker/nginx/nginx.conf`, configure SSL certificates for HTTPS:
```nginx
server {
    listen 443 ssl http2;
    server_name api.jalrakshak.org;

    ssl_certificate /etc/ssl/certs/jalrakshak.crt;
    ssl_certificate_key /etc/ssl/private/jalrakshak.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # ... remaining location blocks ...
}

server {
    listen 80;
    server_name api.jalrakshak.org;
    return 301 https://$host$request_uri;
}
```

---

## 3. Object Storage Private Bucket Policy

To adhere to security requirements:
- MinIO / S3 buckets are **never made public**.
- Client uploads use short-lived presigned URLs generated via `POST /api/v1/reports/upload-intent`.
- Raster and vector tiles are cached and authenticated through the backend or internal proxy.

---

## 4. Production Checklist

- [ ] `.env` is populated with strong random secrets and excluded from git (`.gitignore`).
- [ ] Database credentials restricted to local Docker network.
- [ ] Prometheus metrics endpoint (`/metrics`) protected by firewall or internal network.
- [ ] Grafana default admin password changed.
- [ ] Log level set to `INFO` or `WARNING`.
- [ ] Automated daily backup job configured for PostgreSQL PostGIS volume.
