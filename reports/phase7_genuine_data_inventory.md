# Phase 7 Genuine Data Inventory Report

**Audit Timestamp:** 2026-09-09 14:11:45Z  
**Target Region:** Mumbai Pilot `[72.75, 18.85, 73.05, 19.30]`  
**Canonical Projected CRS:** `EPSG:32643` (UTM zone 43N)  
**Working Grid Resolution:** 256 × 256 pixels  

---

## Summary of Local Artifacts

| Dataset ID | Source | Format | Working Resolution | Units | Authoritative | Usable For |
|---|---|---|---|---|---|---|
| `copernicus_dem_raw` | Copernicus GLO-30 Public DEM | GeoTIFF | Raw 1 arc-second unprojected | meters (orthometric height above EGM2008) | YES | susc, hydr |
| `elevation_canonical_grid` | Copernicus GLO-30 DEM (Reprojected & Cropped) | GeoTIFF | 256x256 (~125.7m x 196.1m) | meters | YES | susc, hydr |
| `slope_canonical_grid` | Derived from Copernicus DEM elevation.tif | GeoTIFF | 256x256 (~125.7m x 196.1m) | degrees | YES | susc, hydr |
| `distance_to_water_canonical_grid` | Derived from OSM Waterways vector features | GeoTIFF | 256x256 (~125.7m x 196.1m) | meters | YES | susc, vuln |
| `roughness_canonical_grid` | Infrastructure Composite Manning's n Parameterization | GeoTIFF | 256x256 (~125.7m x 196.1m) | s / m^(1/3) (Manning's n) | NO (Heuristic) | hydr |
| `susceptibility_v1_grid` | Multi-criteria relative flood susceptibility engine | GeoTIFF | 256x256 (~125.7m x 196.1m) | dimensionless [0, 1] | YES | susc |
| `osm_waterways_vector` | OpenStreetMap waterways | GeoJSON | Vector lines | WGS-84 coordinates | YES | susc, hydr |
| `osm_roads_vector` | OpenStreetMap roads | GeoJSON | Vector lines | WGS-84 coordinates | YES | hydr, expo, vuln |
| `osm_hospitals_vector` | OpenStreetMap hospitals & clinics | GeoJSON | Vector features | WGS-84 coordinates | YES | expo, vuln |
| `osm_schools_vector` | OpenStreetMap schools & colleges | GeoJSON | Vector features | WGS-84 coordinates | YES | expo |
| `osm_emergency_assets_vector` | OpenStreetMap emergency assets (fire, police, shelter) | GeoJSON | Vector features | WGS-84 coordinates | YES | expo, vuln |
| `osm_railways_vector` | OpenStreetMap railway lines & metro tracks | GeoJSON | Vector lines | WGS-84 coordinates | YES | hydr, expo |
| `mumbai_rainfall_events_catalog` | NASA GPM IMERG V07 Final Precipitation Corpus | JSON | 30-minute event windows | mm/h | YES | susc, hydr, vali |

---

## Detailed Data Provenance & Integrity Profiles

### `copernicus_dem_raw`
- **Source Organization:** European Space Agency (ESA) / Airbus Defence and Space
- **Source URL:** https://copernicus-dem-30m.s3.amazonaws.com/
- **File Path:** `data/raw/dem/copernicus_raw.tif`
- **Format & CRS:** GeoTIFF | `EPSG:4326`
- **Spatial Bounds:** `[72.75, 18.85, 73.05, 19.3]`
- **Source Resolution:** 1 arc-second (~30m)
- **Working Resolution:** Raw 1 arc-second unprojected
- **Measurement Units:** meters (orthometric height above EGM2008)
- **Vintage / Acquisition Date:** 2021 (COP30 v1 release)
- **Data License:** Copernicus WorldDEM Open Data License
- **File Size:** 4,069,893 bytes
- **SHA-256 Hash:** `7fd37eed07b1b06d0108e2edb8c75359594d5bc788d6a45305335652b6c1dbd5`
- **Authoritative Observation:** Yes
- **Processing History:**
  - Fetched raw 1x1 degree tiles
  - Mosaicked over Mumbai bounding box
- **Usability Gates:**
  - Flood Susceptibility: True
  - Hydraulic Simulation: True
  - Exposure Aggregation: False
  - Vulnerability Assessment: False
  - Empirical Validation: False

