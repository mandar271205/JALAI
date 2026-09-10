import time
import requests

PAGES = [
    "/command-center",
    "/map",
    "/rainfall",
    "/flood",
    "/risk",
    "/incidents",
    "/reports",
    "/alerts",
    "/analytics",
    "/system",
    "/audit"
]

BACKEND_ENDPOINTS = [
    "/api/v1/dashboard/summary",
    "/api/v1/weather/current",
    "/api/v1/map/risk",
    "/api/v1/map/incidents",
    "/api/v1/risk/cells",
    "/api/v1/incidents",
    "/api/v1/reports",
    "/api/v1/alerts",
    "/api/v1/models/status",
    "/api/v1/audit/logs"
]

print("=== MEASURING FRONTEND PAGES (http://localhost:3000) ===")
page_results = {}
for page in PAGES:
    url = f"http://localhost:3000{page}"
    t0 = time.perf_counter()
    try:
        r = requests.get(url, timeout=10)
        dt = (time.perf_counter() - t0) * 1000
        page_results[page] = (r.status_code, dt, len(r.content))
        print(f"PAGE {page:20s}: status={r.status_code} in {dt:6.1f}ms (size={len(r.content):,} bytes)")
    except Exception as e:
        print(f"PAGE {page:20s}: ERROR {e}")

print("\n=== MEASURING BACKEND APIS (http://127.0.0.1:8000) ===")
headers = {"X-Mock-Role": "disaster_manager"}
api_results = {}
for ep in BACKEND_ENDPOINTS:
    url = f"http://127.0.0.1:8000{ep}"
    t0 = time.perf_counter()
    try:
        r = requests.get(url, headers=headers, timeout=10)
        dt = (time.perf_counter() - t0) * 1000
        api_results[ep] = (r.status_code, dt, len(r.content))
        print(f"API  {ep:30s}: status={r.status_code} in {dt:6.1f}ms")
    except Exception as e:
        print(f"API  {ep:30s}: ERROR {e}")
