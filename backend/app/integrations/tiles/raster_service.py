from typing import Any

from app.core.config import get_settings


class RasterTileService:
    def __init__(self):
        self.settings = get_settings()
        self.titiler_url = getattr(self.settings, "TITILER_URL", "http://localhost:8088")
        self.minio_endpoint = self.settings.MINIO_ENDPOINT
        self.bucket = self.settings.MINIO_BUCKET

    def get_layer_cog_uri(self, layer_name: str) -> str:
        # Map layer to S3/MinIO COG path
        layer_map = {
            "nowcast": f"s3://{self.bucket}/rasters/nowcast_latest.tif",
            "flood_depth": f"s3://{self.bucket}/rasters/flood_depth_latest.tif",
            "flood_velocity": f"s3://{self.bucket}/rasters/flood_velocity_latest.tif",
            "historical_20250726": f"s3://{self.bucket}/replay/20250726_flood_depth.tif",
        }
        return layer_map.get(layer_name, f"s3://{self.bucket}/rasters/{layer_name}.tif")

    def get_tilejson(self, layer_name: str, is_immutable: bool = False) -> dict[str, Any]:
        cog_uri = self.get_layer_cog_uri(layer_name)
        tile_url = f"/api/v1/tiles/raster/{layer_name}/{{z}}/{{x}}/{{y}}.png"

        return {
            "tilejson": "3.0.0",
            "name": f"JalRakshak Raster - {layer_name}",
            "description": f"Raster tile layer for {layer_name}",
            "version": "1.0.0",
            "attribution": "JalRakshak AI / SIH26071",
            "scheme": "xyz",
            "tiles": [tile_url],
            "minzoom": 0,
            "maxzoom": 18,
            "bounds": [72.75, 18.88, 73.02, 19.28],
            "center": [72.87, 19.07, 11],
            "cog_uri": cog_uri,
            "is_immutable": is_immutable,
        }

    def get_cache_control(self, is_immutable: bool = False) -> str:
        if is_immutable:
            return "public, max-age=31536000, immutable"
        return "public, max-age=60"