### `elevation_canonical_grid`
- **Source Organization:** ESA / JalRakshak ML Preprocessing
- **Source URL:** data/raw/dem/copernicus_raw.tif
- **File Path:** `data/processed/static/elevation.tif`
- **Format & CRS:** GeoTIFF | `EPSG:32643`
- **Spatial Bounds:** `[262927.81, 2085360.71, 295101.99, 2135557.25]`
- **Source Resolution:** 1 arc-second (~30m)
- **Working Resolution:** 256x256 (~125.7m x 196.1m)
- **Measurement Units:** meters
- **Vintage / Acquisition Date:** 2026-09-06
- **Data License:** Copernicus Open Access / Derived Work
- **File Size:** 159,348 bytes
- **SHA-256 Hash:** `56bd3208207e276499c1b47bce4a3e76df75d2e62b92903f71878d0fdee86ab0`
- **Authoritative Observation:** Yes
- **Processing History:**
  - Reprojected EPSG:4326 -> EPSG:32643
  - Bilinear resampled to 256x256 canonical grid
- **Usability Gates:**
  - Flood Susceptibility: True
  - Hydraulic Simulation: True
  - Exposure Aggregation: False
  - Vulnerability Assessment: False
  - Empirical Validation: False

### `slope_canonical_grid`
- **Source Organization:** JalRakshak ML Preprocessing
- **Source URL:** internal_derivation
- **File Path:** `data/processed/static/slope.tif`
- **Format & CRS:** GeoTIFF | `EPSG:32643`
- **Spatial Bounds:** `[262927.81, 2085360.71, 295101.99, 2135557.25]`
- **Source Resolution:** 256x256 (~160m)
- **Working Resolution:** 256x256 (~125.7m x 196.1m)
- **Measurement Units:** degrees
- **Vintage / Acquisition Date:** 2026-09-06
- **Data License:** Derived Work
- **File Size:** 163,397 bytes
- **SHA-256 Hash:** `bff27b1d865b7576f9c5dbe19dbb3693035f937aa16e2f9e40a8c7467039c91c`
- **Authoritative Observation:** Yes
- **Processing History:**
  - Finite-difference spatial gradient computation from elevation.tif
- **Usability Gates:**
  - Flood Susceptibility: True
  - Hydraulic Simulation: True
  - Exposure Aggregation: False
  - Vulnerability Assessment: False
  - Empirical Validation: False

### `distance_to_water_canonical_grid`
- **Source Organization:** JalRakshak ML Preprocessing
- **Source URL:** internal_derivation
- **File Path:** `data/processed/static/distance_to_water.tif`
- **Format & CRS:** GeoTIFF | `EPSG:32643`
- **Spatial Bounds:** `[262927.81, 2085360.71, 295101.99, 2135557.25]`
- **Source Resolution:** Vector OSM waterways
- **Working Resolution:** 256x256 (~125.7m x 196.1m)
- **Measurement Units:** meters
- **Vintage / Acquisition Date:** 2026-09-07
- **Data License:** ODbL Derived
- **File Size:** 43,771 bytes
- **SHA-256 Hash:** `d41f6122eb49a78a37af5af1c9a17e501ac301f4a2e13d0727c186ce7776b21e`
- **Authoritative Observation:** Yes
- **Processing History:**
  - Scipy Exact Euclidean Distance Transform from rasterized OSM waterways
- **Usability Gates:**
  - Flood Susceptibility: True
  - Hydraulic Simulation: False
  - Exposure Aggregation: False
  - Vulnerability Assessment: True
  - Empirical Validation: False

