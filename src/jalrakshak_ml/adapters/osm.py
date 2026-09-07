"""OSM geospatial context adapter.

Fetches roads, waterways, railways, critical facilities (hospitals, schools,
fire stations, police stations, shelter candidates), and bridges for a given
bounding box using OSMnx + GeoPandas.

No bbox or tags are hardcoded here — all come from the caller.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd

log = logging.getLogger(__name__)

# OSM tags we want for each feature class
_ROAD_NETWORK_TYPE = "all"  # all drivable + walkable roads

_POI_TAGS: dict[str, dict[str, Any]] = {
    "hospitals": {"amenity": "hospital"},
    "schools": {"amenity": ["school", "college", "university"]},
    "fire_stations": {"amenity": "fire_station"},
    "police_stations": {"amenity": "police"},
    "shelters": {"amenity": ["shelter", "social_facility"], "social_facility": "shelter"},
}

_WATERWAY_TAGS = {
    "waterway": ["river", "stream", "canal", "drain", "ditch"]
}

_RAILWAY_TAGS = {
    "railway": ["rail", "subway", "tram", "monorail", "light_rail"]
}

_BRIDGE_TAGS = {
    "bridge": True,
    "man_made": "bridge",
}


class OSMAdapter:
    """Fetch OpenStreetMap geospatial context layers for a pilot bbox."""

    source_name = "openstreetmap"

    def fetch(
        self,
        bbox_wgs84: list[float],
        raw_dir: Path,
    ) -> dict[str, gpd.GeoDataFrame]:
        """
        Download all OSM layers and save raw GeoJSONs to *raw_dir*.

        Parameters
        ----------
        bbox_wgs84 : [west, south, east, north]
        raw_dir : directory to write raw GeoJSONs

        Returns
        -------
        dict mapping layer name -> GeoDataFrame (CRS=EPSG:4326)
        """
        import osmnx as ox

        raw_dir.mkdir(parents=True, exist_ok=True)
        # OSMnx convention: (north, south, east, west)
        west, south, east, north = bbox_wgs84
        bbox_ox = (north, south, east, west)

        results: dict[str, gpd.GeoDataFrame] = {}

        # osmnx ≥2.0: bbox is a (left, bottom, right, top) tuple i.e. (west, south, east, north)
        bbox_tuple = (west, south, east, north)

        # ── Roads ──────────────────────────────────────────────────────────
        log.info("Fetching road network...")
        try:
            G = ox.graph_from_bbox(
                bbox=bbox_tuple,
                network_type=_ROAD_NETWORK_TYPE,
                retain_all=True,
            )
            _, edges = ox.graph_to_gdfs(G)
            edges = edges.to_crs("EPSG:4326")
            edges_clean = edges[["geometry", "name", "highway", "length"]].copy()
            edges_clean = edges_clean.reset_index(drop=True)
            results["roads"] = edges_clean
            _save_raw(edges_clean, raw_dir / "roads.geojson")
            log.info("Roads: %d features", len(edges_clean))
        except Exception as exc:
            log.warning("Road network fetch failed: %s", exc)

        # ── Waterways ──────────────────────────────────────────────────────
        log.info("Fetching waterways...")
        try:
            gdf = ox.features_from_bbox(
                bbox=bbox_tuple,
                tags=_WATERWAY_TAGS,
            )
            gdf = gdf.to_crs("EPSG:4326")
            results["waterways"] = gdf
            _save_raw(gdf, raw_dir / "waterways.geojson")
            log.info("Waterways: %d features", len(gdf))
        except Exception as exc:
            log.warning("Waterways fetch failed: %s", exc)

        # ── Railways ───────────────────────────────────────────────────────
        log.info("Fetching railways...")
        try:
            gdf = ox.features_from_bbox(
                bbox=bbox_tuple,
                tags=_RAILWAY_TAGS,
            )
            gdf = gdf.to_crs("EPSG:4326")
            results["railways"] = gdf
            _save_raw(gdf, raw_dir / "railways.geojson")
            log.info("Railways: %d features", len(gdf))
        except Exception as exc:
            log.warning("Railways fetch failed: %s", exc)

        # ── Bridges ────────────────────────────────────────────────────────
        log.info("Fetching bridges...")
        try:
            gdf = ox.features_from_bbox(
                bbox=bbox_tuple,
                tags=_BRIDGE_TAGS,
            )
            gdf = gdf.to_crs("EPSG:4326")
            results["bridges"] = gdf
            _save_raw(gdf, raw_dir / "bridges.geojson")
            log.info("Bridges: %d features", len(gdf))
        except Exception as exc:
            log.warning("Bridges fetch failed: %s", exc)

        # ── POIs ───────────────────────────────────────────────────────────
        emergency_layers: list[gpd.GeoDataFrame] = []
        for layer_name, tags in _POI_TAGS.items():
            log.info("Fetching %s...", layer_name)
            try:
                gdf = ox.features_from_bbox(
                    bbox=bbox_tuple,
                    tags=tags,
                )
                gdf = gdf.to_crs("EPSG:4326")
                gdf = gdf[["geometry", "name"]].copy()
                gdf["category"] = layer_name
                results[layer_name] = gdf
                _save_raw(gdf, raw_dir / f"{layer_name}.geojson")
                emergency_layers.append(gdf)
                log.info("%s: %d features", layer_name, len(gdf))
            except Exception as exc:
                log.warning("%s fetch failed: %s", layer_name, exc)

        # Merge all POI layers into one emergency_assets file
        if emergency_layers:
            import pandas as pd
            combined = pd.concat(emergency_layers, ignore_index=True)
            combined = gpd.GeoDataFrame(combined, crs="EPSG:4326")
            results["emergency_assets"] = combined
            _save_raw(combined, raw_dir / "emergency_assets.geojson")

        return results


def _save_raw(gdf: gpd.GeoDataFrame, path: Path) -> None:
    """Serialise GeoDataFrame to GeoJSON, keeping only geometry + non-list columns."""
    # Drop columns with list/dict values that break GeoJSON serialisation
    safe_cols = ["geometry"]
    for col in gdf.columns:
        if col == "geometry":
            continue
        try:
            # Check if the column is serialisable
            gdf[col].to_json()
            safe_cols.append(col)
        except (TypeError, ValueError):
            pass
    gdf[safe_cols].to_file(str(path), driver="GeoJSON")
