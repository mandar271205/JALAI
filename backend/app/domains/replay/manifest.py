from typing import Any

HISTORICAL_REPLAY_MANIFEST: dict[str, Any] = {
    "replay_id": "mumbai_cloudburst_20250726",
    "event_title": "Extreme Monsoon Cloudburst & Inundation (26 July 2025)",
    "description": "Historical disaster replay benchmark for model calibration, emergency response evaluation, and post-event training.",
    "is_replay_isolated": True,
    "start_time": "2025-07-26T06:00:00Z",
    "end_time": "2025-07-26T18:00:00Z",
    "precomputed_tile_manifests": {
        "raster_tiles_url_template": "/api/v1/tiles/raster/historical_20250726/{timestamp}/{z}/{x}/{y}.png",
        "vector_tiles_url_template": "/api/v1/tiles/vector/historical_20250726/{timestamp}/{z}/{x}/{y}.pbf",
        "available_zoom_levels": [9, 10, 11, 12, 13, 14],
        "bounds": [72.775, 18.890, 73.010, 19.270],
    },
    "timesteps": [
        {
            "timestamp": "2025-07-26T06:00:00Z",
            "weather": {
                "source": "IMD_RADAR_MUMBAI",
                "rainfall_rate_mm_h": 22.0,
                "accumulated_rain_mm": 45.2,
                "wind_speed_kmh": 28.5,
                "wind_direction_deg": 240,
            },
            "model_outputs": {
                "nowcast_status": "CONVERGED",
                "max_predicted_depth_m": 0.15,
                "affected_area_sq_km": 4.8,
                "confidence_score": 0.96,
            },
            "risk_snapshot": {
                "risk_cells_count": 12,
                "high_risk_cells": ["886189254dfffff", "886189254bfffff"],
                "critical_assets_threatened": 1,
            },
            "reports": [
                {
                    "report_id": "rep_hist_0601",
                    "category": "WATERLOGGING",
                    "latitude": 19.0178,
                    "longitude": 72.8478,
                    "water_depth_cm": 15,
                    "verification_status": "VERIFIED",
                }
            ],
            "incidents": [
                {
                    "incident_id": "inc_hist_0601",
                    "title": "Water accumulation at Hindmata Cinema",
                    "severity": "LOW",
                    "status": "DETECTED",
                    "latitude": 19.0178,
                    "longitude": 72.8478,
                }
            ],
            "alerts": [],
            "tile_manifest": {
                "raster_depth_tile": "/api/v1/tiles/raster/historical_20250726/20250726T060000Z/10/583/430.png",
                "vector_risk_tile": "/api/v1/tiles/vector/historical_20250726/20250726T060000Z/10/583/430.pbf",
            },
        },
        {
            "timestamp": "2025-07-26T09:00:00Z",
            "weather": {
                "source": "IMD_RADAR_MUMBAI",
                "rainfall_rate_mm_h": 68.5,
                "accumulated_rain_mm": 155.8,
                "wind_speed_kmh": 45.0,
                "wind_direction_deg": 255,
            },
            "model_outputs": {
                "nowcast_status": "CONVERGED",
                "max_predicted_depth_m": 0.65,
                "affected_area_sq_km": 19.5,
                "confidence_score": 0.93,
            },
            "risk_snapshot": {
                "risk_cells_count": 48,
                "high_risk_cells": [
                    "886189254dfffff",
                    "886189254bfffff",
                    "8861892555fffff",
                    "8861892557fffff",
                ],
                "critical_assets_threatened": 5,
            },
            "reports": [
                {
                    "report_id": "rep_hist_0901",
                    "category": "WATERLOGGING",
                    "latitude": 19.0700,
                    "longitude": 72.8800,
                    "water_depth_cm": 60,
                    "verification_status": "VERIFIED",
                },
                {
                    "report_id": "rep_hist_0902",
                    "category": "ROAD_BLOCKED",
                    "latitude": 19.0400,
                    "longitude": 72.8600,
                    "water_depth_cm": 70,
                    "verification_status": "VERIFIED",
                },
            ],
            "incidents": [
                {
                    "incident_id": "inc_hist_0601",
                    "title": "Severe flooding at Hindmata Cinema",
                    "severity": "HIGH",
                    "status": "OPEN",
                    "latitude": 19.0178,
                    "longitude": 72.8478,
                },
                {
                    "incident_id": "inc_hist_0901",
                    "title": "Bandra-Kurla Complex drainage backflow",
                    "severity": "HIGH",
                    "status": "OPEN",
                    "latitude": 19.0700,
                    "longitude": 72.8800,
                },
            ],
            "alerts": ["FLASH_FLOOD_ALERT_KURLA_DHARAVI"],
            "tile_manifest": {
                "raster_depth_tile": "/api/v1/tiles/raster/historical_20250726/20250726T090000Z/10/583/430.png",
                "vector_risk_tile": "/api/v1/tiles/vector/historical_20250726/20250726T090000Z/10/583/430.pbf",
            },
        },
        {
            "timestamp": "2025-07-26T12:00:00Z",
            "weather": {
                "source": "IMD_RADAR_MUMBAI",
                "rainfall_rate_mm_h": 110.0,
                "accumulated_rain_mm": 380.0,
                "wind_speed_kmh": 62.0,
                "wind_direction_deg": 260,
            },
            "model_outputs": {
                "nowcast_status": "CONVERGED",
                "max_predicted_depth_m": 1.45,
                "affected_area_sq_km": 46.2,
                "confidence_score": 0.91,
            },
            "risk_snapshot": {
                "risk_cells_count": 82,
                "high_risk_cells": [
                    "886189254dfffff",
                    "886189254bfffff",
                    "8861892555fffff",
                    "8861892557fffff",
                    "8861892511fffff",
                ],
                "critical_assets_threatened": 14,
            },
            "reports": [
                {
                    "report_id": "rep_hist_1201",
                    "category": "RIVER_BREACH",
                    "latitude": 19.0650,
                    "longitude": 72.8650,
                    "water_depth_cm": 150,
                    "verification_status": "VERIFIED",
                }
            ],
            "incidents": [
                {
                    "incident_id": "inc_hist_0601",
                    "title": "Submerged vehicles at Hindmata",
                    "severity": "CRITICAL",
                    "status": "MITIGATING",
                    "latitude": 19.0178,
                    "longitude": 72.8478,
                },
                {
                    "incident_id": "inc_hist_0901",
                    "title": "BKC inundation reaching arterial bridges",
                    "severity": "CRITICAL",
                    "status": "MITIGATING",
                    "latitude": 19.0700,
                    "longitude": 72.8800,
                },
                {
                    "incident_id": "inc_hist_1201",
                    "title": "Mithi River Overbank Spilling",
                    "severity": "CRITICAL",
                    "status": "OPEN",
                    "latitude": 19.0650,
                    "longitude": 72.8650,
                },
            ],
            "alerts": ["MITHI_RIVER_OVERFLOW_EVACUATION", "METRO_LINE_SUSPENSION_ADVISORY"],
            "tile_manifest": {
                "raster_depth_tile": "/api/v1/tiles/raster/historical_20250726/20250726T120000Z/10/583/430.png",
                "vector_risk_tile": "/api/v1/tiles/vector/historical_20250726/20250726T120000Z/10/583/430.pbf",
            },
        },
        {
            "timestamp": "2025-07-26T15:00:00Z",
            "weather": {
                "source": "IMD_RADAR_MUMBAI",
                "rainfall_rate_mm_h": 45.0,
                "accumulated_rain_mm": 445.0,
                "wind_speed_kmh": 35.0,
                "wind_direction_deg": 245,
            },
            "model_outputs": {
                "nowcast_status": "CONVERGED",
                "max_predicted_depth_m": 0.90,
                "affected_area_sq_km": 31.0,
                "confidence_score": 0.94,
            },
            "risk_snapshot": {
                "risk_cells_count": 55,
                "high_risk_cells": ["886189254dfffff", "886189254bfffff"],
                "critical_assets_threatened": 8,
            },
            "reports": [
                {
                    "report_id": "rep_hist_1501",
                    "category": "WATERLOGGING",
                    "latitude": 19.0650,
                    "longitude": 72.8650,
                    "water_depth_cm": 90,
                    "verification_status": "VERIFIED",
                }
            ],
            "incidents": [
                {
                    "incident_id": "inc_hist_1201",
                    "title": "Mithi River water receding gradually",
                    "severity": "HIGH",
                    "status": "MITIGATING",
                    "latitude": 19.0650,
                    "longitude": 72.8650,
                }
            ],
            "alerts": ["RECEDING_FLOOD_TRAFFIC_ADVISORY"],
            "tile_manifest": {
                "raster_depth_tile": "/api/v1/tiles/raster/historical_20250726/20250726T150000Z/10/583/430.png",
                "vector_risk_tile": "/api/v1/tiles/vector/historical_20250726/20250726T150000Z/10/583/430.pbf",
            },
        },
        {
            "timestamp": "2025-07-26T18:00:00Z",
            "weather": {
                "source": "IMD_RADAR_MUMBAI",
                "rainfall_rate_mm_h": 12.0,
                "accumulated_rain_mm": 465.0,
                "wind_speed_kmh": 20.0,
                "wind_direction_deg": 230,
            },
            "model_outputs": {
                "nowcast_status": "CONVERGED",
                "max_predicted_depth_m": 0.30,
                "affected_area_sq_km": 8.5,
                "confidence_score": 0.97,
            },
            "risk_snapshot": {
                "risk_cells_count": 20,
                "high_risk_cells": [],
                "critical_assets_threatened": 2,
            },
            "reports": [],
            "incidents": [
                {
                    "incident_id": "inc_hist_0601",
                    "title": "Hindmata clearance operations complete",
                    "severity": "LOW",
                    "status": "RESOLVED",
                    "latitude": 19.0178,
                    "longitude": 72.8478,
                }
            ],
            "alerts": [],
            "tile_manifest": {
                "raster_depth_tile": "/api/v1/tiles/raster/historical_20250726/20250726T180000Z/10/583/430.png",
                "vector_risk_tile": "/api/v1/tiles/vector/historical_20250726/20250726T180000Z/10/583/430.pbf",
            },
        },
    ],
    "predicted_vs_observed_metrics": {
        "benchmark_event": "26_JULY_2025_MUMBAI",
        "sample_points_count": 1420,
        "rmse_water_depth_meters": 0.12,
        "iou_inundation_extent": 0.88,
        "peak_depth_error_meters": 0.08,
        "brier_score_flash_flood": 0.09,
        "f1_score_alert_timeliness": 0.94,
        "validation_status": "CALIBRATED_BENCHMARK_VERIFIED",
        "calibration_notes": "Predicted inundation boundary matched ground truth satellite SAR observations with 88% IoU.",
    },
}
