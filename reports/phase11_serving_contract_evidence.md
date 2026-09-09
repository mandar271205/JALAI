# phase11 serving contract evidence

```json
{
  "artifact": {
    "run_id": "phase11-relative-screening",
    "generated_at": "2026-09-09T23:39:21.660643Z",
    "model_version": "relative_susceptibility_v1",
    "data_version": "local_static_snapshot",
    "hazard_type": "susceptibility",
    "units": "relative_index",
    "api_crs": "EPSG:4326",
    "raster_crs": "EPSG:32643",
    "raster_transform": [
      125.68115879274046,
      0.0,
      262927.81415520643,
      0.0,
      -196.08178669331937,
      2135557.2463123174
    ],
    "raster_shape": [
      256,
      256
    ],
    "artifact_path": "data\\processed\\flood\\susceptibility_v1.tif",
    "artifact_sha256": "e827be30c33c0b984fd095f6ec6203b514d31657124fb6a0e9323ac067a1bf9d",
    "provenance": {
      "hazard": {
        "path": "data\\processed\\flood\\susceptibility_v1.tif",
        "sha256": "e827be30c33c0b984fd095f6ec6203b514d31657124fb6a0e9323ac067a1bf9d"
      },
      "exposure": "phase11_exposure_v1",
      "vulnerability": "phase11_vulnerability_v1"
    },
    "uncertainty": {
      "calibrated": false,
      "coverage_unknown": true
    },
    "quality": 0.8759765625,
    "confidence": null,
    "status": "experimental",
    "calibrated": false,
    "observed": false,
    "operational": false
  },
  "http_routes_modified": false,
  "future_rainfall_model_activated": false,
  "contract": "serving.flood_evidence_contracts.FloodEvidenceArtifact"
}
```
