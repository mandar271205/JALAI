# phase11 exposure evidence

```json
{
  "version": "phase11_exposure_v1",
  "status": "PARTIAL_MAPPED_ASSETS",
  "layers": {
    "hospitals": {
      "status": "AVAILABLE",
      "missing_data": false,
      "source": "OpenStreetMap",
      "source_date": "2026-09-07T01:50:08.271703+00:00",
      "source_sha256": "8e6c193628780f7a78e71a52ed003978e9a05fc8f7bc4e0b6b23277f64e30ad5",
      "retrieval_provenance": "local OSM snapshot; source manifest timestamp where available",
      "source_crs": "urn:ogc:def:crs:OGC:1.3:CRS84",
      "crs": "EPSG:32643",
      "shape": [
        256,
        256
      ],
      "transform": [
        125.68115879274046,
        0.0,
        262927.81415520643,
        0.0,
        -196.08178669331937,
        2135557.2463123174
      ],
      "feature_count": 1229,
      "invalid_geometry_count": 0,
      "outside_domain_count": 0,
      "duplicate_count": 0,
      "raw_feature_count": 1229,
      "processing": "reproject, exact domain clip, rasterize ADD",
      "representation": "feature-cell intersection count; not population, unique facilities or length density",
      "occupied_cells": 1254,
      "absence_means_no_assets": false,
      "completeness": "OSM coverage unknown; empty mapped cells do not establish asset absence"
    },
    "schools": {
      "status": "AVAILABLE",
      "missing_data": false,
      "source": "OpenStreetMap",
      "source_date": "2026-09-07T01:50:08.271703+00:00",
      "source_sha256": "5d1a7e64f522abd7ac543c75c9a669f70b2b5b4c68ab305ee5b40ff3feef1cf7",
      "retrieval_provenance": "local OSM snapshot; source manifest timestamp where available",
      "source_crs": "urn:ogc:def:crs:OGC:1.3:CRS84",
      "crs": "EPSG:32643",
      "shape": [
        256,
        256
      ],
      "transform": [
        125.68115879274046,
        0.0,
        262927.81415520643,
        0.0,
        -196.08178669331937,
        2135557.2463123174
      ],
      "feature_count": 944,
      "invalid_geometry_count": 0,
      "outside_domain_count": 0,
      "duplicate_count": 0,
      "raw_feature_count": 944,
      "processing": "reproject, exact domain clip, rasterize ADD",
      "representation": "feature-cell intersection count; not population, unique facilities or length density",
      "occupied_cells": 1882,
      "absence_means_no_assets": false,
      "completeness": "OSM coverage unknown; empty mapped cells do not establish asset absence"
    },
    "roads": {
      "status": "AVAILABLE",
      "missing_data": false,
      "source": "OpenStreetMap",
      "source_date": "2026-09-07T01:50:08.271703+00:00",
      "source_sha256": "d0ec8c98f63cadedd1cdb58bf8b90f7ac6e32618b5dbbb7a83c967aa76be995b",
      "retrieval_provenance": "local OSM snapshot; source manifest timestamp where available",
      "source_crs": "urn:ogc:def:crs:OGC:1.3:CRS84",
      "crs": "EPSG:32643",
      "shape": [
        256,
        256
      ],
      "transform": [
        125.68115879274046,
        0.0,
        262927.81415520643,
        0.0,
        -196.08178669331937,
        2135557.2463123174
      ],
      "feature_count": 292968,
      "invalid_geometry_count": 0,
      "outside_domain_count": 0,
      "duplicate_count": 0,
      "raw_feature_count": 292968,
      "processing": "reproject, exact domain clip, rasterize ADD",
      "representation": "feature-cell intersection count; not population, unique facilities or length density",
      "occupied_cells": 27306,
      "absence_means_no_assets": false,
      "completeness": "OSM coverage unknown; empty mapped cells do not establish asset absence"
    },
    "railways": {
      "status": "AVAILABLE",
      "missing_data": false,
      "source": "OpenStreetMap",
      "source_date": "2026-09-07T01:50:08.271703+00:00",
      "source_sha256": "cce2c022d0fd3ee3d94e4df4a0903c562715046e491626ee3e6532cf306d9a94",
      "retrieval_provenance": "local OSM snapshot; source manifest timestamp where available",
      "source_crs": "urn:ogc:def:crs:OGC:1.3:CRS84",
      "crs": "EPSG:32643",
      "shape": [
        256,
        256
      ],
      "transform": [
        125.68115879274046,
        0.0,
        262927.81415520643,
        0.0,
        -196.08178669331937,
        2135557.2463123174
      ],
      "feature_count": 2342,
      "invalid_geometry_count": 0,
      "outside_domain_count": 0,
      "duplicate_count": 0,
      "raw_feature_count": 2342,
      "processing": "reproject, exact domain clip, rasterize ADD",
      "representation": "feature-cell intersection count; not population, unique facilities or length density",
      "occupied_cells": 3021,
      "absence_means_no_assets": false,
      "completeness": "OSM coverage unknown; empty mapped cells do not establish asset absence"
    },
    "emergency_assets": {
      "status": "AVAILABLE",
      "missing_data": false,
      "source": "OpenStreetMap",
      "source_date": "2026-09-07T01:50:08.271703+00:00",
      "source_sha256": "63a16fde9636082548a0631bf437c4dca424dc2e7fa61b66c6d5bcda0699b230",
      "retrieval_provenance": "local OSM snapshot; source manifest timestamp where available",
      "source_crs": "urn:ogc:def:crs:OGC:1.3:CRS84",
      "crs": "EPSG:32643",
      "shape": [
        256,
        256
      ],
      "transform": [
        125.68115879274046,
        0.0,
        262927.81415520643,
        0.0,
        -196.08178669331937,
        2135557.2463123174
      ],
      "feature_count": 2486,
      "invalid_geometry_count": 0,
      "outside_domain_count": 0,
      "duplicate_count": 0,
      "raw_feature_count": 2486,
      "processing": "reproject, exact domain clip, rasterize ADD",
      "representation": "feature-cell intersection count; not population, unique facilities or length density",
      "occupied_cells": 3211,
      "absence_means_no_assets": false,
      "completeness": "OSM coverage unknown; empty mapped cells do not establish asset absence"
    },
    "bridges": {
      "status": "AVAILABLE",
      "missing_data": false,
      "source": "OpenStreetMap",
      "source_date": "2026-09-07T01:50:08.271703+00:00",
      "source_sha256": "f344b1f381abff3ab84bf37b6d0ce4d464c0876d854f977c66e50e67d0bbda8f",
      "retrieval_provenance": "local OSM snapshot; source manifest timestamp where available",
      "source_crs": "urn:ogc:def:crs:OGC:1.3:CRS84",
      "crs": "EPSG:32643",
      "shape": [
        256,
        256
      ],
      "transform": [
        125.68115879274046,
        0.0,
        262927.81415520643,
        0.0,
        -196.08178669331937,
        2135557.2463123174
      ],
      "feature_count": 3218,
      "invalid_geometry_count": 0,
      "outside_domain_count": 0,
      "duplicate_count": 0,
      "raw_feature_count": 3218,
      "processing": "reproject, exact domain clip, rasterize ADD",
      "representation": "feature-cell intersection count; not population, unique facilities or length density",
      "occupied_cells": 4799,
      "absence_means_no_assets": false,
      "completeness": "OSM coverage unknown; empty mapped cells do not establish asset absence"
    },
    "shelters": {
      "status": "AVAILABLE",
      "missing_data": false,
      "source": "OpenStreetMap",
      "source_date": "2026-09-07T01:50:08.271703+00:00",
      "source_sha256": "c971e05dacc089755da428b1df99118ae96a812ab8a4c08b12ffc9ae8c649fd9",
      "retrieval_provenance": "local OSM snapshot; source manifest timestamp where available",
      "source_crs": "urn:ogc:def:crs:OGC:1.3:CRS84",
      "crs": "EPSG:32643",
      "shape": [
        256,
        256
      ],
      "transform": [
        125.68115879274046,
        0.0,
        262927.81415520643,
        0.0,
        -196.08178669331937,
        2135557.2463123174
      ],
      "feature_count": 135,
      "invalid_geometry_count": 0,
      "outside_domain_count": 0,
      "duplicate_count": 0,
      "raw_feature_count": 135,
      "processing": "reproject, exact domain clip, rasterize ADD",
      "representation": "feature-cell intersection count; not population, unique facilities or length density",
      "occupied_cells": 117,
      "absence_means_no_assets": false,
      "completeness": "OSM coverage unknown; empty mapped cells do not establish asset absence"
    },
    "buildings": {
      "status": "UNAVAILABLE",
      "missing_data": true,
      "feature_count": null,
      "source": "OpenStreetMap",
      "absence_means_no_assets": false
    },
    "power": {
      "status": "UNAVAILABLE",
      "missing_data": true,
      "feature_count": null,
      "source": "OpenStreetMap",
      "absence_means_no_assets": false
    }
  },
  "normalization": "presence per class [0,1]; equal weight over available classes",
  "population_available": false,
  "calibrated_weights": false,
  "missing_classes": [
    "buildings",
    "power"
  ],
  "coverage_assumption": "relative risk conditional on mapped assets only"
}
```