### `roughness_canonical_grid`
- **Source Organization:** JalRakshak ML Hydrology Engine
- **Source URL:** internal_derivation
- **File Path:** `data/processed/static/roughness.tif`
- **Format & CRS:** GeoTIFF | `EPSG:32643`
- **Spatial Bounds:** `[262927.81, 2085360.71, 295101.99, 2135557.25]`
- **Source Resolution:** OSM vector overlays (roads, railways, waterways)
- **Working Resolution:** 256x256 (~125.7m x 196.1m)
- **Measurement Units:** s / m^(1/3) (Manning's n)
- **Vintage / Acquisition Date:** 2026-09-09
- **Data License:** ODbL / Engineering Parameterization
- **File Size:** 11,408 bytes
- **SHA-256 Hash:** `305e91d8ef9b09abaaf88d0c62d8e75978706e1981a52827963b252ea913b038`
- **Authoritative Observation:** No (Engineering Parameterization)
- **Processing History:**
  - Rasterized OSM roads (0.015), railways (0.025), waterways (0.035), terrain (0.040)
- **Usability Gates:**
  - Flood Susceptibility: False
  - Hydraulic Simulation: True
  - Exposure Aggregation: False
  - Vulnerability Assessment: False
  - Empirical Validation: False

### `susceptibility_v1_grid`
- **Source Organization:** JalRakshak ML Flood Intelligence
- **Source URL:** scripts/build_flood_susceptibility.py
- **File Path:** `data/processed/flood/susceptibility_v1.tif`
- **Format & CRS:** GeoTIFF | `EPSG:32643`
- **Spatial Bounds:** `[262927.81, 2085360.71, 295101.99, 2135557.25]`
- **Source Resolution:** Multi-source 30m / vector
- **Working Resolution:** 256x256 (~125.7m x 196.1m)
- **Measurement Units:** dimensionless [0, 1]
- **Vintage / Acquisition Date:** 2026-09-09
- **Data License:** Derived Research Artifact
- **File Size:** 262,708 bytes
- **SHA-256 Hash:** `e827be30c33c0b984fd095f6ec6203b514d31657124fb6a0e9323ac067a1bf9d`
- **Authoritative Observation:** Yes
- **Processing History:**
  - Weighted linear combination: 0.3*elev + 0.25*slope + 0.25*low_lying + 0.2*dist_water
- **Usability Gates:**
  - Flood Susceptibility: True
  - Hydraulic Simulation: False
  - Exposure Aggregation: False
  - Vulnerability Assessment: False
  - Empirical Validation: False

### `osm_waterways_vector`
- **Source Organization:** OpenStreetMap Contributors
- **Source URL:** https://www.openstreetmap.org
- **File Path:** `data/processed/static/waterways.geojson`
- **Format & CRS:** GeoJSON | `EPSG:4326`
- **Spatial Bounds:** `[72.7881, 18.7627, 73.4086, 19.3263]`
- **Source Resolution:** Crowdsourced vector
- **Working Resolution:** Vector lines
- **Measurement Units:** WGS-84 coordinates
- **Vintage / Acquisition Date:** 2026-09-07
- **Data License:** Open Data Commons Open Database License (ODbL)
- **File Size:** 1,188,218 bytes
- **SHA-256 Hash:** `9dc7b4c1c8e6b1a8cbbdd5f7af5684d11daca1c11aaa30c8431b394bf3fea15f`
- **Authoritative Observation:** Yes
- **Processing History:**
  - Overpass API query for waterways in Mumbai metropolitan region
- **Usability Gates:**
  - Flood Susceptibility: True
  - Hydraulic Simulation: True
  - Exposure Aggregation: False
  - Vulnerability Assessment: False
  - Empirical Validation: False

### `osm_roads_vector`
- **Source Organization:** OpenStreetMap Contributors
- **Source URL:** https://www.openstreetmap.org
- **File Path:** `data/processed/static/roads.geojson`
- **Format & CRS:** GeoJSON | `EPSG:4326`
- **Spatial Bounds:** `[72.75, 18.85, 73.05, 19.3]`
- **Source Resolution:** Crowdsourced vector
- **Working Resolution:** Vector lines
- **Measurement Units:** WGS-84 coordinates
- **Vintage / Acquisition Date:** 2026-09-07
- **Data License:** ODbL
- **File Size:** 81,392,078 bytes
- **SHA-256 Hash:** `d0ec8c98f63cadedd1cdb58bf8b90f7ac6e32618b5dbbb7a83c967aa76be995b`
- **Authoritative Observation:** Yes
- **Processing History:**
  - Overpass API query for highway=* in Mumbai region
- **Usability Gates:**
  - Flood Susceptibility: False
  - Hydraulic Simulation: True
  - Exposure Aggregation: True
  - Vulnerability Assessment: True
  - Empirical Validation: False

### `osm_hospitals_vector`
- **Source Organization:** OpenStreetMap Contributors
- **Source URL:** https://www.openstreetmap.org
- **File Path:** `data/processed/static/hospitals.geojson`
- **Format & CRS:** GeoJSON | `EPSG:4326`
- **Spatial Bounds:** `[72.75, 18.85, 73.05, 19.3]`
- **Source Resolution:** Crowdsourced points/polygons
- **Working Resolution:** Vector features
- **Measurement Units:** WGS-84 coordinates
- **Vintage / Acquisition Date:** 2026-09-07
- **Data License:** ODbL
- **File Size:** 304,250 bytes
- **SHA-256 Hash:** `8e6c193628780f7a78e71a52ed003978e9a05fc8f7bc4e0b6b23277f64e30ad5`
- **Authoritative Observation:** Yes
- **Processing History:**
  - Overpass query: amenity=hospital | clinic | doctors
- **Usability Gates:**
  - Flood Susceptibility: False
  - Hydraulic Simulation: False
  - Exposure Aggregation: True
  - Vulnerability Assessment: True
  - Empirical Validation: False

### `osm_schools_vector`
- **Source Organization:** OpenStreetMap Contributors
- **Source URL:** https://www.openstreetmap.org
- **File Path:** `data/processed/static/schools.geojson`
- **Format & CRS:** GeoJSON | `EPSG:4326`
- **Spatial Bounds:** `[72.75, 18.85, 73.05, 19.3]`
- **Source Resolution:** Crowdsourced points/polygons
- **Working Resolution:** Vector features
- **Measurement Units:** WGS-84 coordinates
- **Vintage / Acquisition Date:** 2026-09-07
- **Data License:** ODbL
- **File Size:** 368,236 bytes
- **SHA-256 Hash:** `5d1a7e64f522abd7ac543c75c9a669f70b2b5b4c68ab305ee5b40ff3feef1cf7`
- **Authoritative Observation:** Yes
- **Processing History:**
  - Overpass query: amenity=school | college | university
- **Usability Gates:**
  - Flood Susceptibility: False
  - Hydraulic Simulation: False
  - Exposure Aggregation: True
  - Vulnerability Assessment: False
  - Empirical Validation: False

### `osm_emergency_assets_vector`
- **Source Organization:** OpenStreetMap Contributors
- **Source URL:** https://www.openstreetmap.org
- **File Path:** `data/processed/static/emergency_assets.geojson`
- **Format & CRS:** GeoJSON | `EPSG:4326`
- **Spatial Bounds:** `[72.75, 18.85, 73.05, 19.3]`
- **Source Resolution:** Crowdsourced points/polygons
- **Working Resolution:** Vector features
- **Measurement Units:** WGS-84 coordinates
- **Vintage / Acquisition Date:** 2026-09-07
- **Data License:** ODbL
- **File Size:** 682,483 bytes
- **SHA-256 Hash:** `63a16fde9636082548a0631bf437c4dca424dc2e7fa61b66c6d5bcda0699b230`
- **Authoritative Observation:** Yes
- **Processing History:**
  - Overpass query: amenity=fire_station | police | social_facility
- **Usability Gates:**
  - Flood Susceptibility: False
  - Hydraulic Simulation: False
  - Exposure Aggregation: True
  - Vulnerability Assessment: True
  - Empirical Validation: False

### `osm_railways_vector`
- **Source Organization:** OpenStreetMap Contributors
- **Source URL:** https://www.openstreetmap.org
- **File Path:** `data/processed/static/railways.geojson`
- **Format & CRS:** GeoJSON | `EPSG:4326`
- **Spatial Bounds:** `[72.75, 18.85, 73.05, 19.3]`
- **Source Resolution:** Crowdsourced lines
- **Working Resolution:** Vector lines
- **Measurement Units:** WGS-84 coordinates
- **Vintage / Acquisition Date:** 2026-09-07
- **Data License:** ODbL
- **File Size:** 3,726,415 bytes
- **SHA-256 Hash:** `cce2c022d0fd3ee3d94e4df4a0903c562715046e491626ee3e6532cf306d9a94`
- **Authoritative Observation:** Yes
- **Processing History:**
  - Overpass query: railway=rail | subway | light_rail
- **Usability Gates:**
  - Flood Susceptibility: False
  - Hydraulic Simulation: True
  - Exposure Aggregation: True
  - Vulnerability Assessment: False
  - Empirical Validation: False

### `mumbai_rainfall_events_catalog`
- **Source Organization:** NASA Goddard Space Flight Center / JalRakshak ML
- **Source URL:** https://gpm.nasa.gov/data/imerg
- **File Path:** `data/catalogs/mumbai_rainfall_events_v1.json`
- **Format & CRS:** JSON | `EPSG:4326`
- **Spatial Bounds:** `[72.75, 18.85, 73.05, 19.3]`
- **Source Resolution:** 0.1 deg (~10km) / 30-minute cadence
- **Working Resolution:** 30-minute event windows
- **Measurement Units:** mm/h
- **Vintage / Acquisition Date:** 2021-2024 Monsoon Corpus (18 events)
- **Data License:** NASA Open Data Policy
- **File Size:** 12,829 bytes
- **SHA-256 Hash:** `580fb3f8a5bdbfcfcf29da52d1a1dd3656cbf88192f9ef8fb8253a81c6fa7de9`
- **Authoritative Observation:** Yes
- **Processing History:**
  - Filtered IMERG V07 Final for Mumbai monsoon heavy precipitation episodes
- **Usability Gates:**
  - Flood Susceptibility: True
  - Hydraulic Simulation: True
  - Exposure Aggregation: False
  - Vulnerability Assessment: False
  - Empirical Validation: True
