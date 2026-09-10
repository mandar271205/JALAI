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
    "/audit",
    "/simulation"
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
    "/api/v1/simulation/status",
    "/api/v1/models/status",
    "/api/v1/audit/logs"
]

print("================================================================")
print("=== MEASURING PRODUCTION FRONTEND LATENCY (WARMED / PREFETCHED) ===")
print("================================================================")
session = requests.Session()

# First pass (Initial route hit)
first_pass = {}
for page in PAGES:
    url = f"http://localhost:3000{page}"
    t0 = time.perf_counter()
    try:
        r = session.get(url, timeout=10)
        dt = (time.perf_counter() - t0) * 1000
        first_pass[page] = dt
        print(f"FIRST HIT {page:20s}: status={r.status_code} in {dt:6.1f}ms ({len(r.content):,} bytes)")
    except Exception as e:
        print(f"FIRST HIT {page:20s}: ERROR {e}")

print("\n=== MEASURING INSTANT ROUTE NAVIGATION (WARM CACHE / PRODUCTION) ===")
# Second pass (Repeat navigation with warm cache / CDN-like static chunks)
second_pass = {}
for page in PAGES:
    url = f"http://localhost:3000{page}"
    t0 = time.perf_counter()
    try:
        r = session.get(url, timeout=10)
        dt = (time.perf_counter() - t0) * 1000
        second_pass[page] = dt
        print(f"NAV HIT   {page:20s}: status={r.status_code} in {dt:6.1f}ms")
    except Exception as e:
        print(f"NAV HIT   {page:20s}: ERROR {e}")

avg_first = sum(first_pass.values()) / len(first_pass) if first_pass else 0
avg_warm = sum(second_pass.values()) / len(second_pass) if second_pass else 0

print(f"\nAverage First Load: {avg_first:.1f}ms")
print(f"Average Route Navigation (Warm/Prefetched): {avg_warm:.1f}ms")

print("\n================================================================")
print("=== MEASURING BACKEND OPTIMIZED APIS (http://127.0.0.1:8000) ===")
print("================================================================")
headers = {"X-Mock-Role": "disaster_manager"}
api_times = []
for ep in BACKEND_ENDPOINTS:
    url = f"http://127.0.0.1:8000{ep}"
    t0 = time.perf_counter()
    try:
        r = requests.get(url, headers=headers, timeout=10)
        dt = (time.perf_counter() - t0) * 1000
        api_times.append(dt)
        print(f"API {ep:30s}: status={r.status_code} in {dt:6.1f}ms (size={len(r.content):,} bytes)")
    except Exception as e:
        print(f"API {ep:30s}: ERROR {e}")

avg_api = sum(api_times) / len(api_times) if api_times else 0
print(f"\nAverage Backend Endpoint Latency: {avg_api:.1f}ms")
