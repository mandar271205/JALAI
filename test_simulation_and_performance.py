import time
import requests

BASE_BACKEND = "http://127.0.0.1:8000"
headers = {"X-Mock-Role": "disaster_manager"}

print("=== 1. VERIFYING BACKEND APIS ===")
# Test /alerts
r = requests.get(f"{BASE_BACKEND}/api/v1/alerts", headers=headers)
print(f"GET /api/v1/alerts: status={r.status_code}, data={r.json().get('count')} alerts")
assert r.status_code == 200, f"Expected 200, got {r.status_code}"

# Test /assets GET
r = requests.get(f"{BASE_BACKEND}/api/v1/assets", headers=headers)
print(f"GET /api/v1/assets: status={r.status_code}, total={r.json().get('total')}")
assert r.status_code == 200

# Test /assets POST (create custom asset)
custom_asset = {
    "name": "Dharavi Auxiliary Dewatering Pump 05",
    "asset_type": "PUMPING_STATION",
    "ward_id": "G-North",
    "latitude": 19.0410,
    "longitude": 72.8520,
    "inundation_threshold_m": 0.40
}
r = requests.post(f"{BASE_BACKEND}/api/v1/assets", json=custom_asset, headers=headers)
print(f"POST /api/v1/assets: status={r.status_code}, name={r.json().get('name')}")
assert r.status_code == 201

# Test /risk/cells with simulation
# First, inject a simulation:
sim_payload = {
    "ward": "KURLA",
    "rainfall_rate_mm_h": 138.5,
    "high_tide_m": 4.35,
    "asset_at_risk": "Kurla West Lowlands Station"
}
r = requests.post(f"{BASE_BACKEND}/api/v1/simulation/inject", json=sim_payload, headers=headers)
print(f"POST /api/v1/simulation/inject: status={r.status_code}")
assert r.status_code == 200

# Check /risk/cells has simulated cell at index 0
r = requests.get(f"{BASE_BACKEND}/api/v1/risk/cells", headers=headers)
cells = r.json().get("items", [])
top_cell = cells[0] if cells else {}
print(f"GET /api/v1/risk/cells: top cell={top_cell.get('cell_id')} in {top_cell.get('ward_name')} with rain={top_cell.get('rainfall_rate_mm_h')} mm/h")
assert top_cell.get("rainfall_rate_mm_h") == 138.5, "Simulated cell should be at index 0!"

# Test creating incident
inc_payload = {
    "title": "Severe Stagnation near Kurla Depot",
    "ward_id": "L",
    "severity": "P1_CRITICAL",
    "latitude": 19.0650,
    "longitude": 72.8790,
    "notes": "Testing field simulation app integration"
}
r = requests.post(f"{BASE_BACKEND}/api/v1/incidents", json=inc_payload, headers=headers)
print(f"POST /api/v1/incidents: status={r.status_code}, title={r.json().get('title')}")
assert r.status_code in [200, 201]

# Test creating report
rep_payload = {
    "latitude": 19.0655,
    "longitude": 72.8795,
    "description": "[Ward L] Water level approaching shop entrances"
}
r = requests.post(f"{BASE_BACKEND}/api/v1/reports/draft", json=rep_payload, headers=headers)
print(f"POST /api/v1/reports/draft: status={r.status_code}, report_id={r.json().get('report_id')}")
assert r.status_code in [200, 201]

# Reset simulation
r = requests.post(f"{BASE_BACKEND}/api/v1/simulation/reset", headers=headers)
print(f"POST /api/v1/simulation/reset: status={r.status_code}")
assert r.status_code == 200

print("\nALL BACKEND VERIFICATIONS PASSED CLEANLY (7/7)!")
