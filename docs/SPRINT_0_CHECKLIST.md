# Sprint 0 — Foundation / Data Contract / Canonical Grid

## A. Project and contracts
- [ ] Git repository initialized
- [ ] `contracts/internal-ml-openapi.yaml` reviewed with backend
- [ ] `WeatherFrame` fields agreed
- [ ] Risk enum agreed: LOW / MODERATE / HIGH / SEVERE
- [ ] API boundary agreed: EPSG:4326
- [ ] Internal analysis CRS recorded in pilot config
- [ ] model_version and data_version policy agreed

## B. Pilot
- [ ] Mumbai working bbox reviewed in QGIS
- [ ] 256x256 grid accepted for first dev cycle
- [ ] one historical heavy-rain event will be selected after source availability check

## C. Data acquisition
- [ ] Copernicus DEM sample downloaded
- [ ] OSM roads/waterways/assets sample downloaded
- [ ] GPM IMERG historical sample downloaded
- [ ] NOAA GFS sample downloaded
- [ ] MOSDAC access checked
- [ ] IMD radar/AWS adapter remains interface-only if access is unavailable

## D. Preprocessing/QC
- [ ] timestamps normalized to UTC
- [ ] units explicit
- [ ] source CRS recorded
- [ ] reprojection tested
- [ ] continuous-vs-categorical resampling handled separately
- [ ] no-data mask preserved
- [ ] impossible values flagged
- [ ] missing/duplicate frames detected
- [ ] source freshness stored separately from model confidence
- [ ] input provenance/checksum stored

## E. First integration artifact
- [ ] canonical processed rainfall array exists
- [ ] latest rainfall GeoTIFF exists
- [ ] WeatherFrame manifest exists
- [ ] deterministic demo fixture can be rerun from scratch
- [ ] tests pass
